"""Focused P2 modeled-trade tests: deterministic SYNTHETIC_ONLY fixtures.

No Binance data, original Work private artifacts, PIT, PnL or alpha.
"""
from copy import deepcopy
import unittest

from research_wp_r0.aql_p2_factory_lab import LabContractError, digest
from research_wp_r0.aql_p2_factory_modeled_trades import (
    build_modeled_trade_package, canonical_receipt_bytes, raw_receipt_sha256, BAR_MS,
)
from test_aql_p2_factory_real_development import test_contract


def seal(obj, field="artifact_sha256"):
    obj[field] = digest({k: v for k, v in obj.items() if k != field})
    return obj


def fixture(*, both_trigger=False, unknown=False):
    schedule, prereg, costs = test_contract()
    schedule["test_only"] = False
    p = schedule["pairs"][0]
    p["opportunity"]["feature_prefix_sha256"] = "a" * 64
    seal(schedule)
    source = schedule["source"]
    spec = {
        "schema": "aql.p2.breakout-policy.v1",
        "modeled_entry": "open[i+1], requires finalized same-cohort bar; NO_ACTUAL_FILL",
        "modeled_exit": "open[i+11], requires finalized same-cohort bar; NO_ACTUAL_FILL",
        "modeled_trade_missingness": (
            "trigger signal unchanged if exit unavailable; arm disposition UNKNOWN "
            "and direction null; separate signal_disposition TRIGGERED retained"
        ),
        "fee_round_trip_bps": "20",
        "slippage_round_trip_bps": "10",
        "lookback": 20,
        "shadow_exclude": "volatility > 0.03; equality allowed",
        "manifest_sha256": "d" * 64,
        "source_pins": {
            source["source_id"]: {
                "archive_sha256": source["source_package_sha256"],
                "dataset_normalized_sha256": "e" * 64,
            }
        },
    }
    prereg.update(
        full_protocol=spec,
        source_id=source["source_id"],
        source_manifest_sha256=spec["manifest_sha256"],
        source_normalized_sha256="e" * 64,
        modeled_trade_entry_rule=spec["modeled_entry"],
        modeled_trade_exit_rule=spec["modeled_exit"],
        modeled_trade_missingness_rule=spec["modeled_trade_missingness"],
    )
    seal(prereg)
    costs["round_trip_fee_bps"] = "20"
    costs["round_trip_slippage_bps"] = "10"
    costs["preregistration_sha256"] = prereg["artifact_sha256"]
    seal(costs)
    cutoff = p["opportunity"]["decision_cutoff_ms"]
    bars = []
    for i in range(2 if unknown else 16):
        bars.append({
            "open_ms": cutoff + i * BAR_MS,
            "close_ms": cutoff + (i + 1) * BAR_MS - 1,
            "content_sha256": "b" * 64,
            "open": "100" if i == 0 else "102",
            "high": "104", "low": "98", "close": "102",
        })
    windows = []
    for h in (4, 24, 72):
        status = "CENSORED" if h != 4 or unknown else "COMPLETE"
        win = {
            "pair_id": p["pair_id"], "horizon_hours": h,
            "source_package_sha256": source["source_package_sha256"],
            "reference_price": "100",
            "reference_bar_close_ms": cutoff - 1,
            "availability": status,
            "availability_reason": "END_OF_MONTH" if status != "COMPLETE" else None,
            "bars": deepcopy(bars) if h == 4 else [],
        }
        seal(win, "source_window_sha256")
        windows.append(win)
    decisions = []
    for arm in ("BASE", "SHADOW"):
        status = "UNKNOWN" if unknown else (
            "TRIGGERED" if arm == "BASE" or both_trigger else "REJECTED")
        d = {
            "pair_id": p["pair_id"], "arm": arm,
            "policy_sha256": next(a["definition_sha256"] for a in p["arms"] if a["arm"] == arm),
            "decision_cutoff_ms": cutoff,
            "decision_evidence_sha256": "c" * 64,
            "feature_prefix_sha256": p["opportunity"]["feature_prefix_sha256"],
            "source_package_sha256": source["source_package_sha256"],
            "evidence_class": "RETROSPECTIVE_NON_PIT",
            "execution_status": "NOT_OBSERVED",
            "direction": "LONG" if status == "TRIGGERED" else None,
            "disposition": status,
            "signal_disposition": "TRIGGERED",
            "modeled_trade_availability": "UNKNOWN" if unknown else "COMPLETE",
            "modeled_entry_open_ms": cutoff,
            "modeled_exit_open_ms": None if unknown else cutoff + 10 * BAR_MS,
            "modeled_exit_missingness_reason": (
                "END_OF_COHORT_NO_I_PLUS_11" if unknown else None),
        }
        seal(d, "decision_sha256")
        decisions.append(d)
    return schedule, prereg, costs, windows, decisions


def run(inputs):
    return build_modeled_trade_package(*inputs, provenance_verified=True, prereg_time_verified=True)


