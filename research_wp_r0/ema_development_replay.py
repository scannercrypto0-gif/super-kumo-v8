"""P0 deterministic development-only EMA8/21 replay.

Retrospective source, hypothetical next-open fills; not confirmed custody,
forward results, OOS evaluation, or production trading.
"""
import hashlib
import json
import math

from .ema_first_backtest import ema_crossover_decisions


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
    trades = []
    opportunities = []
    for decision in decisions:
        next_open = decision.bar_open_ms + interval_ms
        next_bar = by_open.get(next_open)
        event = {"decision_cutoff_ms": decision.decision_cutoff_ms,
                 "signal": decision.signal,
                 "ema_fast": decision.ema_fast,
                 "ema_slow": decision.ema_slow,
                 "previous_fast": decision.previous_fast,
                 "previous_slow": decision.previous_slow,
                 "next_open_ms": next_open,
                 "status": "NO_SIGNAL"}
        if decision.signal == "ENTER_LONG" and position is None:
            if next_bar is None:
                event["status"] = "UNRESOLVED_NO_NEXT_BAR"
            else:
                price = next_bar[2]
                position = (next_open, price)
                event["status"] = "SIMULATED_ENTRY"
        elif decision.signal == "EXIT_LONG" and position is not None:
            if next_bar is None:
                event["status"] = "UNRESOLVED_NO_NEXT_BAR"
            else:
                opened, entry_price = position
                gross = (next_bar[2] / entry_price - 1) * 10000
                costs = 2 * (fee_bps + slippage_bps)
                trades.append({"entry_open_ms": opened,
                               "exit_open_ms": next_open,
                               "entry_price": entry_price,
                               "exit_price": next_bar[2],
                               "gross_return_bps": gross,
                               "cost_bps": costs,
                               "net_return_bps": gross - costs})
                position = None
                event["status"] = "SIMULATED_EXIT"
        elif decision.signal != "HOLD":
            event["status"] = "REJECTED_POSITION_STATE"
        opportunities.append(event)
    report = {
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
        "net_bps_sum_one_unit": sum(t["net_return_bps"] for t in trades),
        "risk_limit_status": "NOT_MODELED_NO_PRODUCTION_CLAIM",
    }
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    report["report_sha256"] = hashlib.sha256(encoded).hexdigest()
    return report
