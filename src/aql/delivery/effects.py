"""D2-B v1: opt-in finite synthetic OFFLINE effects, not a live dispatcher.

Source intent, target effect, target receipt and source ACK are separate commits.
Uncertainty is durable; only explicit reconciliation may resume a pending effect.
The SQLite target is independently queryable software evidence, NOT independent
custody, hostile-client isolation, a physical durability test or universal exactly-once.
D1 DELIVERED/events/cursors are never interpreted as D2 confirmation.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from ..archive.contracts import canonical, digest
from ..g1_integrity import require_eligible_db
from .authority import PublicationDenied
from .store_binding import existing

_ACK_GUARD = """CREATE TRIGGER core128_d2_ack_eligibility BEFORE INSERT ON core128_d2_events
WHEN json_extract(NEW.body,'$.op')='D2_CONFIRMED'
AND json_extract(NEW.body,'$.data.receipt.disposition')='APPLIED'
AND EXISTS(SELECT 1 FROM g1_integrity_events g JOIN journal_entries j
ON j.stable_key=g.stable_key WHERE j.id=json_extract(NEW.body,'$.data.source_seq'))
BEGIN SELECT RAISE(ABORT,'source quarantined at D2 ACK authorization'); END"""


class InDoubt(PublicationDenied):
    """A durable attempt lacks a confirmed target disposition/source ACK."""


@dataclass(frozen=True)
class EffectLimits:
    max_effects: int
    max_events: int
    max_bytes: int
    max_attempts: int
    timeout_seconds: float

    def validate(self):
        bounds = ((self.max_effects, 1, 128), (self.max_events, 4, 4096),
                  (self.max_bytes, 1024, 262144), (self.max_attempts, 1, 8))
        if any(type(v) is not int or not low <= v <= high for v, low, high in bounds):
            raise PublicationDenied("Explicit bounded synthetic effect limits required")
        if type(self.timeout_seconds) not in (int, float) or not 0 < self.timeout_seconds <= 2:
            raise PublicationDenied("Explicit bounded target timeout required")


def _path(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise PublicationDenied("Effect target aliases/reparse points denied")
    return str(path)


def _immutable(conn, table):
    for operation in ('UPDATE', 'DELETE'):
        conn.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable D2 evidence'); END")


class SQLiteEffectTarget:
    """Maintenance-only target factory + read metrics; no public effect writer."""

    @classmethod
    def create(cls, path, *, synthetic=False):
        if synthetic is not True:
            raise PublicationDenied("No real effect target implementation")
        path = _path(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Never adopt or truncate another SQLite DB. Failed initialization is
        # conservative: the reserved target is not silently re-enrolled.
        with open(path, 'xb'):
            pass
        with existing(path) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE d2_target_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),body TEXT NOT NULL)')
            conn.execute('CREATE TABLE d2_target_binding(singleton INTEGER PRIMARY KEY CHECK(singleton=1),body TEXT NOT NULL)')
            conn.execute('CREATE TABLE d2_inbox(effect_id TEXT PRIMARY KEY,request TEXT NOT NULL,disposition TEXT NOT NULL,evidence TEXT,origin_epoch INTEGER NOT NULL)')
            conn.execute('CREATE TABLE d2_effects(effect_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            conn.execute('CREATE TABLE d2_receipts(attempt_id TEXT PRIMARY KEY,effect_id TEXT NOT NULL,body TEXT NOT NULL)')
            meta = dict(schema='aql.synthetic-effect-target.v1', target_id=uuid.uuid4().hex, path=path)
            conn.execute('INSERT INTO d2_target_meta VALUES(1,?)', (canonical(meta).decode(),))
            for table in ('d2_target_meta', 'd2_target_binding', 'd2_inbox', 'd2_effects', 'd2_receipts'):
                _immutable(conn, table)
            conn.commit()
        obj = cls()
        obj.path, obj.identity = path, meta
        return obj

    def count(self):
        with existing(self.path) as conn:
            return conn.execute('SELECT COUNT(*) FROM d2_effects').fetchone()[0]


class EffectDelivery:
    """One registered consumer; pending/quotas/target health are consumer-local.

    All source authorization checks serialize on the existing source lock.
    Target transactions are bounded SQLite-only, no network or strategy actions.
    Reopen requires caller-retained D2 anchor AND current per-consumer head.
    That caller commitment is not an independently trusted latest-anchor service.
    """

    def __init__(self, authority, consumer, *, target=None, limits=None,
                 max_consumers=None, synthetic=False, anchor=None, checkpoint=None):
        if synthetic is not True or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', consumer):
            raise PublicationDenied("Explicit synthetic consumer required")
        self.authority, self.consumer = authority, consumer
        self.fault = lambda stage: None
        self._observed_head = None
        with authority._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            authority._verify(conn)
            tables = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='core128_d2_registry'").fetchone())
            if not tables:
                if anchor is not None:
                    raise PublicationDenied("Missing D2 generation")
                if type(max_consumers) is not int or not 1 <= max_consumers <= 16:
                    raise PublicationDenied("Explicit bounded consumer registry required")
                conn.execute('CREATE TABLE core128_d2_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),body TEXT NOT NULL)')
                conn.execute('CREATE TABLE core128_d2_registry(consumer TEXT PRIMARY KEY,body TEXT NOT NULL)')
                conn.execute('CREATE TABLE core128_d2_events(consumer TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(consumer,seq))')
                for table in ('core128_d2_meta', 'core128_d2_registry', 'core128_d2_events'):
                    _immutable(conn, table)
                # INSERT-time authorization preserves ordering: ACK-before-block
                # remains historical, ACK-after-block cannot be backdated by a
                # self-rehashed event, even through raw INSERT rather than API.
                conn.execute(_ACK_GUARD)
                config = dict(schema='aql.d2-registry.v1', source_anchor=digest(authority.anchor), max_consumers=max_consumers)
                conn.execute('INSERT INTO core128_d2_meta VALUES(1,?)', (canonical(config).decode(),))
            row = conn.execute('SELECT body FROM core128_d2_registry WHERE consumer=?', (consumer,)).fetchone()
            if row is None:
                if anchor is not None or type(target) is not SQLiteEffectTarget or type(limits) is not EffectLimits:
                    raise PublicationDenied("Explicit fresh target/limits registration required")
                limits.validate()
                config = json.loads(conn.execute('SELECT body FROM core128_d2_meta').fetchone()[0])
                if max_consumers != config['max_consumers'] or config['source_anchor'] != digest(authority.anchor):
                    raise PublicationDenied("Frozen registry configuration mismatch")
                if conn.execute('SELECT COUNT(*) FROM core128_d2_registry').fetchone()[0] >= max_consumers:
                    raise PublicationDenied("Consumer registry full; no eviction")
                if limits.timeout_seconds > authority.limits.timeout_seconds:
                    raise PublicationDenied("Effect timeout exceeds source fixture bound")
                identity = target.identity
                self.anchor = dict(schema='aql.d2-consumer.v1', generation=uuid.uuid4().hex,
                    source=authority.anchor['source'], source_path=authority.anchor['path'],
                    source_generation=authority.anchor['generation'], inventory=authority.anchor['inventory'],
                    source_anchor=digest(authority.anchor), consumer=consumer, target=identity,
                    max_consumers=max_consumers, limits=asdict(limits))
                self.limits = limits
                with existing(_path(target.path), 0) as dest:
                    dest.execute('BEGIN IMMEDIATE')
                    actual = json.loads(dest.execute('SELECT body FROM d2_target_meta').fetchone()[0])
                    if actual != identity or identity['path'] != _path(target.path):
                        raise PublicationDenied("Target identity mismatch")
                    if any(dest.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('d2_target_binding','d2_inbox','d2_effects','d2_receipts')):
                        raise PublicationDenied("Fresh empty target required; no migration")
                    dest.execute('INSERT INTO d2_target_binding VALUES(1,?)', (canonical(self.anchor).decode(),))
                    dest.commit()
                conn.execute('INSERT INTO core128_d2_registry VALUES(?,?)', (consumer, canonical(self.anchor).decode()))
                self._append(conn, 'D2_INIT', self.anchor)
                conn.commit()
            else:
                if anchor is None or json.loads(row[0]) != anchor:
                    raise PublicationDenied("Separately retained D2 anchor required")
                self.anchor = anchor
                self.limits = EffectLimits(**anchor['limits'])
                self.limits.validate()
                if limits is not None and limits != self.limits:
                    raise PublicationDenied("D2 runtime limits differ from frozen registry")
                if checkpoint is None or tuple(checkpoint) != self._head(conn):
                    raise PublicationDenied("Current per-consumer D2 checkpoint required")
            self._verify_source(conn)
            states, _ = self._replay(conn)
            self._verify_target(conn, states)
            self._observed_head = self._head(conn)

    def _head(self, conn):
        row = conn.execute('SELECT seq,hash FROM core128_d2_events WHERE consumer=? ORDER BY seq DESC LIMIT 1', (self.consumer,)).fetchone()
        if row is None:
            raise PublicationDenied("Missing D2 genesis")
        return tuple(row)

    def _verify_source(self, conn):
        self.authority._verify(conn)
        if self.anchor['source_anchor'] != digest(self.authority.anchor) or self.anchor['consumer'] != self.consumer:
            raise PublicationDenied("D2 source/consumer generation mismatch")
        config = dict(schema='aql.d2-registry.v1', source_anchor=digest(self.authority.anchor), max_consumers=self.anchor['max_consumers'])
        row = conn.execute('SELECT body FROM core128_d2_meta WHERE singleton=1').fetchone()
        bound = conn.execute('SELECT body FROM core128_d2_registry WHERE consumer=?', (self.consumer,)).fetchone()
        if row is None or row[0] != canonical(config).decode() or bound is None or bound[0] != canonical(self.anchor).decode():
            raise PublicationDenied("Frozen D2 registry mismatch")
        guard = conn.execute("SELECT sql FROM sqlite_master WHERE name='core128_d2_ack_eligibility'").fetchone()
        if guard is None or guard[0] != _ACK_GUARD:
            raise PublicationDenied("D2 source ACK authorization guard missing/changed")
        if conn.execute('SELECT COUNT(*) FROM core128_d2_registry').fetchone()[0] > config['max_consumers']:
            raise PublicationDenied("Consumer registry exceeds frozen capacity")
        if self._observed_head is not None:
            prior = conn.execute('SELECT hash FROM core128_d2_events WHERE consumer=? AND seq=?', (self.consumer,self._observed_head[0])).fetchone()
            if prior is None or prior[0] != self._observed_head[1]:
                raise PublicationDenied("D2 progress rollback/fork")

    def _append(self, conn, op, data):
        head = conn.execute('SELECT seq,hash FROM core128_d2_events WHERE consumer=? ORDER BY seq DESC LIMIT 1', (self.consumer,)).fetchone()
        seq, previous = (head[0]+1,head[1]) if head else (1,'0'*64)
        if seq > self.limits.max_events:
            raise PublicationDenied("Consumer event quota full; no eviction")
        event = dict(schema='aql.d2-event.v1', consumer=self.consumer,seq=seq,previous=previous,op=op,data=data)
        raw = canonical(event).decode()
        used = conn.execute('SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM core128_d2_events WHERE consumer=?', (self.consumer,)).fetchone()[0]
        if used + len(raw.encode()) > self.limits.max_bytes:
            raise PublicationDenied("Consumer source byte quota full")
        hashed = digest(event)
        conn.execute('INSERT INTO core128_d2_events VALUES(?,?,?,?)', (self.consumer,seq,raw,hashed))
        return hashed

    def _request(self, conn, seq):
        if type(seq) is not int:
            raise PublicationDenied("Integer source sequence required")
        row = self.authority._row(conn, seq)
        body = dict(registration=digest(self.anchor), source=self.anchor['source'],
            source_generation=self.anchor['source_generation'], inventory=self.anchor['inventory'],
            consumer=self.consumer, target_id=self.anchor['target']['target_id'],
            source_seq=seq,key=row['stable_key'],payload_digest=digest(json.loads(row['payload_json'])))
        return dict(body,effect_id=digest(['aql.d2-effect.v1',body]))

    def _proof_shape(self, receipt, request, attempt):
        if type(receipt) is not dict or set(receipt) != {'schema','request','attempt_id','attempt_epoch','origin_epoch','disposition','evidence','proof_digest'}:
            raise PublicationDenied("Unexpected receipt schema")
        material = {k:v for k,v in receipt.items() if k != 'proof_digest'}
        if (receipt['schema'] != 'aql.d2-target-receipt.v1' or receipt['request'] != request
                or receipt['attempt_id'] != attempt['id'] or type(receipt['attempt_epoch']) is not int
                or receipt['attempt_epoch'] != attempt['epoch'] or type(receipt['origin_epoch']) is not int
                or not 1 <= receipt['origin_epoch'] <= attempt['epoch']
                or receipt['disposition'] != attempt['disposition'] or receipt['evidence'] != attempt['evidence']
                or digest(material) != receipt['proof_digest']):
            raise PublicationDenied("Receipt binding/digest mismatch")

    def _replay(self, conn):
        states, epoch, previous = {}, 0, '0'*64
        rows = conn.execute('SELECT seq,body,hash FROM core128_d2_events WHERE consumer=? ORDER BY seq', (self.consumer,)).fetchall()
        if not rows:
            raise PublicationDenied("Missing D2 genesis")
        for index, (seq,raw,hashed) in enumerate(rows,1):
            event = json.loads(raw)
            if (event != dict(schema='aql.d2-event.v1',consumer=self.consumer,seq=index,previous=previous,op=event.get('op'),data=event.get('data'))
                    or canonical(event).decode() != raw or type(event['seq']) is not int or seq != index or digest(event) != hashed):
                raise PublicationDenied("D2 event chain invalid")
            previous = hashed
            op, data = event['op'], event['data']
            if index == 1:
                if op != 'D2_INIT' or data != self.anchor:
                    raise PublicationDenied("D2 genesis/registration mismatch")
                continue
            if op == 'D2_FENCE':
                if set(data) != {'epoch'} or type(data['epoch']) is not int or data['epoch'] != epoch+1:
                    raise PublicationDenied("D2 fence order invalid")
                epoch = data['epoch']
                continue
            if op not in ('D2_INTENT','D2_RECONCILE','D2_CONFIRMED','D2_WITHHELD'):
                raise PublicationDenied("Unsupported D2 event")
            seq = data['source_seq']
            if type(data.get('epoch')) is not int or data['epoch'] != epoch or epoch < 1:
                raise PublicationDenied("Unfenced D2 disposition event")
            request = self._request(conn,seq)
            s = states.setdefault(seq,dict(request=request,attempts={},receipt=None,withheld=False,evidence=None))
            if op == 'D2_INTENT':
                if (s['receipt'] is not None or type(data.get('epoch')) is not int or data['epoch'] != epoch
                        or data.get('request') != request or data.get('id') != digest([request['effect_id'],epoch])
                        or data.get('disposition') not in ('APPLIED','WITHHELD')
                        or type(data.get('recovering')) is not bool or epoch in s['attempts']):
                    raise PublicationDenied("Invalid D2 intent/fence")
                if len(s['attempts']) >= self.limits.max_attempts:
                    raise PublicationDenied("Effect attempt quota exceeded")
                if data['disposition'] == 'APPLIED' and data.get('evidence') is not None:
                    raise PublicationDenied("Applied intent cannot invent withheld evidence")
                if data['disposition'] == 'WITHHELD':
                    self._evidence(conn, request['key'], data.get('evidence'))
                s['attempts'][epoch] = dict(data)
                if len(states) > self.limits.max_effects:
                    raise PublicationDenied("Consumer effect quota exceeded")
            elif op == 'D2_RECONCILE':
                attempt = s['attempts'].get(epoch)
                if s['receipt'] is not None or attempt is None or attempt['recovering'] or data != dict(source_seq=seq,epoch=epoch,id=attempt['id']):
                    raise PublicationDenied("Invalid D2 reconciliation order")
                attempt['recovering'] = True
            elif op == 'D2_CONFIRMED':
                attempt = s['attempts'].get(epoch)
                if s['receipt'] is not None or attempt is None or data.get('epoch') != epoch or data.get('id') != attempt['id']:
                    raise PublicationDenied("Unproven/duplicate D2 confirmation")
                self._proof_shape(data['receipt'],request,attempt)
                s['receipt'] = data['receipt']
                s['withheld'] = attempt['disposition'] == 'WITHHELD'
                s['evidence'] = attempt['evidence']
            else:
                self._evidence(conn,request['key'],data.get('evidence'))
                if (data.get('epoch') != epoch or s['receipt'] is None or s['withheld']
                        or data.get('receipt') != s['receipt'] or s['receipt']['disposition'] != 'APPLIED'):
                    raise PublicationDenied("Unproven late withheld disposition")
                s['withheld'],s['evidence'] = True,data['evidence']
        return states, epoch

    def _evidence(self, conn, key, evidence=None):
        if evidence is None:
            row = conn.execute('SELECT event_id FROM g1_integrity_events WHERE stable_key=? ORDER BY rowid LIMIT 1',(key,)).fetchone()
        else:
            row = conn.execute('SELECT event_id FROM g1_integrity_events WHERE stable_key=? AND event_id=?',(key,evidence)).fetchone()
        if row is None:
            raise PublicationDenied("Withheld disposition requires source quarantine proof")
        return row[0]

    def _target_meta(self, target):
        actual = target.execute('SELECT body FROM d2_target_meta WHERE singleton=1').fetchone()
        bound = target.execute('SELECT body FROM d2_target_binding WHERE singleton=1').fetchone()
        if (actual is None or json.loads(actual[0]) != self.anchor['target']
                or bound is None or bound[0] != canonical(self.anchor).decode()
                or _path(target.execute('PRAGMA database_list').fetchone()[2]) != self.anchor['target']['path']):
            raise PublicationDenied("Effect target identity/binding replaced")

    @contextmanager
    def _target(self):
        try:
            # Proof reads never wait on optional target locks while a source
            # transaction is held. Only _execute waits, BEFORE taking source.
            with existing(_path(self.anchor['target']['path']), 0) as target:
                self._target_meta(target)
                yield target
        except (sqlite3.DatabaseError, OSError) as exc:
            raise InDoubt("Registered effect target unavailable; consumer denied") from exc

    def _target_budget(self, target):
        if target.execute('SELECT COUNT(*) FROM d2_inbox').fetchone()[0] > self.limits.max_effects:
            raise PublicationDenied("Target inbox quota exceeded")
        if target.execute('SELECT COUNT(*) FROM d2_receipts').fetchone()[0] > self.limits.max_effects*self.limits.max_attempts:
            raise PublicationDenied("Target receipt quota exceeded")
        used = sum(target.execute(f'SELECT COALESCE(SUM(length(CAST({column} AS BLOB))),0) FROM {table}').fetchone()[0]
                   for table,column in (('d2_inbox','request'),('d2_effects','payload'),('d2_receipts','body')))
        if used > self.limits.max_bytes:
            raise PublicationDenied("Consumer target byte quota exceeded")

    def _verify_target(self, conn, states):
        with self._target() as target:
            self._target_budget(target)
            by_id = {s['request']['effect_id']:s for s in states.values()}
            for row in target.execute('SELECT * FROM d2_inbox'):
                s = by_id.get(row['effect_id'])
                if s is None or row['request'] != canonical(s['request']).decode():
                    raise PublicationDenied("Target inbox lacks matching source intent")
                attempts = s['attempts']
                origin = attempts.get(row['origin_epoch'])
                if origin is None or origin['disposition'] != row['disposition'] or origin['evidence'] != row['evidence']:
                    raise PublicationDenied("Unproven target effect origin")
                effect = target.execute('SELECT payload FROM d2_effects WHERE effect_id=?',(row['effect_id'],)).fetchone()
                if row['disposition'] == 'APPLIED':
                    payload = self.authority._row(conn,s['request']['source_seq'])['payload_json']
                    if effect is None or effect[0] != payload:
                        raise PublicationDenied("Persisted effect payload missing/mismatched")
                elif row['disposition'] != 'WITHHELD' or effect is not None:
                    raise PublicationDenied("Withheld target cannot contain applied effect")
            if target.execute('SELECT COUNT(*) FROM d2_effects e WHERE NOT EXISTS(SELECT 1 FROM d2_inbox i WHERE i.effect_id=e.effect_id)').fetchone()[0]:
                raise PublicationDenied("Orphan target effect")
            for row in target.execute('SELECT attempt_id,effect_id,body FROM d2_receipts'):
                s = by_id.get(row['effect_id'])
                receipt = json.loads(row['body'])
                attempt = s['attempts'].get(receipt.get('attempt_epoch')) if s else None
                if attempt is None or row['attempt_id'] != attempt['id']:
                    raise PublicationDenied("Target receipt has no matching source attempt")
                self._proof_shape(receipt,s['request'],attempt)
                inbox = target.execute('SELECT * FROM d2_inbox WHERE effect_id=?',(row['effect_id'],)).fetchone()
                if (inbox is None or receipt['origin_epoch'] != inbox['origin_epoch']
                        or receipt['disposition'] != inbox['disposition'] or receipt['evidence'] != inbox['evidence']):
                    raise PublicationDenied("Target receipt lacks persisted effect/disposition")
            for s in states.values():
                if s['receipt'] is not None:
                    row = target.execute('SELECT body FROM d2_receipts WHERE attempt_id=?',(s['receipt']['attempt_id'],)).fetchone()
                    if row is None or row[0] != canonical(s['receipt']).decode():
                        raise PublicationDenied("Confirmed D2 lacks persisted target receipt")

    @contextmanager
    def _tx(self, *, target=True, nowait=False):
        with self.authority._connection() as conn:
            try:
                conn.execute(f'PRAGMA busy_timeout={0 if nowait else int(self.limits.timeout_seconds*1000)}')
                conn.execute('BEGIN IMMEDIATE')
                self._verify_source(conn)
                states,epoch = self._replay(conn)
                if target:
                    self._verify_target(conn,states)
                yield conn,states,epoch
                # Validate semantic event order before committing, even where
                # the target transaction has already committed separately.
                self._replay(conn)
                conn.commit()
                self._observed_head = self._head(conn)
            except BaseException:
                conn.rollback()
                raise

    def fence(self):
        with self._tx() as (conn,states,epoch):
            self._append(conn,'D2_FENCE',dict(epoch=epoch+1))
        return epoch+1

    def _check_epoch(self, current, epoch):
        if type(epoch) is not int or epoch < 1 or epoch != current:
            raise PublicationDenied("Stale/missing D2 attempt fence")

    def begin(self, epoch, seq, *, disposition='APPLIED', recovering=False):
        self.fault('before_intent')
        with self._tx() as (conn,states,current):
            self._check_epoch(current,epoch)
            request = self._request(conn,seq)
            if disposition == 'APPLIED':
                require_eligible_db(conn,request['key'])
                evidence = None
            elif disposition == 'WITHHELD':
                evidence = self._evidence(conn,request['key'])
            else:
                raise PublicationDenied("Unsupported effect disposition")
            s = states.get(seq)
            if s and s['receipt'] is not None:
                return None,False
            prior = s['attempts'].get(epoch) if s else None
            if prior:
                if prior['disposition'] != disposition or prior['evidence'] != evidence:
                    raise PublicationDenied("A new disposition requires a new fenced attempt")
                if recovering and not prior['recovering']:
                    if self._head(conn)[0] + 2 > self.limits.max_events:
                        raise PublicationDenied("No capacity for reconciliation plus terminal ACK")
                    self._append(conn,'D2_RECONCILE',dict(source_seq=seq,epoch=epoch,id=prior['id']))
                return prior,False
            if (len(states) >= self.limits.max_effects and s is None) or (s and len(s['attempts']) >= self.limits.max_attempts):
                raise PublicationDenied("Consumer effect/attempt quota full")
            if self._head(conn)[0] + 2 > self.limits.max_events:
                raise PublicationDenied("No capacity for intent plus terminal ACK")
            attempt = dict(source_seq=seq,epoch=epoch,id=digest([request['effect_id'],epoch]),request=request,
                           disposition=disposition,evidence=evidence,recovering=recovering)
            self._append(conn,'D2_INTENT',attempt)
        self.fault('after_intent')
        return attempt,True

    def _execute(self, epoch, seq):
        # Optional archive target contention must not hold the source lock.
        # Target-first then NONBLOCKING source acquisition avoids lock-order
        # cycles with another source-held proof reader/receipt writer.
        with self._target() as target:
            target.execute(f'PRAGMA busy_timeout={int(self.limits.timeout_seconds*1000)}')
            target.execute('BEGIN IMMEDIATE')
            with self._tx(nowait=True) as (conn,states,current):
                self._check_epoch(current,epoch)
                s = states.get(seq)
                attempt = s['attempts'].get(epoch) if s else None
                if attempt is None or s['receipt'] is not None:
                    raise PublicationDenied("Current unresolved source intent required")
                request = s['request']
                if attempt['disposition'] == 'APPLIED':
                    require_eligible_db(conn,request['key'])
                else:
                    self._evidence(conn,request['key'],attempt['evidence'])
                self.fault('pre_effect')
                inbox = target.execute('SELECT * FROM d2_inbox WHERE effect_id=?',(request['effect_id'],)).fetchone()
                if inbox is None:
                    target.execute('INSERT INTO d2_inbox VALUES(?,?,?,?,?)',(request['effect_id'],canonical(request).decode(),attempt['disposition'],attempt['evidence'],epoch))
                    if attempt['disposition'] == 'APPLIED':
                        target.execute('INSERT INTO d2_effects VALUES(?,?)',(request['effect_id'],self.authority._row(conn,seq)['payload_json']))
                    self._target_budget(target)
                    target.commit()
                    origin = epoch
                else:
                    if inbox['disposition'] != attempt['disposition'] or inbox['evidence'] != attempt['evidence']:
                        raise InDoubt("Persisted target disposition cannot be overwritten")
                    origin = inbox['origin_epoch']
                    target.rollback()
                self.fault('post_target')
                self.fault('pre_receipt')
                body = dict(schema='aql.d2-target-receipt.v1',request=request,attempt_id=attempt['id'],
                    attempt_epoch=epoch,origin_epoch=origin,disposition=attempt['disposition'],evidence=attempt['evidence'])
                receipt = dict(body,proof_digest=digest(body))
                # Effect COMMIT released target lock. Reacquire without waiting
                # while source is held; contention leaves explicit IN_DOUBT.
                target.execute('PRAGMA busy_timeout=0')
                target.execute('BEGIN IMMEDIATE')
                prior = target.execute('SELECT body FROM d2_receipts WHERE attempt_id=?',(attempt['id'],)).fetchone()
                if prior is None:
                    target.execute('INSERT INTO d2_receipts VALUES(?,?,?)',(attempt['id'],request['effect_id'],canonical(receipt).decode()))
                    self._target_budget(target)
                elif prior[0] != canonical(receipt).decode():
                    raise PublicationDenied("Receipt retry content mismatch")
                target.commit()
                self.fault('post_receipt')
        return receipt

    def perform(self, epoch, seq):
        attempt,created = self.begin(epoch,seq)
        if attempt is None:
            with self._tx() as (_,states,current):
                self._check_epoch(current,epoch)
                return states[seq]['receipt']
        if not created:
            raise InDoubt("Existing attempt requires explicit reconciliation")
        return self._execute(epoch,seq)

    def confirm(self, epoch, receipt):
        with self._tx() as (conn,states,current):
            self._check_epoch(current,epoch)
            if type(receipt) is not dict or type(receipt.get('request')) is not dict:
                raise PublicationDenied("Target receipt envelope required; local publication hash is not proof")
            seq = receipt['request'].get('source_seq')
            s = states.get(seq)
            attempt = s['attempts'].get(epoch) if s else None
            if attempt is None:
                raise PublicationDenied("Receipt has no current source attempt")
            self._proof_shape(receipt,s['request'],attempt)
            with self._target() as target:
                row = target.execute('SELECT body FROM d2_receipts WHERE attempt_id=?',(attempt['id'],)).fetchone()
                if row is None or row[0] != canonical(receipt).decode():
                    raise PublicationDenied("Receipt not persisted at registered target")
            if s['receipt'] is not None:
                if s['receipt'] != receipt:
                    raise PublicationDenied("Contradictory duplicate ACK")
                return False
            if attempt['disposition'] == 'APPLIED':
                require_eligible_db(conn,s['request']['key'])
            else:
                self._evidence(conn,s['request']['key'],attempt['evidence'])
            self.fault('pre_ack')
            self._append(conn,'D2_CONFIRMED',dict(source_seq=seq,epoch=epoch,id=attempt['id'],receipt=receipt))
        self.fault('post_ack')
        return True

    def deliver(self, epoch, seq):
        receipt = self.perform(epoch,seq)
        with self._tx() as (_,states,current):
            self._check_epoch(current,epoch)
            if states[seq]['receipt'] == receipt:
                return receipt  # Historical, already-confirmed effect; no new ACK.
        self.confirm(epoch,receipt)
        return receipt

    def reconcile(self, epoch, seq):
        with self._tx() as (_,states,current):
            self._check_epoch(current,epoch)
            s = states.get(seq)
            if s is None:
                raise PublicationDenied("No uncertain effect to reconcile")
            if s['receipt'] is not None:
                return s['receipt']
            prior = s['attempts'][max(s['attempts'])]
            disposition = prior['disposition']
        self.begin(epoch,seq,disposition=disposition,recovering=True)
        receipt = self._execute(epoch,seq)
        self.confirm(epoch,receipt)
        return receipt

    def withhold(self, epoch, seq):
        with self._tx() as (conn,states,current):
            self._check_epoch(current,epoch)
            request = self._request(conn,seq)
            evidence = self._evidence(conn,request['key'])
            s = states.get(seq)
            if s and s['receipt'] is not None:
                if not s['withheld']:
                    self._append(conn,'D2_WITHHELD',dict(source_seq=seq,epoch=epoch,evidence=evidence,receipt=s['receipt']))
                return s['receipt']
        attempt,created = self.begin(epoch,seq,disposition='WITHHELD')
        if not created:
            raise InDoubt("Withheld attempt needs explicit reconciliation")
        receipt = self._execute(epoch,seq)
        self.confirm(epoch,receipt)
        return receipt

    def view(self):
        with self._tx() as (conn,states,_):
            D,W,V,U,S = [],[],[],[],0
            prefix = True
            for row in conn.execute('SELECT id,stable_key FROM journal_entries ORDER BY id'):
                seq,key = row
                s = states.get(seq)
                terminal = s is not None and s['receipt'] is not None
                blocked = bool(conn.execute('SELECT 1 FROM g1_integrity_events WHERE stable_key=?',(key,)).fetchone())
                if terminal and s['receipt']['disposition'] == 'APPLIED':
                    D.append(seq)
                    if not blocked: V.append(seq)
                if terminal and s['withheld']: W.append(seq)
                if s and not terminal: U.append(seq)
                if prefix and terminal: S=seq
                else: prefix=False
            return dict(schema='aql.d2-view.v1',consumer=self.consumer,D=D,W=W,V=V,S=S,
                        IN_DOUBT=U,coverage='UNKNOWN',scope='SYNTHETIC_OFFLINE_ONLY')

    def checkpoint(self):
        with self._tx(target=False) as (conn,_,_):
            return self._head(conn)

    def rebuild(self):
        # There is no trusted mutable D2 projection: derive all states from the
        # validated append-only consumer chain and independently queried target.
        return self.view()
