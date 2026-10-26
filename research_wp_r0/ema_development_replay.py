"""P0 deterministic development-only EMA8/21 replay.

Retrospective source, hypothetical next-open fills; not confirmed custody,
forward results, OOS evaluation, or production trading.
"""
import hashlib
import json
import math

from .ema_first_backtest import ema_crossover_decisions
from .synthetic_execution import account_long_prices


def replay_ema_development(bars, *, split_cutoff_ms, fee_bps=10,
                           slippage_bps=5, interval_ms=60000,
                           guard_plan=None, input_evidence=None):
    """Replay only bars strictly before reserved OOS split.

    Legacy default is the frozen optimistic zero-latency next-open model.
    guard_plan selects the separate versioned development policy.
    Signals are computed from closed bars; execution is hypothetical.
    A position still open at the split is marked OPEN_UNREALIZED, not closed
    at an invented exit. One-unit long only; no leverage or reinvestment.
    """
    if type(split_cutoff_ms) is not int or split_cutoff_ms <= 0:
        raise ValueError("Reserved split cutoff required")
    if not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 10000
               for x in (fee_bps, slippage_bps)):
        raise ValueError("Invalid per-side costs")
    selected = tuple(b for b in bars if b[0] < split_cutoff_ms)
    guarded = guard_plan is not None
    if not selected or (not guarded and len(selected) < 23):
        raise ValueError("Insufficient development-only history")
    if any(b[1] >= split_cutoff_ms for b in selected):
        raise ValueError("Candle crosses reserved OOS boundary")
    if guarded:
        from .research_guards import ResearchGuardPlan, guarded_decisions, assess_inputs
        from .strategy_definition import digest
        if not isinstance(guard_plan, ResearchGuardPlan):
            raise ValueError("Validated research guard plan required")
        policy = guard_plan.spec
        if (policy["timing"]["mode"] != "RETROSPECTIVE_UNVERIFIED_TIMING" or
            policy["split_cutoff_ms"] != split_cutoff_ms or policy["interval_ms"] != interval_ms or
            digest(selected) != policy["data_sha256"] or digest(input_evidence) != policy["evidence_sha256"] or
            {"fee_bps": fee_bps, "slippage_bps": slippage_bps} not in policy["costs"].values()):
            raise ValueError("Guard context/plan mismatch; verified mode is not implemented")
        decisions = guarded_decisions(selected, interval_ms)
    else:
        if input_evidence is not None:
            raise ValueError("Input evidence needs an explicit versioned guard plan")
        decisions = ema_crossover_decisions(selected, interval_ms=interval_ms)
    by_open = {b[0]: b for b in selected}
    coverage_gap_ms = (next((selected[i-1][1] + 1 for i in range(1, len(selected))
                            if selected[i][0] != selected[i-1][0] + interval_ms), None) if guarded else None)
    position = None
    available_cash = 100000.0
    position_regime = None
    common_stress_cash = 100000.0
    protection_cutoff = None
    required_history_tainted = False
    trades = []
    opportunities = []
    for decision in decisions:
        next_open = (guard_plan.eligible_open(decision.decision_cutoff_ms) if guarded
                     else decision.bar_open_ms + interval_ms)
        next_bar = by_open.get(next_open)
        if guarded and any(t not in by_open for t in range(
                decision.bar_open_ms + interval_ms, next_open + interval_ms, interval_ms)):
            next_bar = None
        regime = ("UNKNOWN" if decision.ema_slow is None else "TARGET" if by_open[decision.bar_open_ms][5] > decision.ema_slow
                  and decision.ema_slow > decision.previous_slow else "OFF_TARGET")
        event = {"regime": regime, "regime_rule": "BTC_CLOSE_ABOVE_EMA21_AND_EMA21_RISING_V1",
                 "availability": "RETROSPECTIVE_NOT_CONFIRMED",
                 "available_at_assumption_ms": decision.decision_cutoff_ms,
                 "historical_observed_at_ms": None,
                 "unknown_context": ["ETH", "BTC_DOMINANCE", "BREADTH", "NEWS", "MACRO",
                                     "SECTOR", "ALTSEASON", "RELATIVE_STRENGTH", "RSI", "MACD"],
                 "bar_volume_btc": by_open[decision.bar_open_ms][6],
                 "bar_range_fraction": (by_open[decision.bar_open_ms][3] - by_open[decision.bar_open_ms][4]) / by_open[decision.bar_open_ms][5],"decision_cutoff_ms": decision.decision_cutoff_ms,
                 "signal": decision.signal,
                 "ema_fast": decision.ema_fast,
                 "ema_slow": decision.ema_slow,
                 "previous_fast": decision.previous_fast,
                 "previous_slow": decision.previous_slow,
                 "next_open_ms": next_open,
                 "status": "NO_SIGNAL"}
        if guarded:
            assessment = assess_inputs(guard_plan, decision, by_open[decision.bar_open_ms], input_evidence)
            if assessment["inputs"]["candles"]["state"] != "VALID":
                required_history_tainted = True
                event["bar_volume_btc"] = None
                event["bar_range_fraction"] = None
            if required_history_tainted:
                assessment["status"] = "BLOCKED_MISSING_REQUIRED_DATA"
                assessment["reasons"].append("EMA_HISTORY_TAINTED_REQUIRED_CANDLE")
                for name in ("ema_8", "ema_21"):
                    assessment["inputs"][name].update(state="UNVERIFIED", value="UNKNOWN")
                for field in ("ema_fast", "ema_slow", "previous_fast", "previous_slow"):
                    event[field] = None
                event["regime"] = "UNKNOWN"
            if protection_cutoff is not None:
                assessment["status"] = "BLOCKED_MISSING_REQUIRED_DATA"
                assessment["reasons"].append("PRIOR_REQUIRED_LOSS_POSITION_PROTECTION_UNRESOLVED")
            event["guard_plan_digest"] = guard_plan.digest
            event["input_assessment"] = assessment
            event["timing_mode"] = "RETROSPECTIVE_UNVERIFIED_TIMING"
            event["actual_decision_ready_ms"] = None
            event["actual_order_submission_ms"] = None
            event["actual_fill_evidence"] = "NOT_OBSERVED"
            if assessment["status"] != "READY" or protection_cutoff is not None:
                if position is not None and protection_cutoff is None:
                    protection_cutoff = decision.decision_cutoff_ms
                event["signal"] = None  # blocked observation is NOT a calculated HOLD/entry
                event["status"] = "BLOCKED_MISSING_REQUIRED_DATA"
                event["protection_status"] = ("UNRESOLVED_PROTECTION_REQUIRED" if protection_cutoff is not None else None)
                event["decision_snapshot"] = {k: v for k, v in event.items() if k not in ("status", "protection_status")}
                event["snapshot_sha256"] = hashlib.sha256(json.dumps(event["decision_snapshot"], sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                opportunities.append(event)
                continue
        event["decision_snapshot"] = {k: v for k, v in event.items() if k != "status"}
        if guarded and next_bar is None:
            event["eligibility_reason"] = ("DEVELOPMENT_BOUNDARY" if next_open >= split_cutoff_ms
                                            else "FIRST_ELIGIBLE_BAR_OR_COVERAGE_MISSING")
        if decision.signal == "ENTER_LONG" and position is None:
            if next_bar is None:
                event["status"] = "UNRESOLVED_NO_NEXT_BAR"
            elif (next_bar[2] * 1.001 * 1.002 > common_stress_cash if guarded else
                  next_bar[2] * (1 + slippage_bps / 10000) * (1 + fee_bps / 10000) > available_cash):
                event["status"] = "REJECTED_CAPITAL_LIMIT"
            else:
                price = next_bar[2]
                available_cash -= price * (1 + slippage_bps / 10000) * (1 + fee_bps / 10000)
                if guarded:
                    common_stress_cash -= price * 1.001 * 1.002
                position = (next_open, price)
                position_regime = regime
                event["status"] = "SIMULATED_ENTRY"
        elif decision.signal == "EXIT_LONG" and position is not None:
            if next_bar is None:
                event["status"] = "UNRESOLVED_NO_NEXT_BAR"
            else:
                opened, entry_price = position
                account = account_long_prices(entry_price, next_bar[2], fee_bps=fee_bps,
                                              slippage_bps=slippage_bps)
                trades.append({"entry_open_ms": opened, "exit_open_ms": next_open,
                               "entry_price": entry_price, "exit_price": next_bar[2],
                               "entry_regime": position_regime,
                               "gross_return_bps": account["raw_gross_return"] * 10000,
                               "cost_bps": (account["slippage_fraction"] + account["fee_fraction"]) * 10000,
                               "net_return_bps": account["net_return"] * 10000,
                               "net_pnl_quote": account["net_return"] * account["entry_execution_price"]})
                available_cash += account["exit_execution_price"] * (1 - fee_bps / 10000)
                if guarded:
                    stress_account = account_long_prices(entry_price, next_bar[2], fee_bps=20, slippage_bps=10)
                    common_stress_cash += stress_account["exit_execution_price"] * .998
                position = None
                event["status"] = "SIMULATED_EXIT"
        elif decision.signal != "HOLD":
            event["status"] = "REJECTED_POSITION_STATE"
        event["snapshot_sha256"] = hashlib.sha256(json.dumps(event["decision_snapshot"], sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        opportunities.append(event)
    # Fixed preregistered capital. One BTC max; no leverage or reinvestment.
    collateral = 100000.0
    cash, held, peak, max_dd = collateral, False, collateral, 0.0
    equity_curve = []
    actions = {e["next_open_ms"]: e["status"] for e in opportunities
               if e["status"] in ("SIMULATED_ENTRY", "SIMULATED_EXIT")}
    for bar in selected:
        action = actions.get(bar[0])
        if action == "SIMULATED_ENTRY":
            cash -= bar[2] * (1 + slippage_bps / 10000) * (1 + fee_bps / 10000)
            held = True
        elif action == "SIMULATED_EXIT":
            cash += bar[2] * (1 - slippage_bps / 10000) * (1 - fee_bps / 10000)
            held = False
        equity = cash + (bar[5] * (1 - slippage_bps / 10000) * (1 - fee_bps / 10000) if held else 0)
        if guarded and ((protection_cutoff is not None and bar[1] + 1 >= protection_cutoff) or
                        (coverage_gap_ms is not None and bar[1] + 1 >= coverage_gap_ms)):
            equity = None  # no invented protective exit or trusted mark after evidence loss
        else:
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        equity_curve.append([bar[1], equity])
    benchmark_open = (guard_plan.eligible_open(selected[21][1] + 1) if guarded and len(selected) > 21
                      else selected[22][0] if not guarded else None)
    benchmark_bar = by_open.get(benchmark_open)
    benchmark = (account_long_prices(benchmark_bar[2], selected[-1][5], fee_bps=fee_bps,
                                     slippage_bps=slippage_bps)
                 if benchmark_bar is not None and protection_cutoff is None and coverage_gap_ms is None else None)
    report = {"initial_collateral_quote": collateral,
        "collateral_basis": "FROZEN_100000_USDT_ONE_BTC_MAX",
        "terminal_equity_quote": equity_curve[-1][1],
        "portfolio_net_return_fraction": (equity_curve[-1][1] / collateral - 1 if equity_curve[-1][1] is not None else None),
        "net_pnl_quote_including_terminal_liquidation_mark": (equity_curve[-1][1] - collateral if equity_curve[-1][1] is not None else None),
        "max_drawdown_fraction_close_marks": max_dd,
        "equity_curve": equity_curve,
        "benchmark_net_return_bps": (benchmark["net_return"] * 10000 if benchmark else None),
        "benchmark_net_pnl_quote_one_btc": (benchmark["net_return"] * benchmark["entry_execution_price"] if benchmark else None),
        "benchmark_window": ([benchmark_open, selected[-1][1]] if benchmark else None),
        "regime_results": {r: {"closed_trades": sum(t["entry_regime"] == r for t in trades),
                              "net_pnl_quote": math.fsum(t["net_pnl_quote"] for t in trades if t["entry_regime"] == r),
                              "sample_status": "INSUFFICIENT_EVIDENCE"} for r in ("TARGET", "OFF_TARGET")},
        "outcome_counts": {status: sum(e["status"] == status for e in opportunities) for status in
                           ("NO_SIGNAL", "SIMULATED_ENTRY", "SIMULATED_EXIT", "REJECTED_POSITION_STATE", "REJECTED_CAPITAL_LIMIT", "UNRESOLVED_NO_NEXT_BAR")},
        "no_fill_count": 0, "expired_count": 0,
        "no_fill_policy": "MISSING_EVIDENCE_UNRESOLVED_NOT_NO_FILL; MARKET_ENTRY_TTL_ONE_BAR",
        "sample_limitation": "ONE_ENGINEERING_SAMPLE_NO_INFERENCE_NO_PROFITABILITY_EVIDENCE",

        "schema_version": "sf-ema-dev-replay-1",
        "data_availability": "RETROSPECTIVE_NOT_CONFIRMED",
        "phase": "HISTORICAL_DEVELOPMENT",
        "oos": "LOCKED_NOT_EVALUATED",
        "split_cutoff_ms": split_cutoff_ms,
        "fee_bps_per_side": fee_bps,
        "slippage_bps_per_side": slippage_bps,
        "opportunities": opportunities,
        "trades": trades,
        "open_position": ({"entry_open_ms": position[0],
                           "entry_price": position[1],
                           "status": "OPEN_UNREALIZED"}
                          if position else None),
        "closed_trade_count": len(trades),
        "sum_trade_net_return_bps_not_portfolio_return": sum(t["net_return_bps"] for t in trades),
        "risk_limit_status": "ONE_BTC_MAX_100000_USDT_NO_LEVERAGE_CROSSOVER_ONLY_NO_STOP",
    }
    if guarded:
        report.update(schema_version="sf-ema-dev-replay-guarded-1", guard_plan_digest=guard_plan.digest,
                      timing_mode="RETROSPECTIVE_UNVERIFIED_TIMING", original_p0="UNCHANGED_SEPARATE_LEGACY_PATH",
                      protection_status=("UNRESOLVED_PROTECTION_REQUIRED" if protection_cutoff is not None else "NOT_TRIGGERED"),
                      protection_cutoff_ms=protection_cutoff,
                      coverage_gap_ms=coverage_gap_ms,
                      mark_status=("UNKNOWN_AFTER_COVERAGE_GAP" if coverage_gap_ms is not None else
                                   "UNKNOWN_AFTER_REQUIRED_DATA_LOSS" if protection_cutoff is not None else "HYPOTHETICAL_CLOSE_MARK"),
                      drawdown_status=("PARTIAL_COVERAGE" if coverage_gap_ms is not None else
                                       "PARTIAL_BEFORE_REQUIRED_DATA_LOSS" if protection_cutoff is not None else "CLOSE_MARKS_ONLY"))
        report["outcome_counts"]["BLOCKED_MISSING_REQUIRED_DATA"] = sum(
            e["status"] == "BLOCKED_MISSING_REQUIRED_DATA" for e in opportunities)
        if report["open_position"] is not None and protection_cutoff is not None:
            report["open_position"]["status"] = "UNRESOLVED_PROTECTION_REQUIRED"
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    report["report_sha256"] = hashlib.sha256(encoded).hexdigest()
    return report
