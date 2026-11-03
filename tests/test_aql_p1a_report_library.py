"""Focused negative-case tests for aql_p1a_report_library.

All fixtures are TEST_ONLY synthetic data — no real P0 inputs.
No network, no private bytes, no real bar data.

Label: TEST_ONLY
"""
from __future__ import annotations

import pytest
import sys
import os

# Ensure the research_wp_r0 package is importable from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research_wp_r0.aql_p1a_report_library import (
    P1AError,
    P1ARow,
    OpportunityInput,
    BarInput,
    compute_outcome_row,
    compute_all_rows,
    build_summary,
    build_artifact,
    render_markdown_report,
    BAR_MS,
    HORIZON_HOURS,
    HORIZONS_MS,
    HORIZON_BARS,
    ORIGINAL_DENOMINATOR,
)

# ---------------------------------------------------------------------------
# TEST_ONLY synthetic helpers
# ---------------------------------------------------------------------------

FAKE_SHA256 = "a" * 64
T0_MS = 1_704_067_200_000  # 2024-01-01 00:00:00 UTC in ms — bar-aligned 15m

def _make_opp(
    opp_id: str = "opp-001",
    disposition: str = "NO_SIGNAL",
    direction: str | None = None,
    cutoff_ms: int = T0_MS,
) -> OpportunityInput:
    return OpportunityInput(
        trial_id="trial-TEST",
        opportunity_id=opp_id,
        producer_event_id=f"evt-{opp_id}",
        envelope_sha256=FAKE_SHA256,
        decision_cutoff_ms=cutoff_ms,
        decision_ms=cutoff_ms,
        f3_disposition=disposition,
        f3_reason_code=None,
        original_direction=direction,
    )


def _make_bar(open_ms: int, ref: float = 50000.0) -> BarInput:
    """Make a neutral synthetic 15m bar."""
    return BarInput(
        open_ms=open_ms,
        open=ref,
        high=ref * 1.002,
        low=ref * 0.998,
        close=ref * 1.001,
        finalized=True,
    )


def _full_bar_index(
    start_ms: int,
    horizon_hours: int,
    ref: float = 50000.0,
) -> dict[int, BarInput]:
    idx = HORIZON_HOURS.index(horizon_hours)
    n = HORIZON_BARS[idx]
    return {start_ms + i * BAR_MS: _make_bar(start_ms + i * BAR_MS, ref) for i in range(n)}


def _source_end(start_ms: int, horizon_hours: int) -> int:
    idx = HORIZON_HOURS.index(horizon_hours)
    return start_ms + HORIZONS_MS[idx]


# ---------------------------------------------------------------------------
# 1. DENOMINATOR MISMATCH — reject wrong count
# ---------------------------------------------------------------------------

def test_denominator_mismatch():
    """compute_all_rows must raise P1AError when N ≠ expected_denominator."""
    opps = [_make_opp(f"opp-{i:04d}") for i in range(10)]  # only 10, expected 653
    bar_idx = _full_bar_index(T0_MS, 4)
    with pytest.raises(P1AError, match="denominator"):
        compute_all_rows(
            opps,
            bar_idx,
            source_end_exclusive_ms=_source_end(T0_MS, 72),
            expected_denominator=ORIGINAL_DENOMINATOR,
        )


# ---------------------------------------------------------------------------
# 2. DUPLICATE OPPORTUNITY — same opportunity_id twice
# ---------------------------------------------------------------------------

def test_duplicate_opportunity_id():
    """compute_all_rows must reject duplicate opportunity_id."""
    opps = [_make_opp("opp-DUPE") for _ in range(2)]
    bar_idx = _full_bar_index(T0_MS, 4)
    with pytest.raises(P1AError, match="duplicate"):
        compute_all_rows(
            opps,
            bar_idx,
            source_end_exclusive_ms=_source_end(T0_MS, 72),
            expected_denominator=2,
        )


# ---------------------------------------------------------------------------
# 3. CENSORED horizon — source ends inside the window
# ---------------------------------------------------------------------------

