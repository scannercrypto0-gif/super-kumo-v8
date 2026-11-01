"""Read-only prospective F1 -> Factory signal handoff; never reconstruct P0 PIT.

Host handoff SHA is a local integrity check, NOT external source/freeze custody.
A structured original may be inspected as an explicitly unverified candidate;
direction/entry/TP/SL are NEVER exported as research-authorized when the
independent proof is missing or the host slot is not RECORDED.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .aql_f1_decision_capture_v1 import (
    ARMS, C2_FIELDS, CaptureError, digest, validate_f1,
)


SOURCE_PINS = (
    "experiment_plan_sha256", "source_version", "source_bytes_sha256",
    "correction_generation", "decision_cutoff_ms",
)


def _fail(message: str) -> None:
    raise CaptureError(message)


def project_original_signal_handoffs(
    scheduled: Sequence[Mapping[str, Any]],
    host_handoffs: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    indicator_registry: Mapping[str, str],
    *,
    independent_proof_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
) -> dict:
    """Return complete 2*N research-safe rows and exact Factory-shaped inputs.

    Caller must pass a separately authenticated verifier to consider a source
    proof. Merely passing a True callback is synthetic in controlled tests,
    never operational PIT authority. No historical F1 is manufactured here.
    """
    plans = {}
    seen_identities = set()
    for scheduled_row in scheduled:
        if not isinstance(scheduled_row, Mapping):
            _fail("SCHEDULE_NOT_MAPPING")
        try:
            identity = dict(scheduled_row["c2_identity"])
            if set(identity) != C2_FIELDS:
                _fail("C2_SCHEDULE_IDENTITY_FIELDS")
            pair = digest({
                "experiment_plan_sha256": scheduled_row["experiment_plan_sha256"],
                "c2_identity": identity,
            })
            if scheduled_row["pair_id"] != pair:
                _fail("SCHEDULE_PAIR_MISMATCH")
            for field in SOURCE_PINS:
                if scheduled_row[field] is None:
                    _fail("SCHEDULE_SOURCE_PIN_MISSING")
            identity_key = tuple(identity[key] for key in sorted(C2_FIELDS))
            if pair in plans or identity_key in seen_identities:
                _fail("DUPLICATE_SCHEDULE")
            plans[pair] = scheduled_row
            seen_identities.add(identity_key)
        except (KeyError, ValueError, TypeError) as exc:
            raise CaptureError("SCHEDULE_INVALID") from exc

    handoffs = {}
    for host in host_handoffs:
        if not isinstance(host, Mapping):
            _fail("HANDOFF_INVALID")
        data = dict(host)
        pair = data.get("pair_id")
        if pair not in plans or pair in handoffs:
            _fail("ORPHAN_OR_DUPLICATE_HANDOFF")
        if data.get("schema_version") != "aql.f1-prospective-host-handoff.v1":
            _fail("HOST_HANDOFF_SCHEMA")
        if data.get("handoff_sha256") != digest({
            key: value for key, value in data.items() if key != "handoff_sha256"
        }):
            _fail("HOST_HANDOFF_DIGEST")
        schedule = plans[pair]
        if data.get("c2_identity") != schedule["c2_identity"] or (
            data.get("experiment_plan_sha256") != schedule["experiment_plan_sha256"]
        ):
            _fail("HOST_HANDOFF_SCHEDULE_MISMATCH")
        slots = data.get("slots")
        if not isinstance(slots, list) or len(slots) != len(ARMS):
            _fail("HANDOFF_TWO_ARM_DENOMINATOR")
        if {r.get("arm") for r in slots if isinstance(r, dict)} != set(ARMS):
            _fail("HANDOFF_ARM_SET_INVALID")
        for slot in slots:
            if (slot.get("pair_id") != pair or
                slot.get("c2_identity") != schedule["c2_identity"] or
                slot.get("capture_status") not in (
                    "MISSING_CAPTURE", "UNVERIFIED", "QUARANTINED", "RECORDED"
                )):
                _fail("HANDOFF_SLOT_IDENTITY_OR_STATUS")
        handoffs[pair] = data
    if set(handoffs) != set(plans):
        _fail("MISSING_HOST_HANDOFF")

    originals = {}
    for item in candidates:
        if not isinstance(item, Mapping):
            _fail("INVALID_ORIGINAL_ROW")
        pair, arm = item.get("pair_id"), item.get("arm")
        if pair not in plans or arm not in ARMS:
            _fail("ORPHAN_ORIGINAL")
        key = (pair, arm)
        if key in originals:
            _fail("DUPLICATE_ORIGINAL")
        originals[key] = dict(item)

    rows = []
    for pair in sorted(plans):
        plan = plans[pair]
        host = handoffs[pair]
        slot_by_arm = {slot["arm"]: slot for slot in host["slots"]}
        for arm in ARMS:
            slot = slot_by_arm[arm]
            source = originals.get((pair, arm))
            status = slot["capture_status"]
            reason = slot["reason_code"]
            claimed = None
            valid = False
            if source is None:
                if status != "MISSING_CAPTURE" or slot["f1_record_sha256"] is not None:
                    _fail("MISSING_CAPTURE_SLOT_MISMATCH")
            else:
                try:
                    validate_f1(source, dict(indicator_registry))
                    valid = (
                        source["pair_id"] == pair and
                        source["arm"] == arm and
                        source["c2_identity"] == plan["c2_identity"] and
                        source["f1_record_sha256"] == slot["f1_record_sha256"]
                    )
                except (CaptureError, KeyError, TypeError, ValueError):
                    valid = False
                if not valid:
                    status, reason = "QUARANTINED", "INVALID_ORIGINAL_OR_HOST_BINDING"
                elif any(source.get(field) != plan.get(field) for field in SOURCE_PINS):
                    status, reason = "QUARANTINED", "PREREGISTERED_SOURCE_CUTOFF_MISMATCH"
                elif status == "MISSING_CAPTURE":
                    status, reason = "QUARANTINED", "HOST_MISSING_PRESENT_ORIGINAL"
                else:
                    # This is descriptive, untrusted candidate metadata only.
                    claimed = {
                        "signal_state": source["f1_signal_state"],
                        "direction": source["direction"],
                        "entry_reference_price": source["reference"]["price"],
                        "target_price": source["tp"]["level"],
                        "stop_price": source["sl"]["level"],
                    }

            # A host-local slot or self-hashed receipt is never independently
            # sufficient. Require BOTH host RECORDED and a fresh verifier.
            if status == "RECORDED":
                verified = False
                if valid and callable(independent_proof_verifier):
                    try:
                        verified = independent_proof_verifier(source) is True
                    except Exception:
                        verified = False
                if not verified:
                    status, reason = "UNVERIFIED", "INDEPENDENT_PROOF_UNCONFIRMED"

            authorized = source if valid and status == "RECORDED" else None
            rows.append({
                "pair_id": pair,
                "arm": arm,
                "c2_identity": dict(plan["c2_identity"]),
                "strategy_id": source["strategy_id"] if valid else None,
                "f1_record_sha256": slot["f1_record_sha256"] if valid else None,
                "capture_status": status,
                "reason_code": reason,
                "claimed_candidate_unverified": claimed if status != "RECORDED" else None,
                "research_signal_state": authorized["f1_signal_state"] if authorized else "UNKNOWN",
                "research_direction": authorized["direction"] if authorized else None,
                "research_entry_reference_price": authorized["reference"]["price"] if authorized else None,
                "research_target_price": authorized["tp"]["level"] if authorized else None,
                "research_stop_price": authorized["sl"]["level"] if authorized else None,
                "directional_outcomes_allowed": bool(
                    authorized and authorized["direction"] in ("LONG", "SHORT")
                    and authorized["predecision_eligibility"] == "YES"
                ),
            })
    result = {
        "schema_version": "aql.f1-research-signal-handoff.v1",
        "evidence_scope": "CONTROLLED_HOST_INTERFACE_NOT_OPERATIONAL_PIT",
        "original_vendor_clock_custody_freeze_anchor_proven": False,
        "scheduled_pairs": len(plans),
        "arm_denominator": len(rows),
        "signal_rows": rows,
    }
    result["handoff_sha256"] = digest(result)
    return result
