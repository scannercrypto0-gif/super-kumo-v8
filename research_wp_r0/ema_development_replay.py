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
                           slippage_bps=5, interval_ms=60000):
    """Replay only bars strictly before reserved OOS split.

    Signals are computed from closed bars; fills are at next bar open.
    A position still open at the split is marked OPEN_UNREALIZED, not closed
    at an invented exit. One-unit long only; no leverage or reinvestment.
    """
    if type(split_cutoff_ms) is not int or split_cutoff_ms <= 0:
        raise ValueError("Reserved split cutoff required")
    if not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 10000
               for x in (fee_bps, slippage_bps)):
        raise ValueError("Invalid per-side costs")
    selected = tuple(b for b in bars if b[0] < split_cutoff_ms)
    if len(selected) < 23:
        raise ValueError("Insufficient development-only history")
    if any(b[1] >= split_cutoff_ms for b in selected):
        raise ValueError("Candle crosses reserved OOS boundary")
    decisions = ema_crossover_decisions(selected, interval_ms=interval_ms)
    by_open = {b[0]: b for b in selected}
    position = None
    available_cash = 100000.0
    position_regime = None
    trades = []
    opportunities = []
    for decision in decisions:
        next_open = decision.bar_open_ms + interval_ms
        next_bar = by_open.get(next_open)
        regime = ("TARGET" if by_open[decision.bar_open_ms][5] > decision.ema_slow
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
        event["decision_snapshot"] = {k: v for k, v in event.items() if k != "status"}
        if decision.signal == "ENTER_LONG" and position is None:
            if next_bar is None:
                event["status"] = "UNRESOLVED_NO_NEXT_BAR"
            elif next_bar[2] * (1 + slippage_bps / 10000) * (1 + fee_bps / 10000) > available_cash:
                event["status"] = "REJECTED_CAPITAL_LIMIT"
            else:
                price = next_bar[2]
                available_cash -= price * (1 + slippage_bps / 10000) * (1 + fee_bps / 10000)
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
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        equity_curve.append([bar[1], equity])
    benchmark = account_long_prices(selected[22][2], selected[-1][5], fee_bps=fee_bps,
                                    slippage_bps=slippage_bps)
    report = {"initial_collateral_quote": collateral,
        "collateral_basis": "FROZEN_100000_USDT_ONE_BTC_MAX",
        "terminal_equity_quote": equity_curve[-1][1],
        "portfolio_net_return_fraction": equity_curve[-1][1] / collateral - 1,
        "net_pnl_quote_including_terminal_liquidation_mark": equity_curve[-1][1] - collateral,
        "max_drawdown_fraction_close_marks": max_dd,
        "equity_curve": equity_curve,
        "benchmark_net_return_bps": benchmark["net_return"] * 10000,
        "benchmark_net_pnl_quote_one_btc": benchmark["net_return"] * benchmark["entry_execution_price"],
        "benchmark_window": [selected[22][0], selected[-1][1]],
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
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    report["report_sha256"] = hashlib.sha256(encoded).hexdigest()
    return report
