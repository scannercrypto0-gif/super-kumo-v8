"""
Tests for Stage 5: coverage analysis — gaps, duplicates, overlap, out-of-order.
"""
import pytest

from tools.raw_vault_offline.coverage import (
    analyse_coverage,
    interval_seconds,
    KNOWN_INTERVALS,
)


BASE_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z
STEP_15M = 900_000            # 15 minutes in ms


def _grid(start_ms: int, count: int, step_ms: int = STEP_15M) -> list[int]:
    return [start_ms + i * step_ms for i in range(count)]


# ── happy path: full coverage ─────────────────────────────────────────────────

def test_full_coverage_no_gaps():
    end_ms = BASE_MS + 4 * STEP_15M
    observed = _grid(BASE_MS, 4)
    report = analyse_coverage(
        "BTCUSDT", "15m", BASE_MS, end_ms, observed
    )
    assert report.expected_bar_count == 4
    assert report.present_count == 4
    assert not report.has_gaps
    assert not report.has_duplicates
    assert report.coverage_fraction == 1.0


# ── gap detection ─────────────────────────────────────────────────────────────

def test_gap_detection():
    end_ms = BASE_MS + 4 * STEP_15M
    observed = _grid(BASE_MS, 4)
    del observed[1]   # remove second bar → gap
    report = analyse_coverage("BTCUSDT", "15m", BASE_MS, end_ms, observed)
    assert report.has_gaps
    assert len(report.missing_slots) == 1
    assert report.missing_slots[0] == BASE_MS + STEP_15M


def test_empty_observed():
    end_ms = BASE_MS + 4 * STEP_15M
    report = analyse_coverage("BTCUSDT", "15m", BASE_MS, end_ms, [])
    assert report.expected_bar_count == 4
    assert report.present_count == 0
    assert len(report.missing_slots) == 4
    assert report.coverage_fraction == 0.0


# ── duplicate detection ───────────────────────────────────────────────────────

def test_duplicate_detection():
    end_ms = BASE_MS + 3 * STEP_15M
    observed = _grid(BASE_MS, 3) + [BASE_MS]  # duplicate first bar
    report = analyse_coverage("BTCUSDT", "15m", BASE_MS, end_ms, observed)
    assert report.has_duplicates
    assert BASE_MS in report.duplicate_slots


# ── out-of-order detection ────────────────────────────────────────────────────

def test_out_of_order_detection():
    end_ms = BASE_MS + 3 * STEP_15M
    observed = [BASE_MS, BASE_MS + 2 * STEP_15M, BASE_MS + STEP_15M]
    report = analyse_coverage("BTCUSDT", "15m", BASE_MS, end_ms, observed)
    assert report.has_out_of_order
    assert BASE_MS + STEP_15M in report.out_of_order_slots


# ── overlap with prior chunk ──────────────────────────────────────────────────

def test_overlap_with_prior_chunk():
    prior_end = BASE_MS + 2 * STEP_15M
    end_ms = BASE_MS + 4 * STEP_15M
    # observed includes a bar that precedes prior_end
    observed = _grid(BASE_MS, 4)
    report = analyse_coverage(
        "BTCUSDT", "15m", BASE_MS, end_ms, observed,
        prior_chunk_last_close_utc_ms=prior_end,
    )
    assert report.overlap_with_prior_chunk


def test_no_overlap_when_clean():
    prior_end = BASE_MS
    end_ms = BASE_MS + 4 * STEP_15M
    observed = _grid(BASE_MS, 4)
    report = analyse_coverage(
        "BTCUSDT", "15m", BASE_MS, end_ms, observed,
        prior_chunk_last_close_utc_ms=prior_end,
    )
    # all observed bars start at BASE_MS which equals prior_end (boundary, not overlap)
    # first bar open_time == prior_end → NOT < prior_end → no overlap
    # But actually BASE_MS < BASE_MS is False, so no overlap
    assert not report.overlap_with_prior_chunk


# ── incomplete final bar ──────────────────────────────────────────────────────

def test_incomplete_final_bar():
    end_ms = BASE_MS + 2 * STEP_15M
    observed = _grid(BASE_MS, 2)
    # now_utc_ms < last bar close → incomplete final
    last_open = BASE_MS + STEP_15M
    last_close = last_open + STEP_15M
    now_ms = last_close - 1  # before close
    report = analyse_coverage(
        "BTCUSDT", "15m", BASE_MS, end_ms, observed,
        now_utc_ms=now_ms,
    )
    assert report.has_incomplete_final


def test_no_incomplete_when_bar_closed():
    end_ms = BASE_MS + 2 * STEP_15M
    observed = _grid(BASE_MS, 2)
    last_close = BASE_MS + 2 * STEP_15M
    now_ms = last_close + 1
    report = analyse_coverage(
        "BTCUSDT", "15m", BASE_MS, end_ms, observed,
        now_utc_ms=now_ms,
    )
    assert not report.has_incomplete_final


# ── known intervals ───────────────────────────────────────────────────────────

def test_interval_seconds_known():
    assert interval_seconds("1m") == 60
    assert interval_seconds("1h") == 3600
    assert interval_seconds("1d") == 86400


def test_interval_seconds_unknown():
    with pytest.raises(ValueError):
        interval_seconds("99x")


# ── empty grid (chunk start == end) ──────────────────────────────────────────

def test_empty_grid():
    report = analyse_coverage("BTCUSDT", "15m", BASE_MS, BASE_MS, [])
    assert report.expected_bar_count == 0
    assert any("EMPTY_EXPECTED_GRID" in n for n in report.notes)
