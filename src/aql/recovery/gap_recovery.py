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

Weight accounting:
  X-MBX-USED-WEIGHT-1M is the CUMULATIVE rolling 1-minute window weight
  across ALL requests from this IP — it is NOT the cost of a single request.
  Per Binance docs, GET /api/v3/klines costs KLINES_WEIGHT_PER_REQUEST=2 per
  call.  We track cost as (requests_made * KLINES_WEIGHT_PER_REQUEST) and
  separately record last_seen_window_weight for observability.
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

# REST weight per Binance docs (2024-12):
# GET /api/v3/klines  weight = 2 per request (IP weight)
# IP rate limit:      6000 weight/min (X-MBX-USED-WEIGHT-1M header shows cumulative)
KLINES_WEIGHT_PER_REQUEST = 2
MAX_KLINES_PER_REQUEST = 1000

# Headroom: stop fetching if we calculate we'd exceed this threshold.
# This is per-session cost, not the window total shown in the header.
MAX_SESSION_WEIGHT = 1200  # 20% of 6000 limit; conservative


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
    weight_cost: int           # cost = requests_made * KLINES_WEIGHT_PER_REQUEST
    last_seen_window_weight: int  # last X-MBX-USED-WEIGHT-1M value (cumulative, for observation)


def _binance_interval_ms(interval: str) -> int:
    """Convert Binance interval string to milliseconds."""
    unit_map = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    try:
        n = int(interval[:-1])
        unit = interval[-1]
        return n * unit_map[unit]
    except (KeyError, ValueError, IndexError):
        raise ValueError(f"Unsupported interval: {interval}")


def _align_to_grid(ts_ms: int, interval_ms: int, direction: str = "ceil") -> int:
    """
    Align a timestamp to the nearest Binance bar boundary.

    direction="ceil"  → next boundary >= ts_ms (used for gap start)
    direction="floor" → last boundary <= ts_ms (used for gap end)
    """
    if direction == "ceil":
        return ((ts_ms + interval_ms - 1) // interval_ms) * interval_ms
    else:  # floor
        return (ts_ms // interval_ms) * interval_ms


def _fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = MAX_KLINES_PER_REQUEST,
) -> tuple[list, int]:
    """
    Fetch klines from Binance REST.

    Returns (rows, window_weight) where:
      rows          — raw Binance kline rows
      window_weight — value of X-MBX-USED-WEIGHT-1M header (cumulative window,
                      NOT the cost of this individual request)
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
        # This is the CUMULATIVE rolling-window weight, not the request cost.
        window_weight = int(resp.headers.get("X-MBX-USED-WEIGHT-1M", 0))
        data = json.loads(resp.read())

    return data, window_weight


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
                   (used to count already_stored; not used to skip fetch,
                   because we still need to verify the full set).

    Returns (bars_to_insert, report).
    bars_to_insert excludes bars already in existing_keys (idempotent).

    Weight accounting: cost tracked as requests_made * KLINES_WEIGHT_PER_REQUEST.
    The header X-MBX-USED-WEIGHT-1M (cumulative window weight) is recorded
    separately for observability only.
    """
    interval_ms = _binance_interval_ms(interval)

    # Align gap boundaries to bar grid for accurate expected-count calculation.
    # Gap start: first bar boundary at or after gap_start_ms
    # Gap end:   last fully-closed bar boundary at or before gap_end_ms
    aligned_start = _align_to_grid(gap_start_ms, interval_ms, "ceil")
    aligned_end = _align_to_grid(gap_end_ms, interval_ms, "floor")

    # Expected number of bars on the aligned grid.
    # A bar at boundary T is fully closed if T + interval_ms <= gap_end_ms.
    expected = max(0, (aligned_end - aligned_start) // interval_ms)
    if aligned_end <= aligned_start:
        expected = 0

    all_bars: List[MarketBar] = []
    requests_made = 0
    last_seen_window_weight = 0
    cursor = aligned_start

    while cursor <= aligned_end and expected > 0:
        # Safety: stop if we've used too much of our self-imposed budget.
        session_cost = requests_made * KLINES_WEIGHT_PER_REQUEST
        if session_cost >= MAX_SESSION_WEIGHT:
            logger.warning(
                "Gap recovery: reached session weight budget (%d >= %d), stopping.",
                session_cost, MAX_SESSION_WEIGHT,
            )
            break

        try:
            rows, window_weight = _fetch_klines(
                symbol, interval, cursor, aligned_end
            )
            requests_made += 1
            last_seen_window_weight = window_weight
        except Exception as exc:
            logger.warning("REST fetch failed: %s", exc)
            break

        if not rows:
            break

        for row in rows:
            bar = MarketBar.from_binance_rest_kline(row, symbol, interval)
            # Filter: only include bars whose open time is within the aligned gap.
            # Binance may return bars starting before startTime in rare edge cases.
            if bar.bar_open < aligned_start or bar.bar_open > aligned_end:
                logger.debug(
                    "Skipping out-of-range bar: bar_open=%d not in [%d, %d]",
                    bar.bar_open, aligned_start, aligned_end,
                )
                continue
            all_bars.append(bar)

        last_open = int(rows[-1][0])
        cursor = last_open + interval_ms

        if len(rows) < MAX_KLINES_PER_REQUEST:
            break

    # Deduplicate by bar_open (safety against any edge cases returning same bar twice)
    seen_opens: set = set()
    unique_bars: List[MarketBar] = []
    for bar in all_bars:
        if bar.bar_open not in seen_opens:
            seen_opens.add(bar.bar_open)
            unique_bars.append(bar)
    all_bars = unique_bars

    # Separate new bars from already-stored ones
    recovered_new = [b for b in all_bars if b.bar_open not in existing_keys]
    already_stored = len(all_bars) - len(recovered_new)
    unresolved = max(0, expected - len(all_bars))

    if unresolved > 0:
        status = "UNRESOLVED_DATA_GAP"
    elif expected > 0 and len(all_bars) >= expected:
        status = "FULL"
    else:
        status = "PARTIAL"

    weight_cost = requests_made * KLINES_WEIGHT_PER_REQUEST

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
        weight_cost=weight_cost,
        last_seen_window_weight=last_seen_window_weight,
    )

    logger.info(
        "Gap recovery: symbol=%s interval=%s expected=%d recovered=%d "
        "already_stored=%d unresolved=%d status=%s "
        "weight_cost=%d window_weight=%d",
        symbol, interval, expected, len(all_bars),
        already_stored, unresolved, status,
        weight_cost, last_seen_window_weight,
    )

    return recovered_new, report
