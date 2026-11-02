"""Fail-closed Coinbase Exchange public 15m candle normalization (no network/trading).

Public REST product candles use [time, low, high, open, close, volume].
The adapter intentionally does not impersonate Binance WS or assert PIT custody.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

BAR_SECONDS = 900
PRODUCT_RE = re.compile(r"^[A-Z0-9]{2,20}-USD$")


class CoinbaseSourceError(ValueError):
    """Malformed, stale, unfinished, or incorrectly attributed source bar."""


@dataclass(frozen=True)
class CoinbaseFinalCandle:
    source: str
    product_id: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    custody: str = "UNVERIFIED_PUBLIC_REST"
    executable_on_binance: bool = False


def parse_final_candle(row, *, product_id: str, received_at_ms: int) -> CoinbaseFinalCandle:
    """Normalize one completed 15m public candle; no implicit USD/USDT conversion.

    `received_at_ms` is a caller-observed UTC timestamp, not trusted exchange time.
    No data is fetched, persisted, or traded by this function.
    """
    if not isinstance(product_id, str) or not PRODUCT_RE.fullmatch(product_id):
        raise CoinbaseSourceError("INVALID_COINBASE_USD_PRODUCT")
    if type(received_at_ms) is not int or received_at_ms <= 0:
        raise CoinbaseSourceError("INVALID_OBSERVED_TIME")
    if not isinstance(row, (tuple, list)) or len(row) != 6:
        raise CoinbaseSourceError("INVALID_CANDLE_SHAPE")
    epoch, low, high, opened, closed, volume = row
    if type(epoch) is not int or epoch < 0 or epoch % BAR_SECONDS:
        raise CoinbaseSourceError("INVALID_CANDLE_GRID")
    try:
        values = tuple(float(v) for v in (low, high, opened, closed, volume))
    except (TypeError, ValueError, OverflowError) as exc:
        raise CoinbaseSourceError("INVALID_OHLCV") from exc
    lo, hi, op, cl, vol = values
    if not all(math.isfinite(v) for v in values) or not (0 < lo <= min(op, cl) <= max(op, cl) <= hi and vol >= 0):
        raise CoinbaseSourceError("INVALID_OHLCV")
    open_ms = epoch * 1000
    end_ms = (epoch + BAR_SECONDS) * 1000
    if end_ms > received_at_ms:
        raise CoinbaseSourceError("UNFINISHED_CANDLE")
    return CoinbaseFinalCandle(
        source="coinbase_exchange_public_rest", product_id=product_id,
        interval="15m", open_time_ms=open_ms, close_time_ms=end_ms - 1,
        open=op, high=hi, low=lo, close=cl, volume=vol,
    )


def normalize_response(rows, *, product_id: str, received_at_ms: int):
    """Require a nonempty, unique, contiguous completed source prefix, oldest first."""
    if not isinstance(rows, list) or not rows:
        raise CoinbaseSourceError("EMPTY_OR_INVALID_RESPONSE")
    bars = [parse_final_candle(row, product_id=product_id, received_at_ms=received_at_ms) for row in rows]
    bars.sort(key=lambda b: b.open_time_ms)
    for previous, current in zip(bars, bars[1:]):
        if current.open_time_ms != previous.open_time_ms + BAR_SECONDS * 1000:
            raise CoinbaseSourceError("DUPLICATE_OR_GAPPED_SOURCE")
    return tuple(bars)
