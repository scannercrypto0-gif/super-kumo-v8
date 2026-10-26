"""P0 causal EMA 8/21 crossover research signals.

Pure calculation from historical CLOSED candles. No exchange calls, orders,
regime claims, or retrospective custody promotion.
"""
import hashlib
import json
import math
from dataclasses import dataclass
from .indicator_library_v2 import _ema


@dataclass(frozen=True)
class EmaDecision:
    decision_cutoff_ms: int
    bar_open_ms: int
    ema_fast: float
    ema_slow: float
    previous_fast: float
    previous_slow: float
    signal: str


def ema_crossover_decisions(bars, *, fast=8, slow=21, interval_ms=60000):
    """Return causal decisions after slow+1 closed candles.

    bars: (open_ms, close_ms, open, high, low, close, volume) records.
    Entry/exit must be simulated at a subsequent eligible bar, never this close.
    """
    if (type(fast) is not int or type(slow) is not int or
        not 1 <= fast < slow or type(interval_ms) is not int or interval_ms <= 0):
        raise ValueError("Invalid fixed EMA parameters")
    records = tuple(bars)
    if len(records) < slow + 1:
        raise ValueError("Insufficient EMA warmup; do not fabricate signals")
    closes = []
    previous_open = None
    for record in records:
        if len(record) != 7:
            raise ValueError("Expected canonical OHLCV")
        opening, closing = record[:2]
        if (type(opening) is not int or type(closing) is not int or
            closing != opening + interval_ms - 1 or opening % interval_ms or
            (previous_open is not None and opening != previous_open + interval_ms)):
            raise ValueError("Noncontiguous or invalid candle grid")
        values = [float(v) for v in record[2:]]
        op, high, low, close, volume = values
        if (not all(math.isfinite(v) for v in values) or
            min(op, high, low, close) <= 0 or volume < 0 or
            high < max(op, low, close) or low > min(op, close)):
            raise ValueError("Invalid OHLCV")
        closes.append(close)
        previous_open = opening
    fast_values = [None] * (fast - 1) + _ema(closes, fast)
    slow_values = [None] * (slow - 1) + _ema(closes, slow)
    output = []
    for i in range(slow, len(records)):
        pf, ps = fast_values[i-1], slow_values[i-1]
        cf, cs = fast_values[i], slow_values[i]
        direction = ("ENTER_LONG" if pf <= ps and cf > cs else
                     "EXIT_LONG" if pf >= ps and cf < cs else "HOLD")
        output.append(EmaDecision(records[i][1] + 1, records[i][0],
                                  cf, cs, pf, ps, direction))
    return tuple(output)


def frozen_ema_plan(*, archive_sha256, source_reference, split_cutoff_ms,
                    fast=8, slow=21, fee_bps=10, slippage_bps=5):
    """Canonical immutable plan commitment; OOS is not evaluated here."""
    if (type(archive_sha256) is not str or len(archive_sha256) != 64 or
        any(c not in "0123456789abcdef" for c in archive_sha256) or
        not isinstance(source_reference, str) or not source_reference.strip() or
        type(split_cutoff_ms) is not int or split_cutoff_ms <= 0 or
        (fast, slow) != (8, 21) or
        not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 10000
                for x in (fee_bps, slippage_bps))):
        raise ValueError("Explicit validated frozen research plan required")
    plan = {"schema_version": "sf-ema-first-backtest-plan-1",
            "strategy": "EMA_8_21_CROSS_LONG_ONLY",
            "indicator_version": "SF-IND-02:2:_ema:fsum",
            "interval_ms": 60000,
            "symbol": "BTCUSDT",
            "benchmark": "BUY_HOLD_SAME_WINDOW_AND_COSTS",
            "risk": "ONE_BTC_MAX_LONG_NO_LEVERAGE_NO_REINVESTMENT",
            "initial_capital_usdt": 100000,
            "stop_target": "NONE_CROSSOVER_EXIT_ONLY",
            "entry_ttl_bars": 1,
            "terminal_position": "UNRESOLVED_MARK_TO_MARKET_SEPARATE",
            "target_regime": "BTC_CLOSE_ABOVE_EMA21_AND_EMA21_RISING_V1",
            "missing_bar": "REJECT_DATASET",
            "availability_assumption": "CLOSED_BAR_AVAILABLE_AT_CLOSE_PLUS_1MS_UNVERIFIED",
            "archive_sha256": archive_sha256,
            "source_reference": source_reference,
            "split_cutoff_ms": split_cutoff_ms,
            "fee_bps_per_side": fee_bps,
            "slippage_bps_per_side": slippage_bps,
            "entry": "NEXT_OPEN_AFTER_CLOSED_SIGNAL",
            "exit": "NEXT_OPEN_AFTER_CLOSED_OPPOSITE_SIGNAL",
            "availability": "RETROSPECTIVE_NOT_CONFIRMED",
            "oos_state": "LOCKED_NOT_EVALUATED"}
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return plan, hashlib.sha256(encoded).hexdigest()
