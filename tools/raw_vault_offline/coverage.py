"""
Stage 5 — Temporal coverage / gap / overlap ledger.

All intervals are half-open UTC [start, end).
No forward-fill in RAW. No silently repaired source.
UNKNOWN coverage is represented, never invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


KNOWN_INTERVALS: dict[str, int] = {
    "1m":   60,
    "3m":   180,
    "5m":   300,
    "15m":  900,
    "30m":  1800,
    "1h":   3600,
    "2h":   7200,
    "4h":   14400,
    "6h":   21600,
    "8h":   28800,
    "12h":  43200,
    "1d":   86400,
    "3d":   259200,
    "1w":   604800,
}


def interval_seconds(interval: str) -> int:
    if interval not in KNOWN_INTERVALS:
        raise ValueError(f"Unknown interval: {interval!r}. Known: {sorted(KNOWN_INTERVALS)}")
    return KNOWN_INTERVALS[interval]


class BarStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    INCOMPLETE_FINAL = "INCOMPLETE_FINAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BarSlot:
    """One expected candle bar slot in half-open UTC grid."""
    open_time_utc_ms: int   # epoch milliseconds, half-open interval start
    close_time_utc_ms: int  # exclusive end of this bar's interval
    status: BarStatus
    observed_count: int = 0  # how many times this slot appeared in source


@dataclass
class CoverageReport:
    """
    Gap/overlap report for one (instrument, interval, chunk) combination.
    No fill applied: gaps are reported, not patched.
    """
    instrument: str
    interval: str
    chunk_start_utc_ms: int    # inclusive
    chunk_end_utc_ms: int      # exclusive
    expected_bar_count: int
    present_count: int
    missing_slots: list[int]   # open_time_utc_ms of missing bars
    duplicate_slots: list[int] # open_time_utc_ms of duplicates
    out_of_order_slots: list[int]
    overlap_with_prior_chunk: bool
    has_incomplete_final: bool
    coverage_fraction: float   # 0.0–1.0
    notes: list[str] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing_slots)

    @property
    def has_duplicates(self) -> bool:
        return bool(self.duplicate_slots)

    @property
    def has_out_of_order(self) -> bool:
        return bool(self.out_of_order_slots)


def _ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _expected_grid(
    start_utc_ms: int,
    end_utc_ms: int,
    interval_sec: int,
) -> list[int]:
    """Return sorted list of expected bar open_times in [start, end)."""
    step_ms = interval_sec * 1000
    ts = start_utc_ms
    result = []
    while ts < end_utc_ms:
        result.append(ts)
        ts += step_ms
    return result


def analyse_coverage(
    instrument: str,
    interval: str,
    chunk_start_utc_ms: int,
    chunk_end_utc_ms: int,
    observed_open_times_ms: list[int],
    *,
    prior_chunk_last_close_utc_ms: Optional[int] = None,
    now_utc_ms: Optional[int] = None,
) -> CoverageReport:
    """
    Produce a CoverageReport for one chunk.

    Parameters
    ----------
    observed_open_times_ms : open_time of each bar actually seen in source data,
                             in the order they appear (may be unsorted).
    prior_chunk_last_close_utc_ms : exclusive end of the previous chunk, for
                                     cross-day continuity check.
    now_utc_ms             : current time for incomplete-final detection.
    """
    sec = interval_seconds(interval)
    step_ms = sec * 1000
    expected = _expected_grid(chunk_start_utc_ms, chunk_end_utc_ms, sec)

    # build frequency map
    freq: dict[int, int] = {}
    for t in observed_open_times_ms:
        freq[t] = freq.get(t, 0) + 1

    # classify bars
    present_count = 0
    missing_slots = []
    duplicate_slots = []

    for slot in expected:
        cnt = freq.get(slot, 0)
        if cnt == 0:
            missing_slots.append(slot)
        elif cnt == 1:
            present_count += 1
        else:
            duplicate_slots.append(slot)
            present_count += 1  # the first occurrence is considered present

    # detect out-of-order
    prev = None
    out_of_order = []
    for t in observed_open_times_ms:
        if prev is not None and t <= prev:
            out_of_order.append(t)
        prev = t

    # cross-day overlap
    overlap = False
    if prior_chunk_last_close_utc_ms is not None:
        # if any observed bar starts before the prior chunk's exclusive end → overlap
        for t in observed_open_times_ms:
            if t < prior_chunk_last_close_utc_ms:
                overlap = True
                break

    # incomplete final bar
    has_incomplete_final = False
    if now_utc_ms is not None and expected:
        last_expected = expected[-1]
        last_close = last_expected + step_ms
        if last_close > now_utc_ms and last_expected in freq:
            has_incomplete_final = True

    coverage_frac = (present_count / len(expected)) if expected else 0.0

    notes: list[str] = []
    if not expected:
        notes.append("EMPTY_EXPECTED_GRID — check chunk boundaries")
    if overlap:
        notes.append("OVERLAP_WITH_PRIOR_CHUNK detected")
    if has_incomplete_final:
        notes.append("INCOMPLETE_FINAL_BAR (bar open but close not yet reached)")

    return CoverageReport(
        instrument=instrument,
        interval=interval,
        chunk_start_utc_ms=chunk_start_utc_ms,
        chunk_end_utc_ms=chunk_end_utc_ms,
        expected_bar_count=len(expected),
        present_count=present_count,
        missing_slots=missing_slots,
        duplicate_slots=duplicate_slots,
        out_of_order_slots=out_of_order,
        overlap_with_prior_chunk=overlap,
        has_incomplete_final=has_incomplete_final,
        coverage_fraction=round(coverage_frac, 6),
        notes=notes,
    )
