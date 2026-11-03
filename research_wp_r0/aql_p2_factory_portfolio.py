"""AQL-P2-PORTFOLIO-001: independent offline capital-ledger consumer.

Consumes immutable Factory ten-bar *modeled* returns. No signal generation,
market-data access, execution venue, or portfolio-policy auto-approval.
Current policy is a PROPOSAL; only synthetic TEST_ONLY cases may run until a
distinct owner approval and independent pre-score policy anchor are verified.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json

from research_wp_r0.aql_p2_factory_lab import digest, hash_ok
from research_wp_r0.aql_p2_factory_real_development import BAR_MS, dec, fail

RULE = "P2_OFFLINE_SINGLE_POSITION_FULL_CASH_V1"
MODEL_COST = Decimal("0.003")
CANDIDATE_STATUSES = ("NO_SIGNAL", "REJECTED", "UNKNOWN", "TRIGGERED")
SOURCE_SCHEMA = "aql.p2.factory.breakout-modeled-trades.v1"
POLICY_SCHEMA = "aql.p2.factory.portfolio-policy.v1"
REPORT_SCHEMA = "aql.p2.factory.offline-portfolio.v1"


def seal(obj):
    result = deepcopy(obj)
    result["artifact_sha256"] = digest(result)
    return result


def propose_portfolio_policy(initial_capital="10000"):
    """Candidate envelope: NOT an owner approval or a retroactive prereg."""
    cash = dec(initial_capital)
    if cash <= 0:
        fail("BAD_INITIAL_CAPITAL")
    return seal({
        "schema": POLICY_SCHEMA,
        "research_scope": "EXPLORATORY_PORTFOLIO_SEPARATE_FROM_FROZEN_P2_TRIAL",
        "policy_rule": RULE,
        "approval_status": "PROPOSED_NOT_OWNER_APPROVED",
        "test_only": False,
        "owner_approval_url": None,
        "pre_score_anchor_receipt_sha256": None,
        "initial_capital": str(cash),
        "max_open_positions": 1,
        "leverage": "1",
        "allocation": "FULL_AVAILABLE_CASH_NORMALIZED_MODELED_ENTRY",
        "cash_constraint": "ONE_POSITION_100_PERCENT_RESERVED_DURING_HOLD",
        "occupied_signal": "SKIP_AND_PRESERVE_ORIGINAL_SIGNAL",
        "tie_break": "PAIR_ID_ASCENDING_AT_SAME_ENTRY_TIME",
        "same_clock_order": "EXIT_BEFORE_ENTRY",
        "modeled_exit": "OPEN_I_PLUS_11_AFTER_TEN_BARS",
        "modeled_cost_method": "FROZEN_ADDITIVE_GROSS_MINUS_30BPS_ON_ENTRY_NOTIONAL",
        "entry_fee_accounting": "MODEL_ONLY_DEFERRED_TO_EXIT_SETTLEMENT_NO_REAL_FEE_CASHFLOW",
        "mark_to_market": "NOT_AVAILABLE_REALIZED_SETTLEMENT_EQUITY_ONLY",
        "cohorts": "SEPARATE_RESET_INITIAL_CAPITAL_NO_CROSS_MONTH_STITCH",
        "source_evidence": "SOURCE_BACKED_ONLY_IF_PARENT_REPORT_INDEPENDENTLY_VERIFIED",
        "holdout_status": "SEALED_UNOPENED",
    })


def _validate_policy(policy, *, test_only, approval_verified, pre_score_anchor_verified):
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        fail("MISSING_FROZEN_PORTFOLIO_POLICY")
    if not hash_ok(policy.get("artifact_sha256")) or digest({
        k: v for k, v in policy.items() if k != "artifact_sha256"
    }) != policy["artifact_sha256"]:
        fail("PORTFOLIO_POLICY_HASH_MISMATCH")
    proposed = propose_portfolio_policy(policy.get("initial_capital"))
    fixed = (
        "research_scope", "policy_rule", "initial_capital", "max_open_positions",
        "leverage", "allocation", "cash_constraint", "occupied_signal",
        "tie_break", "same_clock_order", "modeled_exit", "modeled_cost_method",
        "entry_fee_accounting", "mark_to_market", "cohorts",
        "source_evidence", "holdout_status",
    )
    if any(policy.get(x) != proposed[x] for x in fixed):
        fail("UNAPPROVED_PORTFOLIO_SEMANTIC_CHANGE")
    if test_only is True:
        if (policy.get("test_only") is not True
            or policy.get("approval_status") != "TEST_ONLY_SYNTHETIC"
            or policy.get("owner_approval_url") is not None
            or policy.get("pre_score_anchor_receipt_sha256") is not None):
            fail("TEST_ONLY_POLICY_REQUIRED")
    else:
        if (policy.get("test_only") is not False
            or policy.get("approval_status") != "OWNER_APPROVED_PROVISIONAL"
            or not isinstance(policy.get("owner_approval_url"), str)
            or not policy["owner_approval_url"].startswith(
                "https://github.com/scannercrypto0-gif/super-kumo-v8/issues/")
            or not hash_ok(policy.get("pre_score_anchor_receipt_sha256"))
            or approval_verified is not True
            or pre_score_anchor_verified is not True):
            fail("OWNER_PORTFOLIO_POLICY_APPROVAL_AND_PRE_SCORE_ANCHOR_REQUIRED")
    return dec(policy["initial_capital"])


def _validate_report(report):
    if not isinstance(report, dict) or report.get("schema") != SOURCE_SCHEMA:
        fail("UNSUPPORTED_PARENT_TRADE_REPORT")
    pin = report.get("artifact_sha256")
    if not hash_ok(pin) or digest({
        k: v for k, v in report.items() if k != "artifact_sha256"
    }) != pin:
        fail("PARENT_TRADE_REPORT_DIGEST_MISMATCH")
    if (report.get("scope") != "RETROSPECTIVE_NON_PIT_DEVELOPMENT_ONLY"
        or report.get("execution_status") != "NOT_OBSERVED"
        or report.get("holdout_status") != "SEALED_UNOPENED"
        or report.get("pit_status") != "NOT_ATTESTED"
        or report.get("oos_status") != "NOT_ATTESTED"
        or report.get("modeled_exit_spec") != "NEXT_OPEN_I_PLUS_1_EXIT_OPEN_I_PLUS_11_V1"
        or dec(report.get("modeled_cost_round_trip_bps")) != Decimal(30)
        or not hash_ok(report.get("source_schedule_sha256"))
        or not hash_ok(report.get("source_package_sha256"))
        or not hash_ok(report.get("preregistration_artifact_sha256"))
        or not hash_ok(report.get("cost_model_artifact_sha256"))
        or not hash_ok(report.get("descriptive_4_24_72h_artifact_sha256"))):
        fail("PARENT_TRADE_CONTRACT_MISMATCH")
    rows = report.get("modeled_trades")
    matches = report.get("paired_comparison")
    n = report.get("pair_count")
    if (not isinstance(n, int) or isinstance(n, bool) or n <= 0
        or not isinstance(rows, list) or len(rows) != 2 * n
        or report.get("arm_count") != 2 * n or not isinstance(matches, list)
        or len(matches) != n):
        fail("PARENT_PAIRED_DENOMINATOR_MISMATCH")
    observed = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("BAD_PARENT_TRADE_ROW")
        pid, arm = row.get("pair_id"), row.get("arm")
        k = (pid, arm)
        if (not hash_ok(pid) or arm not in ("BASE", "SHADOW")
            or k in observed or not hash_ok(row.get("arm_decision_sha256"))
            or not hash_ok(row.get("four_hour_source_window_sha256"))
            or row.get("execution_status") != "NOT_OBSERVED"):
            fail("BAD_OR_DUPLICATE_TRADE_PROVENANCE")
        disposition = row.get("disposition")
        status = row.get("status")
        if disposition not in CANDIDATE_STATUSES:
            fail("BAD_TRADE_DISPOSITION")
        if (row.get("cost_class") != "MODEL_ONLY_NOT_EXECUTION"
            or row.get("fee_bps") != "20"
            or row.get("slippage_bps") != "10"):
            fail("UNTRUSTED_PARENT_MODELED_COST_CLASS")
        if disposition == "TRIGGERED":
            if (status != "MODELED_COMPLETE" or row.get("modeled_trade_availability") != "COMPLETE"
                or row.get("missingness_reason") is not None
                or row.get("holding_period_bars") != 10
                or not isinstance(row.get("entry_open_ms"), int)
                or not isinstance(row.get("exit_open_ms"), int)
                or row["exit_open_ms"] - row["entry_open_ms"] != 10 * BAR_MS
                or row.get("fee_entry_return") != "0.001"
                or row.get("fee_exit_return") != "0.001"
                or row.get("slippage_entry_return") != "0.0005"
                or row.get("slippage_exit_return") != "0.0005"):
                fail("TRADE_MODELED_ENTRY_EXIT_OR_COST_DRIFT")
            entry, exit_ = dec(row.get("entry_open")), dec(row.get("exit_open"))
            if entry <= 0 or exit_ <= 0:
                fail("NONPOSITIVE_TRADE_PRICE")
            gross = exit_ / entry - 1
            net = gross - MODEL_COST
            if (dec(row.get("modeled_gross_return")) != gross
                or dec(row.get("modeled_net_return")) != net):
                fail("PARENT_TRADE_RETURN_MISMATCH")
        else:
            expected = "UNKNOWN" if disposition == "UNKNOWN" else "INELIGIBLE"
            if (status != expected or row.get("modeled_net_return") is not None
                or row.get("modeled_gross_return") is not None
                or row.get("entry_open") is not None or row.get("exit_open") is not None):
                fail("INELIGIBLE_TRADE_FABRICATED_RETURN")
        observed[k] = row
    if len(observed) != 2 * n:
        fail("INCOMPLETE_PARENT_ARM_DENOMINATOR")
    pairs = {k[0] for k in observed}
    pair_index = {}
    for m in matches:
        if not isinstance(m, dict) or m.get("pair_id") in pair_index:
            fail("DUPLICATE_PARENT_PAIR")
        pid = m.get("pair_id")
        if pid not in pairs:
            fail("UNKNOWN_PARENT_PAIR")
        base, shadow = observed[(pid, "BASE")], observed[(pid, "SHADOW")]
        if (m.get("base_disposition") != base["disposition"]
            or m.get("shadow_disposition") != shadow["disposition"]
            or m.get("both_modeled_complete") !=
              (base["status"] == "MODELED_COMPLETE" and shadow["status"] == "MODELED_COMPLETE")):
            fail("PARENT_PAIR_IDENTITY_MISMATCH")
        pair_index[pid] = m
    if set(pair_index) != pairs:
        fail("INCOMPLETE_PARENT_PAIR_COMPARISON")
    return observed


def _validate_bounds(report, bounds):
    if not isinstance(bounds, dict):
        fail("MISSING_COHORT_SOURCE_BOUNDS")
    sid = report["source_id"]
    if (bounds.get("source_id") != sid
        or bounds.get("source_package_sha256") != report["source_package_sha256"]
        or not isinstance(bounds.get("start_ms"), int)
        or not isinstance(bounds.get("end_exclusive_ms"), int)
        or bounds["start_ms"] >= bounds["end_exclusive_ms"]
        or (bounds["end_exclusive_ms"] - bounds["start_ms"]) % BAR_MS):
        fail("BAD_COHORT_BOUNDARY_OR_SOURCE_PIN")
    return bounds["start_ms"], bounds["end_exclusive_ms"]


def _arm_ledger(report, observed, arm, start, end, initial):
    selected, decisions, events = [], [], []
    candidates = []
    for (pid, name), row in observed.items():
        if name != arm:
            continue
        base = {
            "pair_id": pid, "arm": arm, "source_id": report["source_id"],
            "arm_decision_sha256": row["arm_decision_sha256"],
            "four_hour_source_window_sha256": row["four_hour_source_window_sha256"],
            "signal_disposition": row.get("signal_disposition"),
            "original_disposition": row["disposition"],
            "original_model_status": row["status"],
            "original_censored": row.get("censored"),
            "original_missingness_reason": row.get("missingness_reason"),
            "portfolio_action": None,
            "portfolio_reason": None,
        }
        if row["status"] != "MODELED_COMPLETE":
            base["portfolio_action"] = "NOT_ELIGIBLE"
            base["portfolio_reason"] = row["disposition"]
            decisions.append(base)
        else:
            if (not start <= row["entry_open_ms"] < row["exit_open_ms"] < end
                or (row["entry_open_ms"] - start) % BAR_MS != 0):
                fail("CROSS_COHORT_TRADE_OR_NON_GRID_TIME")
            candidates.append((row["entry_open_ms"], pid, row, base))
    candidates.sort(key=lambda x: (x[0], x[1]))
    cash = initial
    current_exit = None
    active = None
    peak = initial
    max_drawdown = Decimal(0)
    exposure_ms = 0
    for entry_ms, pid, row, decision in candidates:
        if active is not None and current_exit <= entry_ms:
            old, invested, exit_ms, selected_row = active
            settled = invested * (Decimal(1) + dec(old["modeled_net_return"]))
            if settled <= 0:
                fail("MODELED_PORTFOLIO_INSOLVENT")
            cash = settled
            peak = max(peak, cash)
            dd = cash / peak - 1
            max_drawdown = min(max_drawdown, dd)
            events.append({
                "event": "MODEL_EXIT", "at_ms": exit_ms, "pair_id": old["pair_id"],
                "arm_decision_sha256": old["arm_decision_sha256"],
                "cash_after": str(cash), "realized_cash_equity": str(cash),
                "modeled_pnl": str(settled - invested),
                "realized_only_drawdown": str(dd),
                "marked_equity": None, "execution_status": "NOT_OBSERVED",
            })
            selected_row["cash_after_exit"] = str(cash)
            active = None
        if active is not None:
            decision["portfolio_action"] = "SKIPPED"
            decision["portfolio_reason"] = ("SIMULTANEOUS_PRIORITY_LOSS" if entry_ms ==
                active[0]["entry_open_ms"] else "POSITION_ALREADY_OCCUPIED")
            decisions.append(decision)
            continue
        if cash <= 0:
            fail("NO_AVAILABLE_CASH")
        invested = cash
        cash = Decimal(0)
        decision["portfolio_action"] = "MODELED_SELECTED"
        decision["portfolio_reason"] = None
        decisions.append(decision)
        selected_row = {
            "pair_id": pid, "arm": arm, "entry_open_ms": entry_ms,
            "exit_open_ms": row["exit_open_ms"],
            "entry_price": row["entry_open"], "exit_price": row["exit_open"],
            "notional_entry_cash": str(invested),
            "modeled_units": str(invested / dec(row["entry_open"])),
            "modeled_unit_gross_return": row["modeled_gross_return"],
            "modeled_unit_net_return": row["modeled_net_return"],
            "modeled_cost_amount": str(invested * MODEL_COST),
            "cash_after_exit": None,
            "parent_arm_decision_sha256": row["arm_decision_sha256"],
            "parent_four_hour_window_sha256": row["four_hour_source_window_sha256"],
            "model_only_deferred_entry_cost": True,
        }
        selected.append(selected_row)
        events.append({
            "event": "MODEL_ENTRY", "at_ms": entry_ms, "pair_id": pid,
            "arm_decision_sha256": row["arm_decision_sha256"],
            "cash_before": str(invested), "cash_after": "0",
            "reserved_capital": str(invested),
            "realized_cash_equity": str(invested),
            "marked_equity": None, "execution_status": "NOT_OBSERVED",
        })
        exposure_ms += row["exit_open_ms"] - entry_ms
        current_exit = row["exit_open_ms"]
        active = (row, invested, current_exit, selected_row)
    if active is not None:
        old, invested, exit_ms, selected_row = active
        settled = invested * (Decimal(1) + dec(old["modeled_net_return"]))
        if settled <= 0:
            fail("MODELED_PORTFOLIO_INSOLVENT")
        cash = settled
        peak = max(peak, cash)
        dd = cash / peak - 1
        max_drawdown = min(max_drawdown, dd)
        events.append({
            "event": "MODEL_EXIT", "at_ms": exit_ms, "pair_id": old["pair_id"],
            "arm_decision_sha256": old["arm_decision_sha256"],
            "cash_after": str(cash), "realized_cash_equity": str(cash),
            "modeled_pnl": str(settled - invested),
            "realized_only_drawdown": str(dd),
            "marked_equity": None, "execution_status": "NOT_OBSERVED",
        })
        selected_row["cash_after_exit"] = str(cash)
    events.sort(key=lambda e: (e["at_ms"], 0 if e["event"] == "MODEL_EXIT" else 1,
                               e["pair_id"]))
    decisions.sort(key=lambda d: d["pair_id"])
    if len(decisions) != report["pair_count"]:
        fail("PORTFOLIO_CENSUS_DROPPED_OPPORTUNITIES")
    activity = Counter(d["portfolio_action"] for d in decisions)
    summary = {
        "arm": arm,
        "initial_capital": str(initial), "terminal_realized_cash_equity": str(cash),
        "realized_only_total_return": str(cash / initial - 1),
        "realized_only_max_drawdown": str(max_drawdown),
        "time_exposure_fraction": str(Decimal(exposure_ms) / Decimal(end - start)),
        "occupied_ms": exposure_ms,
        "modeled_selected_count": activity["MODELED_SELECTED"],
        "skipped_occupied_or_tie_count": activity["SKIPPED"],
        "ineligible_null_count": activity["NOT_ELIGIBLE"],
        "scheduled_opportunity_denominator": report["pair_count"],
        "equity_valuation": "REALIZED_SETTLEMENT_ONLY_NOT_INTRATRADE_MARK_TO_MARKET",
        "cost_accounting": "FROZEN_ADDITIVE_30BPS_DEFERRED_TO_MODEL_EXIT_NOT_EXCHANGE_CASH",
    }
    if summary["modeled_selected_count"] != len(selected):
        fail("SELECTED_LEDGER_COUNT_MISMATCH")
    return {"arm": arm, "ledger_events": events, "position_rows": selected,
            "opportunity_census": decisions, "summary": summary}


def build_offline_portfolio_package(trade_reports, policy, cohort_bounds, *,
                                    test_only=False, owner_approval_verified=False,
                                    pre_score_anchor_verified=False,
                                    independent_parent_receipts_verified=False):
    """Ledger per arm per cohort. Real scoring gated by owner-approved policy."""
    original = deepcopy(trade_reports)
    initial = _validate_policy(policy, test_only=test_only,
                               approval_verified=owner_approval_verified,
                               pre_score_anchor_verified=pre_score_anchor_verified)
    if test_only is not True and independent_parent_receipts_verified is not True:
        fail("INDEPENDENT_PARENT_TRADE_RECEIPT_ATTESTATION_REQUIRED")
    if not isinstance(trade_reports, list) or not trade_reports:
        fail("MISSING_PARENT_TRADE_REPORTS")
    if not isinstance(cohort_bounds, dict):
        fail("MISSING_COHORT_BOUNDS")
    ids = set()
    cohorts = []
    for report in sorted(trade_reports, key=lambda x: x.get("source_id", "")):
        if not isinstance(report.get("source_id"), str) or not report["source_id"]:
            fail("BAD_PARENT_COHORT_ID")
        if test_only is True and not report["source_id"].startswith("TEST_ONLY_"):
            fail("REAL_SOURCE_FORBIDDEN_IN_TEST_ONLY_PORTFOLIO")
        if report.get("source_id") in ids or report["source_id"] not in cohort_bounds:
            fail("DUPLICATE_OR_UNKNOWN_PORTFOLIO_COHORT")
        ids.add(report["source_id"])
        observed = _validate_report(report)
        start, end = _validate_bounds(report, cohort_bounds[report["source_id"]])
        arms = {arm: _arm_ledger(report, observed, arm, start, end, initial)
                for arm in ("BASE", "SHADOW")}
        b = dec(arms["BASE"]["summary"]["terminal_realized_cash_equity"])
        s = dec(arms["SHADOW"]["summary"]["terminal_realized_cash_equity"])
        cohorts.append({
            "source_id": report["source_id"],
            "source_package_sha256": report["source_package_sha256"],
            "parent_trade_report_sha256": report["artifact_sha256"],
            "original_source_schedule_sha256": report["source_schedule_sha256"],
            "interval": {"start_ms": start, "end_exclusive_ms": end},
            "pair_count": report["pair_count"],
            "arms": arms,
            "shadow_minus_base_terminal_modeled_equity": str(s - b),
            "comparison_limit": "SELECTION_AND_OVERLAP_DEPENDENT_EXPLORATORY_NOT_CAUSAL_UPLIFT",
        })
    if set(cohort_bounds) != ids:
        fail("UNUSED_OR_MISSING_COHORT_BOUNDS")
    if trade_reports != original:
        fail("PARENT_REPORT_MUTATED")
    result = {
        "schema": REPORT_SCHEMA,
        "evidence_class": "TEST_ONLY_SYNTHETIC" if test_only else
            "RETROSPECTIVE_NON_PIT_EXPLORATORY_SOURCE_BACKED_IF_EXTERNALLY_ATTESTED",
        "policy_artifact_sha256": policy["artifact_sha256"],
        "policy_approval_url": policy.get("owner_approval_url"),
        "policy_pre_score_anchor_raw_sha256": policy.get("pre_score_anchor_receipt_sha256"),
        "scope": "SEPARATE_EXPLORATORY_PORTFOLIO_NOT_FROZEN_BREAKOUT_TRADE_PREREG",
        "cohorts": cohorts,
        "capital_linking": "RESET_PER_MONTH_NO_CROSS_COHORT_COMPOUNDING",
        "total_scheduled_pairs": sum(x["pair_count"] for x in cohorts),
        "total_arm_slots": sum(2*x["pair_count"] for x in cohorts),
        "valuation_scope": "REALIZED_SETTLEMENT_ONLY_INTRATRADE_MARK_TO_MARKET_UNKNOWN",
        "execution_status": "NOT_OBSERVED",
        "alpha_claim": "NOT_ESTABLISHED", "pit_status": "NOT_ATTESTED",
        "oos_status": "NOT_ATTESTED", "holdout_status": "SEALED_UNOPENED",
    }
    result["artifact_sha256"] = digest(result)
    return result


def canonical_portfolio_receipt_bytes(receipt):
    if not isinstance(receipt, dict) or receipt.get("schema") != REPORT_SCHEMA:
        fail("BAD_PORTFOLIO_RECEIPT")
    if not hash_ok(receipt.get("artifact_sha256")) or digest({
        k:v for k,v in receipt.items() if k!="artifact_sha256"
    }) != receipt["artifact_sha256"]:
        fail("PORTFOLIO_RECEIPT_HASH_MISMATCH")
    return (json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def raw_portfolio_receipt_sha256(receipt):
    return sha256(canonical_portfolio_receipt_bytes(receipt)).hexdigest()


def render_portfolio_report(receipt):
    """Public-ready *technical* summary, not an alpha or prospective result."""
    canonical_portfolio_receipt_bytes(receipt)
    out = ["# ATLAS P2 — exploratory offline portfolio scenario", "",
           "Policy SHA: " + receipt["policy_artifact_sha256"],
           "Retrospective NON_PIT; no actual fills, trading, alpha, or unseen OOS.",
           "Settlement-only equity/drawdown; intratrade mark-to-market unknown.",
           "Cohorts simulated separately (capital reset).", "",
           "| Cohort | Arm | Scheduled | Selected | Skipped | NULL/ineligible | Terminal modeled cash | Realized-only drawdown | Exposure |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cohort in receipt["cohorts"]:
        for arm in ("BASE","SHADOW"):
            s=cohort["arms"][arm]["summary"]
            out.append(f"| {cohort['source_id']} | {arm} | {s['scheduled_opportunity_denominator']} | {s['modeled_selected_count']} | {s['skipped_occupied_or_tie_count']} | {s['ineligible_null_count']} | {s['terminal_realized_cash_equity']} | {s['realized_only_max_drawdown']} | {s['time_exposure_fraction']} |")
    out.extend(["", "No cross-month equity curve or statistical uplift inferred.",
                "Full provenance, tie skips, NULL and original reasons are retained in private receipts.",
                "Scientific acceptance deferred; no G0, holdout, paper/live or orders.", ""])
    return "\n".join(out)
