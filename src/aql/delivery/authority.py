"""CORE-128: opt-in finite synthetic publication authority, never live wiring.

Publication and conflict events share the source SQLite transaction. Staging is
private to this adapter; cooperating clients read exclusively through read().
Not an OS security boundary, external custody service, or rollback-resistant DB.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
import time

from ..archive.contracts import canonical, digest, market_envelope
from ..g1_integrity import ContentConflictError, require_eligible_db

_PROCESS_FAULTS = set()


class PublicationDenied(ValueError):
    pass


def enabled(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='core128_meta'").fetchone())


def deny_legacy(conn):
    if enabled(conn):
        raise PublicationDenied("v2 synthetic source requires protected authority reader")


def fault_path(conn):
    return Path(conn.execute("PRAGMA database_list").fetchone()[2] + ".core128-fault")


def _trip(conn):
    # Outside SQL rollback, conservative latch. If the medium cannot persist it,
    # no durable fault/custody guarantee can be made; reopening needs an anchor.
    _PROCESS_FAULTS.add(str(fault_path(conn)))
    with open(fault_path(conn), "wb") as handle:
        handle.write(b"BOOTSTRAP_BLOCKED\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())


def _append(conn, op, data):
    meta = conn.execute("SELECT value FROM core128_meta WHERE singleton=1").fetchone()
    limits = json.loads(meta[0])["limits"]
    if conn.execute("SELECT COUNT(*) FROM core128_events").fetchone()[0] >= limits["max_events"]:
        raise PublicationDenied("Disposition ledger full; no eviction")
    row = conn.execute("SELECT seq,hash FROM core128_events ORDER BY seq DESC LIMIT 1").fetchone()
    seq, previous = (row[0]+1, row[1]) if row else (1, "0"*64)
    body = dict(schema="aql.core.consumer-disposition.v1", seq=seq,
                previous=previous, op=op, data=data)
    hashed = digest(body)
    conn.execute("INSERT INTO core128_events VALUES (?,?,?)", (seq, canonical(body).decode(), hashed))
    return hashed


def conflict_in_transaction(conn, key):
    """Called by record_event before its COMMIT; never async mirror a conflict."""
    if enabled(conn):
        try:
            evidence=conn.execute("SELECT event_id FROM g1_integrity_events WHERE stable_key=? ORDER BY rowid DESC LIMIT 1",(key,)).fetchone()
            _append(conn, "BLOCK", {"key": key,"evidence":evidence[0]})
            _project(conn)
        except Exception:
            _trip(conn)
            raise


def prepare_candidate(target, incoming, *, force=False):
    """Persist a denial intent BEFORE an evidence transaction can fail.

    Retained pending intents deny protected reads until matching evidence exists.
    No withheld settlement/ACK is invented by this weaker pre-evidence record.
    """
    conn=target._connect()
    try:
        if not enabled(conn): return
        if str(fault_path(conn)) in _PROCESS_FAULTS or fault_path(conn).exists():
            raise PublicationDenied("BOOTSTRAP_BLOCKED")
        conn.execute("BEGIN IMMEDIATE")
        original=target._original_bar(conn,incoming.stable_key())
        from ..g1_integrity import content
        if original is not None and (force or content(original)!=content(incoming)):
            raw=canonical(incoming.to_dict()).decode()
            conn.execute("INSERT OR IGNORE INTO core128_pending VALUES (?,?,?)",
                         (incoming.stable_key(),digest(incoming.to_dict()),raw))
        conn.commit()
    except BaseException:
        conn.rollback()
        if enabled(conn):
            _PROCESS_FAULTS.add(str(fault_path(conn)))
            try: _trip(conn)
            except OSError: pass
        raise
    finally:
        conn.close()


def _replay(conn):
    states, epochs, blocked = {}, {}, set()
    store_state = None
    previous = "0"*64
    initialized=False
    for index, (seq, raw, hashed) in enumerate(conn.execute("SELECT * FROM core128_events ORDER BY seq"), 1):
        event = json.loads(raw)
        if (canonical(event).decode()!=raw or type(event.get('seq')) is not int
                or seq != index or event.get("schema") != "aql.core.consumer-disposition.v1"
                or event.get("seq") != seq or event.get("previous") != previous or digest(event) != hashed):
            raise PublicationDenied("Disposition chain invalid")
        previous = hashed
        op, data = event["op"], event["data"]
        if index==1 and op!='INIT': raise PublicationDenied("Missing genesis initialization")
        if op == "INIT":
            if index != 1: raise PublicationDenied("Duplicate initialization")
            meta=conn.execute("SELECT value FROM core128_meta WHERE singleton=1").fetchone()
            if meta is None or data!=json.loads(meta[0]): raise PublicationDenied("Genesis anchor mismatch")
            initialized=True
            from .store_binding import initial_state
            store_state = initial_state(data)
        elif op.startswith("STORE_"):
            from .store_binding import apply_store_event
            apply_store_event(store_state, op, data)
        elif op == "FENCE":
            c = data["consumer"]
            if (not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",c) or type(data['epoch']) is not int
                    or data["epoch"] != epochs.get(c, 0)+1):
                raise PublicationDenied("Epoch sequence invalid")
            epochs[c] = data["epoch"]
        elif op == "BLOCK":
            proof=conn.execute("SELECT stable_key FROM g1_integrity_events WHERE event_id=?",(data.get('evidence'),)).fetchone()
            if proof is None or proof[0]!=data['key']: raise PublicationDenied("Unproven block event")
            blocked.add(data["key"])
        elif op in ("STAGE", "PUBLISH", "DELIVERED", "WITHHELD"):
            c, source_seq = data["consumer"], data["source_seq"]
            if type(source_seq) is not int or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",c):
                raise PublicationDenied("Invalid disposition identity")
            if (c not in epochs or type(data.get('epoch')) is not int
                    or data['epoch']!=epochs[c]):
                raise PublicationDenied("Unfenced disposition event")
            source=conn.execute("SELECT * FROM journal_entries WHERE id=?",(source_seq,)).fetchone()
            if source is None: raise PublicationDenied("Missing disposition source")
            source_key=source['stable_key']
            key = (c, source_seq)
            state = states.setdefault(key, dict(stage=None, publication=None, delivered=False, withheld=False))
            if op == "STAGE":
                if state["stage"] is not None: raise PublicationDenied("Duplicate stage event")
                staged=conn.execute("SELECT * FROM core128_stages WHERE id=?",(data['stage'],)).fetchone()
                if staged is None or staged['consumer']!=c or staged['seq']!=source_seq:
                    raise PublicationDenied("Stage binding mismatch")
                state["stage"] = data["stage"]
            elif op == "PUBLISH":
                if source_key in blocked: raise PublicationDenied("Publication after block")
                if (not isinstance(data.get('stage'),str) or len(data['stage'])!=64
                        or not state['stage'] or state["stage"] != data["stage"] or state["publication"] is not None):
                    raise PublicationDenied("Unstaged/duplicate publication")
                if data["epoch"] != epochs.get(c): raise PublicationDenied("Stale publication event")
                state["publication"] = hashed
            elif op == "DELIVERED":
                if source_key in blocked: raise PublicationDenied("Delivery ACK after block")
                if (not state['stage'] or not state['publication'] or not isinstance(data.get('receipt'),str)
                        or len(data['receipt'])!=64 or state["publication"] != data["receipt"]):
                    raise PublicationDenied("Unproven delivery ACK")
                state["delivered"] = True
            else:
                proof=conn.execute("SELECT stable_key FROM g1_integrity_events WHERE event_id=?",(data.get('evidence'),)).fetchone()
                if (data["key"]!=source_key or data["key"] not in blocked
                        or proof is None or proof[0]!=source_key):
                    raise PublicationDenied("Unproven withheld disposition")
                state["withheld"] = True
        else:
            raise PublicationDenied("Unsupported disposition operation")
    if not initialized: raise PublicationDenied("Empty disposition log")
    return states, epochs, blocked


def _project(conn):
    states, epochs, blocked = _replay(conn)
    value = {"states": [[c,s,v] for (c,s),v in sorted(states.items())],
             "epochs": epochs, "blocked": sorted(blocked)}
    conn.execute("INSERT OR REPLACE INTO core128_projection VALUES (1,?)", (canonical(value).decode(),))
    return value


def _source(conn):
    return [dict(row) for row in conn.execute("SELECT * FROM journal_entries ORDER BY id")]


@dataclass(frozen=True)
class Limits:
    max_records: int
    max_bytes: int
    timeout_seconds: float
    max_events: int

    def validate(self):
        if (type(self.max_records) is not int or not 1 <= self.max_records <= 128
                or type(self.max_bytes) is not int or not 1 <= self.max_bytes <= 262144
                or type(self.timeout_seconds) not in (int,float) or not 0 < self.timeout_seconds <= 2):
            raise ValueError("Explicit bounded synthetic limits required")
        if type(self.max_events) is not int or not 1 <= self.max_events <= 4096:
            raise ValueError("Explicit event capacity required")


class Authority:
    def __init__(self, journal, *, limits, synthetic=False, anchor=None, checkpoint=None,
                 stores=()):
        if synthetic is not True:
            raise PublicationDenied("No real-mode authority implementation")
        limits.validate()
        self.journal, self.limits = journal, limits
        self.fault = lambda stage: None
        with self._connection() as conn:
            if not enabled(conn):
                if anchor is not None: raise PublicationDenied("Missing authority generation")
                if not stores:
                    raise PublicationDenied("Explicit OperationalStore writer binding required")
                rows = _source(conn)
                if len(rows) > limits.max_records or len(canonical(rows)) > limits.max_bytes:
                    raise PublicationDenied("Source exceeds finite synthetic admission")
                for row in rows:
                    if not row["source"].startswith("synthetic"):
                        raise PublicationDenied("Only synthetic fixture sources admitted")
                    market_envelope(row, journal_id=journal.instance_id, market="spot", build="core128",
                                    policy="synthetic-v2", cutoff_ms=int(time.time()*1000))
                self.anchor = dict(source=journal.instance_id,path=str(Path(journal.db_path).resolve()),
                                   inventory=digest(rows), limits=limits.__dict__)
                from .store_binding import freeze_stores
                self.anchor.update(freeze_stores(self, stores))
                conn.executescript("""
                CREATE TABLE core128_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),value TEXT NOT NULL);
                CREATE TABLE core128_events(seq INTEGER PRIMARY KEY,body TEXT NOT NULL,hash TEXT NOT NULL);
                CREATE TABLE core128_stages(id TEXT PRIMARY KEY,consumer TEXT NOT NULL,seq INTEGER NOT NULL,
                  payload TEXT NOT NULL, UNIQUE(consumer,seq));
                CREATE TABLE core128_projection(singleton INTEGER PRIMARY KEY CHECK(singleton=1),value TEXT NOT NULL);
                CREATE TABLE core128_pending(key TEXT NOT NULL,hash TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(key,hash));
                CREATE TRIGGER core128_pending_no_update BEFORE UPDATE ON core128_pending BEGIN
                  SELECT RAISE(ABORT,'immutable denial intent'); END;
                CREATE TRIGGER core128_pending_no_delete BEFORE DELETE ON core128_pending BEGIN
                  SELECT RAISE(ABORT,'immutable denial intent'); END;
                CREATE TRIGGER core128_events_no_update BEFORE UPDATE ON core128_events BEGIN
                  SELECT RAISE(ABORT,'immutable disposition'); END;
                CREATE TRIGGER core128_events_no_delete BEFORE DELETE ON core128_events BEGIN
                  SELECT RAISE(ABORT,'immutable disposition'); END;
                CREATE TRIGGER core128_stage_no_update BEFORE UPDATE ON core128_stages BEGIN
                  SELECT RAISE(ABORT,'immutable stage'); END;
                CREATE TRIGGER core128_stage_no_delete BEFORE DELETE ON core128_stages BEGIN
                  SELECT RAISE(ABORT,'immutable stage'); END;
                """)
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT INTO core128_meta VALUES (1,?)", (canonical(self.anchor).decode(),))
                _append(conn, "INIT", self.anchor)
                # Import already durable quarantine; never assume absent stages mean clean.
                for row in conn.execute("SELECT stable_key,event_id FROM g1_integrity_events").fetchall():
                    _append(conn, "BLOCK", {"key": row[0],"evidence":row[1]})
                _project(conn)
                conn.commit()
            else:
                if anchor is None: raise PublicationDenied("Reopen requires separately retained source anchor")
                self.anchor = anchor
            self._verify(conn)
            if anchor is not None:
                head=tuple(conn.execute("SELECT seq,hash FROM core128_events ORDER BY seq DESC LIMIT 1").fetchone())
                if checkpoint is None or tuple(checkpoint)!=head:
                    raise PublicationDenied("Current independently retained progress checkpoint required")

    @contextmanager
    def _connection(self):
        conn = self.journal._connect()
        try:
            conn.execute(f"PRAGMA busy_timeout={int(self.limits.timeout_seconds*1000)}")
            yield conn
        finally:
            conn.close()

    def _verify(self, conn, *, pending_store_intent=None):
        if str(fault_path(conn)) in _PROCESS_FAULTS or fault_path(conn).exists():
            raise PublicationDenied("BOOTSTRAP_BLOCKED: failed conflict write")
        meta = conn.execute("SELECT value FROM core128_meta WHERE singleton=1").fetchone()
        if meta is None or json.loads(meta[0]) != self.anchor:
            raise PublicationDenied("Authority source/anchor mismatch")
        if self.limits.__dict__ != self.anchor["limits"]:
            raise PublicationDenied("Runtime limits differ from frozen source configuration")
        if str(Path(self.journal.db_path).resolve()) != self.anchor["path"]:
            raise PublicationDenied("Copied source path requires separate reconciliation")
        if self.journal.instance_id != self.anchor["source"] or digest(_source(conn)) != self.anchor["inventory"]:
            raise PublicationDenied("Full source record inventory changed")
        states, epochs, blocked = _replay(conn)
        from .store_binding import verify_bindings
        verify_bindings(conn, self.anchor, pending_store_intent=pending_store_intent)
        projected = {"states": [[c,s,v] for (c,s),v in sorted(states.items())],
                     "epochs": epochs, "blocked": sorted(blocked)}
        p = conn.execute("SELECT value FROM core128_projection WHERE singleton=1").fetchone()
        if p is None or json.loads(p[0]) != projected:
            raise PublicationDenied("Projection differs from durable events; rebuild explicitly")
        evidence = {r[0] for r in conn.execute("SELECT DISTINCT stable_key FROM g1_integrity_events")}
        if evidence != blocked: raise PublicationDenied("Conflict ledger/evidence mismatch")
        for pending in conn.execute("SELECT key,hash,payload FROM core128_pending"):
            value=json.loads(pending['payload'])
            from ..g1_integrity import content
            from ..models.bar import MarketBar
            candidate=MarketBar.from_dict(value)
            if digest(value)!=pending['hash'] or candidate.stable_key()!=pending['key']:
                raise PublicationDenied("Invalid conflict denial intent")
            proofs=conn.execute("SELECT evidence_json FROM g1_integrity_events WHERE stable_key=?",(pending['key'],)).fetchall()
            if not any(content(MarketBar.from_dict(json.loads(p[0])['incoming_record']))==content(candidate) for p in proofs):
                raise PublicationDenied("BOOTSTRAP_BLOCKED: pending conflict lacks audit proof")
        for row in conn.execute("SELECT * FROM core128_stages"):
            original = self._row(conn, row["seq"])
            if (row["payload"] != original["payload_json"] or
                    digest([self.anchor, row["consumer"], row["seq"], row["payload"]]) != row["id"]):
                raise PublicationDenied("Stage source/digest mismatch")
        return states, epochs, blocked

    def _row(self, conn, seq):
        row = conn.execute("SELECT * FROM journal_entries WHERE id=?", (seq,)).fetchone()
        if row is None: raise PublicationDenied("Unknown source sequence")
        return row

    @contextmanager
    def _transaction(self):
        with self._connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._verify(conn)
                yield conn
                _project(conn)
                self.fault("before_commit")
                conn.commit()
                self.fault("after_commit")
            except BaseException:
                conn.rollback()
                raise

    def fence(self, consumer):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", consumer): raise ValueError("Invalid target/consumer binding")
        with self._transaction() as conn:
            _, epochs, _ = _replay(conn)
            epoch = epochs.get(consumer,0)+1
            _append(conn,"FENCE",dict(consumer=consumer,epoch=epoch))
        return epoch

    def _check(self, conn, consumer, epoch):
        _, epochs, _ = _replay(conn)
        if type(epoch) is not int or epochs.get(consumer) != epoch:
            raise PublicationDenied("Stale/missing fence")

    def stage(self, consumer, epoch, seq):
        with self._transaction() as conn:
            self._check(conn,consumer,epoch)
            row = self._row(conn,seq)
            require_eligible_db(conn,row["stable_key"])
            sid = digest([self.anchor,consumer,seq,row["payload_json"]])
            prior = conn.execute("SELECT * FROM core128_stages WHERE id=?", (sid,)).fetchone()
            if prior is None:
                if conn.execute("SELECT COUNT(*) FROM core128_stages").fetchone()[0] >= self.limits.max_records:
                    raise PublicationDenied("Private staging full; no eviction")
                used=conn.execute("SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM core128_stages").fetchone()[0]
                if used+len(row["payload_json"].encode()) > self.limits.max_bytes:
                    raise PublicationDenied("Private staging byte capacity reached")
                conn.execute("INSERT INTO core128_stages VALUES (?,?,?,?)",(sid,consumer,seq,row["payload_json"]))
                _append(conn,"STAGE",dict(consumer=consumer,source_seq=seq,stage=sid,epoch=epoch))
                self.fault("after_stage")
        return sid

    def publish(self, consumer, epoch, seq, sid):
        with self._transaction() as conn:
            self._check(conn,consumer,epoch)
            row=self._row(conn,seq)
            require_eligible_db(conn,row["stable_key"])
            states,_,_=_replay(conn)
            state=states.get((consumer,seq))
            if state is None or state["stage"]!=sid: raise PublicationDenied("No matching private stage")
            if state["publication"]:
                return state["publication"]
            self.fault("before_publish")
            receipt=_append(conn,"PUBLISH",dict(consumer=consumer,source_seq=seq,stage=sid,epoch=epoch))
        return receipt

    def settle(self,consumer,epoch,seq,*,receipt=None,withheld=False):
        with self._transaction() as conn:
            self._check(conn,consumer,epoch)
            row=self._row(conn,seq)
            if withheld:
                evidence=conn.execute("SELECT event_id FROM g1_integrity_events WHERE stable_key=? LIMIT 1",
                                      (row["stable_key"],)).fetchone()
                if evidence is None: raise PublicationDenied("No durable withheld evidence")
                _append(conn,"WITHHELD",dict(consumer=consumer,source_seq=seq,key=row["stable_key"],evidence=evidence[0],epoch=epoch))
            else:
                require_eligible_db(conn,row["stable_key"])
                states,_,_=_replay(conn)
                if not receipt or states.get((consumer,seq),{}).get("publication")!=receipt:
                    raise PublicationDenied("Unproven delivery ACK")
                _append(conn,"DELIVERED",dict(consumer=consumer,source_seq=seq,receipt=receipt,epoch=epoch))

    def deliver(self,consumer,epoch,seq):
        try:
            sid=self.stage(consumer,epoch,seq)
            receipt=self.publish(consumer,epoch,seq,sid)
            self.settle(consumer,epoch,seq,receipt=receipt)
            return receipt
        except ContentConflictError:
            self.settle(consumer,epoch,seq,withheld=True)
            return None

    def read(self,consumer,seq):
        # A source transaction is the read authorization linearization point.
        # No network or unbounded file read occurs while holding this lock.
        with self._transaction() as conn:
            row=self._row(conn,seq)
            require_eligible_db(conn,row["stable_key"])
            states,_,_=_replay(conn)
            state=states.get((consumer,seq))
            if not state or not state["publication"]: raise PublicationDenied("Private/unpublished record")
            staged=conn.execute("SELECT payload FROM core128_stages WHERE id=?",(state["stage"],)).fetchone()
            if staged is None: raise PublicationDenied("Missing sealed payload")
            return json.loads(staged[0])

    def view(self,consumer):
        with self._transaction() as conn:
            states,_,blocked=_replay(conn)
            D,W,V,S=set(),set(),set(),0
            prefix=True
            for row in conn.execute("SELECT id,stable_key FROM journal_entries ORDER BY id"):
                seq,key=row
                state=states.get((consumer,seq),{})
                if state.get("delivered"): D.add(seq)
                if state.get("withheld"): W.add(seq)
                if state.get("publication") and key not in blocked: V.add(seq)
                if prefix and (state.get("delivered") or state.get("withheld")): S=seq
                else: prefix=False
            return dict(D=sorted(D),W=sorted(W),V=sorted(V),S=S)

    def rebuild(self):
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _project(conn)
            self._verify(conn)
            conn.commit()

    def checkpoint(self):
        with self._transaction() as conn:
            return tuple(conn.execute("SELECT seq,hash FROM core128_events ORDER BY seq DESC LIMIT 1").fetchone())

    def reader(self, consumer):
        return ProtectedReader(lambda seq:self.read(consumer,seq))

    def store_writer(self, store):
        """Validate a configured writer; never enroll it implicitly on reopen."""
        from .store_binding import store_state
        with self._transaction() as conn:
            token = getattr(store, '_core128_token', None)
            if not token or token[0] not in [i['binding'] for i in self.anchor['stores']]:
                raise PublicationDenied("Unbound configured store writer")
            binding, epoch = token
            if str(Path(store.db_path).resolve()) != binding['path']:
                raise PublicationDenied("Store writer path changed")
            if store_state(conn, self.anchor)[binding['store']]['epoch'] != epoch:
                raise PublicationDenied("Stale store writer fence")
        return store


class ProtectedReader:
    """Operational facade: no connection, source handle, or stage operation.

    Trusted maintenance still owns the Authority. This is capability discipline,
    not protection from hostile Python introspection or filesystem credentials.
    """
    __slots__=('__read',)

    def __init__(self, read): self.__read=read
    def read(self,seq): return self.__read(seq)
