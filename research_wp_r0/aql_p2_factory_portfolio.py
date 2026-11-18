"""AQL-P2-PORTFOLIO-001 Option C: independent overlapping opportunity research.

Owner C approval #77/6603278584 supersedes the never-approved full-cash
single-position proposal. This is NOT a funded portfolio or order backtester.
Consumes exact original immutable Factory 10-bar model outcomes and retains all
NO_SIGNAL, REJECTED, UNKNOWN, CENSORED without zero-imputation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json

from research_wp_r0.aql_p2_factory_lab import digest, hash_ok
from research_wp_r0.aql_p2_factory_real_development import BAR_MS, dec, fail

RULE = "ALL_INDEPENDENT_ELIGIBLE_OVERLAPS_INCLUDED_V1"
POLICY_SCHEMA = "aql.p2.factory.independent-opportunity-policy.v1"
REPORT_SCHEMA = "aql.p2.factory.independent-opportunity-study.v1"
PARENT_SCHEMA = "aql.p2.factory.breakout-modeled-trades.v1"
OWNER_C_URL = (
    "https://github.com/scannercrypto0-gif/super-kumo-v8/"
    "issues/77#issuecomment-6603278584"
)
COST_PER_RAW_ENTRY = Decimal("0.003")
DISPOSITIONS = ("TRIGGERED", "NO_SIGNAL", "REJECTED", "UNKNOWN")


def frozen_option_c_policy():
    """Already owner-approved C *rule*, not a claim of temporal prereg of data."""
    policy = {
        "schema": POLICY_SCHEMA,
        "decision_id": "AQL-P2-PORTFOLIO-001-OPTION-C",
        "owner_decision_url": OWNER_C_URL,
        "approval_status": "OWNER_APPROVED_PROVISIONAL",
        "policy_rule": RULE,
        "source": "EXISTING_PINNED_FACTORY_TEN_BAR_REPORTS_ONLY",
        "eligibility": "EACH_TRIGGERED_MODELED_COMPLETE_LONG_INDEPENDENTLY",
        "overlaps": "KEEP_EVERY_ELIGIBLE_OPPORTUNITY_NO_ARBITRATION",
        "capital_account": "NONE",
        "allocation_budget": "NONE",
        "position_cap": "NONE",
        "leverage_assumption": "NONE",
        "occupied_signal_behavior": "NOT_APPLICABLE_NO_SHARED_POSITION",
        "model_entry_exit": "ORIGINAL_OPEN_I_PLUS_1_TO_OPEN_I_PLUS_11",
        "modeled_cost": "FROZEN_ADDITIVE_30BPS_PER_RAW_ENTRY_NO_REPRICING",
        "outcomes": "MODEL_ONLY_PER_OPPORTUNITY_UNIT_RETURN_DISTRIBUTION",
        "overlap_clock": "HALF_OPEN_INTERVAL_EXIT_BEFORE_SAME_TIME_ENTRY",
        "cohort_boundary": "SEPARATE_MONTHS_NO_CROSS_COHORT_POOLING",
        "nulls": "RETAIN_ALL_NO_SIGNAL_REJECTED_UNKNOWN_CENSORED_AS_NULL",
        "aggregation": "DESCRIPTIVE_COUNTS_MEDIAN_MEANS_NO_FUNDED_EQUITY",
        "portfolio_equity_drawdown_cashflow": "NOT_APPLICABLE_NOT_FUNDED",
        "trial_relation": "EXPLORATORY_AFTER_PRIOR_TRADE_OUTCOMES_EXPOSED",
        "pit_oos_alpha": "NOT_CLAIMED",
        "holdout_status": "SEALED_UNOPENED",
    }
    policy["artifact_sha256"] = digest(policy)
    return policy


def _canonical_hash_valid(obj, key="artifact_sha256"):
    return isinstance(obj, dict) and hash_ok(obj.get(key)) and digest({
        k: v for k, v in obj.items() if k != key
    }) == obj[key]


def _validate_policy(policy):
    if not _canonical_hash_valid(policy):
        fail("OPTION_C_POLICY_DIGEST_MISMATCH")
    if policy != frozen_option_c_policy():
        fail("OPTION_C_POLICY_CHANGED_OR_UNAPPROVED")
    return policy["artifact_sha256"]


def canonical_option_c_policy_bytes(policy):
    """Exact metadata-only byte form published as the GitHub pre-score artifact."""
    _validate_policy(policy)
    return (json.dumps(policy, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def raw_option_c_policy_sha256(policy):
    return sha256(canonical_option_c_policy_bytes(policy)).hexdigest()


def _validate_parent(report):
    if not _canonical_hash_valid(report) or report.get("schema") != PARENT_SCHEMA:
        fail("INVALID_PARENT_MODELED_TRADE_RECEIPT")
    if (report.get("scope") != "RETROSPECTIVE_NON_PIT_DEVELOPMENT_ONLY"
        or report.get("execution_status") != "NOT_OBSERVED"
        or report.get("holdout_status") != "SEALED_UNOPENED"
        or report.get("pit_status") != "NOT_ATTESTED"
        or report.get("oos_status") != "NOT_ATTESTED"
        or report.get("modeled_exit_spec") != "NEXT_OPEN_I_PLUS_1_EXIT_OPEN_I_PLUS_11_V1"
        or dec(report.get("modeled_cost_round_trip_bps")) != Decimal(30)
        or any(not hash_ok(report.get(k)) for k in (
            "source_schedule_sha256", "source_package_sha256",
            "preregistration_artifact_sha256", "cost_model_artifact_sha256",
            "descriptive_4_24_72h_artifact_sha256"))):
        fail("PARENT_TRADE_CONTRACT_OR_LINEAGE_MISMATCH")
    sid = report.get("source_id")
    n = report.get("pair_count")
    rows = report.get("modeled_trades")
    comparisons = report.get("paired_comparison")
    if (not isinstance(sid, str) or not sid or type(n) is not int or n < 1
        or not isinstance(rows, list) or len(rows) != 2*n
        or report.get("arm_count") != 2*n
        or not isinstance(comparisons, list) or len(comparisons) != n):
        fail("PARENT_SOURCE_OR_PAIRED_DENOMINATOR_MISMATCH")
    keyed = {}
    for r in rows:
        if not isinstance(r, dict):
            fail("BAD_PARENT_TRADE_ROW")
        pid, arm = r.get("pair_id"), r.get("arm")
        key = (pid, arm)
        if (not hash_ok(pid) or arm not in ("BASE", "SHADOW")
            or key in keyed
            or not hash_ok(r.get("arm_decision_sha256"))
            or not hash_ok(r.get("four_hour_source_window_sha256"))
            or r.get("execution_status") != "NOT_OBSERVED"
            or r.get("cost_class") != "MODEL_ONLY_NOT_EXECUTION"
            or r.get("fee_bps") != "20" or r.get("slippage_bps") != "10"):
            fail("DUPLICATE_OR_UNVERIFIED_PARENT_ARM")
        state = r.get("disposition")
        if state not in DISPOSITIONS:
            fail("BAD_PARENT_ARM_DISPOSITION")
        if state == "TRIGGERED":
            if (r.get("status") != "MODELED_COMPLETE"
                or r.get("modeled_trade_availability") != "COMPLETE"
                or r.get("holding_period_bars") != 10
                or r.get("missingness_reason") is not None
                or r.get("fee_entry_return") != "0.001"
                or r.get("fee_exit_return") != "0.001"
                or r.get("slippage_entry_return") != "0.0005"
                or r.get("slippage_exit_return") != "0.0005"
                or type(r.get("entry_open_ms")) is not int
                or type(r.get("exit_open_ms")) is not int
                or r["exit_open_ms"] - r["entry_open_ms"] != 10*BAR_MS):
                fail("MODELED_ENTRY_EXIT_OR_COST_DRIFT")
            entry, exit_ = dec(r.get("entry_open")), dec(r.get("exit_open"))
            if entry <= 0 or exit_ <= 0:
                fail("NONPOSITIVE_PARENT_PRICE")
            gross = exit_ / entry - Decimal(1)
            net = gross - COST_PER_RAW_ENTRY
            if (dec(r.get("modeled_gross_return")) != gross
                or dec(r.get("modeled_net_return")) != net):
                fail("PARENT_MODELED_RETURN_MISMATCH")
            if (r.get("modeled_gross_pnl_per_base_unit") is not None and
                dec(r["modeled_gross_pnl_per_base_unit"]) != exit_ - entry):
                fail("PARENT_GROSS_UNIT_PNL_MISMATCH")
            if (r.get("modeled_net_pnl_per_base_unit") is not None and
                dec(r["modeled_net_pnl_per_base_unit"]) != (exit_ - entry) -
                entry*COST_PER_RAW_ENTRY):
                fail("PARENT_NET_UNIT_PNL_MISMATCH")
        else:
            if (r.get("status") != ("UNKNOWN" if state == "UNKNOWN" else "INELIGIBLE")
                or any(r.get(k) is not None for k in (
                    "modeled_gross_return", "modeled_net_return", "entry_open",
                    "exit_open"))):
                fail("NULL_ARM_PROMOTED_TO_TRADE")
        keyed[key] = r
    pids = {k[0] for k in keyed}
    if len(pids) != n:
        fail("INCOMPLETE_PAIR_SET")
    comparison_ids = set()
    for c in comparisons:
        if not isinstance(c, dict):
            fail("BAD_PARENT_PAIR_COMPARISON")
        pid = c.get("pair_id")
        if pid in comparison_ids or pid not in pids:
            fail("MISSING_OR_DUPLICATE_PAIR_COMPARISON")
        b, s = keyed[(pid, "BASE")], keyed[(pid, "SHADOW")]
        complete = (b["disposition"] == "TRIGGERED"
                    and s["disposition"] == "TRIGGERED")
        if (c.get("base_disposition") != b["disposition"]
            or c.get("shadow_disposition") != s["disposition"]
            or c.get("both_modeled_complete") is not complete):
            fail("PAIR_COMPARISON_PARENT_DRIFT")
        if complete and any(b[k] != s[k] for k in (
            "entry_open_ms", "exit_open_ms", "entry_open", "exit_open")):
            fail("SAME_PAIR_ARMS_MODEL_PRICE_DRIFT")
        comparison_ids.add(pid)
    if comparison_ids != pids:
        fail("UNPAIRED_SOURCE_DECISIONS")
    return keyed


def _check_bounds(report, bounds):
    if (not isinstance(bounds, dict)
        or bounds.get("source_id") != report["source_id"]
        or bounds.get("source_package_sha256") != report["source_package_sha256"]
        or type(bounds.get("start_ms")) is not int
        or type(bounds.get("end_exclusive_ms")) is not int
        or bounds["end_exclusive_ms"] <= bounds["start_ms"]
        or (bounds["end_exclusive_ms"] - bounds["start_ms"]) % BAR_MS != 0):
        fail("SOURCE_COHORT_BOUNDARY_OR_PIN_MISMATCH")
    return bounds["start_ms"], bounds["end_exclusive_ms"]


def _quantile_nearest_rank(values, percent):
    if not values:
        return None
    n = len(values)
    # transparent nearest-rank, no inference of independent observations.
    idx = max(0, (n*percent + 99)//100 - 1)
    return str(values[idx])


def _arm_study(report, arm, keyed, start, end):
    decisions, completed = [], []
    intervals = {}
    for (pid, a), r in keyed.items():
        if a != arm:
            continue
        record = {
            "pair_id": pid, "arm": arm, "source_id": report["source_id"],
            "arm_decision_sha256": r["arm_decision_sha256"],
            "four_hour_source_window_sha256": r["four_hour_source_window_sha256"],
            "original_signal_disposition": r.get("signal_disposition"),
            "original_disposition": r["disposition"],
            "original_status": r["status"],
            "original_censored": r.get("censored"),
            "original_missingness_reason": r.get("missingness_reason"),
            "eligible": r["disposition"] == "TRIGGERED",
            "entry_open_ms": r.get("entry_open_ms") if r["disposition"] == "TRIGGERED" else None,
            "exit_open_ms": r.get("exit_open_ms") if r["disposition"] == "TRIGGERED" else None,
            "modeled_gross_unit_return": r.get("modeled_gross_return"),
            "modeled_net_unit_return": r.get("modeled_net_return"),
            "overlaps_other_eligible_opportunity": None,
            "overlapping_partner_count": None,
            "account_cash": None, "funded_equity": None,
            "execution_status": "NOT_OBSERVED",
        }
        if record["eligible"]:
            entry_ms, exit_ms = r["entry_open_ms"], r["exit_open_ms"]
            if (not start <= entry_ms < exit_ms < end
                or (entry_ms-start) % BAR_MS or (exit_ms-start) % BAR_MS):
                fail("CROSS_COHORT_OR_OFF_GRID_MODELED_OPPORTUNITY")
            completed.append(record)
            intervals[pid] = (entry_ms, exit_ms)
        decisions.append(record)
    decisions.sort(key=lambda x:x["pair_id"])
    if len(decisions) != report["pair_count"]:
        fail("ARM_SCHEDULED_OPPORTUNITY_DENOMINATOR_LOST")

    # Exact half-open intervals [entry,exit): a closing trade at t does not
    # overlap a new one beginning at the very same t.
    events = []
    for pid,(begin,finish) in intervals.items():
        events.extend([(begin,1,pid),(finish,0,pid)])  # exit (0) first
    events.sort(key=lambda x:(x[0],x[1],x[2]))
    active = set()
    partners = defaultdict(set)
    prev = start
    exposure_ms, concurrent_unit_ms, overlap_ms, maximum = 0,0,0,0
    timeline = []
    for t,kind,pid in events:
        if t < prev or t > end:
            fail("BAD_OPPORTUNITY_SWEEP_TIME")
        delta = t-prev
        if active:
            exposure_ms += delta
        concurrent_unit_ms += len(active)*delta
        if len(active)>1:
            overlap_ms += delta
        prev=t
        if kind==0:
            if pid not in active:
                fail("ORPHAN_EXIT_EVENT")
            active.remove(pid)
        else:
            for other in active:
                partners[pid].add(other)
                partners[other].add(pid)
            active.add(pid)
            maximum=max(maximum,len(active))
        timeline.append({
            "at_ms": t,
            "event": "MODELED_EXIT_BOUNDARY" if kind==0 else "MODELED_ENTRY_BOUNDARY",
            "pair_id": pid, "concurrent_after_event": len(active),
            "cash_ledger": None, "execution_status": "NOT_OBSERVED",
        })
    if active:
        fail("UNCLOSED_MODELED_OPPORTUNITY")
    for row in decisions:
        if row["eligible"]:
            row["overlapping_partner_count"] = len(partners[row["pair_id"]])
            row["overlaps_other_eligible_opportunity"] = bool(partners[row["pair_id"]])
    values = sorted(dec(r["modeled_net_unit_return"]) for r in completed)
    gross = sorted(dec(r["modeled_gross_unit_return"]) for r in completed)
    disposition_counts = Counter(r["original_disposition"] for r in decisions)
    if sum(disposition_counts.values()) != report["pair_count"]:
        fail("BAD_DISPOSITION_CENSUS")
    summary = {
        "arm": arm, "scheduled_pair_denominator": report["pair_count"],
        "dispositions": {x:disposition_counts[x] for x in DISPOSITIONS},
        "complete_modeled_count": len(completed),
        "null_or_ineligible_count": report["pair_count"]-len(completed),
        "modeled_net_mean_complete_only": str(sum(values)/len(values)) if values else None,
        "modeled_net_median_nearest_rank_complete_only":
            _quantile_nearest_rank(values,50),
        "modeled_net_p25_nearest_rank_complete_only": _quantile_nearest_rank(values,25),
        "modeled_net_p75_nearest_rank_complete_only": _quantile_nearest_rank(values,75),
        "modeled_net_min_complete_only": str(values[0]) if values else None,
        "modeled_net_max_complete_only": str(values[-1]) if values else None,
        "modeled_gross_mean_complete_only": str(sum(gross)/len(gross)) if gross else None,
        "positive_net_complete_count": sum(v>0 for v in values),
        "zero_net_complete_count": sum(v==0 for v in values),
        "negative_net_complete_count": sum(v<0 for v in values),
        "eligible_opportunities_with_overlap": sum(bool(partners[x["pair_id"]])
                                                   for x in completed),
        "max_simultaneous_eligible_opportunities": maximum,
        "any_eligible_active_ms": exposure_ms,
        "two_or_more_eligible_active_ms": overlap_ms,
        "concurrent_opportunity_unit_ms": concurrent_unit_ms,
        "eligible_count_time_average_over_cohort":
            str(Decimal(concurrent_unit_ms)/Decimal(end-start)),
        "funded_portfolio_equity": None,
        "funded_portfolio_drawdown": None,
        "cash_ledger": None,
        "interpretation": "DEPENDENT_OVERLAPPING_UNIT_RETURNS_NO_FUNDED_PORTFOLIO_OR_ALPHA",
    }
    if len(timeline)!=2*len(completed):
        fail("BAD_CONCURRENCY_EVENT_DENOMINATOR")
    return {
        "arm": arm, "opportunities": decisions, "overlap_timeline": timeline,
        "summary": summary,
    }


def build_independent_opportunity_package(trade_reports, policy, cohort_bounds, *,
                                          test_only=False,
                                          owner_decision_verified=False,
                                          before_scoring_anchor_verified=False,
                                          independent_parent_receipts_verified=False,
                                          policy_anchor_raw_sha256=None):
    """Owner C, no capital budget. Independent Work proof needed for real inputs."""
    before=deepcopy(trade_reports)
    policy_sha=_validate_policy(policy)
    if test_only is not True:
        if (owner_decision_verified is not True
            or before_scoring_anchor_verified is not True
            or independent_parent_receipts_verified is not True
            or not hash_ok(policy_anchor_raw_sha256)):
            fail("INDEPENDENT_OWNER_C_AND_PRE_SCORE_ANCHOR_REQUIRED")
        if policy_anchor_raw_sha256 != raw_option_c_policy_sha256(policy):
            fail("FROZEN_OPTION_C_ANCHOR_BYTES_MISMATCH")
    if not isinstance(trade_reports,list) or not trade_reports:
        fail("MISSING_PARENT_REPORTS")
    if not isinstance(cohort_bounds,dict):
        fail("MISSING_SOURCE_BOUNDARIES")
    result_rows=[]
    seen=set()
    for report in sorted(trade_reports,key=lambda r:r.get("source_id","")):
        keyed=_validate_parent(report)
        sid=report["source_id"]
        if test_only and not sid.startswith("TEST_ONLY_"):
            fail("REAL_SOURCE_CANNOT_BE_CALLED_TEST_ONLY")
        if test_only is not True and sid.startswith("TEST_ONLY_"):
            fail("TEST_ONLY_SOURCE_FORBIDDEN_IN_REAL_SCORING")
        if sid in seen or sid not in cohort_bounds:
            fail("DUPLICATE_OR_UNBOUND_SOURCE_COHORT")
        seen.add(sid)
        start,end=_check_bounds(report,cohort_bounds[sid])
        arms={name:_arm_study(report,name,keyed,start,end)
              for name in ("BASE","SHADOW")}
        compared=[]
        for pid in sorted({k[0] for k in keyed}):
            b,s=keyed[(pid,"BASE")],keyed[(pid,"SHADOW")]
            common=b["disposition"]=="TRIGGERED" and s["disposition"]=="TRIGGERED"
            delta=(str(dec(s["modeled_net_return"])-dec(b["modeled_net_return"]))
                   if common else None)
            if common and dec(delta)!=0:
                fail("PAIRED_IDENTICAL_TRADE_PRICE_WITH_NONZERO_DELTA")
            compared.append({
                "pair_id":pid, "base_disposition":b["disposition"],
                "shadow_disposition":s["disposition"],
                "paired_complete":common, "shadow_minus_base_unit_return":delta,
                "filtered_arm_outcome":None if s["disposition"]!="TRIGGERED"
                                     else s["modeled_net_return"],
            })
        result_rows.append({
            "source_id":sid,"source_package_sha256":report["source_package_sha256"],
            "parent_trade_report_sha256":report["artifact_sha256"],
            "original_source_schedule_sha256":report["source_schedule_sha256"],
            "start_ms":start,"end_exclusive_ms":end,
            "pair_count":report["pair_count"],"arms":arms,
            "paired_comparison":compared,
            "paired_evidence_class":"DESCRIPTIVE_SELECTED_POPULATIONS_NOT_CAUSAL_EFFECT",
        })
    if seen!=set(cohort_bounds):
        fail("UNUSED_OR_MISSING_SOURCE_BOUNDARY")
    if trade_reports!=before:
        fail("MUTATED_PARENT_REPORT")
    out={
        "schema":REPORT_SCHEMA,"owner_decision_url":OWNER_C_URL,
        "policy_artifact_sha256":policy_sha,
        "policy_anchor_raw_sha256":policy_anchor_raw_sha256,
        "scope":"EXPLORATORY_INDEPENDENT_OVERLAPPING_DEVELOPMENT_OPPORTUNITIES",
        "evidence_class":("TEST_ONLY_SYNTHETIC" if test_only else
                          "RETROSPECTIVE_NON_PIT_SOURCE_BACKED_IF_EXTERNALLY_VERIFIED"),
        "cohorts":result_rows,
        "source_cohort_handling":"SEPARATE_NO_CROSS_MONTH_STITCH",
        "total_pair_denominator":sum(x["pair_count"] for x in result_rows),
        "total_arm_slots":sum(2*x["pair_count"] for x in result_rows),
        "common_cash_account":None,"funded_equity":None,"drawdown":None,
        "leverage_assumption":None,"position_cap":None,
        "execution_status":"NOT_OBSERVED","holdout_status":"SEALED_UNOPENED",
        "pit_status":"NOT_ATTESTED","oos_status":"NOT_ATTESTED",
        "alpha_claim":"NOT_ESTABLISHED",
        "scientific_acceptance":"NOT_OBTAINED",
    }
    out["artifact_sha256"]=digest(out)
    return out


def canonical_opportunity_receipt_bytes(report):
    if not _canonical_hash_valid(report) or report.get("schema")!=REPORT_SCHEMA:
        fail("BAD_INDEPENDENT_OPPORTUNITY_RECEIPT")
    return (json.dumps(report,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)+"\n").encode("utf-8")


def raw_opportunity_receipt_sha256(report):
    return sha256(canonical_opportunity_receipt_bytes(report)).hexdigest()


def render_opportunity_research_report(report):
    canonical_opportunity_receipt_bytes(report)
    lines=["# ATLAS P2 — Option C independent overlapping opportunity research","",
           "No common capital, position cap, leverage, cash, funded equity, or feasible drawdown.",
           "Already exposed retrospective NON_PIT development only; no alpha/PIT/OOS claim.",
           "FROZEN BASE/SHADOW next-open/i+11 30bps model-only results, independent opportunities.","",
           "| Source cohort | Arm | Scheduled | Eligible | NULL | Mean net on eligible only | Max concurrent | Eligible with overlaps |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for cohort in report["cohorts"]:
        for arm in ("BASE","SHADOW"):
            s=cohort["arms"][arm]["summary"]
            lines.append(f"| {cohort['source_id']} | {arm} | {s['scheduled_pair_denominator']} | {s['complete_modeled_count']} | {s['null_or_ineligible_count']} | {s['modeled_net_mean_complete_only']} | {s['max_simultaneous_eligible_opportunities']} | {s['eligible_opportunities_with_overlap']} |")
    lines.extend(["","Overlapping signals are counted as dependent research opportunities, NOT simultaneously funded positions.",
                  "No exploratory strategy promotion, no real execution, no G0, holdout or scientific acceptance.",""])
    return "\n".join(lines)
