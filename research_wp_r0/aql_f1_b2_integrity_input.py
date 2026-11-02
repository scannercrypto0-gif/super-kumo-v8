"""Deterministic TEST_ONLY Core B2 integrity input contract for Factory.

This is a *test instrument*, not original 2024 strategy observations, an
operational PIT attestation, a real source/custody receipt, or an alpha test.
No historical P0 F1 reconstruction and no live F3 entrypoint.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from .aql_f1_decision_capture_v1 import ARMS, CaptureError, digest, hash_f1, validate_f1
from .aql_f1_research_signal_handoff_v1 import project_original_signal_handoffs

HORIZONS_MS = (14_400_000, 86_400_000, 259_200_000)
STRATEGY_ID = "SF_BREAKOUT_BASE_20_10_DEV_v1"
STRATEGY_VERSION = "TEST_ONLY_1"
TEST_ORIGIN = "SYNTHETIC_DETERMINISTIC_NOT_HISTORICAL_2024"
CORE_INTERFACE = "aql.f1-decision-capture.v1"
FACTORY_INTERFACE = "project_core_verified_f1_slots"
VAULT_INTERFACE = "RawVault.admit/readback (not called by Core B2)"
F3_PRODUCTION_INTERFACE = "NOT_CONNECTED"

def _invalid(reason: str) -> None:
    raise CaptureError(reason)

def make_b2_test_records() -> tuple[list[dict], list[dict], dict[str, str]]:
    """Build two fixed pair IDs, two arms per pair, one directional TEST candidate.

    Only F1 schema-valid synthetic candidate rows; the host and consumer are
    exercised separately, so this function never writes to a real journal.
    """
    # Test builders are explicit fixture dependencies. Production code cannot
    # consume this module as evidence or as an original strategy producer.
    from tests.test_aql_f1_decision_capture_v1 import fixture

    scheduled, candidates = [], []
    registry = None
    for number in (1, 2):
        base, current_registry = fixture(
            "BASE", state="ARMED" if number == 1 else "NO_SIGNAL",
            direction="LONG" if number == 1 else None,
            eligible="YES" if number == 1 else "NOT_ESTABLISHED",
        )
        shadow, _ = fixture("SHADOW")
        registry = current_registry
        for rec in (base, shadow):
            rec["strategy_id"] = STRATEGY_ID
            rec["arm_strategy_version"] = STRATEGY_VERSION
            rec["opportunity_id"] = f"B2-TEST-OPPORTUNITY-{number:02d}"
            rec["producer_event_id"] = f"B2-TEST-EVENT-{number:02d}"
            rec["c2_identity"] = {
                key: rec[key] for key in (
                    "trial_id", "opportunity_id", "producer_event_id",
                    "envelope_sha256",
                )
            }
            rec["pair_id"] = digest({
                "experiment_plan_sha256": rec["experiment_plan_sha256"],
                "c2_identity": rec["c2_identity"],
            })
            rec["f1_record_sha256"] = hash_f1(rec)
            validate_f1(rec, current_registry)
        if number == 1:
            for key, level in (("tp", "110"), ("sl", "90")):
                base[key] = {
                    "status": "DEFINED_PREDECISION", "level": level,
                    "unit": "USDT", "basis": "ABSOLUTE",
                    "reference_price_kind": "bar-close",
                    "defined_at_ms": base["decision_cutoff_ms"],
                    "tick_size": "0.01", "decimal_scale": 2,
                    "rounding_mode": "HALF_EVEN",
                }
            base["f1_record_sha256"] = hash_f1(base)
            validate_f1(base, current_registry)
        scheduled.append({
            "pair_id": base["pair_id"],
            "c2_identity": copy.deepcopy(base["c2_identity"]),
            "experiment_plan_sha256": base["experiment_plan_sha256"],
            "decision_cutoff_ms": base["decision_cutoff_ms"],
            "source_id": base["source_id"],
            "source_version": base["source_version"],
            "source_bytes_sha256": base["source_bytes_sha256"],
            "correction_generation": base["correction_generation"],
            "run_manifest_sha256": base["run_manifest_sha256"],
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "test_origin": TEST_ORIGIN,
        })
        candidates.extend((base, shadow))
    return scheduled, candidates, registry or {}

def factory_schedules(scheduled: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Drop only test-exclusive metadata; keep the exact Factory pin fields."""
    keys = (
        "pair_id", "c2_identity", "experiment_plan_sha256",
        "decision_cutoff_ms", "source_version",
        "source_bytes_sha256", "correction_generation",
    )
    return [{key: copy.deepcopy(s[key]) for key in keys} for s in scheduled]

