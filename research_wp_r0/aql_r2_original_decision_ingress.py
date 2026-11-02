"""R2 offline original-decision ingress. No producer, clock or F3 is activated here.

A genuine G2 caller must inject an event obtained during its decision lifecycle.
This adapter never manufactures a decision from historical market data.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .aql_f1_decision_capture_v1 import ARMS, CaptureError, digest
from .aql_f1_prospective_host_v1 import run_prospective_host

DECISIONS = ("NO_SIGNAL", "REJECTED", "TRIGGERED")
REQUIRED = frozenset((
    "opportunity_id", "arm", "decision_status", "strategy_id",
    "strategy_version", "decision_ms", "decision_cutoff_ms",
    "source_id", "source_version", "correction_generation",
    "feature_snapshot_sha256", "regime_snapshot_sha256",
    "original_f1_record",
))


def capture_original_g2_pair(
    *, c2: Mapping[str, Any], plan_sha: str,
    producer: Callable[[str, Mapping[str, Any]], Mapping[str, Any] | None] | None,
    registry: Mapping[str, str], journal_dir: Any,
    pre_f3_gate: Callable[[Mapping[str, Any]], bool],
    **proof_kwargs: Any,
) -> dict:
    """Fail closed if a real producer is absent; preserve both scheduled arms.

    Producer must be invoked by the genuine prospective G2 host, before F3.
    Local persistence is not independent issuer/clock/source/custody proof.
    """
    if c2.get("availability_mode") != "PROSPECTIVE_CAPTURE":
        raise CaptureError("R2_PROSPECTIVE_ONLY")
    if producer is None:
        return {
            "schema_version": "aql.r2-original-decision-ingress.v1",
            "connection_status": "NOT_CONNECTED",
            "proof_status": "BLOCKED_EXTERNAL_EVIDENCE",
            "reason_code": "ORIGINAL_G2_PRODUCER_NOT_CONNECTED",
            "opportunity_id": c2.get("opportunity_id"),
            "arm_statuses": {arm: "MISSING_CAPTURE" for arm in ARMS},
        }
    if not callable(producer) or not callable(pre_f3_gate):
        raise CaptureError("R2_PRODUCER_OR_GATE_INVALID")
    # Check before invoking any producer: never obtain a decision after F3.
    if pre_f3_gate(c2) is not True:
        raise CaptureError("R2_PRE_F3_GATE_DENIED")
    records = {}
    event_ids = set()
    strategy_versions = set()
    for arm in ARMS:
        event = producer(arm, c2)
        if event is None:
            records[arm] = None
            continue
        if not isinstance(event, Mapping) or set(event) != REQUIRED:
            raise CaptureError("R2_ORIGINAL_EVENT_FIELDS")
        if event["arm"] != arm or event["opportunity_id"] != c2.get("opportunity_id"):
            raise CaptureError("R2_OPPORTUNITY_ARM_MISMATCH")
        if event["decision_status"] not in DECISIONS:
            raise CaptureError("R2_DECISION_STATUS_INVALID")
        if event["decision_cutoff_ms"] != c2.get("decision_cutoff_ms"):
            raise CaptureError("R2_CUTOFF_MISMATCH")
        if type(event["decision_ms"]) is not int or event["decision_ms"] < event["decision_cutoff_ms"]:
            raise CaptureError("R2_CLOCK_REVERSAL")
        if any(not isinstance(event[k], str) or not event[k] for k in (
            "strategy_id", "strategy_version", "source_id",
            "source_version", "correction_generation")):
            raise CaptureError("R2_VERSION_IDENTITY_MISSING")
        if any(not isinstance(event[k], str) or len(event[k]) != 64 or
               any(ch not in "0123456789abcdef" for ch in event[k])
               for k in ("feature_snapshot_sha256", "regime_snapshot_sha256")):
            raise CaptureError("R2_SNAPSHOT_HASH_INVALID")
        record = event["original_f1_record"]
        if not isinstance(record, Mapping):
            raise CaptureError("R2_ORIGINAL_F1_MISSING")
        if any(record.get(k) != event[v] for k, v in (
            ("strategy_id", "strategy_id"),
            ("arm_strategy_version", "strategy_version"),
            ("decision_ms", "decision_ms"),
            ("decision_cutoff_ms", "decision_cutoff_ms"),
            ("source_id", "source_id"),
            ("source_version", "source_version"),
            ("correction_generation", "correction_generation"))):
            raise CaptureError("R2_EVENT_F1_PROVENANCE_MISMATCH")
        if record.get("source_available_at_ms", 2**63) > event["decision_cutoff_ms"]:
            raise CaptureError("R2_LATE_SOURCE")
        if event["decision_status"] == "TRIGGERED" and record.get("direction") not in ("LONG", "SHORT"):
            raise CaptureError("R2_TRIGGER_WITHOUT_ORIGINAL_DIRECTION")
        if event["decision_status"] != "TRIGGERED" and record.get("direction") is not None:
            raise CaptureError("R2_DIRECTION_WITHOUT_TRIGGER")
        if event["decision_status"] == "NO_SIGNAL" and record.get("f1_signal_state") != "NO_SIGNAL":
            raise CaptureError("R2_NO_SIGNAL_F1_MISMATCH")
        event_id = record.get("arm_event_id")
        if not isinstance(event_id, str) or not event_id or event_id in event_ids:
            raise CaptureError("R2_DUPLICATE_OR_MISSING_EVENT_ID")
        event_ids.add(event_id)
        strategy_versions.add((event["strategy_id"], event["strategy_version"]))
        records[arm] = dict(record)
    if len(strategy_versions) > 1:
        raise CaptureError("R2_CROSS_ARM_STRATEGY_VERSION_DRIFT")
    if pre_f3_gate(c2) is not True:
        raise CaptureError("R2_PRE_F3_GATE_DENIED")
    handoff = run_prospective_host(
        c2, plan_sha, records, registry, journal_dir,
        pre_f3_gate=pre_f3_gate, **proof_kwargs,
    )
    # Never interpret a locally valid event as an independent PIT witness.
    return {
        "schema_version": "aql.r2-original-decision-ingress.v1",
        "connection_status": "ORIGINAL_EVENTS_RECEIVED",
        "proof_status": "BLOCKED_EXTERNAL_EVIDENCE"
        if any(row["capture_status"] != "RECORDED" for row in handoff["slots"])
        else "INDEPENDENT_PROOF_REPORTED_BY_HOST",
        "opportunity_id": c2["opportunity_id"],
        "arm_statuses": {row["arm"]: row["capture_status"] for row in handoff["slots"]},
        "handoff_sha256": handoff["handoff_sha256"],
        "pair_id": handoff["pair_id"],
    }
