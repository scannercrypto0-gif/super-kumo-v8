"""Owner Option C: focused synthetic-only independent opportunity tests."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import unittest

from research_wp_r0.aql_p2_factory_lab import LabContractError, digest
from research_wp_r0.aql_p2_factory_portfolio import (
    BAR_MS, OWNER_C_URL, frozen_option_c_policy,
    build_independent_opportunity_package, canonical_opportunity_receipt_bytes,
    raw_opportunity_receipt_sha256, render_opportunity_research_report,
)


def sealed(obj):
    r=deepcopy(obj)
    r.pop("artifact_sha256",None)
    r["artifact_sha256"]=digest(r)
    return r


def fixture(*, no_triggers=False, other_month=False, negative=False):
    start=0 if not other_month else 1000*BAR_MS
    source_id="TEST_ONLY_FEB" if not other_month else "TEST_ONLY_AUG"
    report={
        "schema":"aql.p2.factory.breakout-modeled-trades.v1",
        "scope":"RETROSPECTIVE_NON_PIT_DEVELOPMENT_ONLY",
        "source_id":source_id,
        "source_package_sha256":"a"*64 if not other_month else "b"*64,
        "source_schedule_sha256":"c"*64,
        "preregistration_artifact_sha256":"d"*64,
        "cost_model_artifact_sha256":"e"*64,
        "descriptive_4_24_72h_artifact_sha256":"f"*64,
        "execution_status":"NOT_OBSERVED","holdout_status":"SEALED_UNOPENED",
        "pit_status":"NOT_ATTESTED","oos_status":"NOT_ATTESTED",
        "modeled_exit_spec":"NEXT_OPEN_I_PLUS_1_EXIT_OPEN_I_PLUS_11_V1",
        "modeled_cost_round_trip_bps":"30",
        "modeled_trades":[],"paired_comparison":[],
    }
    # Half-open clock: first exits exactly when two more begin; occupied
    # original signal overlaps first and both later entries.
    scenarios=[
        ("first",1,"TRIGGERED","TRIGGERED","102"),
        ("occupied",5,"TRIGGERED","REJECTED","95"),
        ("same-clock-A",11,"TRIGGERED","TRIGGERED",
         "95" if negative else "101"),
        ("same-clock-B",11,"TRIGGERED","TRIGGERED",
         "95" if negative else "101"),
        ("no-signal",3,"NO_SIGNAL","NO_SIGNAL",None),
        ("censored",4,"UNKNOWN","UNKNOWN",None),
    ]
    for label,index,base_state,shadow_state,price in scenarios:
        pid=digest({"source_id":source_id,"label":label})
        for arm,state in (("BASE",base_state),("SHADOW",shadow_state)):
            if no_triggers:
                state="NO_SIGNAL"
            full=state=="TRIGGERED"
            r={
                "pair_id":pid,"arm":arm,
                "disposition":state,
                "signal_disposition":"NO_SIGNAL" if state=="NO_SIGNAL" else "TRIGGERED",
                "status":"MODELED_COMPLETE" if full else "UNKNOWN" if state=="UNKNOWN" else "INELIGIBLE",
                "modeled_trade_availability":"COMPLETE" if full else "UNKNOWN",
                "arm_decision_sha256":digest({"pid":pid,"arm":arm}),
                "four_hour_source_window_sha256":digest({"window":pid}),
                "entry_open_ms":start+index*BAR_MS if full else None,
                "exit_open_ms":start+(index+10)*BAR_MS if full else None,
                "entry_open":"100" if full else None,
                "exit_open":price if full else None,
                "holding_period_bars":10,
                "modeled_gross_return":(str(Decimal(price)/100-1) if full else None),
                "modeled_net_return":(str(Decimal(price)/100-Decimal("1.003"))
                                       if full else None),
                "fee_entry_return":"0.001" if full else None,
                "fee_exit_return":"0.001" if full else None,
                "slippage_entry_return":"0.0005" if full else None,
                "slippage_exit_return":"0.0005" if full else None,
                "cost_class":"MODEL_ONLY_NOT_EXECUTION",
                "fee_bps":"20","slippage_bps":"10",
                "missingness_reason":"END_OF_COHORT" if state=="UNKNOWN" else None,
                "censored":state=="UNKNOWN",
                "execution_status":"NOT_OBSERVED",
            }
            report["modeled_trades"].append(r)
        report["paired_comparison"].append({
            "pair_id":pid,
            "base_disposition":base_state if not no_triggers else "NO_SIGNAL",
            "shadow_disposition":shadow_state if not no_triggers else "NO_SIGNAL",
            "both_modeled_complete":(base_state=="TRIGGERED" and
                shadow_state=="TRIGGERED" and not no_triggers),
        })
    report["pair_count"]=len(scenarios)
    report["arm_count"]=2*len(scenarios)
    report=sealed(report)
    bounds={source_id:{
        "source_id":source_id,
        "source_package_sha256":report["source_package_sha256"],
        "start_ms":start,"end_exclusive_ms":start+50*BAR_MS,
    }}
    return [report],frozen_option_c_policy(),bounds


def run(inputs):
    return build_independent_opportunity_package(*inputs,test_only=True)


class IndependentOptionCTests(unittest.TestCase):
    def test_frozen_owner_c_policy_has_no_funded_portfolio_assumption(self):
        p=frozen_option_c_policy()
        self.assertEqual(p["owner_decision_url"],OWNER_C_URL)
        self.assertEqual(p["approval_status"],"OWNER_APPROVED_PROVISIONAL")
        self.assertEqual(p["capital_account"],"NONE")
        self.assertEqual(p["overlaps"],"KEEP_EVERY_ELIGIBLE_OPPORTUNITY_NO_ARBITRATION")
        self.assertEqual(p["position_cap"],"NONE")
        self.assertEqual(p["artifact_sha256"],digest({k:v for k,v in p.items()
                                                     if k!="artifact_sha256"}))

    def test_all_eligible_trades_including_overlap_are_preserved(self):
        out=run(fixture())
        c=out["cohorts"][0]
        b=c["arms"]["BASE"]["summary"]
        s=c["arms"]["SHADOW"]["summary"]
        self.assertEqual(out["total_pair_denominator"],6)
        self.assertEqual(out["total_arm_slots"],12)
        self.assertEqual(b["complete_modeled_count"],4)
        self.assertEqual(s["complete_modeled_count"],3)
        self.assertEqual(b["null_or_ineligible_count"],2)
        self.assertEqual(s["null_or_ineligible_count"],3)
        self.assertEqual(b["max_simultaneous_eligible_opportunities"],3)
        self.assertEqual(s["max_simultaneous_eligible_opportunities"],2)
        self.assertEqual(b["eligible_opportunities_with_overlap"],4)
        self.assertEqual(s["eligible_opportunities_with_overlap"],2)
        self.assertIsNone(out["funded_equity"])
        self.assertIsNone(out["drawdown"])
        self.assertIsNone(out["common_cash_account"])
        self.assertIsNone(out["leverage_assumption"])

    def test_exit_before_entry_at_same_clock_does_not_create_false_overlap(self):
        out=run(fixture())
        rows=out["cohorts"][0]["arms"]["SHADOW"]["opportunities"]
        first=next(x for x in rows if x["eligible"] and
                   x["entry_open_ms"]==BAR_MS)
        self.assertFalse(first["overlaps_other_eligible_opportunity"])
        late=[x for x in rows if x["eligible"] and
              x["entry_open_ms"]==11*BAR_MS]
        self.assertEqual(len(late),2)
        self.assertTrue(all(x["overlapping_partner_count"]==1 for x in late))
        events=out["cohorts"][0]["arms"]["SHADOW"]["overlap_timeline"]
        at_time=[x["event"] for x in events if x["at_ms"]==11*BAR_MS]
        self.assertEqual(at_time[0],"MODELED_EXIT_BOUNDARY")

    def test_independent_opportunity_time_exposure_integral(self):
        b=run(fixture())["cohorts"][0]["arms"]["BASE"]["summary"]
        self.assertEqual(b["concurrent_opportunity_unit_ms"],40*BAR_MS)
        self.assertEqual(b["any_eligible_active_ms"],20*BAR_MS)
        self.assertEqual(b["two_or_more_eligible_active_ms"],16*BAR_MS)
        self.assertEqual(b["eligible_count_time_average_over_cohort"],"0.8")
        self.assertIsNone(b["cash_ledger"])
        self.assertIsNone(b["funded_portfolio_drawdown"])

    def test_rejected_unknown_and_no_signal_remain_null_not_skipped_or_zero(self):
        out=run(fixture())
        b=out["cohorts"][0]["arms"]["BASE"]
        s=out["cohorts"][0]["arms"]["SHADOW"]
        self.assertEqual(b["summary"]["dispositions"]["NO_SIGNAL"],1)
        self.assertEqual(b["summary"]["dispositions"]["UNKNOWN"],1)
        self.assertEqual(s["summary"]["dispositions"]["REJECTED"],1)
        self.assertEqual(s["summary"]["dispositions"]["UNKNOWN"],1)
        self.assertTrue(all(x["modeled_net_unit_return"] is None
                            for x in b["opportunities"] if not x["eligible"]))
        self.assertTrue(all(x["overlaps_other_eligible_opportunity"] is None
                            for x in s["opportunities"] if not x["eligible"]))
        self.assertEqual(len(out["cohorts"][0]["paired_comparison"]),6)
        self.assertTrue(any(x["shadow_minus_base_unit_return"] is None
                            for x in out["cohorts"][0]["paired_comparison"]))

    def test_distribution_is_conditional_not_funded_equity(self):
        b=run(fixture())["cohorts"][0]["arms"]["BASE"]["summary"]
        self.assertEqual(b["complete_modeled_count"],4)
        self.assertEqual(b["positive_net_complete_count"],3)
        self.assertEqual(b["negative_net_complete_count"],1)
        self.assertEqual(b["modeled_net_min_complete_only"],"-0.053")
        self.assertEqual(b["modeled_net_max_complete_only"],"0.017")
        self.assertIsNotNone(b["modeled_net_median_nearest_rank_complete_only"])
        self.assertNotIn("terminal_realized_cash_equity",b)

    def test_negative_previously_observed_returns_do_not_drive_policy_tuning(self):
        inp=fixture(negative=True)
        out=run(inp)
        self.assertEqual(out["policy_artifact_sha256"],inp[1]["artifact_sha256"])
        self.assertEqual(out["scientific_acceptance"],"NOT_OBTAINED")
        self.assertEqual(out["alpha_claim"],"NOT_ESTABLISHED")

    def test_null_only_cohort_has_no_arbitrary_return_or_overlap(self):
        out=run(fixture(no_triggers=True))
        for arm in ("BASE","SHADOW"):
            s=out["cohorts"][0]["arms"][arm]["summary"]
            self.assertEqual(s["complete_modeled_count"],0)
            self.assertEqual(s["max_simultaneous_eligible_opportunities"],0)
            self.assertEqual(s["two_or_more_eligible_active_ms"],0)
            self.assertIsNone(s["modeled_net_mean_complete_only"])
            self.assertIsNone(s["modeled_net_median_nearest_rank_complete_only"])

    def test_separate_source_cohorts_no_cross_month_stitch(self):
        f=fixture()
        a=fixture(other_month=True)
        out=run((f[0]+a[0],f[1],{**f[2],**a[2]}))
        self.assertEqual(len(out["cohorts"]),2)
        self.assertEqual(out["total_pair_denominator"],12)
        self.assertEqual(out["total_arm_slots"],24)
        self.assertEqual(out["source_cohort_handling"],
                         "SEPARATE_NO_CROSS_MONTH_STITCH")

    def test_determinism_and_immutable_parent(self):
        inp=fixture()
        saved=deepcopy(inp)
        out=run(inp)
        self.assertEqual(out,run(inp))
        self.assertEqual(inp,saved)
        raw=canonical_opportunity_receipt_bytes(out)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw_opportunity_receipt_sha256(out),sha256(raw).hexdigest())
        self.assertIn("No common capital",render_opportunity_research_report(out))

    def test_real_execution_blocked_without_independent_anchor(self):
        inp=fixture()
        with self.assertRaisesRegex(LabContractError,"INDEPENDENT_OWNER_C_AND_PRE_SCORE_ANCHOR_REQUIRED"):
            build_independent_opportunity_package(*inp)
        with self.assertRaisesRegex(LabContractError,"INDEPENDENT_OWNER_C_AND_PRE_SCORE_ANCHOR_REQUIRED"):
            build_independent_opportunity_package(
                *inp,owner_decision_verified=True,before_scoring_anchor_verified=True,
                independent_parent_receipts_verified=True)

    def test_policy_tamper_and_rehash_fail_closed(self):
        r,p,b=fixture()
        p["position_cap"]="1"
        with self.assertRaisesRegex(LabContractError,"OPTION_C_POLICY_DIGEST_MISMATCH"):
            run((r,p,b))
        p=sealed(p)
        with self.assertRaisesRegex(LabContractError,"OPTION_C_POLICY_CHANGED_OR_UNAPPROVED"):
            run((r,p,b))

    def test_parent_price_rehash_cannot_forge_returns(self):
        r,p,b=fixture()
        row=r[0]["modeled_trades"][0]
        row["modeled_net_return"]="999"
        r[0]=sealed(r[0])
        with self.assertRaisesRegex(LabContractError,"PARENT_MODELED_RETURN_MISMATCH"):
            run((r,p,b))

    def test_parent_hash_and_cost_contract_fail(self):
        r,p,b=fixture()
        r[0]["modeled_cost_round_trip_bps"]="20"
        with self.assertRaisesRegex(LabContractError,"INVALID_PARENT_MODELED_TRADE_RECEIPT"):
            run((r,p,b))
        r,p,b=fixture()
        r[0]["modeled_cost_round_trip_bps"]="20"
        r[0]=sealed(r[0])
        with self.assertRaisesRegex(LabContractError,"PARENT_TRADE_CONTRACT_OR_LINEAGE_MISMATCH"):
            run((r,p,b))

    def test_null_forged_model_return_rejected(self):
        r,p,b=fixture()
        row=next(x for x in r[0]["modeled_trades"]
                 if x["disposition"]=="UNKNOWN")
        row["modeled_net_return"]="0"
        r[0]=sealed(r[0])
        with self.assertRaisesRegex(LabContractError,"NULL_ARM_PROMOTED_TO_TRADE"):
            run((r,p,b))

    def test_duplicate_or_missing_pair_arm_rejected(self):
        r,p,b=fixture()
        r[0]["modeled_trades"][1]["arm"]="BASE"
        r[0]=sealed(r[0])
        with self.assertRaisesRegex(LabContractError,"DUPLICATE_OR_UNVERIFIED_PARENT_ARM"):
            run((r,p,b))
        r,p,b=fixture()
        r[0]["modeled_trades"].pop()
        r[0]=sealed(r[0])
        with self.assertRaisesRegex(LabContractError,"PARENT_SOURCE_OR_PAIRED_DENOMINATOR_MISMATCH"):
            run((r,p,b))

    def test_cross_cohort_forged_time_rejected(self):
        r,p,b=fixture()
        b["TEST_ONLY_FEB"]["end_exclusive_ms"]=10*BAR_MS
        with self.assertRaisesRegex(LabContractError,"CROSS_COHORT_OR_OFF_GRID_MODELED_OPPORTUNITY"):
            run((r,p,b))

    def test_same_pair_price_divergence_rejected(self):
        r,p,b=fixture()
        row=next(x for x in r[0]["modeled_trades"]
                 if x["arm"]=="SHADOW" and x["disposition"]=="TRIGGERED")
        row["exit_open"]="103"
        row["modeled_gross_return"]="0.03"
        row["modeled_net_return"]="0.027"
        r[0]=sealed(r[0])
        with self.assertRaisesRegex(LabContractError,"SAME_PAIR_ARMS_MODEL_PRICE_DRIFT"):
            run((r,p,b))

    def test_no_source_disguised_as_test_only(self):
        r,p,b=fixture()
        old=r[0]["source_id"]
        r[0]["source_id"]="REAL_BINANCE_2024"
        r[0]=sealed(r[0])
        b["REAL_BINANCE_2024"]=b.pop(old)
        b["REAL_BINANCE_2024"]["source_id"]="REAL_BINANCE_2024"
        with self.assertRaisesRegex(LabContractError,"REAL_SOURCE_CANNOT_BE_CALLED_TEST_ONLY"):
            run((r,p,b))

    def test_receipt_tamper_rejected(self):
        out=run(fixture())
        out["cohorts"][0]["arms"]["BASE"]["summary"]["complete_modeled_count"]=0
        with self.assertRaisesRegex(LabContractError,"BAD_INDEPENDENT_OPPORTUNITY_RECEIPT"):
            canonical_opportunity_receipt_bytes(out)
