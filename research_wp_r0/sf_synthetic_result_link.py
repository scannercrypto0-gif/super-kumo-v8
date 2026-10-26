"""Bounded SF-LEDGER-LINK-01 synthetic evidence linked to sealed Factory attempts.

Adds an independently validated SYNTHETIC-ONLY evidence table in the SAME
Factory SQLite database. Does not alter the version-1 attempt event protocol,
permit COMPLETE, or create Core WATCH/TRIGGER/READY events.
"""
import hashlib
import json
import re

from .attempt_ledger import AttemptLedger, ZERO
from .frozen_attempt_writer import FrozenAttemptWriter
from .frozen_research_plan import commit_research_plan, verify_research_plan
from .sf_breakout_pilot import PilotPlan, SPEC, COSTS, run_pilot
from .strategy_definition import canonical, digest

_HEX = re.compile(r"[a-f0-9]{64}\Z")
FAMILY = "SF_BREAKOUT_SYNTHETIC_01"
VERSIONS = ("BASE", "SHADOW")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def version_digest(name):
    if name not in VERSIONS:
        raise ValueError("Unknown immutable pilot version")
    return digest({"pilot": SPEC, "version": "BREAKOUT_20_10_" + name + "_v1"})


def frozen_pilot_family(*, plan, expected_plan_digest, expected_data_digest):
    """Create a research-plan commitment for two *synthetic* pending attempts.

    Caller must independently retain the resulting family digest BEFORE
    observing or recording results. No holdout or research completion.
    """
    if not isinstance(plan, PilotPlan) or plan.digest != expected_plan_digest:
        raise ValueError("Pilot plan commitment mismatch")
    _digest(expected_data_digest)
    return commit_research_plan(
        FAMILY, [(name, version_digest(name)) for name in VERSIONS],
        protocol_digest=expected_plan_digest,
        dataset_digest=expected_data_digest,
        split_digest=digest({"scope": "500_SYNTHETIC_BARS_ONLY", "oos": "NOT_OPENED"}),
        metrics=["synthetic_path", "paired_costs"],
        selection_rule={"kind": "NO_SELECTION_SYNTHETIC_ONLY"},
        cost_model=COSTS,
        baseline_digest=digest({"baseline": "NO_PROFITABILITY_PROMOTION"}))