def make_b2_evidence_contract(
    schedules: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    handoffs: Sequence[Mapping[str, Any]],
    registry: Mapping[str, str],
) -> dict:
    """Enforce total N/2N/6N denominator before Factory handoff."""
    plans = list(schedules)
    originals = list(candidates)
    handoffs = list(handoffs)
    if len(plans) != 2 or len(originals) > 2 * len(plans):
        _invalid("B2_SCHEDULE_OR_CAPTURE_DENOMINATOR")
    identity_keys = {tuple(sorted(row["c2_identity"].items())) for row in plans}
    if len(identity_keys) != len(plans):
        _invalid("B2_DUPLICATE_OPPORTUNITY")
    projection = project_original_signal_handoffs(
        factory_schedules(plans), handoffs, originals, registry)
    if (projection["scheduled_pairs"] != len(plans)
            or projection["arm_denominator"] != 2 * len(plans)):
        _invalid("B2_ARM_DENOMINATOR")
    rows = projection["signal_rows"]
    expected_keys = {
        (plan["pair_id"], arm) for plan in plans for arm in ARMS
    }
    if len(rows) != len(expected_keys) or {
        (row["pair_id"], row["arm"]) for row in rows
    } != expected_keys:
        _invalid("B2_ARM_IDENTITY_LOSS")
    if any(row["capture_status"] == "RECORDED" or
           row["directional_outcomes_allowed"] or
           row["research_direction"] is not None for row in rows):
        _invalid("B2_UNAUTHENTICATED_PIT_PROMOTION")
    contract = {
        "schema_version": "aql.b2-core-factory-integrity-input.v1",
        "evidence_class": "TEST_ONLY_CONTROLLED_SYSTEM_INPUT",
        "original_2024_strategy_decisions_supplied": False,
        "original_pit_verified": False,
        "live_f3_connected": False,
        "n": len(plans),
        "expected_2n": 2 * len(plans),
        "expected_6n": len(plans) * len(ARMS) * len(HORIZONS_MS),
        "horizons_ms": list(HORIZONS_MS),
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "schedule": plans,
        "original_candidates_test_only": originals,
        "indicator_registry": dict(registry),
        "host_handoffs": handoffs,
        "core_projection": projection,
        "interface_map": {
            "opportunity_to_f1": CORE_INTERFACE,
            "f1_capture_to_host": "run_prospective_host(PROSPECTIVE_CAPTURE)",
            "host_to_factory": FACTORY_INTERFACE,
            "original_parent_to_vault": VAULT_INTERFACE,
            "real_producer_f3": F3_PRODUCTION_INTERFACE,
            "market_2024_factory_sha": "54316200aa6887cf8f4e7e752c469361fc250aea",
            "note": "Factory independently joins real 2024 MARKET_ONLY input; Core never claims candidate PIT",
        },
        "expected_statuses": {
            "BASE": "UNVERIFIED",
            "SHADOW": "UNVERIFIED",
            "missing_arm": "MISSING_CAPTURE",
            "invalid_or_conflicting": "QUARANTINED",
            "late_original": "REJECT",
            "no_independent_source_clock": "UNVERIFIED",
            "no_approved_market_custody": "BLOCKED_EXTERNAL_EVIDENCE",
        },
    }
    contract["contract_sha256"] = digest(contract)
    return contract