def test_censored_row_when_source_ends_early():
    """Row must be CENSORED when source ends before window_end."""
    opp = _make_opp("opp-cens", disposition="NO_SIGNAL")
    bar_idx = _full_bar_index(T0_MS, 72)
    # Source ends exactly half-way through the 72h window
    partial_end = T0_MS + HORIZONS_MS[2] // 2
    row = compute_outcome_row(opp, 72, bar_idx, source_end_exclusive_ms=partial_end)
    assert row.coverage_status == "CENSORED"
    assert row.market_high_pct is None
    assert row.mfe is None
    assert row.mae is None


# ---------------------------------------------------------------------------
# 4. EXACT CUTOFF BOUNDARY — window starts exactly at source_end
# ---------------------------------------------------------------------------

def test_censored_when_source_end_equals_window_start():
    """Source ending exactly at the window start → CENSORED."""
    opp = _make_opp("opp-boundary")
    row = compute_outcome_row(
        opp, 4, {},
        source_end_exclusive_ms=T0_MS,  # == decision_cutoff_ms
    )
    assert row.coverage_status == "CENSORED"


# ---------------------------------------------------------------------------
# 5. DIRECTION NULL → directional metrics MUST be null
# ---------------------------------------------------------------------------

def test_direction_null_means_no_directional_metrics():
    """NO_SIGNAL rows have direction=None → mfe/mae must be None even if COMPLETE."""
    opp = _make_opp("opp-nosig", disposition="NO_SIGNAL", direction=None)
    bar_idx = _full_bar_index(T0_MS, 4)
    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.coverage_status == "COMPLETE"
    assert row.market_high_pct is not None   # unsigned metric IS present
    assert row.mfe is None
    assert row.mae is None


# ---------------------------------------------------------------------------
# 6. NO_SIGNAL / REJECTED → fills and PnL always None
# ---------------------------------------------------------------------------

def test_no_signal_has_no_fills_pnl():
    """P1ARow for NO_SIGNAL must never carry fills or pnl."""
    opp = _make_opp("opp-nosig2", disposition="NO_SIGNAL")
    bar_idx = _full_bar_index(T0_MS, 4)
    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.fills is None
    assert row.pnl is None


def test_rejected_has_no_fills_pnl():
    """P1ARow for REJECTED must never carry fills or pnl."""
    opp = _make_opp("opp-rej", disposition="REJECTED")
    bar_idx = _full_bar_index(T0_MS, 4)
    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.fills is None
    assert row.pnl is None


# ---------------------------------------------------------------------------
# 7. FULL 1959 SLOTS — N × 3 horizons integrity
# ---------------------------------------------------------------------------

def test_full_slot_count_small():
    """N opportunities × 3 horizons = N*3 rows, all present."""
    N = 5
    opps = [_make_opp(f"opp-{i:04d}", cutoff_ms=T0_MS + i * BAR_MS) for i in range(N)]

    # Build bar index for all windows
    max_end = T0_MS + N * BAR_MS + HORIZONS_MS[2]
    bar_idx: dict[int, BarInput] = {}
    ts = T0_MS
    while ts < max_end:
        bar_idx[ts] = _make_bar(ts)
        ts += BAR_MS

    rows = compute_all_rows(
        opps, bar_idx,
        source_end_exclusive_ms=max_end,
        expected_denominator=N,
    )
    assert len(rows) == N * 3
    for h in HORIZON_HOURS:
        assert len([r for r in rows if r.horizon_hours == h]) == N


# ---------------------------------------------------------------------------
# 8. DETERMINISTIC HASH — same content, same SHA256
# ---------------------------------------------------------------------------

