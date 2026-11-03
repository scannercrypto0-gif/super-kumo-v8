"""Focused TEST_ONLY offline portfolio lifecycle and fail-closed provenance."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import unittest

from research_wp_r0.aql_p2_factory_lab import LabContractError, digest
from research_wp_r0.aql_p2_factory_portfolio import (
    BAR_MS, build_offline_portfolio_package, propose_portfolio_policy,
    canonical_portfolio_receipt_bytes, raw_portfolio_receipt_sha256,
    render_portfolio_report,
)


def sealed(obj):
    row = deepcopy(obj)
    row.pop("artifact_sha256", None)
    row["artifact_sha256"] = digest(row)
    return row


def fixture(*, negative_second=False, no_triggers=False, other_month=False):
    start = (0 if not other_month else 1000 * BAR_MS)
    sid = "TEST_ONLY_FEB" if not other_month else "TEST_ONLY_AUG"
    parent = {
        "schema": "aql.p2.factory.breakout-modeled-trades.v1",
        "scope": "RETROSPECTIVE_NON_PIT_DEVELOPMENT_ONLY",
        "source_id": sid,
        "source_package_sha256": "a" * 64 if not other_month else "b" * 64,
        "source_schedule_sha256": "c" * 64,
        "preregistration_artifact_sha256": "d" * 64,
        "cost_model_artifact_sha256": "e" * 64,
        "descriptive_4_24_72h_artifact_sha256": "f" * 64,
        "execution_status": "NOT_OBSERVED",
        "holdout_status": "SEALED_UNOPENED",
        "pit_status": "NOT_ATTESTED",
        "oos_status": "NOT_ATTESTED",
        "modeled_exit_spec": "NEXT_OPEN_I_PLUS_1_EXIT_OPEN_I_PLUS_11_V1",
        "modeled_cost_round_trip_bps": "30",
        "modeled_trades": [], "paired_comparison": [],
    }
    # Two same-time competing eligible opportunities at t=11 bars, alongside
    # occupied and original null dispositions.
    specs = [
        ("first", 1, "TRIGGERED", "TRIGGERED", "102"),
        ("occupied", 5, "TRIGGERED", "REJECTED", "95"),
        ("tie-A", 11, "TRIGGERED", "TRIGGERED",
         "95" if negative_second else "101"),
        ("tie-B", 11, "TRIGGERED", "TRIGGERED",
         "95" if negative_second else "101"),
        ("no-signal", 3, "NO_SIGNAL", "NO_SIGNAL", None),
        ("unknown", 4, "UNKNOWN", "UNKNOWN", None),
    ]
    for label, index, base_status, shadow_status, exit_px in specs:
        pid = digest({"source_id": sid, "label": label})
        for arm, status in (("BASE", base_status), ("SHADOW", shadow_status)):
            full = status == "TRIGGERED" and not no_triggers
            effective_status = status if not no_triggers else "NO_SIGNAL"
            if no_triggers:
                full = False
            row = {
                "pair_id": pid, "arm": arm, "disposition": effective_status,
                "signal_disposition": "TRIGGERED" if effective_status != "NO_SIGNAL" else "NO_SIGNAL",
                "status": ("MODELED_COMPLETE" if full else "UNKNOWN" if
                           effective_status == "UNKNOWN" else "INELIGIBLE"),
                "modeled_trade_availability": "COMPLETE" if full else "UNKNOWN",
                "arm_decision_sha256": digest({"pid": pid, "arm": arm}),
                "four_hour_source_window_sha256": digest({"window": pid}),
                "entry_open_ms": start + index * BAR_MS if full else None,
                "exit_open_ms": start + (index + 10) * BAR_MS if full else None,
                "entry_open": "100" if full else None,
                "exit_open": exit_px if full else None,
                "holding_period_bars": 10,
                "modeled_net_return": (
                    str(Decimal(exit_px) / Decimal(100) - Decimal("1.003"))
                    if full else None),
                "modeled_gross_return": (
                    str(Decimal(exit_px) / Decimal(100) - Decimal(1))
                    if full else None),
                "fee_entry_return": "0.001" if full else None,
                "fee_exit_return": "0.001" if full else None,
                "slippage_entry_return": "0.0005" if full else None,
                "slippage_exit_return": "0.0005" if full else None,
                "entry_availability": "COMPLETE" if full else "UNKNOWN",
                "exit_availability": "COMPLETE" if full else "UNKNOWN",
                "missingness_reason": "END_OF_COHORT" if effective_status == "UNKNOWN" else None,
                "censored": effective_status == "UNKNOWN",
                "execution_status": "NOT_OBSERVED",
            }
            parent["modeled_trades"].append(row)
        both = not no_triggers and base_status == "TRIGGERED" and shadow_status == "TRIGGERED"
        parent["paired_comparison"].append({
            "pair_id": pid,
            "base_disposition": base_status if not no_triggers else "NO_SIGNAL",
            "shadow_disposition": shadow_status if not no_triggers else "NO_SIGNAL",
            "both_modeled_complete": both,
        })
    parent["pair_count"] = len(specs)
    parent["arm_count"] = 2 * len(specs)
    parent = sealed(parent)
    bounds = {sid: {
        "source_id": sid, "source_package_sha256": parent["source_package_sha256"],
        "start_ms": start, "end_exclusive_ms": start + 50 * BAR_MS,
    }}
    policy = propose_portfolio_policy("10000")
    policy["approval_status"] = "TEST_ONLY_SYNTHETIC"
    policy["test_only"] = True
    policy = sealed(policy)
    return [parent], policy, bounds


def run(inputs):
    return build_offline_portfolio_package(*inputs, test_only=True)


class PortfolioTests(unittest.TestCase):
    def test_proposed_policy_cannot_score_private_or_synthetic(self):
        r, p, b = fixture()
        candidate = propose_portfolio_policy("10000")
        self.assertEqual(candidate["approval_status"], "PROPOSED_NOT_OWNER_APPROVED")
        with self.assertRaisesRegex(LabContractError, "OWNER_PORTFOLIO_POLICY_APPROVAL_AND_PRE_SCORE_ANCHOR_REQUIRED"):
            build_offline_portfolio_package(r, candidate, b,
                                            independent_parent_receipts_verified=True)
        with self.assertRaisesRegex(LabContractError, "TEST_ONLY_POLICY_REQUIRED"):
            build_offline_portfolio_package(r, candidate, b, test_only=True)

    def test_owner_approval_and_anchor_not_forgeable_by_test_flag(self):
        r, p, b = fixture()
        p["test_only"] = False
        p["approval_status"] = "OWNER_APPROVED_PROVISIONAL"
        p["owner_approval_url"] = "https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-123"
        p["pre_score_anchor_receipt_sha256"] = "0" * 64
        p = sealed(p)
        with self.assertRaisesRegex(LabContractError, "OWNER_PORTFOLIO_POLICY_APPROVAL_AND_PRE_SCORE_ANCHOR_REQUIRED"):
            build_offline_portfolio_package(r, p, b,
                                            independent_parent_receipts_verified=True)

    def test_full_one_position_occupied_skip_and_exit_first(self):
        out = run(fixture())
        cohort = out["cohorts"][0]
        base, shadow = (cohort["arms"][x] for x in ("BASE", "SHADOW"))
        self.assertEqual(out["total_scheduled_pairs"], 6)
        self.assertEqual(out["total_arm_slots"], 12)
        self.assertEqual(base["summary"]["modeled_selected_count"], 2)
        self.assertEqual(base["summary"]["skipped_occupied_or_tie_count"], 2)
        self.assertEqual(base["summary"]["ineligible_null_count"], 2)
        self.assertEqual(shadow["summary"]["modeled_selected_count"], 2)
        self.assertEqual(shadow["summary"]["skipped_occupied_or_tie_count"], 1)
        self.assertEqual(shadow["summary"]["ineligible_null_count"], 3)
        self.assertEqual(len(base["opportunity_census"]), 6)
        events = base["ledger_events"]
        self.assertEqual([x["event"] for x in events],
                         ["MODEL_ENTRY", "MODEL_EXIT", "MODEL_ENTRY", "MODEL_EXIT"])
        self.assertEqual(events[1]["at_ms"], events[2]["at_ms"])
        self.assertEqual(events[0]["cash_after"], "0")
        self.assertEqual(events[-1]["execution_status"], "NOT_OBSERVED")
        self.assertEqual(base["summary"]["time_exposure_fraction"], "0.4")

    def test_exit_cash_cost_and_deterministic_tie(self):
        out = run(fixture())
        base = out["cohorts"][0]["arms"]["BASE"]
        selected = base["position_rows"]
        self.assertEqual(selected[0]["cash_after_exit"], "10170.000")
        self.assertEqual(selected[0]["modeled_cost_amount"], "30.000")
        self.assertEqual(selected[1]["cash_after_exit"], "10241.190000")
        self.assertEqual(base["summary"]["terminal_realized_cash_equity"], "10241.190000")
        self.assertEqual(selected[1]["pair_id"], min(
            x["pair_id"] for x in fixture()[0][0]["modeled_trades"]
            if x["entry_open_ms"] == 11 * BAR_MS))
        self.assertEqual(out["cohorts"][0]["shadow_minus_base_terminal_modeled_equity"], "0.000000")

    def test_realized_only_drawdown_no_mark_to_market_claim(self):
        out = run(fixture(negative_second=True))
        s = out["cohorts"][0]["arms"]["BASE"]["summary"]
        self.assertEqual(s["realized_only_max_drawdown"], "-0.053")
        self.assertTrue(Decimal(s["terminal_realized_cash_equity"]) < Decimal("10000"))
        self.assertEqual(s["equity_valuation"],
                         "REALIZED_SETTLEMENT_ONLY_NOT_INTRATRADE_MARK_TO_MARKET")
        self.assertTrue(all(x["marked_equity"] is None for x in
                            out["cohorts"][0]["arms"]["BASE"]["ledger_events"]))

    def test_no_signal_all_null_remain_cash_and_zero_exposure(self):
        r, p, b = fixture(no_triggers=True)
        out = run((r, p, b))
        for arm in ("BASE", "SHADOW"):
            s = out["cohorts"][0]["arms"][arm]["summary"]
            self.assertEqual(s["terminal_realized_cash_equity"], "10000")
            self.assertEqual(s["selected_count"] if "selected_count" in s else
                             s["modeled_selected_count"], 0)
            self.assertEqual(s["ineligible_null_count"], 6)
            self.assertEqual(s["time_exposure_fraction"], "0")

    def test_cohort_independent_no_cash_stitch(self):
        f = fixture()
        a = fixture(other_month=True)
        r = f[0] + a[0]
        b = {**f[2], **a[2]}
        out = run((r, f[1], b))
        self.assertEqual(len(out["cohorts"]), 2)
        self.assertEqual(out["total_scheduled_pairs"], 12)
        self.assertTrue(all(c["arms"]["BASE"]["summary"]["initial_capital"] == "10000"
                            for c in out["cohorts"]))
        self.assertEqual(out["capital_linking"], "RESET_PER_MONTH_NO_CROSS_COHORT_COMPOUNDING")

    def test_determinism_and_input_immutability(self):
        inp = fixture()
        original = deepcopy(inp)
        x = run(inp)
        self.assertEqual(x, run(inp))
        self.assertEqual(inp, original)
        raw = canonical_portfolio_receipt_bytes(x)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw_portfolio_receipt_sha256(x), sha256(raw).hexdigest())
        self.assertIn("Realized", render_portfolio_report(x).replace("realized", "Realized"))

    def test_rehashed_price_or_cost_forgery_still_rejected(self):
        r, p, b = fixture()
        trade = r[0]["modeled_trades"][0]
        trade["modeled_net_return"] = "0.50"
        r[0] = sealed(r[0])
        with self.assertRaisesRegex(LabContractError, "PARENT_TRADE_RETURN_MISMATCH"):
            run((r, p, b))
        r,p,b = fixture()
        r[0]["modeled_trades"][0]["fee_entry_return"] = "0"
        r[0] = sealed(r[0])
        with self.assertRaisesRegex(LabContractError, "TRADE_MODELED_ENTRY_EXIT_OR_COST_DRIFT"):
            run((r,p,b))

    def test_malformed_or_duplicate_parent_arms_fail_closed(self):
        r,p,b = fixture()
        r[0]["modeled_trades"].append(deepcopy(r[0]["modeled_trades"][0]))
        r[0]["arm_count"] += 1
        r[0] = sealed(r[0])
        with self.assertRaises(LabContractError):
            run((r,p,b))
        r,p,b = fixture()
        r[0]["modeled_trades"][1]["arm"] = "BASE"
        r[0] = sealed(r[0])
        with self.assertRaises(LabContractError):
            run((r,p,b))

    def test_hash_mismatch_policy_and_parent_rejected(self):
        r,p,b=fixture()
        p["max_open_positions"] = 2
        with self.assertRaisesRegex(LabContractError, "PORTFOLIO_POLICY_HASH_MISMATCH"):
            run((r,p,b))
        r,p,b=fixture()
        p["max_open_positions"] = 2
        p=sealed(p)
        with self.assertRaisesRegex(LabContractError, "UNAPPROVED_PORTFOLIO_SEMANTIC_CHANGE"):
            run((r,p,b))
        r,p,b=fixture()
        r[0]["pair_count"] += 1
        with self.assertRaisesRegex(LabContractError, "PARENT_TRADE_REPORT_DIGEST_MISMATCH"):
            run((r,p,b))

    def test_nonfinite_capital_and_cross_cohort_boundary_rejected(self):
        with self.assertRaises(LabContractError):
            propose_portfolio_policy("NaN")
        with self.assertRaises(LabContractError):
            propose_portfolio_policy("-10")
        r,p,b=fixture()
        b["TEST_ONLY_FEB"]["end_exclusive_ms"] = 10 * BAR_MS
        with self.assertRaisesRegex(LabContractError, "CROSS_COHORT_TRADE_OR_NON_GRID_TIME"):
            run((r,p,b))

    def test_bad_parent_fills_held_mfe_not_portfolio_equity(self):
        r,p,b=fixture()
        r[0]["modeled_trades"][0]["status"] = "ACTUAL_FILLED"
        r[0] = sealed(r[0])
        with self.assertRaisesRegex(LabContractError, "TRADE_MODELED_ENTRY_EXIT_OR_COST_DRIFT"):
            run((r,p,b))
        out=run(fixture())
        self.assertEqual(out["alpha_claim"], "NOT_ESTABLISHED")
        self.assertEqual(out["pit_status"], "NOT_ATTESTED")
        self.assertEqual(out["oos_status"], "NOT_ATTESTED")
        self.assertEqual(out["holdout_status"], "SEALED_UNOPENED")

    def test_receipt_tamper_rejected_and_private_readiness_not_asserted(self):
        out=run(fixture())
        out["cohorts"][0]["arms"]["BASE"]["summary"]["terminal_realized_cash_equity"]="1"
        with self.assertRaisesRegex(LabContractError, "PORTFOLIO_RECEIPT_HASH_MISMATCH"):
            canonical_portfolio_receipt_bytes(out)
