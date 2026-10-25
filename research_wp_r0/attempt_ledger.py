"""Factory-owned local receipt adapter, v1. No evaluator/legacy journal imports.

SQLite transactions provide a single ordered append boundary, not physically
immutable storage or independently authenticated custody. FULL/WAL is a request
to the OS, not power-loss certification. Callers retain checkpoints separately.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .strategy_definition import AttemptRecorder, canonical, identifier, load_json


@dataclass(frozen=True)
class StateMapping:
    main_state: str
    legacy_state: str
    semantics: str


STATE_MAPPING = (
    StateMapping("PENDING", "ABSENT", "Accepted definition; not evaluated"),
    StateMapping("INVALID", "INELIGIBLE", "Not lossless: legacy lacks main validation/error payload"),
    StateMapping("FAILED", "FAILED", "Failure; error retained when supplied"),
    StateMapping("ABANDONED", "ABSENT", "Explicit termination, not success"),
    StateMapping("COMPLETE", "COMPLETE", "Unsupported until evaluator/result contract reconciled"),
)
LEGACY_INCOMPATIBILITIES = (
    "Main dictionary sink versus typed Attempt plus event_id",
    "FrozenSearchFamily/metric/alpha/temporal manifest absent from main sink",
    "Main raw-input/strategy/error payload has no lossless legacy mapping",
)
ZERO = "0" * 64


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _checked_path(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            s = part.lstat()
            if part.is_symlink() or getattr(s, "st_file_attributes", 0) & 0x400:
                raise ValueError("Symlink/reparse ledger path forbidden")
    if not path.parent.is_dir():
        raise ValueError("Existing private local parent required")
    return path


class AttemptLedger:
    """Persist-or-raise AttemptRecorder sink; serialized concurrent transactions.

    One input digest per family/candidate; identical event replay is a no-op.
    No UPDATE/DELETE API. Entire bounded chain/state replay checked each append.
    A supplied external checkpoint must match a retained prefix, including on open.
    """
    def __init__(self, path, *, expected_checkpoint=None, require_admission=False):
        self.path = _checked_path(path)
        self.expected_checkpoint = expected_checkpoint
        self.require_admission = require_admission
        existed = self.path.exists()
        if not existed and expected_checkpoint is not None:
            raise ValueError("Anchored ledger missing; refusing recreation")
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            if not existed:
                db.execute("CREATE TABLE receipts(seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, payload BLOB NOT NULL, chain_hash TEXT NOT NULL)")
                db.execute("PRAGMA user_version=1")
                db.execute("CREATE TABLE ledger_policy (id INTEGER PRIMARY KEY CHECK(id=1), require_admission INTEGER NOT NULL CHECK(require_admission IN (0,1)))")
                db.execute("INSERT INTO ledger_policy VALUES(1,?)", (int(bool(require_admission)),))
                db.execute("CREATE TABLE frozen_plan_policy (id INTEGER PRIMARY KEY CHECK(id=1), plan_digest TEXT NOT NULL, plan_bytes BLOB NOT NULL)")
            stored = db.execute("SELECT require_admission FROM ledger_policy WHERE id=1").fetchone()
            if stored is None or stored[0] not in (0, 1):
                raise ValueError("Missing or invalid durable admission policy; no automatic repair")
            # Existing legacy/incomplete schemas must not be silently migrated.
            db.execute("SELECT plan_digest,plan_bytes FROM frozen_plan_policy WHERE id=1").fetchone()
            self._read(db)
            self.require_admission = bool(stored[0])
            if require_admission and not self.require_admission:
                db.execute("UPDATE ledger_policy SET require_admission=1 WHERE id=1")
                self.require_admission = True
            db.execute("COMMIT")
        finally:
            if db.in_transaction: db.execute("ROLLBACK")
            db.close()
        self._identity = (self.path.stat().st_dev, self.path.stat().st_ino)

    def _connect(self):
        _checked_path(self.path)
        if hasattr(self, "_identity"):
            s = self.path.stat()
            if (s.st_dev, s.st_ino) != self._identity:
                raise ValueError("Ledger path replaced")
        existed = self.path.exists()
        db = sqlite3.connect(self.path, timeout=1, isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            if existed:
                if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                    raise ValueError("Incompatible ledger journal mode; no automatic migration")
            else:
                db.execute("PRAGMA journal_mode=WAL")
        except Exception:
            db.close()
            raise
        return db

    @staticmethod
    def _validate(event, states, identities):
        if type(event) is not dict:
            raise ValueError("Event dictionary required")
        kind = event.get("state")
        if kind not in {"PENDING", "INVALID", "FAILED", "ABANDONED", "INPUTS"}:
            raise ValueError("Unsupported state; COMPLETE requires reconciled evaluator")
        base = {"state", "family_id", "candidate_id", "input_digest"}
        if not base <= event.keys():
            raise ValueError("Missing attempt identity")
        identifier(event["family_id"]); identifier(event["candidate_id"])
        for field in ("input_digest", "strategy_digest", "binding_digest", "result_digest", "inputs_digest"):
            value = event.get(field)
            if value is not None and (type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
                raise ValueError("Invalid digest")
        if type(event["input_digest"]) is not str:
            raise ValueError("Input digest required")
        allowed = base | {"strategy_digest", "error_type", "binding_digest", "result_digest"}
        if kind == "INPUTS": allowed |= {"inputs", "inputs_digest"}
        if event.keys() - allowed:
            raise ValueError("Unsupported receipt fields")
        if "error_type" in event and (type(event["error_type"]) is not str or not 1 <= len(event["error_type"]) <= 128):
            raise ValueError("Bounded error type required; no raw exception/secret dumps")
        pair = (event["family_id"], event["candidate_id"])
        identity = (event["input_digest"], event.get("strategy_digest"))
        if pair in identities and identities[pair] != identity:
            raise ValueError("Conflicting family/candidate input")
        old = states.get(pair)
        if kind == "INPUTS":
            if old != "PENDING" or type(event.get("inputs")) is not str:
                raise ValueError("INPUTS requires pending attempt")
            if _hash(event["inputs"].encode()) != event.get("inputs_digest"):
                raise ValueError("Input receipt commitment mismatch")
            bundle = load_json(event["inputs"])
            if bundle.get("state") != "INPUTS_ONLY_NOT_EVALUATED":
                raise ValueError("Only unevaluated input receipts supported")
            if bundle.get("binding", {}).get("binding", {}).get("strategy_digest") != event.get("strategy_digest"):
                raise ValueError("Inputs strategy binding mismatch")
        else:
            if old is not None and (old != "PENDING" or kind == "PENDING"):
                raise ValueError("Illegal attempt transition")
            if old is None and kind == "ABANDONED":
                raise ValueError("ABANDONED requires pending")
            if kind == "PENDING" and event.get("strategy_digest") is None:
                raise ValueError("Accepted definition commitment required")
            states[pair] = kind
        identities[pair] = identity

    def _read(self, db):
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Unsupported ledger version")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Corrupt ledger")
        count, size = db.execute("SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM receipts").fetchone()
        if count > 10000 or size > 16_000_000:
            raise ValueError("Bounded receipt inventory exceeded")
        rows = db.execute("SELECT seq,event_id,payload,chain_hash FROM receipts ORDER BY seq LIMIT 10001").fetchall()
        if len(rows) > 10000:
            raise ValueError("Bounded ledger capacity exceeded")
        prev = ZERO; states = {}; identities = {}; events = []; hashes = {0: ZERO}
        for n, (seq, eid, raw, chain) in enumerate(rows, 1):
            raw = bytes(raw)
            if len(raw) > 2_000_000 or seq != n:
                raise ValueError("Invalid sequence or receipt size")
            event = json.loads(raw)
            expected_id = self.event_id(event)
            if raw != canonical(event) or eid != expected_id or chain != _hash(bytes.fromhex(prev) + raw):
                raise ValueError("Corrupt receipt/hash chain")
            self._validate(event, states, identities)
            events.append(event); prev = chain; hashes[n] = prev
        anchor = self.expected_checkpoint
        if anchor is not None and (type(anchor) is not tuple or len(anchor) != 2 or hashes.get(anchor[0]) != anchor[1]):
            raise ValueError("External checkpoint mismatch/rollback")
        return events, (len(events), prev)

    @staticmethod
    def event_id(event):
        # Same logical transition with a different payload is a conflict.
        identity = {k: event.get(k) for k in ("family_id", "candidate_id", "input_digest", "state")}
        return _hash(b"AQL:ATTEMPT-ID:1\0" + canonical(identity))

    def bind_frozen_plan(self, raw_plan, expected_digest):
        """Enroll an empty ledger into a durable plan policy (one-time only).

        Plan identity is checked inside each subsequent append transaction.
        Custody of the initial digest must be verified independently.
        """
        from .frozen_research_plan import verify_research_plan
        plan = verify_research_plan(raw_plan, expected_digest)
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            events, _ = self._read(db)
            policy = db.execute("SELECT require_admission FROM ledger_policy WHERE id=1").fetchone()
            if policy is None or policy[0] not in (0, 1):
                raise ValueError("Missing durable admission policy; no automatic repair")
            stored = db.execute("SELECT plan_digest,plan_bytes FROM frozen_plan_policy WHERE id=1").fetchone()
            if stored is not None:
                if stored[0] != expected_digest or bytes(stored[1]) != raw_plan:
                    raise ValueError("Frozen plan policy cannot be replaced")
                if policy[0] != 1:
                    raise ValueError("Invalid sealed frozen plan admission policy")
                self._frozen_membership(plan, events)
            else:
                if events:
                    raise ValueError("Frozen plan enrollment requires empty ledger")
                db.execute("INSERT INTO frozen_plan_policy VALUES(1,?,?)",
                           (expected_digest, raw_plan))
                db.execute("UPDATE ledger_policy SET require_admission=1 WHERE id=1")
            db.execute("COMMIT")
            self.require_admission = True
        finally:
            if db.in_transaction: db.execute("ROLLBACK")
            db.close()

    @staticmethod
    def _frozen_membership(plan, events):
        allowed = {item["candidate_id"]: item["strategy_digest"] for item in plan["candidates"]}
        for event in events:
            if (event.get("family_id") != plan["family_id"] or
                    event.get("candidate_id") not in allowed or
                    event.get("strategy_digest") != allowed[event["candidate_id"]]):
                raise ValueError("Event violates sealed frozen plan")

    def record_attempt(self, event, *, admission=None):
        """Append receipt; optional admission is checked under BEGIN IMMEDIATE.

        A callback is supplemental, deterministic and side-effect free. On a
        sealed ledger it cannot bypass membership, including idempotent replay.
        Unsealed legacy usage remains separate from the frozen writer path.
        """
        raw = canonical(event)
        if len(raw) > 2_000_000:
            raise ValueError("Receipt exceeds bounded size")
        # Roundtrip detaches caller references, rejects NaN via canonical().
        event = json.loads(raw); eid = self.event_id(event)
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            events, checkpoint = self._read(db)
            policy = db.execute("SELECT require_admission FROM ledger_policy WHERE id=1").fetchone()
            if policy is None or policy[0] not in (0, 1):
                raise ValueError("Missing durable admission policy")
            sealed = db.execute("SELECT plan_digest,plan_bytes FROM frozen_plan_policy WHERE id=1").fetchone()
            if sealed is not None:
                from .frozen_research_plan import verify_research_plan
                plan = verify_research_plan(bytes(sealed[1]), sealed[0])
                self._frozen_membership(plan, (*events, event))
                if policy[0] != 1:
                    raise ValueError("Invalid sealed frozen plan admission policy")
            elif bool(policy[0]):
                raise ValueError("Durable admission policy requires enrolled frozen plan")
            if bool(policy[0]) and admission is None:
                raise ValueError("Durable admission policy requires callback")
            existing = db.execute("SELECT payload FROM receipts WHERE event_id=?", (eid,)).fetchone()
            if existing:
                if bytes(existing[0]) != raw:
                    raise ValueError("Conflicting same-ID payload")
                db.execute("COMMIT"); return checkpoint
            if checkpoint[0] >= 10000:
                raise ValueError("Bounded ledger capacity exceeded")
            size = db.execute("SELECT COALESCE(SUM(length(payload)),0) FROM receipts").fetchone()[0]
            if size + len(raw) > 16_000_000:
                raise ValueError("Bounded receipt inventory exceeded")
            states = {}; identities = {}
            for prior in events: self._validate(prior, states, identities)
            self._validate(event, states, identities)
            if admission is not None:
                admission(event, tuple(events), checkpoint)
            chain = _hash(bytes.fromhex(checkpoint[1]) + raw)
            db.execute("INSERT INTO receipts VALUES(?,?,?,?)", (checkpoint[0]+1, eid, raw, chain))
            db.execute("COMMIT")  # ACK only after successful real SQLite commit.
            return checkpoint[0]+1, chain
        finally:
            if db.in_transaction: db.execute("ROLLBACK")
            db.close()

    def snapshot(self):
        db = self._connect()
        try:
            db.execute("BEGIN")
            return self._read(db)
        finally:
            if db.in_transaction: db.execute("ROLLBACK")
            db.close()


def prepare_durable_candidate(ledger, *args, **kwargs):
    """Legacy bridge, disabled for frozen-plan protected ledgers.

    A frozen research run must use a plan-aware recorder/adapter; never
    allow this legacy bridge to silently write through a sealed policy.
    """
    if not isinstance(ledger, AttemptLedger):
        raise ValueError("Real Factory AttemptLedger required")
    db = ledger._connect()
    try:
        sealed = db.execute("SELECT 1 FROM frozen_plan_policy WHERE id=1").fetchone()
        policy = db.execute("SELECT require_admission FROM ledger_policy WHERE id=1").fetchone()
        if sealed is not None or policy is None or bool(policy[0]):
            raise ValueError("Legacy preparation prohibited on protected ledger")
    finally:
        db.close()
    from .historical_evaluation_bridge import prepare_candidate
    prepared, inputs = prepare_candidate(AttemptRecorder(ledger), *args, **kwargs)
    ledger.record_attempt({**prepared.__dict__, "state": "INPUTS",
                           "inputs": inputs.payload.decode(), "inputs_digest": inputs.digest})
    return prepared, inputs
