"""Package E owner-side durable Discoverer checkpoint and attempt journal.

SQLite WAL + FULL synchronous, each transaction atomically appends exactly one
content-addressed immutable ledger snapshot OR handoff attempt. Fresh process
readback is mandatory for recovery; this is not proof of external publisher
custody, remote replication, or historical scientific validity.

Only store test-safe Digests/metadata; never private candle bytes or holdout.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from tools.strategy_discoverer_offline.contracts import _digest
from tools.strategy_discoverer_offline.ledger import DiscovererLedger
from tools.strategy_discoverer_offline.ledger_membership_verifier import (
    verify_ledger_membership,
)

SCHEMA = "aql.discoverer.e.durable-checkpoint.v1"
GENESIS = "0" * 64


def _canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False)


class DurableDiscovererError(ValueError):
    pass


class DurableDiscovererCheckpoint:
    """Persist immutable append-only attempts and exact-chain membership snapshots.

    Ownership of the SQLite path is local to Discoverer, separate from Factory's
    results-store transaction and operational Scanner/Secretary queues.
    """

    def __init__(self, path):
        self.path = str(Path(path))
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _initialize(self):
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ledger_checkpoints (
                sequence INTEGER PRIMARY KEY,
                predecessor_sha TEXT NOT NULL,
                checkpoint_sha TEXT NOT NULL UNIQUE,
                snapshot_sha TEXT NOT NULL,
                canonical_json TEXT NOT NULL,
                schema_version TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS handoff_attempts (
                sequence INTEGER PRIMARY KEY,
                predecessor_sha TEXT NOT NULL,
                attempt_key TEXT NOT NULL UNIQUE,
                event_sha TEXT NOT NULL UNIQUE,
                canonical_json TEXT NOT NULL,
                schema_version TEXT NOT NULL)""")

    def _read_chain(self, db, table, digest_field):
        rows = db.execute(
            f"SELECT sequence, predecessor_sha, {digest_field}, canonical_json, schema_version "
            f"FROM {table} ORDER BY sequence"
        ).fetchall()
        previous = GENESIS
        for index, (seq, pred, digest, payload, version) in enumerate(rows, start=1):
            if seq != index or pred != previous or version != SCHEMA:
                raise DurableDiscovererError(table + ": broken predecessor/schema/index")
            try:
                fields = json.loads(payload)
            except (ValueError, TypeError) as exc:
                raise DurableDiscovererError(table + ": invalid record JSON") from exc
            if _canonical(fields) != payload:
                raise DurableDiscovererError(table + ": noncanonical JSON")
            expected = _digest({
                "schema_version": SCHEMA,
                "sequence": seq,
                "predecessor_sha": pred,
                "record": fields,
            })
            if expected != digest:
                raise DurableDiscovererError(table + ": tampered record digest")
            previous = digest
        return rows

    def ledger_snapshots(self):
        with self._connect() as db:
            rows = self._read_chain(db, "ledger_checkpoints", "checkpoint_sha")
        result = []
        previous_len = 0
        for seq, pred, digest, data, schema in rows:
            obj = json.loads(data)
            entries = obj["entries"]
            if not isinstance(entries, list) or len(entries) <= previous_len:
                raise DurableDiscovererError("ledger checkpoint must advance")
            ledger = DiscovererLedger.from_dict_list(entries, max_entries=max(4096, len(entries)))
            if not ledger.verify_chain() or ledger.head_digest() != obj["ledger_head"]:
                raise DurableDiscovererError("ledger snapshot invalid")
            if _digest(entries) != obj["entries_digest"]:
                raise DurableDiscovererError("ledger snapshot digest invalid")
            if result and entries[:previous_len] != result[-1]["entries"]:
                raise DurableDiscovererError("ledger history was replaced")
            result.append(dict(entries=entries, ledger_head=obj["ledger_head"],
                               entries_digest=obj["entries_digest"],
                               checkpoint_sha=digest, sequence=seq))
            previous_len = len(entries)
        return tuple(result)

    def append_ledger(self, entries_data):
        if not isinstance(entries_data, (tuple, list)) or not entries_data:
            raise DurableDiscovererError("nonempty ledger entries required")
        entries = list(entries_data)
        try:
            reconstructed = DiscovererLedger.from_dict_list(
                entries, max_entries=max(4096, len(entries)))
        except (ValueError, TypeError, KeyError) as exc:
            raise DurableDiscovererError("invalid ledger chain") from exc
        if not reconstructed.verify_chain():
            raise DurableDiscovererError("invalid ledger chain")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = self._read_chain(db, "ledger_checkpoints", "checkpoint_sha")
                if rows:
                    last = json.loads(rows[-1][3])["entries"]
                    if len(entries) == len(last) and entries == last:
                        db.execute("COMMIT")
                        return rows[-1][2]
                    if len(entries) <= len(last) or entries[:len(last)] != last:
                        raise DurableDiscovererError("conflicting ledger append/replay")
                seq = len(rows) + 1
                predecessor = rows[-1][2] if rows else GENESIS
                obj = dict(ledger_head=reconstructed.head_digest(),
                           entries_digest=_digest(entries), entries=entries)
                canonical = _canonical(obj)
                digest = _digest(dict(schema_version=SCHEMA, sequence=seq,
                                      predecessor_sha=predecessor, record=obj))
                db.execute("""INSERT INTO ledger_checkpoints
                    (sequence,predecessor_sha,checkpoint_sha,snapshot_sha,canonical_json,schema_version)
                    VALUES (?,?,?,?,?,?)""",
                    (seq,predecessor,digest,obj["entries_digest"],canonical,SCHEMA))
                db.execute("COMMIT")
                return digest
            except Exception:
                db.execute("ROLLBACK")
                raise

    def read_latest_ledger(self):
        snapshots = self.ledger_snapshots()
        if not snapshots:
            raise DurableDiscovererError("no persisted ledger checkpoint")
        return snapshots[-1]

    def verify_membership(self, *, package, ledger_attempt_id,
                          ledger_head_digest, ledger_reference):
        # Read back from durable custody; caller cannot submit arbitrary bytes.
        return verify_ledger_membership(
            entries_data=self.read_latest_ledger()["entries"], package=package,
            ledger_attempt_id=ledger_attempt_id,
            ledger_head_digest=ledger_head_digest,
            ledger_reference=ledger_reference,
        )

    def attempt_events(self):
        with self._connect() as db:
            rows = self._read_chain(db, "handoff_attempts", "event_sha")
        return tuple(dict(json.loads(data), event_sha=digest)
                     for seq,pred,digest,data,version in rows)

    def append_attempt(self, *, attempt_key, outcome, candidate_id, package_digest,
                       decision_digest, reason="", intake_digest=None):
        """Atomic, retry-idempotent event with unique request key.

        Same key + same content returns original digest; changed payload for
        the same key is a hard conflict and creates no second event.
        """
        if not isinstance(attempt_key, str) or not attempt_key.strip():
            raise DurableDiscovererError("attempt_key required")
        for name, value in (("package_digest",package_digest),
                            ("decision_digest",decision_digest)):
            if not isinstance(value,str) or len(value)!=64 or any(
                    c not in "0123456789abcdef" for c in value):
                raise DurableDiscovererError(name + ": SHA-256 required")
        if intake_digest is not None and (len(intake_digest)!=64 or any(
                c not in "0123456789abcdef" for c in intake_digest)):
            raise DurableDiscovererError("intake_digest: SHA-256 required")
        obj = dict(attempt_key=attempt_key,outcome=outcome,candidate_id=candidate_id,
                   package_digest=package_digest,decision_digest=decision_digest,
                   reason=reason,intake_digest=intake_digest)
        canonical = _canonical(obj)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = self._read_chain(db,"handoff_attempts","event_sha")
                existing = db.execute(
                    "SELECT canonical_json,event_sha FROM handoff_attempts WHERE attempt_key=?",
                    (attempt_key,)).fetchone()
                if existing:
                    if existing[0] != canonical:
                        raise DurableDiscovererError("attempt key idempotency conflict")
                    db.execute("COMMIT")
                    return existing[1]
                seq = len(rows)+1
                predecessor = rows[-1][2] if rows else GENESIS
                digest = _digest(dict(schema_version=SCHEMA, sequence=seq,
                                      predecessor_sha=predecessor,record=obj))
                db.execute("""INSERT INTO handoff_attempts
                    (sequence,predecessor_sha,attempt_key,event_sha,canonical_json,schema_version)
                    VALUES (?,?,?,?,?,?)""",
                    (seq,predecessor,attempt_key,digest,canonical,SCHEMA))
                db.execute("COMMIT")
                return digest
            except Exception:
                db.execute("ROLLBACK")
                raise
