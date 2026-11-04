"""TEST_ONLY Factory research intake and descriptive report adapter.

Reuses frozen Core paired-schedule and Factory descriptive validator; does not
run a new evaluator, trade simulator, private source, or executable strategy.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json

from research_wp_r0.aql_p2_factory_lab import (
    LabContractError, build_lab, validate_schedule,
)

SCHEMA = "aql.factory.research-consumer-seam.v1"
REPORT_SCHEMA = "aql.factory.research-consumer-report.v1"
STATES = frozenset((
    "NO_SIGNAL", "REJECTED", "UNKNOWN", "NULL", "UNSCANNED",
    "UNRESOLVED", "NOMINATED",
))
HEX = frozenset("0123456789abcdef")
SOURCE_STATUS_MAP = {
    "NO_SIGNAL": frozenset(("NO_SIGNAL",)),
    "REJECTED": frozenset(("REJECTED",)),
    "UNKNOWN": frozenset(("UNKNOWN", "UNRESOLVED", "UNSCANNED")),
    "TRIGGERED": frozenset(("NOMINATED", "NULL", "UNKNOWN", "UNRESOLVED")),
}


def fail(reason):
    raise LabContractError("RESEARCH_SEAM_" + reason)


def digest(obj):
    return sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def hash_ok(value):
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def require(condition, reason):
    if not condition:
        fail(reason)


def seal(obj):
    """Return a detached TEST_ONLY input envelope with an immutable digest."""
    require(type(obj) is dict and "artifact_sha256" not in obj, "SEAL_SHAPE")
    result = dict(obj)
    result["artifact_sha256"] = digest(result)
    return result


def _validate_envelope(schedule, envelope, pairs):
    require(type(envelope) is dict and envelope.get("schema") == SCHEMA, "SCHEMA")
    require(
        envelope.get("test_only") is True
        and envelope.get("evidence_class") == "TEST_ONLY"
        and envelope.get("execution_status") == "NOT_OBSERVED"
        and envelope.get("trading_authority") == "NONE",
        "AUTHORITY",
    )
    pin = envelope.get("artifact_sha256")
    require(hash_ok(pin), "INPUT_RECEIPT_MISSING")
    require(digest({k: v for k, v in envelope.items()
                    if k != "artifact_sha256"}) == pin, "INPUT_RECEIPT_TAMPER")
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
        opp = pairs[key[0]]["opportunity"]
        require(row.get("opportunity_id") == opp["opportunity_id"], "OPPORTUNITY_ID")
        require(type(row.get("attempt_id")) is str and bool(row["attempt_id"]), "ATTEMPT_ID")
        require(row.get("cohort_id") == envelope["cohort_id"], "MIXED_COHORT")
        require(row.get("strategy_version") == envelope["strategy_version"], "MIXED_STRATEGY")
        require(row.get("source_manifest_sha256") == envelope["source_manifest_sha256"], "MIXED_MANIFEST")
        require(row.get("source_package_sha256") == envelope["source_package_sha256"], "MIXED_SOURCE")
        require(type(row.get("decision_cutoff_ms")) is int and
                row["decision_cutoff_ms"] == opp["decision_cutoff_ms"], "CUTOFF")
        require(type(row.get("feature_available_ms")) is int and
                0 <= row["feature_available_ms"] <= opp["decision_cutoff_ms"], "LATE_FEATURE")
        require(row.get("feature_availability_class") == "RETROSPECTIVE_NON_PIT",
                "AVAILABILITY_CLASS")
        require(hash_ok(row.get("feature_snapshot_sha256")), "FEATURE_SNAPSHOT")
        require(row.get("source_disposition") == opp["disposition"], "SOURCE_DISPOSITION")
        state = row.get("status")
        require(state in STATES and state in SOURCE_STATUS_MAP[opp["disposition"]],
                "STATUS_OR_UNAUTHORIZED_PROMOTION")
        require(row.get("descriptive_outcomes_4_24_72h") is None
                and row.get("modeled_trade") is None
                and row.get("execution_status") == "NOT_OBSERVED",
                "OUTCOME_OR_EXECUTION_AUTHORITY")
        require("return" in row and row["return"] is None, "NULL_TO_ZERO_OR_RETURN")
        actual[key] = row
    require(set(actual) == expected, "INCOMPLETE_DENOMINATOR")
    attempts = [(row["cohort_id"], row["attempt_id"]) for row in actual.values()]
    require(len(set(attempts)) == len(attempts), "DUPLICATE_ATTEMPT")
    return actual


def build_research_handoff(schedule, envelope):
    """Preserve every Core pair/arm and output an immutable, no-authority census.

    UNSCANNED only names a supplied Core UNKNOWN slot: external Scanner universe
    members not provided to the paired schedule remain NOT_CONNECTED.
    """
    pairs = validate_schedule(schedule)
    require(schedule["test_only"] is True, "TEST_ONLY_REQUIRED")
    actual = _validate_envelope(schedule, envelope, pairs)
    counts = Counter(row["status"] for row in actual.values())
    source_counts = Counter(p["opportunity"]["disposition"] for p in pairs.values())
    receipt = {
        "schema": "aql.factory.research-consumer-receipt.v1",
        "test_only": True, "evidence_class": "TEST_ONLY",
        "source_schedule_sha256": schedule["artifact_sha256"],
        "source_manifest_sha256": envelope["source_manifest_sha256"],
        "source_package_sha256": envelope["source_package_sha256"],
        "input_envelope_sha256": envelope["artifact_sha256"],
        "cohort_id": envelope["cohort_id"],
        "strategy_version": envelope["strategy_version"],
        "scheduled_pairs": len(pairs), "arm_slots": len(actual),
        "status_counts": {state: counts[state] for state in sorted(STATES)},
        "original_core_pair_dispositions": dict(sorted(source_counts.items())),
        "external_scanner_universe": "NOT_CONNECTED",
        "descriptive_4_24_72h": "NOT_EVALUATED",
        "modeled_trades": "NOT_EVALUATED", "execution_status": "NOT_OBSERVED",
        "pit_status": "NOT_ATTESTED", "oos_status": "NOT_ATTESTED",
        "holdout_status": "SEALED_UNOPENED", "trading_authority": "NONE",
    }
    require(sum(receipt["status_counts"].values()) == receipt["arm_slots"]
            == 2 * receipt["scheduled_pairs"], "CENSUS_CONSERVATION")
    receipt["artifact_sha256"] = digest(receipt)
    return receipt


def build_research_report(schedule, envelope, observations):
    """Actual existing Factory descriptive engine invocation; no trade engine.

    Input observations are pre-existing TEST_ONLY 4/24/72h coverage records.
    They cannot carry resolved directional outcomes or intrabar win/loss labels.
    """
    candidate = build_research_handoff(schedule, envelope)
    descriptive = build_lab(schedule, observations, test_only=True)
    require(descriptive["scheduled_opportunities"] == candidate["scheduled_pairs"]
            and descriptive["observation_slots"] == 3 * candidate["arm_slots"]
            and descriptive["source_schedule_sha256"] == candidate["source_schedule_sha256"],
            "DESCRIPTIVE_CENSUS_OR_SOURCE")
    report = {
        "schema": REPORT_SCHEMA,
        "test_only": True,
        "evidence_class": "TEST_ONLY_RETROSPECTIVE_NON_PIT",
        "source_schedule_sha256": candidate["source_schedule_sha256"],
        "source_manifest_sha256": candidate["source_manifest_sha256"],
        "input_envelope_sha256": candidate["input_envelope_sha256"],
        "research_consumer_receipt_sha256": candidate["artifact_sha256"],
        "factory_descriptive_receipt_sha256": descriptive["artifact_sha256"],
        "scheduled_pairs": candidate["scheduled_pairs"],
        "arm_slots": candidate["arm_slots"],
        "status_counts": candidate["status_counts"],
        "descriptive_observation_slots": descriptive["observation_slots"],
        "market_coverage_by_horizon": descriptive["market_coverage_by_horizon"],
        "ambiguous_intrabar": "UNKNOWN_NOT_RESOLVED",
        "modeled_trade_engine": "NOT_INVOKED",
        "fills_pnl_alpha": "NOT_COMPUTED",
        "scanner_universe": "NOT_CONNECTED",
        "execution_status": "NOT_OBSERVED",
        "pit_status": "NOT_ATTESTED", "oos_status": "NOT_ATTESTED",
        "holdout_status": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    }
    report["artifact_sha256"] = digest(report)
    return report
