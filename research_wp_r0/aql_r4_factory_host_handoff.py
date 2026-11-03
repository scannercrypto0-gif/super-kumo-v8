"""Factory R4 strict boundary for Core call-time fixture-only host handoff.

This module NEVER promotes a host invocation to an original G2/F1 event.
"""
from __future__ import annotations

from .aql_r3_factory_event_outcome_consumer import (
    ARMS, C2_FIELDS, PINS, digest, ishash, need, project_r3, read_json, text, timestamp,
)

SCHEDULE_SCHEMA = "aql.r4-predecision-schedule.v1"
RESULT_SCHEMA = "aql.r4-nontrading-evaluation-host.v1"
RESEARCH_SCHEMA = "aql.r3-breakout-closed-prefix-evaluation.v1"
REQUIRED_SCHEDULE = set(("schema_version", "c2_identity", "pair_id",
    "experiment_plan_sha256", "decision_cutoff_ms", "scheduled_at_ms",
    "availability_mode", "arms", "source_available_at_ms",
    "scheduled_source_proof", "schedule_sha256")) | set(PINS)


def consume_r4_host(schedule: dict, result: dict, *, asof_ms: int) -> dict:
    """Validate real Core R4 files, retain them outside genuine opportunity counts."""
    need(type(schedule) is dict and set(schedule) == REQUIRED_SCHEDULE, "R4_SCHEDULE_FIELDS")
    need(schedule["schema_version"] == SCHEDULE_SCHEMA, "R4_SCHEDULE_SCHEMA")
    c2 = schedule["c2_identity"]
    need(type(c2) is dict and set(c2) == set(C2_FIELDS), "R4_C2_IDENTITY")
    need(all(text(c2[k]) for k in C2_FIELDS[:-1]) and
         ishash(c2["envelope_sha256"]), "R4_C2_PIN")
    need(ishash(schedule["experiment_plan_sha256"]), "R4_PLAN_SHA")
    pair = digest({"experiment_plan_sha256": schedule["experiment_plan_sha256"],
                   "c2_identity": c2})
    need(schedule["pair_id"] == pair, "R4_PAIR_DRIFT")
    need(schedule["schedule_sha256"] ==
         digest({k: v for k, v in schedule.items() if k != "schedule_sha256"}),
         "R4_SCHEDULE_SHA_DRIFT")
    for key in PINS:
        need(ishash(schedule[key]) if key.endswith("sha256") else text(schedule[key]),
             "R4_PIN_INVALID")
    cutoff, scheduled = schedule["decision_cutoff_ms"], schedule["scheduled_at_ms"]
    need(timestamp(cutoff) and cutoff > 0 and cutoff % 900000 == 0 and
         timestamp(scheduled) and scheduled < cutoff, "R4_SCHEDULE_CLOCK")
    need(schedule["availability_mode"] == "RETROSPECTIVE_NON_PIT" and
         schedule["scheduled_source_proof"] == "UNVERIFIED_LOCAL_INPUT",
         "R4_UNSUPPORTED_PROSPECTIVE_CLAIM")
    source_at = schedule["source_available_at_ms"]
    need(source_at is None or (timestamp(source_at) and source_at <= cutoff),
         "R4_SOURCE_LATE")
    arms = schedule["arms"]
    need(type(arms) is list and len(arms) == 2 and
         {a.get("arm") for a in arms if type(a) is dict} == set(ARMS) and
         all(type(a) is dict and a.get("capture_status") == "MISSING_CAPTURE"
             for a in arms), "R4_ARMS_NOT_MISSING")

    need(type(result) is dict and result.get("schema_version") == RESULT_SCHEMA,
         "R4_RESULT_SCHEMA")
    need(result.get("result_sha256") ==
         digest({k: v for k, v in result.items() if k != "result_sha256"}),
         "R4_RESULT_SHA_DRIFT")
    need(result.get("pair_id") == pair and result.get("c2_identity") == c2 and
         result.get("schedule_sha256") == schedule["schedule_sha256"],
         "R4_RESULT_SCHEDULE_MISMATCH")
    need(result.get("availability_mode") == schedule["availability_mode"] and
         result.get("source_available_at_ms") == source_at,
         "R4_RESULT_CLOCK_MISMATCH")
    need(result.get("runtime_invocation") == "CALLED_NOW_IN_THIS_HOST" and
         result.get("runtime_evaluation_status") == "COMPLETED_LOCAL_NONTRADING" and
         result.get("original_g2_event_status") == "NOT_CONNECTED" and
         result.get("proof_status") == "BLOCKED_EXTERNAL_EVIDENCE" and
         result.get("f3_monitor_status") == "NOT_CONNECTED" and
         result.get("trade_execution") == "DISABLED" and
         result.get("historical_replay_is_original_proof") is False,
         "R4_FORGED_ORIGINAL")
    need(result.get("original_f1_capture_status") ==
         "BLOCKED_ON_ORIGINAL_F1_RECORD_AND_INDEPENDENT_EVIDENCE" and
         type(result.get("original_f1_missing_fields")) is list,
         "R4_FORGED_F1")
    statuses = result.get("arm_statuses")
    decisions = result.get("decision_status_by_arm")
    evaluation = result.get("evaluation")
    need(type(statuses) is dict and set(statuses) == set(ARMS) and
         all(statuses[a] == "MISSING_CAPTURE" for a in ARMS),
         "R4_ARM_CAPTURE_FORGED")
    need(type(decisions) is dict and set(decisions) == set(ARMS) and
         type(evaluation) is dict and
         evaluation.get("schema_version") == RESEARCH_SCHEMA and
         evaluation.get("original_g2_event_status") == "NOT_CONNECTED" and
         evaluation.get("pre_f3_capture_status") == "NOT_CONNECTED" and
         evaluation.get("f3_monitor_status") == "NOT_CONNECTED" and
         evaluation.get("proof_status") == "BLOCKED_EXTERNAL_EVIDENCE" and
         evaluation.get("execution") == "DISABLED" and
         evaluation.get("direction") is None and
         evaluation.get("breakout_signal_state") in ("ARMED", "NO_SIGNAL") and
         all(decisions[a] == evaluation["breakout_signal_state"] for a in ARMS),
         "R4_DECISION_FORGED")
    need(evaluation.get("decision_cutoff_ms") == cutoff and
         all(evaluation.get(k) == schedule[k] for k in
             ("source_id", "source_version", "correction_generation",
              "strategy_id", "strategy_version")) and
         ishash(evaluation.get("prefix_sha256")), "R4_EVALUATION_PIN_DRIFT")

    # A research fixture MUST NOT enter R3's genuine N/2N/6N denominator.
    bounded = project_r3([], asof_ms=asof_ms)
    need(bounded["scheduled_opportunities"] == 0 and
         bounded["arm_slots"] == 0 and bounded["horizon_rows"] == 0,
         "R4_DENOMINATOR_CONTAMINATION")
    return {"schema_version": "aql.r4-factory-fixture-handoff.v1",
            "software_handoff_status": "SOFTWARE_HANDOFF_ACCEPTED",
            "genuine_original_event_status": "BLOCKED_ON_REAL_G2_EVENT",
            "external_proof_status": "BLOCKED_EXTERNAL_EVIDENCE",
            "f3_monitor_status": "NOT_CONNECTED",
            "fixture_pair_id": pair,
            "fixture_schedule_sha256": schedule["schedule_sha256"],
            "fixture_result_sha256": result["result_sha256"],
            "scheduled_opportunities": 0, "arm_slots": 0, "horizon_rows": 0,
            "trade_execution": "DISABLED", "g0_merge_authorized": False}


def consume_r4_json(schedule_bytes: bytes, result_bytes: bytes, *, asof_ms: int) -> dict:
    return consume_r4_host(read_json(schedule_bytes), read_json(result_bytes),
                           asof_ms=asof_ms)