def test_deterministic_artifact_sha256():
    """build_artifact must produce the same content_sha256 on repeated calls."""
    N = 3
    opps = [_make_opp(f"opp-{i:04d}", cutoff_ms=T0_MS + i * BAR_MS) for i in range(N)]
    max_end = T0_MS + N * BAR_MS + HORIZONS_MS[2]
    bar_idx = {
        T0_MS + j * BAR_MS: _make_bar(T0_MS + j * BAR_MS)
        for j in range(max_end // BAR_MS - T0_MS // BAR_MS + 1)
    }

    rows = compute_all_rows(
        opps, bar_idx,
        source_end_exclusive_ms=max_end,
        expected_denominator=N,
    )
    art1 = build_artifact(
        rows,
        input_manifest_sha256=FAKE_SHA256,
        source_end_exclusive_ms=max_end,
        generated_at_utc="2026-11-03T00:00:00Z",
    )
    art2 = build_artifact(
        rows,
        input_manifest_sha256=FAKE_SHA256,
        source_end_exclusive_ms=max_end,
        generated_at_utc="2026-11-03T00:00:00Z",
    )
    assert art1["content_sha256"] == art2["content_sha256"]


# ---------------------------------------------------------------------------
# 9. INVALID COVERAGE STATUS raises P1AError
# ---------------------------------------------------------------------------

def test_row_rejects_invalid_coverage_status():
    """P1ARow must reject unknown coverage_status."""
    with pytest.raises(P1AError, match="coverage_status"):
        P1ARow(
            trial_id="t", opportunity_id="o", producer_event_id="e",
            envelope_sha256=FAKE_SHA256,
            decision_cutoff_ms=T0_MS, decision_ms=T0_MS,
            f3_disposition="NO_SIGNAL", f3_reason_code=None,
            original_direction=None,
            horizon_hours=4, horizon_ms=HORIZONS_MS[0],
            window_start_ms=T0_MS, window_end_exclusive_ms=T0_MS + HORIZONS_MS[0],
            expected_bars=16,
            coverage_status="PARTIAL",    # invalid
            coverage_reason=None,
            observed_bars=None,
            market_high_pct=None, market_low_pct=None, market_return_pct=None,
            mfe=None, mae=None,
        )


# ---------------------------------------------------------------------------
# 10. SHADOW always NOT_EVALUABLE
# ---------------------------------------------------------------------------

def test_shadow_is_always_not_evaluable():
    """shadow_status must always be NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE."""
    opp = _make_opp("opp-shadow")
    bar_idx = _full_bar_index(T0_MS, 4)
    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.shadow_status == "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE"

    # Also in summary
    N = 2
    opps = [_make_opp(f"opp-{i:04d}", cutoff_ms=T0_MS + i * BAR_MS) for i in range(N)]
    max_end = T0_MS + N * BAR_MS + HORIZONS_MS[2]
    bar_idx2 = {T0_MS + j * BAR_MS: _make_bar(T0_MS + j * BAR_MS)
                for j in range((max_end - T0_MS) // BAR_MS + 1)}
    rows = compute_all_rows(opps, bar_idx2,
                            source_end_exclusive_ms=max_end, expected_denominator=N)
    s = build_summary(rows)
    assert s["shadow_status"] == "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE"


# ---------------------------------------------------------------------------
# 11. GAP IN BAR DATA → UNKNOWN coverage
# ---------------------------------------------------------------------------

def test_gap_produces_unknown_coverage():
    """Missing a bar in the middle of the window → coverage_status=UNKNOWN."""
    opp = _make_opp("opp-gap")
    bar_idx = _full_bar_index(T0_MS, 4)  # 16 bars
    # Remove one bar from the middle
    missing_ts = T0_MS + 8 * BAR_MS
    del bar_idx[missing_ts]
    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.coverage_status == "UNKNOWN"
    assert row.coverage_reason == "GAPPED_WINDOW"
    assert row.market_high_pct is None


# ---------------------------------------------------------------------------
# 12. LONG direction → mfe = max(0, high_excursion), mae = max(0, -low_excursion)
# ---------------------------------------------------------------------------

def test_long_direction_directional_metrics():
    """TRIGGERED LONG row with COMPLETE coverage must have correct mfe/mae signs."""
    opp = _make_opp("opp-long", disposition="TRIGGERED", direction="LONG")
    # Manually build bars with known extreme
    ref = 50000.0
    bar_idx: dict[int, BarInput] = {}
    for i in range(HORIZON_BARS[0]):  # 4h = 16 bars
        ts = T0_MS + i * BAR_MS
        # Bar 8 has a big spike up; bar 12 has a big dip down
        if i == 8:
            bar_idx[ts] = BarInput(open_ms=ts, open=ref, high=ref * 1.05,
                                   low=ref * 0.999, close=ref * 1.01)
        elif i == 12:
            bar_idx[ts] = BarInput(open_ms=ts, open=ref * 1.01, high=ref * 1.011,
                                   low=ref * 0.97, close=ref * 0.985)
        else:
            bar_idx[ts] = _make_bar(ts, ref)

    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.coverage_status == "COMPLETE"
    assert row.original_direction == "LONG"
    # MFE for LONG = max high excursion = (max_high / ref_open) - 1  — must be > 0
    assert row.mfe is not None and row.mfe > 0
    # MAE for LONG = max down excursion = max(0, -(min_low/ref_open - 1)) — must be > 0
    assert row.mae is not None and row.mae > 0


# ---------------------------------------------------------------------------
# 13. COMPLETE row with missing observed_bars raises P1AError
# ---------------------------------------------------------------------------

def test_complete_row_wrong_bar_count_rejected():
    """P1ARow marked COMPLETE must have observed_bars == expected_bars."""
    with pytest.raises(P1AError, match="observed_bars"):
        P1ARow(
            trial_id="t", opportunity_id="o", producer_event_id="e",
            envelope_sha256=FAKE_SHA256,
            decision_cutoff_ms=T0_MS, decision_ms=T0_MS,
            f3_disposition="NO_SIGNAL", f3_reason_code=None,
            original_direction=None,
            horizon_hours=4, horizon_ms=HORIZONS_MS[0],
            window_start_ms=T0_MS, window_end_exclusive_ms=T0_MS + HORIZONS_MS[0],
            expected_bars=16,
            coverage_status="COMPLETE",
            coverage_reason=None,
            observed_bars=15,           # wrong
            market_high_pct=0.01, market_low_pct=-0.01, market_return_pct=0.001,
            mfe=None, mae=None,
        )


# ---------------------------------------------------------------------------
# 14. Markdown report contains required scope label
# ---------------------------------------------------------------------------

def test_markdown_report_contains_scope():
    """render_markdown_report output must contain the RETROSPECTIVE_NON_PIT scope label."""
    N = 2
    opps = [_make_opp(f"opp-{i:04d}", cutoff_ms=T0_MS + i * BAR_MS) for i in range(N)]
    max_end = T0_MS + N * BAR_MS + HORIZONS_MS[2]
    bar_idx = {T0_MS + j * BAR_MS: _make_bar(T0_MS + j * BAR_MS)
               for j in range((max_end - T0_MS) // BAR_MS + 1)}
    rows = compute_all_rows(opps, bar_idx,
                            source_end_exclusive_ms=max_end, expected_denominator=N)
    art = build_artifact(rows, input_manifest_sha256=FAKE_SHA256,
                         source_end_exclusive_ms=max_end,
                         generated_at_utc="2026-11-03T00:00:00Z")
    md = render_markdown_report(art)
    assert "RETROSPECTIVE_NON_PIT" in md
    assert "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE" in md
    assert "MISSING_ORIGINAL_CAPTURE" in md


# ---------------------------------------------------------------------------
# 15. NON-COMPLETE row must not carry metric values
# ---------------------------------------------------------------------------

def test_non_complete_row_rejects_metrics():
    """P1ARow with CENSORED coverage must not carry market excursion values."""
    with pytest.raises(P1AError):
        P1ARow(
            trial_id="t", opportunity_id="o", producer_event_id="e",
            envelope_sha256=FAKE_SHA256,
            decision_cutoff_ms=T0_MS, decision_ms=T0_MS,
            f3_disposition="NO_SIGNAL", f3_reason_code=None,
            original_direction=None,
            horizon_hours=4, horizon_ms=HORIZONS_MS[0],
            window_start_ms=T0_MS, window_end_exclusive_ms=T0_MS + HORIZONS_MS[0],
            expected_bars=16,
            coverage_status="CENSORED",
            coverage_reason="ARCHIVE_END_CENSORED",
            observed_bars=None,
            market_high_pct=0.02,   # must be null for non-COMPLETE
            market_low_pct=None, market_return_pct=None,
            mfe=None, mae=None,
        )


# ---------------------------------------------------------------------------
# 16. F1/G2 constants on every row
# ---------------------------------------------------------------------------

def test_f1_g2_constants_on_rows():
    """Every row must carry f1_capture=MISSING_ORIGINAL_CAPTURE and g2_status=NOT_CONNECTED."""
    opp = _make_opp("opp-const")
    bar_idx = _full_bar_index(T0_MS, 4)
    row = compute_outcome_row(
        opp, 4, bar_idx,
        source_end_exclusive_ms=_source_end(T0_MS, 4),
    )
    assert row.f1_capture == "MISSING_ORIGINAL_CAPTURE"
    assert row.g2_status == "NOT_CONNECTED"
