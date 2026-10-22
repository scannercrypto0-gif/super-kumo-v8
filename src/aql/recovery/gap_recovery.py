"""
AQL Gap Recovery — G1-WP01-MVP

Uses Binance REST /api/v3/klines to recover final bars missed during
WebSocket disconnection.

Rules (execution order §D):
- Recovery is idempotent: re-fetching an already-stored bar is a no-op.
- RECOVERED bars are distinguished from RECEIVED bars via source + state fields.
- A bar retrieved via recovery is NOT treated as having been available to the
  system at an earlier time (TIME-01 / no retroactive backdating).
- UNRESOLVED_DATA_GAP: a gap that cannot be filled (e.g. gap pre-dates
  available REST history, or REST returns fewer bars than expected).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import urllib.request
import urllib.parse
import json

from ..models.bar import BarState, MarketBar

logger = logging.getLogger(__name__)

# Binance REST base (public, no API key required for market data)
BINANCE_REST_BASE = "https://api.binance.com"

# REST weight limits per Binance docs (2024):
# GET /api/v3/klines  weight=2 per request (IP weight)
# IP rate limit: 6000 weight/min (X-MBX-USED-WEIGHT-1M header)
KLINES_WEIGHT_PER_REQUEST = 2
MAX_KLINES_PER_REQUEST = 1000


@dataclass
class RecoveryReport:
    symbol: str
    interval: str
    gap_start_ms: int
    gap_end_ms: int
    expected_bars: int
    recovered_bars: int
    already_stored: int
    unresolved: int
    status: str  # "FULL" | "PARTIAL" | "UNRESOLVED_DATA_GAP"
    weight_used: int


def _binance_interval_ms(interval: str) -> int:
    """Convert Binance interval string to milliseconds."""
    unit_map = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    try:
        n = int(interval[:-1])
        unit = interval[-1]
        return n * unit_map[unit]
    except (KeyError, ValueError, IndexError):
        raise ValueError(f"Unsupported interval: {interval}")


def _fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = MAX_KLINES_PER_REQUEST,
    proxies: Optional[dict] = None,
) -> tuple[list, int]:
    """
    Fetch klines from Binance REST.
    Returns (rows, weight_used).
    weight_used is read from X-MBX-USED-WEIGHT-1M header if available,
    else estimated as KLINES_WEIGHT_PER_REQUEST.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": str(start_ms),
        "endTime": str(end_ms),
        "limit": str(limit),
    }
    url = f"{BINANCE_REST_BASE}/api/v3/klines?" + urllib.parse.urlencode(params)
    logger.debug("REST klines fetch: %s", url)

    req = urllib.request.Request(url, headers={"User-Agent": "AQL-G1-MVP/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        weight = int(resp.headers.get("X-MBX-USED-WEIGHT-1M", KLINES_WEIGHT_PER_REQUEST))
        data = json.loads(resp.read())

    return data, weight


def recover_gap(
    symbol: str,
    interval: str,
    gap_start_ms: int,
    gap_end_ms: int,
    existing_keys: set,
) -> tuple[List[MarketBar], RecoveryReport]:
    """
    Fetch all final bars in [gap_start_ms, gap_end_ms] from Binance REST.
    existing_keys: set of bar_open timestamps already in the journal/store
                   (used to count already_stored, not to skip fetch).
    Returns (bars_to_insert, report).
    bars_to_insert excludes bars already in existing_keys (idempotent).
    """
    interval_ms = _binance_interval_ms(interval)
    expected = max(0, (gap_end_ms - gap_start_ms) // interval_ms)

    all_bars: List[MarketBar] = []
    total_weight = 0
    cursor = gap_start_ms

    while cursor <= gap_end_ms:
        try:
            rows, weight = _fetch_klines(symbol, interval, cursor, gap_end_ms)
        except Exception as exc:
            logger.warning("REST fetch failed: %s", exc)
            break

        total_weight += weight

        if not rows:
            break

        for row in rows:
            bar = MarketBar.from_binance_rest_kline(row, symbol, interval)
            all_bars.append(bar)

        last_open = int(rows[-1][0])
        cursor = last_open + interval_ms

        if len(rows) < MAX_KLINES_PER_REQUEST:
            break

    recovered_new = [b for b in all_bars if b.bar_open not in existing_keys]
    already_stored = len(all_bars) - len(recovered_new)
    unresolved = max(0, expected - len(all_bars))

    if unresolved > 0:
        status = "UNRESOLVED_DATA_GAP"
    elif expected > 0 and len(all_bars) >= expected:
        status = "FULL"
    else:
        status = "PARTIAL"

    report = RecoveryReport(
        symbol=symbol,
        interval=interval,
        gap_start_ms=gap_start_ms,
        gap_end_ms=gap_end_ms,
        expected_bars=expected,
        recovered_bars=len(all_bars),
        already_stored=already_stored,
        unresolved=unresolved,
        status=status,
        weight_used=total_weight,
    )

    logger.info(
        "Gap recovery: symbol=%s interval=%s expected=%d recovered=%d "
        "already_stored=%d unresolved=%d status=%s weight=%d",
        symbol, interval, expected, len(all_bars),
        already_stored, unresolved, status, total_weight,
    )

    return recovered_new, report