def _digest(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("SHA-256 commitment required")


def _check_result(result, *, plan, expected_plan_digest, expected_data_digest):
    if type(result) is not dict or result.get("schema") != "sf-breakout-pilot-result-1":
        raise ValueError("Breakout result contract required")
    if result.get("phase") != "SYNTHETIC_INTEGRATION_ONLY" or result.get("oos") != "NOT_OPENED":
        raise ValueError("Synthetic-only phase required")
    if result.get("paper") != "NOT_STARTED" or result.get("actual_fills") != "NOT_OBSERVED":
        raise ValueError("No PAPER or actual fills allowed")
    if result.get("plan_digest") != expected_plan_digest or result.get("data_digest") != expected_data_digest:
        raise ValueError("Frozen pilot/data commitment mismatch")
    if set(result) != {"schema", "phase", "plan_digest", "data_digest", "versions",
                       "actual_fills", "oos", "paper", "result_digest"}:
        raise ValueError("Unknown result fields")
    if type(result["versions"]) is not dict or set(result["versions"]) != set(VERSIONS):
        raise ValueError("Exactly BASE/SHADOW required")
    for name in VERSIONS:
        item = result["versions"][name]
        if type(item) is not dict or item.get("version") != "BREAKOUT_20_10_" + name + "_v1":
            raise ValueError("Wrong immutable version")
        if type(item.get("accounting")) is not dict or set(item["accounting"]) != set(COSTS):
            raise ValueError("Paired costs required")
    result_digest = result["result_digest"]
    _digest(result_digest)
    without_digest = {k: v for k, v in result.items() if k != "result_digest"}
    if digest(without_digest) != result_digest:
        raise ValueError("Result digest mismatch")
    return result_digest


def _evidence_rows(db):
    rows = db.execute("SELECT seq,evidence_id,payload,chain_hash,attempt_seq,attempt_hash "
                      "FROM synthetic_result_evidence ORDER BY seq LIMIT 101").fetchall()
    if len(rows) > 100:
        raise ValueError("Synthetic evidence exceeds bound")
    prior = ZERO
    seen = {}
    for pos, (seq, eid, raw, chain, attempt_seq, attempt_hash) in enumerate(rows, 1):
        data = json.loads(bytes(raw))
        if (seq != pos or len(raw) > 500000 or canonical(data) != bytes(raw)
                or type(data) is not dict
                or data.get("schema") != "sf-synthetic-evidence-1"
                or data.get("status") != "SYNTHETIC_INTEGRATION_RESULT_NOT_RESEARCH_COMPLETE"):
            raise ValueError("Corrupt synthetic evidence")
        if eid != _sha(b"AQL:SYNTHETIC-EVIDENCE:1\0" + canonical({
                "family_id": data.get("family_id"),
                "pilot_result_digest": data.get("pilot_result_digest")})):
            raise ValueError("Synthetic evidence identity mismatch")
        if chain != _sha(bytes.fromhex(prior) + bytes(raw)):
            raise ValueError("Synthetic evidence hash chain mismatch")
        _digest(attempt_hash)
        if data.get("attempt_checkpoint") != [attempt_seq, attempt_hash]:
            raise ValueError("Synthetic evidence attempt checkpoint mismatch")
        if eid in seen and seen[eid] != bytes(raw):
            raise ValueError("Conflicting synthetic evidence")
        seen[eid] = bytes(raw)
        prior = chain
    return rows, (len(rows), prior)


def record_synthetic_result(writer, *, raw_plan, expected_family_digest,
                            plan, expected_plan_digest, bars,
                            expected_data_digest, result):
    """Persist one synthetic result link only after two sealed PENDING attempts.

    Fail closed on changed plan/data, mismatched replay, tampered evidence or
    missing attempts. Replayed identical receipt is idempotent.
    """
    if not isinstance(writer, FrozenAttemptWriter) or not isinstance(writer.ledger, AttemptLedger):
        raise ValueError("Sealed Factory writer required")
    family = verify_research_plan(raw_plan, expected_family_digest)
    canonical_raw, expected = frozen_pilot_family(
        plan=plan, expected_plan_digest=expected_plan_digest,
        expected_data_digest=expected_data_digest)
    if expected != expected_family_digest or canonical_raw != raw_plan:
        raise ValueError("Wrong immutable synthetic family")
    if writer.family_id != FAMILY or writer.expected_digest != expected_family_digest:
        raise ValueError("Writer is not bound to frozen synthetic family")
    _check_result(result, plan=plan, expected_plan_digest=expected_plan_digest,
                  expected_data_digest=expected_data_digest)
    # Independently regenerate from supplied synthetic bars; digest matching
    # an untrusted user-supplied result alone cannot establish a valid run.
    replay = run_pilot(bars, plan=plan, expected_plan_digest=expected_plan_digest,
                       expected_data_digest=expected_data_digest)
    if canonical(replay) != canonical(result):
        raise ValueError("Synthetic replay/result mismatch")

    db = writer.ledger._connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        events, checkpoint = writer.ledger._read(db)
        stored = db.execute("SELECT plan_digest,plan_bytes FROM frozen_plan_policy WHERE id=1").fetchone()
        if stored is None or stored[0] != expected_family_digest or bytes(stored[1]) != raw_plan:
            raise ValueError("Ledger frozen plan changed")
        status = {v: None for v in VERSIONS}
        for event in events:
            if event["family_id"] == FAMILY and event["candidate_id"] in status:
                if event["state"] != "INPUTS":
                    status[event["candidate_id"]] = event["state"]
        if any(state != "PENDING" for state in status.values()):
            raise ValueError("Separate BASE/SHADOW pending attempts required")
        schema = db.execute("SELECT type FROM sqlite_master WHERE name='synthetic_result_evidence'").fetchone()
        if schema is not None and schema[0] != "table":
            raise ValueError("Incompatible synthetic evidence surface")
        if schema is None:
            db.execute("CREATE TABLE synthetic_result_evidence (seq INTEGER PRIMARY KEY, "
                       "evidence_id TEXT UNIQUE NOT NULL, payload BLOB NOT NULL, "
                       "chain_hash TEXT NOT NULL, attempt_seq INTEGER NOT NULL, "
                       "attempt_hash TEXT NOT NULL)")
        rows, head = _evidence_rows(db)
        data = {"schema": "sf-synthetic-evidence-1",
                "status": "SYNTHETIC_INTEGRATION_RESULT_NOT_RESEARCH_COMPLETE",
                "family_id": family["family_id"], "family_digest": expected_family_digest,
                "pilot_plan_digest": expected_plan_digest,
                "fixture_digest": expected_data_digest,
                "pilot_result_digest": result["result_digest"],
                "version_digests": {v: version_digest(v) for v in VERSIONS},
                "version_result_digests": {v: digest(result["versions"][v]) for v in VERSIONS},
                "costs_digest": digest(COSTS),
                "attempt_checkpoint": list(checkpoint),
                "custody": "NOT_INDEPENDENTLY_VERIFIED", "oos": "NOT_OPENED",
                "paper": "NOT_STARTED"}
        raw = canonical(data)
        eid = _sha(b"AQL:SYNTHETIC-EVIDENCE:1\0" + canonical({
            "family_id": FAMILY, "pilot_result_digest": result["result_digest"]}))
        for row in rows:
            if row[1] == eid:
                if bytes(row[2]) != raw:
                    raise ValueError("Conflicting synthetic result identity")
                db.execute("COMMIT")
                return (row[0], row[3]), data
        if len(rows) >= 100:
            raise ValueError("Synthetic evidence capacity exceeded")
        chain = _sha(bytes.fromhex(head[1]) + raw)
        db.execute("INSERT INTO synthetic_result_evidence VALUES(?,?,?,?,?,?)",
                   (head[0]+1, eid, raw, chain, checkpoint[0], checkpoint[1]))
        db.execute("COMMIT")
        return (head[0]+1, chain), data
    finally:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()


def read_synthetic_evidence(ledger, *, expected_evidence_checkpoint=None):
    """Verify bounded synthetic evidence chain plus linked main-ledger prefix."""
    if not isinstance(ledger, AttemptLedger):
        raise ValueError("Factory AttemptLedger required")
    db = ledger._connect()
    try:
        db.execute("BEGIN")
        events, current_checkpoint = ledger._read(db)
        exists = db.execute("SELECT type FROM sqlite_master "
                            "WHERE name='synthetic_result_evidence'").fetchone()
        if exists is None:
            if expected_evidence_checkpoint is not None:
                raise ValueError("Expected synthetic evidence is missing")
            return (), (0, ZERO)
        if exists[0] != "table":
            raise ValueError("Invalid synthetic evidence surface")
        rows, head = _evidence_rows(db)
        if expected_evidence_checkpoint is not None and head != expected_evidence_checkpoint:
            raise ValueError("External synthetic evidence anchor mismatch/rollback")
        all_main_rows = db.execute("SELECT seq,chain_hash FROM receipts ORDER BY seq").fetchall()
        anchors = dict(all_main_rows)
        anchors[0] = ZERO
        for row in rows:
            if anchors.get(row[4]) != row[5] or row[4] > current_checkpoint[0]:
                raise ValueError("Attempt ledger prefix missing/changed")
        return tuple(json.loads(bytes(row[2])) for row in rows), head
    finally:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()
