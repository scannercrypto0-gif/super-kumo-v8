"""P2 Factory real-development readiness gate and paired outcome consumer.

No source fetch, opportunity generation, signal policy, execution simulator or OOS.
Requires externally frozen real preregistration, real Core schedule and source-backed
15m windows. Market excursions are retrospective NON_PIT; costs are MODEL_ONLY.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from research_wp_r0.aql_p2_factory_lab import (
    HORIZONS, LabContractError, build_lab, digest, hash_ok, validate_schedule,
)

BAR_MS = 900_000
REQUIRED_PROTOCOL = "aql.p2.core.paired-schedule.v1"
REQUIRED_PREREG = "aql.p2.breakout.preregistration.v1"


def fail(code):
    raise LabContractError(code)


def dec(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        fail("BAD_DECIMAL")
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail("BAD_DECIMAL")
    if not out.is_finite():
        fail("NONFINITE_DECIMAL")
    return out


def seal_hash(obj):
    return digest({k: v for k, v in obj.items() if k != "artifact_sha256"})


def validate_prereg(schedule, prereg, cost_model):
    """Fail closed until an independent frozen, source-specific protocol exists."""
    validate_schedule(schedule)
    if schedule.get("test_only") is not False:
        fail("REAL_SOURCE_SCHEDULE_REQUIRED")
    if not isinstance(prereg, dict) or prereg.get("schema") != REQUIRED_PREREG:
        fail("MISSING_FROZEN_BREAKOUT_PREREG")
    if not hash_ok(prereg.get("artifact_sha256")) or seal_hash(prereg) != prereg["artifact_sha256"]:
        fail("UNSEALED_PREREG")
    protocol = schedule["protocol"]
    if (prereg.get("trial_id") != protocol["trial_id"] or
        prereg.get("protocol_sha256") != protocol["protocol_sha256"] or
        prereg.get("hypothesis_sha256") != protocol["hypothesis_sha256"] or
        prereg.get("preregistration_sha256") != protocol["preregistration_sha256"] or
        prereg.get("base_definition_sha256") != protocol["base_definition_sha256"] or
        prereg.get("shadow_definition_sha256") != protocol["shadow_definition_sha256"]):
        fail("PREREG_CORE_PROTOCOL_MISMATCH")
    if prereg.get("strategy_family") != "BREAKOUT" or prereg.get("horizons_hours") != list(HORIZONS):
        fail("UNSUPPORTED_OR_UNFROZEN_OUTCOME_RULE")
    if prereg.get("outcome_rule") != "CUTOFF_REFERENCE_TO_4_24_72H_CLOSE_AND_EXCURSIONS_V1":
        fail("UNFROZEN_OUTCOME_RULE")
    if prereg.get("source_package_sha256") != schedule["source"]["source_package_sha256"]:
        fail("PREREG_SOURCE_MISMATCH")
    if prereg.get("holdout_status") != "SEALED_UNOPENED":
        fail("HOLDOUT_OPEN")
    if not isinstance(cost_model, dict) or not hash_ok(cost_model.get("artifact_sha256")):
        fail("MISSING_MODELED_COSTS")
    if seal_hash(cost_model) != cost_model["artifact_sha256"]:
        fail("UNSEALED_COST_MODEL")
    if (cost_model.get("schema") != "aql.p2.factory.modeled-costs.v1" or
        cost_model.get("model_kind") != "MODEL_ONLY_NOT_EXECUTION" or
        cost_model.get("trial_id") != protocol["trial_id"] or
        cost_model.get("preregistration_sha256") != prereg["artifact_sha256"]):
        fail("COST_PROTOCOL_MISMATCH")
    fee, slip = dec(cost_model.get("round_trip_fee_bps")), dec(cost_model.get("round_trip_slippage_bps"))
    if not (0 <= fee <= 10000 and 0 <= slip <= 10000):
        fail("BAD_MODELED_COST")
    return fee + slip


def prepare_real_development(schedule, prereg, cost_model, windows, arm_decisions):
    """Produce strictly source-backed descriptive paired outcomes.

    windows: list of {pair_id, horizon_hours, source_package_sha256,
      reference_price, reference_bar_close_ms, bars:[{open_ms,close_ms,
      content_sha256, high,low,close}]}. One window per pair/horizon.
    arm_decisions: list of {pair_id,arm,policy_sha256,direction,
      decision_evidence_sha256}. Direction LONG/SHORT/NONE is a new
      explicitly sourced research decision, not an original venue fill.
    """
    original = deepcopy(schedule)
    cost_bps = validate_prereg(schedule, prereg, cost_model)
    pairs = validate_schedule(schedule)
    if not pairs or not isinstance(windows, list) or not isinstance(arm_decisions, list):
        fail("MISSING_REAL_INPUTS")
    expected_windows = {(pid, h) for pid in pairs for h in HORIZONS}
    seen_windows = {}
    for win in windows:
        if not isinstance(win, dict):
            fail("BAD_WINDOW")
        key = (win.get("pair_id"), win.get("horizon_hours"))
        if key not in expected_windows or key in seen_windows:
            fail("DUPLICATE_OR_UNKNOWN_WINDOW")
        if win.get("source_package_sha256") != schedule["source"]["source_package_sha256"]:
            fail("WINDOW_SOURCE_MISMATCH")
        if not hash_ok(win.get("source_window_sha256")) or seal_hash(win) != win["source_window_sha256"]:
            fail("WINDOW_DIGEST_MISMATCH")
        seen_windows[key] = win
    if set(seen_windows) != expected_windows:
        fail("INCOMPLETE_WINDOW_DENOMINATOR")
    expected_arms = {(pid, arm) for pid in pairs for arm in ("BASE", "SHADOW")}
    seen_arms = {}
    for decision in arm_decisions:
        if not isinstance(decision, dict):
            fail("BAD_ARM_DECISION")
        key = (decision.get("pair_id"), decision.get("arm"))
        if key not in expected_arms or key in seen_arms:
            fail("DUPLICATE_OR_UNKNOWN_ARM_DECISION")
        pair = pairs[key[0]]
        required_policy = next(a["definition_sha256"] for a in pair["arms"] if a["arm"] == key[1])
        if decision.get("policy_sha256") != required_policy:
            fail("ARM_POLICY_MISMATCH")
        direction = decision.get("direction")
        if direction not in ("LONG", "SHORT", None):
            fail("BAD_ARM_DIRECTION")
        if not hash_ok(decision.get("decision_evidence_sha256")):
            fail("UNVERIFIED_ARM_DECISION")
        if not hash_ok(decision.get("decision_sha256")) or seal_hash(decision) != decision["decision_sha256"]:
            fail("ARM_DECISION_DIGEST_MISMATCH")
        if decision.get("decision_cutoff_ms") != pair["opportunity"]["decision_cutoff_ms"]:
            fail("ARM_DECISION_TIME_MISMATCH")
        seen_arms[key] = decision
    if set(seen_arms) != expected_arms:
        fail("INCOMPLETE_ARM_DECISIONS")

    observations, outcomes = [], []
    for pid, pair in pairs.items():
        cutoff = pair["opportunity"]["decision_cutoff_ms"]
        for horizon in HORIZONS:
            win = seen_windows[(pid, horizon)]
            bars = win.get("bars")
            if not isinstance(bars, list):
                fail("MISSING_SOURCE_BARS")
            if win.get("reference_bar_close_ms") != cutoff - 1:
                fail("REFERENCE_TIME_MISMATCH")
            reference = dec(win.get("reference_price"))
            if reference <= 0:
                fail("BAD_REFERENCE")
            if len(bars) > horizon * 4:
                fail("TOO_MANY_WINDOW_BARS")
            highs, lows, closes = [], [], []
            for i, bar in enumerate(bars):
                if not isinstance(bar, dict) or not hash_ok(bar.get("content_sha256")):
                    fail("UNPINNED_BAR")
                if (bar.get("open_ms") != cutoff + i * BAR_MS or
                    bar.get("close_ms") != cutoff + (i + 1) * BAR_MS - 1):
                    fail("NONCONTIGUOUS_OR_LOOKAHEAD_BAR")
                high, low, close = (dec(bar.get(k)) for k in ("high", "low", "close"))
                if low <= 0 or not low <= close <= high:
                    fail("INVALID_OHLC")
                highs.append(high); lows.append(low); closes.append(close)
            status = win.get("availability")
            reason = win.get("availability_reason")
            if status == "COMPLETE":
                if len(bars) != horizon * 4 or reason is not None:
                    fail("FALSE_COMPLETE_WINDOW")
            elif status in ("CENSORED", "UNKNOWN"):
                if not isinstance(reason, str) or not reason.strip() or len(bars) == horizon * 4:
                    fail("UNVERIFIED_MISSINGNESS")
            else:
                fail("BAD_AVAILABILITY")
            metrics = None
            if status == "COMPLETE":
                metrics = {"reference_price": float(reference),
                           "observed_high": float(max(highs)),
                           "observed_low": float(min(lows))}
            for arm in ("BASE", "SHADOW"):
                decision = seen_arms[(pid, arm)]
                observations.append({
                    "pair_id": pid, "arm": arm, "horizon_hours": horizon,
                    "availability": status, "availability_reason": reason,
                    "market_metrics": metrics, "directional_metrics": None,
                    "execution_status": "NOT_OBSERVED",
                })
                direction = decision["direction"]
                gross, modeled_net, mfe, mae = None, None, None, None
                if status == "COMPLETE" and direction is not None:
                    sign = Decimal(1) if direction == "LONG" else Decimal(-1)
                    gross = sign * (closes[-1] / reference - 1)
                    modeled_net = gross - cost_bps / Decimal(10000)
                    mfe = ((max(highs) / reference - 1) if sign == 1
                           else (1 - min(lows) / reference))
                    mae = ((min(lows) / reference - 1) if sign == 1
                           else (1 - max(highs) / reference))
                outcomes.append({
                    "pair_id": pid, "arm": arm, "horizon_hours": horizon,
                    "availability": status, "availability_reason": reason,
                    "source_window_sha256": win["source_window_sha256"],
                    "arm_decision_sha256": decision["decision_sha256"],
                    "direction": direction, "cost_class": "MODEL_ONLY_NOT_EXECUTION",
                    "gross_directional_return": str(gross) if gross is not None else None,
                    "modeled_net_directional_return": str(modeled_net) if modeled_net is not None else None,
                    "directional_mfe": str(mfe) if mfe is not None else None,
                    "directional_mae": str(mae) if mae is not None else None,
                })
    base = build_lab({**schedule, "test_only": True,
                      "artifact_sha256": digest({**{k:v for k,v in schedule.items()
                          if k != "artifact_sha256"}, "test_only": True})}, observations,
                     test_only=True)
    if schedule != original:
        fail("INPUT_MUTATED")
    receipt = {
        "schema": "aql.p2.factory.real-development-paired-consumer.v1",
        "scope": "RETROSPECTIVE_NON_PIT_DEVELOPMENT_ONLY",
        "evidence_class": "SOURCE_BACKED_ONLY_IF_INPUTS_INDEPENDENTLY_VERIFIED",
        "source_schedule_sha256": schedule["artifact_sha256"],
        "source_package_sha256": schedule["source"]["source_package_sha256"],
        "preregistration_artifact_sha256": prereg["artifact_sha256"],
        "modeled_cost_artifact_sha256": cost_model["artifact_sha256"],
        "pair_count": len(pairs), "outcome_slots": len(outcomes),
        "coverage_by_horizon": base["market_coverage_by_horizon"],
        "outcomes": outcomes,
        "execution_status": "NOT_OBSERVED",
        "alpha_claim": "NOT_ESTABLISHED",
        "pit_status": "NOT_ATTESTED",
        "oos_status": "NOT_ATTESTED",
        "holdout_status": "SEALED_UNOPENED",
    }
    receipt["artifact_sha256"] = digest(receipt)
    return receipt
