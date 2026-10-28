"""Standalone Binance evidence ledger. Never establishes issuer publication time.

Run outside the G1 process. A local hash chain detects edits relative to an
externally retained head; it does not confer immutable off-host custody.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import sqlite3
import time
import uuid

from aql.data_proof import ObservationVersion, ProofError, verify_chain
from aql.data_proof_envelope import export_envelope


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value):
    try:
        v = Decimal(str(value))
        if not v.is_finite() or v < 0:
            raise ValueError()
        return format(v.normalize(), 'f')
    except (InvalidOperation, ValueError):
        raise ProofError('invalid market number')


def payload(*, symbol, interval, row):
    if (not symbol.isalnum() or interval not in {'1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'}
            or len(row) < 11):
        raise ProofError('invalid bar identity')
    if any(type(row[i]) is not int or row[i] < 0 for i in (0, 6, 8)) or row[6] < row[0]:
        raise ProofError('invalid bar times/count')
    p = dict(symbol=symbol.upper(), interval=interval, t=row[0], T=row[6], n=row[8])
    p.update({key: number(row[i]) for key, i in [('o', 1), ('h', 2), ('l', 3), ('c', 4), ('v', 5), ('q', 7), ('V', 9), ('Q', 10)]})
    if Decimal(p['h']) < max(Decimal(p['o']), Decimal(p['c']), Decimal(p['l'])) or Decimal(p['l']) > min(Decimal(p['o']), Decimal(p['c'])):
        raise ProofError('invalid OHLC')
    return p


def ws_payload(raw, symbol, interval):
    msg = json.loads(raw)
    k = msg['k']
    if msg.get('e') != 'kline' or msg.get('s') != symbol or k.get('s') != symbol or k.get('i') != interval:
        raise ProofError('wrong stream')
    if k.get('x') is not True:
        return None, msg
    row = [k['t'], k['o'], k['h'], k['l'], k['c'], k['v'], k['T'], k['q'], k['n'], k['V'], k['Q']]
    return payload(symbol=symbol, interval=interval, row=row), msg


class ObserverLedger:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS evidence (seq INTEGER PRIMARY KEY, body TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)')
        self.db.execute("CREATE INDEX IF NOT EXISTS evidence_kind ON evidence(json_extract(body,'$.kind'),seq)")
        self.db.execute("CREATE INDEX IF NOT EXISTS evidence_bar ON evidence(json_extract(body,'$.data.observation.logical_bar_id'),seq)")
        self.verify()
        self.session = str(uuid.uuid4())
        self.record('SESSION_START', {'session': self.session, 'coverage': 'UNKNOWN', 'reason': 'startup_or_restart'})

    def close(self):
        self.db.close()

    def _append(self, kind, data):
        last = self.db.execute('SELECT hash FROM evidence ORDER BY seq DESC LIMIT 1').fetchone()
        previous = last[0] if last else '0' * 64
        body = canonical({'kind': kind, 'data': data})
        h = digest({'previous': previous, 'body': body})
        self.db.execute('INSERT INTO evidence(body,previous,hash) VALUES (?,?,?)', (body, previous, h))
        return h

    def record(self, kind, data):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            h = self._append(kind, data)
            self.db.execute('COMMIT')
            return h
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def entries(self):
        return [dict(seq=s, body=json.loads(b), previous=p, hash=h) for s, b, p, h in self.db.execute('SELECT seq,body,previous,hash FROM evidence ORDER BY seq')]

    def verify(self, expected_head=None):
        previous = '0' * 64
        groups = {}
        for e in self.entries():
            if e['previous'] != previous or e['hash'] != digest({'previous': previous, 'body': canonical(e['body'])}):
                raise ProofError('evidence chain tampered')
            previous = e['hash']
            if e['body']['kind'] == 'VERSION':
                d = e['body']['data']
                v = ObservationVersion(**d['observation'])
                if v.version_id != d['version_id'] or v.payload_digest != digest(d['payload']):
                    raise ProofError('observation binding mismatch')
                groups.setdefault(v.logical_bar_id, []).append(v)
        for chain in groups.values():
            verify_chain(tuple(chain))
        if expected_head is not None and previous != expected_head:
            raise ProofError('externally pinned head mismatch')
        return previous

    def versions(self, logical_bar_id=None):
        sql = "SELECT body FROM evidence WHERE json_extract(body,'$.kind')='VERSION'"
        args = ()
        if logical_bar_id is not None:
            sql += " AND json_extract(body,'$.data.observation.logical_bar_id')=?"
            args = (logical_bar_id,)
        return tuple(ObservationVersion(**json.loads(b)['data']['observation'])
                     for b, in self.db.execute(sql+' ORDER BY seq', args))

    def observe(self, p, *, raw, endpoint, transport, wall_ms, monotonic_ns, clock_ref, source_event_ms=None, metadata=None):
        """Atomic durable raw->version binding. All live clock status stays UNKNOWN.

        Reversion A->B->A creates a third version; duplicate latest payload does not.
        Polling proves snapshots only, never completeness between polls.
        """
        if type(wall_ms) is not int or type(monotonic_ns) is not int or wall_ms < 0 or monotonic_ns < 0:
            raise ProofError('invalid receive clock')
        logical = f"BINANCE:SPOT:{p['symbol']}:{p['interval']}:{p['t']}"
        self.db.execute('BEGIN IMMEDIATE')
        try:
            chain = list(self.versions(logical))
            prev = chain[-1] if chain else None
            if prev and wall_ms < prev.first_local_seen_ms:
                raise ProofError('clock moved backwards across versions')
            evidence = dict(raw=raw, raw_sha256=hashlib.sha256(raw.encode()).hexdigest(), endpoint=endpoint,
                            transport=transport, wall_ms=wall_ms, monotonic_ns=monotonic_ns,
                            clock_ref=clock_ref, source_event_ms=source_event_ms, session=self.session,
                            metadata=metadata or {}, coverage='UNKNOWN', clock_status='UNKNOWN')
            prior_row = self.db.execute(
                "SELECT body FROM evidence WHERE json_extract(body,'$.kind')='RECEIVE' ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prior = json.loads(prior_row[0])['data'] if prior_row else None
            if prior and prior['session'] == self.session:
                delta = (wall_ms-prior['wall_ms']) - (monotonic_ns-prior['monotonic_ns'])/1_000_000
                if monotonic_ns < prior['monotonic_ns'] or abs(delta) > 1000:
                    self._append('GAP', dict(reason='CLOCK_DISCONTINUITY', delta_ms=delta, coverage='UNKNOWN'))
            raw_ref = self._append('RECEIVE', evidence)
            if prev and prev.payload_digest == digest(p):
                self.db.execute('COMMIT')
                return prev
            v = ObservationVersion(logical_bar_id=logical, version_number=len(chain)+1,
                payload_digest=digest(p), bar_open_ms=p['t'], bar_close_ms=p['T'],
                first_local_seen_ms=wall_ms, source_id='BINANCE_SPOT_INDEPENDENT_WATCHER',
                supersedes_version_id=prev.version_id if prev else None,
                clock_evidence_ref=clock_ref, local_commit_evidence_ref=raw_ref)
            verify_chain(tuple([*chain, v]))
            self._append('VERSION', dict(observation=asdict(v), version_id=v.version_id,
                payload=p, receive_ref=raw_ref, timing_class='FIRST_INDEPENDENT_OBSERVED',
                utc_status='UNKNOWN', issuer_status='UNATTESTED'))
            self.db.execute('COMMIT')
            # Do not invent an ingest_committed timestamp inside the transaction.
            self.record('POSTCOMMIT', dict(version_id=v.version_id, wall_ms=time.time_ns()//1_000_000,
                                          clock_status='LOCAL_WALL_CLOCK_UNATTESTED'))
            return v
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def envelope(self, consumer='factory', epoch=1):
        versions = self.versions()
        # No assertion of complete coverage, even after reconnect or REST repair.
        return export_envelope(consumer=consumer, epoch=epoch, versions=versions,
                               gap_states={v.logical_bar_id: 'UNKNOWN' for v in versions})

    def bundle(self):
        return dict(schema='binance-watcher-evidence-v1', ledger_head=self.verify(),
                    evidence=self.entries(), envelope=self.envelope(),
                    timing_class='FIRST_INDEPENDENT_OBSERVED', utc_status='UNKNOWN',
                    issuer_status='UNATTESTED', custody='LOCAL_HASH_CHAIN_REQUIRES_EXTERNAL_PIN')

    def as_of(self, cutoff_ms):
        """Select only known versions; UNKNOWN UTC blocks temporal acceptance."""
        if type(cutoff_ms) is not int:
            raise ProofError('invalid cutoff')
        result = {}
        for v in self.versions():
            if v.first_local_seen_ms <= cutoff_ms:
                result[v.logical_bar_id] = v
        return dict(versions=tuple(result.values()), status='UNKNOWN_CLOCK_OR_COVERAGE', real_pit_accepted=False)


def verify_bundle(bundle, pinned_head):
    """Verify archived evidence and its canonical Core envelope without trusting labels."""
    from aql.data_proof_envelope import verify_envelope
    previous = '0'*64
    observations = []
    receives = {}
    for e in bundle['evidence']:
        if e['previous'] != previous or e['hash'] != digest({'previous': previous, 'body': canonical(e['body'])}):
            raise ProofError('bundle chain mismatch')
        previous = e['hash']
        body = e['body']
        if body['kind'] == 'RECEIVE':
            d = body['data']
            if hashlib.sha256(d['raw'].encode()).hexdigest() != d['raw_sha256']:
                raise ProofError('raw digest mismatch')
            receives[e['hash']] = d
        if body['kind'] == 'VERSION':
            d = body['data']; v = ObservationVersion(**d['observation'])
            r = receives.get(d['receive_ref'])
            if not r or v.payload_digest != digest(d['payload']) or v.version_id != d['version_id'] or v.first_local_seen_ms != r['wall_ms']:
                raise ProofError('version receive binding mismatch')
            if r['transport'] == 'WS':
                actual, msg = ws_payload(r['raw'], d['payload']['symbol'], d['payload']['interval'])
                if msg.get('E') != r['source_event_ms']:
                    raise ProofError('source event binding mismatch')
                candidates = [actual]
            elif r['transport'] == 'REST':
                candidates = [payload(symbol=r['metadata']['symbol'], interval=r['metadata']['interval'], row=row)
                              for row in json.loads(r['raw'])]
            else:
                raise ProofError('unknown transport')
            if d['payload'] not in candidates or v.provider_available_ms is not None or v.provider_evidence_ref is not None:
                raise ProofError('raw payload or issuer scope mismatch')
            if (v.local_commit_evidence_ref != d['receive_ref'] or v.clock_evidence_ref != r['clock_ref']
                    or v.ingest_committed_ms is not None or v.source_id != 'BINANCE_SPOT_INDEPENDENT_WATCHER'
                    or v.logical_bar_id != f"BINANCE:SPOT:{d['payload']['symbol']}:{d['payload']['interval']}:{d['payload']['t']}"
                    or v.bar_open_ms != d['payload']['t'] or v.bar_close_ms != d['payload']['T']):
                raise ProofError('observation metadata mismatch')
            observations.append(v)
    if previous != pinned_head or bundle['ledger_head'] != pinned_head:
        raise ProofError('bundle external pin mismatch')
    env = bundle['envelope']
    versions = verify_envelope(env, consumer='factory', minimum_epoch=1, pinned_sha256=env['manifest_sha256'])
    if versions != tuple(sorted(observations, key=lambda v:(v.logical_bar_id,v.version_number))):
        raise ProofError('envelope evidence mismatch')
    return versions