class ModeledTradeTests(unittest.TestCase):
    def test_base_trade_shadow_rejection_no_fake_pnl(self):
        s, p, c, w, d = fixture()
        original = deepcopy(s)
        result = run((s, p, c, w, d))
        self.assertEqual(s, original)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["arm_count"], 2)
        self.assertEqual(result["modeled_trades"][0]["entry_open"], "100")
        self.assertEqual(result["modeled_trades"][0]["exit_open"], "102")
        self.assertEqual(result["modeled_trades"][0]["modeled_gross_return"], "0.02")
        self.assertEqual(result["modeled_trades"][0]["modeled_net_return"], "0.017")
        self.assertIsNone(result["modeled_trades"][1]["modeled_net_return"])
        self.assertEqual(result["status_counts"]["SHADOW"]["REJECTED"], 1)
        self.assertEqual(result["both_arms_modeled_complete_pairs"], 0)
        self.assertIsNone(result["paired_comparison"][0]["shadow_minus_base"])
        self.assertEqual(result["descriptive_coverage_by_horizon"]["4"]["COMPLETE"], 1)
        self.assertEqual(result["execution_status"], "NOT_OBSERVED")

    def test_receipt_canonical_raw_sha_and_tamper_guard(self):
        from hashlib import sha256
        report = run(fixture())
        raw = canonical_receipt_bytes(report)
        self.assertTrue(raw.endswith(bytes([10])))
        self.assertEqual(raw_receipt_sha256(report), sha256(raw).hexdigest())
        self.assertNotEqual(raw_receipt_sha256(report), report["artifact_sha256"])
        report["modeled_trades"][0]["modeled_net_return"] = "999"
        with self.assertRaisesRegex(LabContractError, "BAD_MODELED_REPORT_DIGEST"):
            canonical_receipt_bytes(report)

    def test_arm_summary_conditional_denominators_not_zero_imputation(self):
        report = run(fixture())
        b = report["descriptive_arm_summaries"]["BASE"]
        s = report["descriptive_arm_summaries"]["SHADOW"]
        self.assertEqual(b["modeled_complete_count"], 1)
        self.assertEqual(b["scheduled_opportunity_denominator"], 1)
        self.assertEqual(b["modeled_net_mean_on_complete_only"], "0.017")
        self.assertEqual(s["modeled_complete_count"], 0)
        self.assertIsNone(s["modeled_net_mean_on_complete_only"])
        self.assertEqual(s["null_or_ineligible_count"], 1)

    def test_deterministic_receipt_and_unmodified_inputs(self):
        inp = fixture()
        original = deepcopy(inp)
        r1, r2 = run(inp), run(inp)
        self.assertEqual(r1, r2)
        self.assertEqual(inp, original)
        self.assertEqual(r1["artifact_sha256"], digest({
            k: v for k, v in r1.items() if k != "artifact_sha256"}))

    def test_both_eligible_identical_pair_delta_no_alpha(self):
        r = run(fixture(both_trigger=True))
        self.assertEqual(r["both_arms_modeled_complete_pairs"], 1)
        self.assertEqual(r["paired_comparison"][0]["shadow_minus_base"], "0.000")
        self.assertEqual(r["effect_status"], "DESCRIPTIVE_ONLY_NO_STATISTICAL_OR_ALPHA_CLAIM")

    def test_trade_excursion_excludes_post_exit_high_low(self):
        inp = fixture()
        before = run(inp)
        self.assertEqual(before["modeled_trades"][0]["modeled_trade_mfe"], "0.04")
        self.assertEqual(before["modeled_trades"][0]["modeled_trade_mae"], "-0.02")
        # Bar 10 is the exit bar. Its HIGH/LOW are after exit open.
        inp[3][0]["bars"][10]["high"] = "1000"
        inp[3][0]["bars"][10]["low"] = "1"
        seal(inp[3][0], "source_window_sha256")
        after = run(inp)
        self.assertEqual(after["modeled_trades"][0]["modeled_trade_mfe"],
                         before["modeled_trades"][0]["modeled_trade_mfe"])
        self.assertEqual(after["modeled_trades"][0]["modeled_trade_mae"],
                         before["modeled_trades"][0]["modeled_trade_mae"])

    def test_four_hour_censored_can_still_complete_ten_bar_trade(self):
        inp = fixture()
        inp[3][0]["bars"] = inp[3][0]["bars"][:11]
        inp[3][0]["availability"] = "CENSORED"
        inp[3][0]["availability_reason"] = "FOUR_HOUR_WINDOW_CENSORED"
        seal(inp[3][0], "source_window_sha256")
        out = run(inp)
        self.assertEqual(out["descriptive_coverage_by_horizon"]["4"]["CENSORED"], 1)
        self.assertEqual(out["modeled_trades"][0]["status"], "MODELED_COMPLETE")

    def test_unknown_exit_with_available_bar_fails_even_if_rehashed(self):
        inp = fixture(unknown=True)
        inp[3][0]["bars"] = fixture()[3][0]["bars"][:11]
        seal(inp[3][0], "source_window_sha256")
        with self.assertRaisesRegex(LabContractError, "MODEL_EXIT_UNKNOWN_WITH_AVAILABLE_SOURCE"):
            run(inp)

    def test_tail_unknown_retains_signal_and_nulls(self):
        r = run(fixture(unknown=True))
        self.assertEqual(r["status_counts"]["BASE"]["UNKNOWN"], 1)
        self.assertEqual(r["status_counts"]["SHADOW"]["UNKNOWN"], 1)
        self.assertEqual(r["modeled_trades"][0]["missingness_reason"],
                         "END_OF_COHORT_NO_I_PLUS_11")
        self.assertIsNone(r["modeled_trades"][0]["modeled_gross_return"])

    def test_fail_closed_if_private_verification_absent(self):
        inp = fixture()
        with self.assertRaisesRegex(LabContractError, "INDEPENDENT_SOURCE_AND_TIME"):
            build_modeled_trade_package(*inp)
        with self.assertRaisesRegex(LabContractError, "INDEPENDENT_SOURCE_AND_TIME"):
            build_modeled_trade_package(*inp, provenance_verified=True)

    def test_window_digest_mutation_rejected(self):
        inp = fixture()
        inp[3][0]["bars"][10]["open"] = "999"
        with self.assertRaisesRegex(LabContractError, "WINDOW_DIGEST_MISMATCH"):
            run(inp)

    def test_rehashed_window_price_outside_ohlc_rejected(self):
        inp = fixture()
        inp[3][0]["bars"][10]["open"] = "999"
        seal(inp[3][0], "source_window_sha256")
        with self.assertRaisesRegex(LabContractError, "BAD_TRADE_BAR_OHLC"):
            run(inp)

    def test_rehashed_gap_rejected_by_existing_descriptive_consumer(self):
        inp = fixture()
        inp[3][0]["bars"][9]["open_ms"] += 1
        seal(inp[3][0], "source_window_sha256")
        with self.assertRaisesRegex(LabContractError, "NONCONTIGUOUS_OR_LOOKAHEAD_BAR"):
            run(inp)

    def test_rehashed_forged_shadow_direction_rejected(self):
        inp = fixture()
        inp[4][1]["direction"] = "LONG"
        seal(inp[4][1], "decision_sha256")
        with self.assertRaisesRegex(LabContractError, "BAD_SHADOW_REJECTION"):
            run(inp)

    def test_wrong_entry_time_rejected(self):
        inp = fixture()
        inp[4][0]["modeled_entry_open_ms"] += BAR_MS
        seal(inp[4][0], "decision_sha256")
        with self.assertRaisesRegex(LabContractError, "FROZEN_TRADE_ENTRY_EXIT_TIME_DRIFT"):
            run(inp)

    def test_duplicate_or_missing_pair_window_rejected(self):
        inp = fixture()
        inp[3].append(deepcopy(inp[3][0]))
        with self.assertRaisesRegex(LabContractError, "DUPLICATE_OR_UNKNOWN_WINDOW"):
            run(inp)
        inp = fixture()
        inp[3].pop()
        with self.assertRaisesRegex(LabContractError, "INCOMPLETE_WINDOW_DENOMINATOR"):
            run(inp)

    def test_policy_exit_drift_even_when_resealed_rejected(self):
        inp = fixture()
        inp[1]["full_protocol"]["modeled_exit"] = "open[i+12]"
        inp[1]["modeled_trade_exit_rule"] = "open[i+12]"
        seal(inp[1])
        inp[2]["preregistration_sha256"] = inp[1]["artifact_sha256"]
        seal(inp[2])
        with self.assertRaisesRegex(LabContractError, "UNFROZEN_TRADE_POLICY_MISMATCH"):
            run(inp)

    def test_cost_drift_even_when_resealed_rejected(self):
        inp = fixture()
        inp[2]["round_trip_fee_bps"] = "30"
        seal(inp[2])
        with self.assertRaisesRegex(LabContractError, "UNFROZEN_TRADE_COSTS"):
            run(inp)

    def test_missing_exit_cannot_be_scored(self):
        inp = fixture()
        inp[3][0]["bars"] = inp[3][0]["bars"][:9]
        inp[3][0]["availability"] = "CENSORED"
        inp[3][0]["availability_reason"] = "END_OF_MONTH"
        seal(inp[3][0], "source_window_sha256")
        with self.assertRaisesRegex(LabContractError, "ELIGIBLE_TRADE_MISSING_EXIT_BAR"):
            run(inp)

    def test_fake_test_only_schedule_cannot_be_promoted(self):
        inp = fixture()
        inp[0]["test_only"] = True
        seal(inp[0])
        with self.assertRaisesRegex(LabContractError, "REAL_SOURCE_SCHEDULE_REQUIRED"):
            run(inp)


if __name__ == "__main__":
    unittest.main()
