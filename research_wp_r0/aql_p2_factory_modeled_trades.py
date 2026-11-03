"""Frozen P2 Breakout next-open / ten-bar modeled trade research, no orders.

Consumes ORIGINAL Core arm decisions and ORIGINAL source windows. This module does
not create signals, fetch bars or reinterpret fixed 4/24/72h descriptive returns.
Only one eligible LONG per pair/arm, entry open[i+1], exit open[i+11],
30bps modeled round-trip fees/slippage as frozen by Core. No actual fills/PnL.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal

from research_wp_r0.aql_p2_factory_lab import digest, hash_ok, validate_schedule
from research_wp_r0.aql_p2_factory_real_development import (
    BAR_MS, dec, fail, validate_prereg,
)

ENTRY_OFFSET = 0
EXIT_OFFSET = 10
FOUR_HOURS = 4
TRADE_RULE = "NEXT_OPEN_I_PLUS_1_EXIT_OPEN_I_PLUS_11_V1"


def _full_hash(row, key):
    return hash_ok(row.get(key)) and digest({k: v for k, v in row.items() if k != key}) == row[key]


def _frozen_policy(prereg, cost_model):
    spec = prereg.get("full_protocol")
    if not isinstance(spec, dict) or spec.get("schema") != "aql.p2.breakout-policy.v1":
        fail("MISSING_FROZEN_FULL_TRADE_POLICY")
    if (spec.get("modeled_entry") != "open[i+1], requires finalized same-cohort bar; NO_ACTUAL_FILL"
        or spec.get("modeled_exit") != "open[i+11], requires finalized same-cohort bar; NO_ACTUAL_FILL"
        or spec.get("modeled_trade_missingness") !=
            "trigger signal unchanged if exit unavailable; arm disposition UNKNOWN and direction null; separate signal_disposition TRIGGERED retained"
        or spec.get("fee_round_trip_bps") != "20"
        or spec.get("slippage_round_trip_bps") != "10"
        or spec.get("lookback") != 20
        or spec.get("shadow_exclude") != "volatility > 0.03; equality allowed"
        or prereg.get("modeled_trade_entry_rule") != spec["modeled_entry"]
        or prereg.get("modeled_trade_exit_rule") != spec["modeled_exit"]
        or prereg.get("modeled_trade_missingness_rule") != spec["modeled_trade_missingness"]):
        fail("UNFROZEN_TRADE_POLICY_MISMATCH")
    if (dec(cost_model["round_trip_fee_bps"]) != Decimal(20)
        or dec(cost_model["round_trip_slippage_bps"]) != Decimal(10)):
        fail("UNFROZEN_TRADE_COSTS")
    if (prereg.get("source_manifest_sha256") != spec.get("manifest_sha256")
        or prereg.get("source_normalized_sha256") !=
            spec.get("source_pins", {}).get(prereg.get("source_id"), {}).get("dataset_normalized_sha256")
        or prereg.get("source_package_sha256") !=
            spec.get("source_pins", {}).get(prereg.get("source_id"), {}).get("archive_sha256")):
        fail("FROZEN_SOURCE_PIN_MISMATCH")


def _validate_pair_arms(pairs, decisions):
    expected = {(pid, arm) for pid in pairs for arm in ("BASE", "SHADOW")}
    got = {}
    if not isinstance(decisions, list):
        fail("BAD_ARM_DECISION_LIST")
    for d in decisions:
        if not isinstance(d, dict):
            fail("BAD_ARM_DECISION")
        k = (d.get("pair_id"), d.get("arm"))
        if k not in expected or k in got:
            fail("DUPLICATE_OR_UNKNOWN_ARM_DECISION")
        p = pairs[k[0]]
        policy = next(x["definition_sha256"] for x in p["arms"] if x["arm"] == k[1])
        if (not _full_hash(d, "decision_sha256")
            or not hash_ok(d.get("decision_evidence_sha256"))
            or d.get("policy_sha256") != policy
            or d.get("decision_cutoff_ms") != p["opportunity"]["decision_cutoff_ms"]
            or d.get("source_package_sha256") != p["opportunity"]["source_package_sha256"]
            or d.get("feature_prefix_sha256") != p["opportunity"]["feature_prefix_sha256"]
            or d.get("evidence_class") != "RETROSPECTIVE_NON_PIT"
            or d.get("execution_status") != "NOT_OBSERVED"):
            fail("ARM_PROVENANCE_MISMATCH")
        status, signal, direction = (
            d.get("disposition"), d.get("signal_disposition"), d.get("direction"))
        availability = d.get("modeled_trade_availability")
        if signal not in ("TRIGGERED", "NO_SIGNAL"):
            fail("BAD_SIGNAL_DISPOSITION")
        if status == "TRIGGERED":
            if (signal != "TRIGGERED" or direction != "LONG"
                or availability != "COMPLETE"
                or d.get("modeled_exit_missingness_reason") is not None):
                fail("BAD_TRIGGERED_TRADE_ELIGIBILITY")
        elif status == "NO_SIGNAL":
            if (signal != "NO_SIGNAL" or direction is not None
                or availability != "NOT_APPLICABLE"):
                fail("BAD_NO_SIGNAL_ARM")
        elif status == "REJECTED":
            if signal != "TRIGGERED" or direction is not None or k[1] != "SHADOW":
                fail("BAD_SHADOW_REJECTION")
        elif status == "UNKNOWN":
            if (signal != "TRIGGERED" or direction is not None
                or availability != "UNKNOWN" or
                d.get("modeled_exit_missingness_reason") != "END_OF_COHORT_NO_I_PLUS_11"):
                fail("BAD_UNKNOWN_EXIT")
        else:
            fail("BAD_ARM_DISPOSITION")
        got[k] = d
    if set(got) != expected:
        fail("INCOMPLETE_ARM_DENOMINATOR")
    for pid in pairs:
        b, s = got[(pid, "BASE")], got[(pid, "SHADOW")]
        if (b["signal_disposition"] != s["signal_disposition"]
            or b["decision_cutoff_ms"] != s["decision_cutoff_ms"]):
            fail("PAIR_SIGNAL_MISMATCH")
        if s["disposition"] == "TRIGGERED" and b["disposition"] != "TRIGGERED":
            fail("SHADOW_TRIGGER_WITHOUT_BASE")
    return got


def _bar_at(bar, cutoff, offset):
    if not isinstance(bar, dict) or not hash_ok(bar.get("content_sha256")):
        fail("UNPINNED_TRADE_BAR")
    if (bar.get("open_ms") != cutoff + BAR_MS * offset
        or bar.get("close_ms") != cutoff + BAR_MS * (offset + 1) - 1):
        fail("TRADE_BAR_TIME_OR_COHORT_MISMATCH")
    op, hi, lo, cl = [dec(bar.get(k)) for k in ("open", "high", "low", "close")]
    if not (Decimal(0) < lo <= op <= hi and lo <= cl <= hi):
        fail("BAD_TRADE_BAR_OHLC")
    return op


def build_modeled_trade_package(schedule, prereg, cost_model, windows, arm_decisions,
                               *, provenance_verified=False, prereg_time_verified=False):
    """Produce fixed-denominator modeled next-open/ten-bar artifacts, no scientific acceptance.

    Inputs are the exact unchanged genuine Core handoff and independent Work
    private source windows. Caller MUST independently attest original ZIP,
    full original row hashes, registration anchor ordering and saved window files;
    booleans do not by themselves constitute evidence of those external facts.
    """
    before = deepcopy(schedule)
    total_cost_bps = validate_prereg(schedule, prereg, cost_model)
    _frozen_policy(prereg, cost_model)
    if provenance_verified is not True or prereg_time_verified is not True:
        fail("INDEPENDENT_SOURCE_AND_TIME_ATTESTATION_REQUIRED")
    if total_cost_bps != Decimal(30):
        fail("COST_BPS_MISMATCH")
    pairs = validate_schedule(schedule)
    arms = _validate_pair_arms(pairs, arm_decisions)
    expected = {(pid, h) for pid in pairs for h in (4, 24, 72)}
    all_windows = {}
    if not isinstance(windows, list):
        fail("MISSING_SOURCE_WINDOWS")
    for w in windows:
        if not isinstance(w, dict):
            fail("BAD_WINDOW")
        k = (w.get("pair_id"), w.get("horizon_hours"))
        if k not in expected or k in all_windows:
            fail("DUPLICATE_OR_UNKNOWN_WINDOW")
        if (not _full_hash(w, "source_window_sha256")
            or w.get("source_package_sha256") != schedule["source"]["source_package_sha256"]
            or w.get("reference_bar_close_ms") != pairs[k[0]]["opportunity"]["decision_cutoff_ms"] - 1):
            fail("WINDOW_LINEAGE_OR_DIGEST_MISMATCH")
        all_windows[k] = w
    if set(all_windows) != expected:
        fail("INCOMPLETE_SOURCE_WINDOW_DENOMINATOR")
    modeled = []
    paired = []
    counts = Counter()
    for pid, p in pairs.items():
        cutoff = p["opportunity"]["decision_cutoff_ms"]
        # The original 4h window contains >=11 sequential finalized 15m bars
        # for all modeled entry/exit prices. Do not read another month/horizon.
        w = all_windows[(pid, FOUR_HOURS)]
        bs = w.get("bars")
        if not isinstance(bs, list) or len(bs) > 16:
            fail("BAD_FOUR_HOUR_WINDOW")
        if w.get("availability") == "COMPLETE" and (len(bs) != 16 or
                                                      w.get("availability_reason") is not None):
            fail("INVALID_COMPLETE_WINDOW")
        if w.get("availability") != "COMPLETE" and (
            w.get("availability") not in ("CENSORED", "UNKNOWN")
            or not isinstance(w.get("availability_reason"), str)
            or not w["availability_reason"].strip()
            or len(bs) >= 16):
            fail("BAD_CENSORED_WINDOW")
        for i, bar in enumerate(bs):
            _bar_at(bar, cutoff, i)
        rows = {}
        for name in ("BASE", "SHADOW"):
            d = arms[(pid, name)]
            status = d["disposition"]
            entry_ms = d.get("modeled_entry_open_ms")
            exit_ms = d.get("modeled_exit_open_ms")
            row = {
                "pair_id": pid, "arm": name, "policy_sha256": d["policy_sha256"],
                "arm_decision_sha256": d["decision_sha256"],
                "four_hour_source_window_sha256": w["source_window_sha256"],
                "signal_disposition": d["signal_disposition"],
                "disposition": status,
                "modeled_trade_availability": d["modeled_trade_availability"],
                "entry_open_ms": entry_ms, "exit_open_ms": exit_ms,
                "entry_open": None, "exit_open": None,
                "modeled_gross_return": None, "modeled_net_return": None,
                "fee_bps": "20", "slippage_bps": "10",
                "cost_class": "MODEL_ONLY_NOT_EXECUTION",
                "status": "INELIGIBLE" if status in ("NO_SIGNAL", "REJECTED") else
                          "UNKNOWN" if status == "UNKNOWN" else "MODELED_COMPLETE",
                "missingness_reason": d.get("modeled_exit_missingness_reason") if status == "UNKNOWN" else None,
                "execution_status": "NOT_OBSERVED",
            }
            # Core stores entry/exit eligibility for rejected arms too (signal
            # truth), but never score their rejected policy as a trade.
            if status == "TRIGGERED":
                if (entry_ms != cutoff or exit_ms != cutoff + 10 * BAR_MS):
                    fail("FROZEN_TRADE_ENTRY_EXIT_TIME_DRIFT")
                if len(bs) < 11:
                    fail("ELIGIBLE_TRADE_MISSING_EXIT_BAR")
                entry, exit_ = (_bar_at(bs[j], cutoff, j) for j in (0, 10))
                gross = exit_ / entry - 1  # Core strategy is LONG only
                net = gross - total_cost_bps / Decimal(10000)
                row.update(entry_open=str(entry), exit_open=str(exit_),
                           modeled_gross_return=str(gross), modeled_net_return=str(net))
            elif status == "UNKNOWN":
                if entry_ms != cutoff or exit_ms is not None:
                    fail("UNKNOWN_EXIT_TIME_CONTRACT_MISMATCH")
            rows[name] = row
            modeled.append(row)
            counts[(name, status)] += 1
        base, shadow = rows["BASE"], rows["SHADOW"]
        base_net = dec(base["modeled_net_return"]) if base["modeled_net_return"] is not None else None
        shadow_net = dec(shadow["modeled_net_return"]) if shadow["modeled_net_return"] is not None else None
        both = base_net is not None and shadow_net is not None
        paired.append({
            "pair_id": pid, "base_disposition": base["disposition"],
            "shadow_disposition": shadow["disposition"],
            "both_modeled_complete": both,
            "base_modeled_net_return": base["modeled_net_return"],
            "shadow_modeled_net_return": shadow["modeled_net_return"],
            "shadow_minus_base": str(shadow_net - base_net) if both else None,
            "comparison_class": "DESCRIPTIVE_ONLY_NO_ALPHA_OR_CAUSAL_UPLIFT",
        })
    if schedule != before:
        fail("SOURCE_SCHEDULE_MUTATED")
    report = {
        "schema": "aql.p2.factory.breakout-modeled-trades.v1",
        "scope": "RETROSPECTIVE_NON_PIT_DEVELOPMENT_ONLY",
        "study_trial_id": schedule["protocol"]["trial_id"],
        "source_id": schedule["source"]["source_id"],
        "source_package_sha256": schedule["source"]["source_package_sha256"],
        "source_schedule_sha256": schedule["artifact_sha256"],
        "preregistration_artifact_sha256": prereg["artifact_sha256"],
        "cost_model_artifact_sha256": cost_model["artifact_sha256"],
        "pair_count": len(pairs), "arm_count": len(modeled),
        "status_counts": {a: {s: counts[(a, s)] for s in ("TRIGGERED", "NO_SIGNAL", "REJECTED", "UNKNOWN")}
                          for a in ("BASE", "SHADOW")},
        "modeled_trades": modeled, "paired_comparison": paired,
        "modeled_exit_spec": TRADE_RULE,
        "modeled_cost_round_trip_bps": "30",
        "effect_status": "DESCRIPTIVE_ONLY_NO_STATISTICAL_OR_ALPHA_CLAIM",
        "execution_status": "NOT_OBSERVED",
        "pit_status": "NOT_ATTESTED", "oos_status": "NOT_ATTESTED",
        "holdout_status": "SEALED_UNOPENED",
    }
    report["artifact_sha256"] = digest(report)
    return report
