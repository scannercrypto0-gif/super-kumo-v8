"""Bounded synthetic-only deterministic LONG order execution primitive.

Not a signal generator, historical research result, or position ledger.
Ambiguous fills/exits are UNRESOLVED, never scored as losses or wins.
"""
from .strategy_definition import integer, number, digest, keys


def account_long_prices(entry_open, exit_open, *, fee_bps, slippage_bps):
    """Accepted #108 arithmetic, shared by synthetic and retrospective adapters.

    Fractions are relative to slipped entry notional. Raw gross minus execution
    slippage drag minus both-side notional fees equals net.
    """
    number(entry_open, 0.0000000001)
    number(exit_open, 0.0000000001)
    number(fee_bps, 0, 10000)
    number(slippage_bps, 0, 10000)
    if slippage_bps >= 10000:
        raise ValueError("Exit slippage must leave a positive price")
    entry = entry_open * (1 + slippage_bps / 10000)
    exit_price = exit_open * (1 - slippage_bps / 10000)
    raw_gross = exit_open / entry_open - 1
    gross = exit_price / entry - 1
    fees = fee_bps / 10000 * (1 + exit_price / entry)
    return {"entry_execution_price": entry, "exit_execution_price": exit_price,
            "raw_gross_return": raw_gross, "gross_return": gross,
            "slippage_fraction": raw_gross - gross, "fee_fraction": fees,
            "net_return": gross - fees}


def execute_synthetic_long(bars, decision_bar_index, *, stop_fraction,
                           target_fraction, ttl_bars, holding_bars,
                           fee_bps, slippage_bps):
    """One signal, one unlevered position; never execute on decision bar."""
    if type(bars) is not list or not 2 <= len(bars) <= 10000:
        raise ValueError("Bounded bars required")
    integer(decision_bar_index, 0, len(bars)-1)
    for name, value in (("stop_fraction", stop_fraction), ("target_fraction", target_fraction)):
        number(value, 0.000001, 10 if name == "target_fraction" else 0.999999)
    integer(ttl_bars, 1, 1000)
    if ttl_bars != 1:
        raise ValueError("Only next-bar entry TTL=1 is supported")
    integer(holding_bars, 1, 10000)
    number(fee_bps, 0, 10000)
    number(slippage_bps, 0, 10000)
    if slippage_bps >= 10000:
        raise ValueError("Exit slippage must leave a positive price")
    previous_close = None
    expected_span = None
    for row in bars:
        keys(row, "bar_open bar_close open high low close")
        integer(row["bar_open"], 0, 2**53-1)
        integer(row["bar_close"], 0, 2**53-1)
        if row["bar_close"] < row["bar_open"] or (previous_close is not None and row["bar_open"] <= previous_close):
            raise ValueError("Overlapping or unsorted bars")
        span = row["bar_close"] - row["bar_open"] + 1
        if expected_span is None:
            expected_span = span
        elif span != expected_span:
            raise ValueError("Mixed bar durations")
        previous_close = row["bar_close"]
        for field in ("open", "high", "low", "close"):
            number(row[field], 0.0000000001)
        if row["high"] < max(row["open"], row["close"]) or row["low"] > min(row["open"], row["close"]):
            raise ValueError("Invalid OHLC")
    decision = bars[decision_bar_index]
    entry_idx = decision_bar_index + 1
    if entry_idx >= len(bars):
        status, details = "NO_FILL", {"reason": "NO_NEXT_BAR"}
    elif bars[entry_idx]["bar_open"] != decision["bar_close"] + 1:
        status, details = "UNRESOLVED", {"reason": "ENTRY_GAP"}
    else:
        entry = bars[entry_idx]["open"] * (1 + slippage_bps / 10000)
        stop = entry * (1 - stop_fraction)
        target = entry * (1 + target_fraction)
        status, details = "UNRESOLVED", {"reason": "HORIZON_NOT_OBSERVED"}
        for idx in range(entry_idx, min(len(bars), entry_idx + holding_bars)):
            bar = bars[idx]
            if idx > entry_idx and bar["bar_open"] != bars[idx-1]["bar_close"] + 1:
                details = {"reason": "HOLDING_GAP"}
                break
            # The opening print is temporally prior to the intrabar extremes.
            # Handle known opening gaps before ambiguous high/low ordering.
            if idx > entry_idx and bar["open"] <= stop:
                exit_price = bar["open"] * (1 - slippage_bps / 10000)
                account = account_long_prices(entry, exit_price, fee_bps=fee_bps, slippage_bps=0)
                gross, fees = account["gross_return"], account["fee_fraction"]
                status = "RESOLVED_STOP"
                details = {"entry_bar_index": entry_idx, "exit_bar_index": idx,
                           "gross_return": gross, "fee_fraction": fees,
                           "net_return": gross - fees}
                break
            if idx > entry_idx and bar["open"] >= target:
                details = {"reason": "TARGET_GAP_UNRESOLVED"}
                break
            stop_hit, target_hit = bar["low"] <= stop, bar["high"] >= target
            if stop_hit and target_hit:
                details = {"reason": "SAME_BAR_STOP_TARGET"}
                break
            if stop_hit or target_hit:
                exit_price = (min(bar["open"], stop) if stop_hit else target)
                exit_price *= 1 - slippage_bps / 10000
                account = account_long_prices(entry, exit_price, fee_bps=fee_bps, slippage_bps=0)
                gross, fees = account["gross_return"], account["fee_fraction"]
                status = "RESOLVED_STOP" if stop_hit else "RESOLVED_TARGET"
                details = {"entry_bar_index": entry_idx, "exit_bar_index": idx,
                           "gross_return": gross, "fee_fraction": fees,
                           "net_return": gross - fees}
                break
    result = {"schema": "synthetic-execution-1", "status": status,
              "details": details, "synthetic_only": True,
              "independent_custody_verified": False}
    result["receipt_hash"] = digest(result)
    return result
