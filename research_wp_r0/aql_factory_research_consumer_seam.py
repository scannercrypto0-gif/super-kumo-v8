"""TEST_ONLY read-only research handoff into existing Factory schedule validator.

No evaluation, trading, fills, PnL, PIT promotion, or private source access.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
import json
from research_wp_r0.aql_p2_factory_lab import validate_schedule, LabContractError

SCHEMA = "aql.factory.research-consumer-seam.v1"
STATES = frozenset(("NO_SIGNAL", "REJECTED", "UNKNOWN", "NULL", "UNSCANNED", "UNRESOLVED", "NOMINATED"))
HEX = frozenset("0123456789abcdef")

def fail(reason):
    raise LabContractError("RESEARCH_SEAM_" + reason)

def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def hash_ok(value):
    return type(value) is str and len(value) == 64 and set(value) <= HEX

def require(condition, reason):
    if not condition:
        fail(reason)

def build_research_handoff(schedule, envelope):
    """Validate frozen external nominations; emit a non-authoritative census receipt.

    Exact one row per scheduled pair and arm; unscanned and unresolved remain
    explicit rather than silently dropped. No inferred strategy outcomes.
    """
    pairs = validate_schedule(schedule)
    require(schedule["test_only"] is True, "TEST_ONLY_REQUIRED")
    require(type(envelope) is dict and envelope.get("schema") == SCHEMA, "SCHEMA")
    require(envelope.get("test_only") is True and envelope.get("execution_status") == "NOT_OBSERVED", "AUTHORITY")
    require(envelope.get("source_schedule_sha256") == schedule["artifact_sha256"], "SCHEDULE_SHA")
    require(envelope.get("source_package_sha256") == schedule["source"]["source_package_sha256"], "SOURCE_SHA")
    require(type(envelope.get("cohort_id")) is str and bool(envelope["cohort_id"]), "COHORT")
    require(type(envelope.get("strategy_version")) is str and bool(envelope["strategy_version"]), "STRATEGY")
    require(hash_ok(envelope.get("source_manifest_sha256")), "MANIFEST")
    require(type(envelope.get("rows")) is list, "ROWS")
    expected = {(pid, arm) for pid in pairs for arm in ("BASE", "SHADOW")}
    actual = {}
    for row in envelope["rows"]:
        require(type(row) is dict, "ROW")
        key = (row.get("pair_id"), row.get("arm"))
        require(key in expected and key not in actual, "DUPLICATE_OR_FOREIGN_SLOT")
        pair = pairs[key[0]]
        opp = pair["opportunity"]
        require(row.get("opportunity_id") == opp["opportunity_id"], "OPPORTUNITY_ID")
        require(type(row.get("attempt_id")) is str and bool(row["attempt_id"]), "ATTEMPT_ID")
        require(row.get("cohort_id") == envelope["cohort_id"], "MIXED_COHORT")
        require(row.get("strategy_version") == envelope["strategy_version"], "MIXED_STRATEGY")
        require(row.get("source_manifest_sha256") == envelope["source_manifest_sha256"], "MIXED_MANIFEST")
        require(row.get("source_package_sha256") == envelope["source_package_sha256"], "MIXED_SOURCE")
        require(row.get("decision_cutoff_ms") == opp["decision_cutoff_ms"], "CUTOFF")
        require(type(row.get("feature_available_ms")) is int and
                row["feature_available_ms"] <= opp["decision_cutoff_ms"], "LATE_FEATURE")
        require(hash_ok(row.get("feature_snapshot_sha256")), "FEATURE_SNAPSHOT")
        require(row.get("status") in STATES, "STATUS")
        require(row.get("descriptive_outcomes_4_24_72h") is None and
                row.get("modeled_trade") is None and row.get("execution_status") == "NOT_OBSERVED",
                "OUTCOME_OR_EXECUTION_AUTHORITY")
        require(row.get("return") is None, "NULL_TO_ZERO_OR_RETURN")
        actual[key] = row
    require(set(actual) == expected, "INCOMPLETE_DENOMINATOR")
    attempts = [(row["cohort_id"], row["attempt_id"]) for row in actual.values()]
    require(len(set(attempts)) == len(attempts), "DUPLICATE_ATTEMPT")
    counts = Counter(row["status"] for row in actual.values())
    report = {
        "schema": "aql.factory.research-consumer-receipt.v1",
        "test_only": True, "evidence_class": "TEST_ONLY",
        "source_schedule_sha256": schedule["artifact_sha256"],
        "source_manifest_sha256": envelope["source_manifest_sha256"],
        "source_package_sha256": envelope["source_package_sha256"],
        "cohort_id": envelope["cohort_id"], "strategy_version": envelope["strategy_version"],
        "scheduled_pairs": len(pairs), "arm_slots": len(expected),
        "status_counts": {state: counts[state] for state in sorted(STATES)},
        "descriptive_4_24_72h": "NOT_EVALUATED",
        "modeled_trades": "NOT_EVALUATED", "execution_status": "NOT_OBSERVED",
        "pit_status": "NOT_ATTESTED", "oos_status": "NOT_ATTESTED",
        "holdout_status": "SEALED_UNOPENED", "trading_authority": "NONE",
    }
    report["artifact_sha256"] = digest(report)
    return report
