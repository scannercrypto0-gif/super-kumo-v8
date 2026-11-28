"""Fail-closed, offline research projections from immutable finalized 1m Binance bars.

No network, scheduler, persistence, strategy approval, or trading authority.
Input schema is deliberately explicit; upstream source authenticity is NOT proven here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json

MINUTE = 60_000
WIDTHS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 1440, "1w": 10080}
WEEK_ORIGIN_MS = 4 * 86_400_000  # 1970-01-05 00:00 UTC (Monday)


def _need(ok, code):
    if not ok:
        raise ValueError(code)


def _price(value):
    _need(type(value) is str, "DECIMAL_STRING_REQUIRED")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("INVALID_DECIMAL") from exc
    _need(result.is_finite() and result >= 0, "INVALID_DECIMAL")
    return result


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def project_finalized_1m(bars, interval, *, source_class="RETROSPECTIVE_NON_PIT"):
    """Return one sealed research projection or fail closed on gaps/duplicates.

    Each input: symbol, interval='1m', open_ms, final=True, o/h/l/c/v
    as decimal strings, source_sha256 as 64 lowercase hex, available_at_ms.
    All constituent bars must have been available by the projection's
    available_at_ms; that timestamp is the maximum observed availability,
    not a claim of historical PIT eligibility.
    """
    _need(interval in WIDTHS, "INTERVAL_UNSUPPORTED")
    _need(source_class in ("RETROSPECTIVE_NON_PIT", "FORWARD_UNQUALIFIED"),
          "SOURCE_CLASS_UNSUPPORTED")
    width = WIDTHS[interval]
    _need(type(bars) is list and len(bars) == width, "INCOMPLETE_WINDOW")
    first = bars[0]
    _need(type(first) is dict, "INVALID_BAR")
    start = first.get("open_ms")
    _need(type(start) is int and start >= 0 and type(first.get("symbol")) is str
          and first["symbol"], "INVALID_IDENTITY")
    origin = WEEK_ORIGIN_MS if interval == "1w" else 0
    _need((start - origin) % (width * MINUTE) == 0, "UTC_WINDOW_MISALIGNED")
    values = []
    for index, bar in enumerate(bars):
        _need(type(bar) is dict and bar.get("symbol") == first["symbol"]
              and bar.get("interval") == "1m" and bar.get("final") is True
              and type(bar.get("open_ms")) is int
              and bar["open_ms"] == start + index * MINUTE, "GAP_DUPLICATE_OR_PROVISIONAL")
        sha = bar.get("source_sha256")
        _need(type(sha) is str and len(sha) == 64
              and all(ch in "0123456789abcdef" for ch in sha), "SOURCE_DIGEST_REQUIRED")
        available = bar.get("available_at_ms")
        _need(type(available) is int and available >= bar["open_ms"] + MINUTE,
              "AVAILABILITY_INVALID")
        o, h, l, c, v = (_price(bar.get(k)) for k in ("o", "h", "l", "c", "v"))
        _need(l <= min(o, c) <= max(o, c) <= h, "OHLC_INVALID")
        values.append((o, h, l, c, v, available, sha))
    result = {
        "schema": "aql.research.finalized-timeframe.v1",
        "source_class": source_class,
        "symbol": first["symbol"],
        "interval": interval,
        "open_ms": start,
        "close_exclusive_ms": start + width * MINUTE,
        "available_at_ms": max(x[5] for x in values),
        "constituent_count": width,
        "constituent_sha256": [x[6] for x in values],
        "o": str(values[0][0]),
        "h": str(max(x[1] for x in values)),
        "l": str(min(x[2] for x in values)),
        "c": str(values[-1][3]),
        "v": str(sum((x[4] for x in values), Decimal(0))),
        "trading_authority": "NONE",
        "pit_oos": "NOT_ATTESTED",
    }
    result["sha256"] = hashlib.sha256(_canon(result)).hexdigest()
    return result
