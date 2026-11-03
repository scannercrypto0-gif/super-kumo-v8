"""Focused negative-case tests for aql_p1a_report_library.

All fixtures are TEST_ONLY synthetic data aligned with Work PR #220 schema.
No real P0 inputs, no network, no private bytes.

Label: TEST_ONLY
Schema: aql-p1-original-opportunity-outcomes.v1 (Work PR #220 HEAD 3d045048)
"""
from __future__ import annotations

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research_wp_r0.aql_p1a_report_library import (
    P1AError,
    InboundRow,
    validate_rows,
    aggregate_summary,
    build_artifact,
    render_markdown_report,
    EXPECTED_DENOMINATOR,
    F1_STATUS_REQUIRED,
    G2_STATUS_REQUIRED,
    SHADOW_STATUS_REQUIRED,
    DIRECTIONAL_STATUS_REQUIRED,
    REFERENCE_KIND_REQUIRED,
    SCOPE,
)

# ---------------------------------------------------------------------------
# TEST_ONLY synthetic helpers — mirror Work PR #220 row structure
# ---------------------------------------------------------------------------

FAKE_SHA256 = "a" * 64
FAKE_WORK_SHA = "3d045048a1145dc58f919dc95849662f47019fb2"
T0_MS = 1_704_067_200_000   # 2024-01-01 00:00:00 UTC bar-aligned

# Expected bars per horizon (Work convention)
_EXPECTED_BARS = {4: 16, 24: 96, 72: 288}

def _market_metrics(ref: float = 50000.0) -> dict:
    """TEST_ONLY neutral market_metrics dict."""
    return {
        "reference_price": ref,
        "observed_high": ref * 1.006,
        "observed_low": ref * 0.995,
        "market_high_return": 0.006,
        "market_low_return": -0.005,
        "market_close_return": 0.001,
    }


def _make_raw_row(
    opp_id: str = "opp-001",
    horizon_hours: int = 4,
    f3_disposition: str = "NO_SIGNAL",
    availability: str = "COMPLETE",
    market_metrics: dict | None = None,
    *,
    override: dict | None = None,
) -> dict:
    """Build a valid TEST_ONLY raw row dict (as Work would emit)."""
    base = {
        "trial_id": "trial-TEST",
        "opportunity_id": opp_id,
        "producer_event_id": f"evt-{opp_id}",
        "envelope_sha256": FAKE_SHA256,
        "decision_cutoff_ms": T0_MS,
        "decision_ms": T0_MS + 2000,
        "f3_disposition": f3_disposition,
        "f3_reason": None,
        "f3_reason_status": "MISSING_FROM_ORIGINAL_RECEIPT",
        "horizon_hours": horizon_hours,
        "window_end_exclusive_ms": T0_MS + horizon_hours * 3_600_000,
        "expected_bars": _EXPECTED_BARS[horizon_hours],
        "observed_bars": _EXPECTED_BARS[horizon_hours] if availability == "COMPLETE" else None,
        "availability": availability,
        "availability_reason": None if availability == "COMPLETE" else "ARCHIVE_END_CENSORED",
        "market_metrics": (market_metrics if market_metrics is not None
                           else (_market_metrics() if availability == "COMPLETE" else None)),
        "directional_metrics": None,
        "direction": None,
        "directional_status": DIRECTIONAL_STATUS_REQUIRED,
        "f1_status": F1_STATUS_REQUIRED,
        "g2_prospective_status": G2_STATUS_REQUIRED,
        "reference_kind": REFERENCE_KIND_REQUIRED,
        "w1_outcome_id": f"w1-{opp_id}-{horizon_hours}h",
        "regime": None,
        "regime_status": "MISSING_ORIGINAL_REGIME",
    }
    if override:
        base.update(override)
    return base


def _make_all_rows(opps: list[dict]) -> list[dict]:
    """For each opportunity dict, create all three horizon rows."""
    rows = []
    for opp in opps:
        for h in (4, 24, 72):
            rows.append(_make_raw_row(
                opp_id=opp["id"],
                horizon_hours=h,
                f3_disposition=opp.get("disposition", "NO_SIGNAL"),
                availability=opp.get("availability", "COMPLETE"),
            ))
    return rows


def _n_opps(n: int) -> list[dict]:
    return [{"id": f"opp-{i:04d}"} for i in range(n)]


# ---------------------------------------------------------------------------
# 1. DENOMINATOR MISMATCH
# ---------------------------------------------------------------------------

def test_denominator_mismatch():
    """validate_rows rejects when unique opportunities ≠ expected_denominator."""
    rows = _make_all_rows(_n_opps(10))
    with pytest.raises(P1AError, match="denominator"):
        validate_rows(rows, expected_denominator=EXPECTED_DENOMINATOR)


# ---------------------------------------------------------------------------
# 2. DUPLICATE (opportunity_id, horizon_hours)
# ---------------------------------------------------------------------------

def test_duplicate_opportunity_horizon():
    """Duplicate (opportunity_id, horizon_hours) must be rejected."""
    rows = _make_all_rows(_n_opps(3))
    # Add a second 4h row for opp-0000
    rows.append(_make_raw_row("opp-0000", horizon_hours=4))
    with pytest.raises(P1AError, match="duplicate"):
        validate_rows(rows, expected_denominator=3)


# ---------------------------------------------------------------------------
# 3. CENSORED row has null market_metrics
# ---------------------------------------------------------------------------

def test_censored_row_has_null_market_metrics():
    """CENSORED availability must have market_metrics=null; non-null raises."""
    raw = _make_raw_row("opp-cens", availability="CENSORED",
                        override={"market_metrics": _market_metrics()})
    with pytest.raises(P1AError, match="non-COMPLETE"):
        validate_rows([raw, *[_make_raw_row("opp-cens", h, availability="CENSORED")
                              for h in (24, 72)]], expected_denominator=1)


# ---------------------------------------------------------------------------
# 4. COMPLETE row with null market_metrics is rejected
# ---------------------------------------------------------------------------

def test_complete_row_requires_market_metrics():
    """COMPLETE availability without market_metrics raises P1AError."""
    raw = _make_raw_row("opp-complete-null", availability="COMPLETE",
                        override={"market_metrics": None})
    with pytest.raises(P1AError, match="COMPLETE row must have"):
        validate_rows([raw, *[_make_raw_row("opp-complete-null", h)
                              for h in (24, 72)]], expected_denominator=1)


# ---------------------------------------------------------------------------
# 5. DIRECTION must always be null (no original direction)
# ---------------------------------------------------------------------------

def test_direction_must_be_null():
    """Any non-null direction value must be rejected."""
    raw = _make_raw_row("opp-dir", override={"direction": "LONG"})
    with pytest.raises(P1AError, match="direction must be null"):
        validate_rows([raw, *[_make_raw_row("opp-dir", h) for h in (24, 72)]],
                      expected_denominator=1)


# ---------------------------------------------------------------------------
# 6. directional_metrics must always be null
# ---------------------------------------------------------------------------

def test_directional_metrics_must_be_null():
    """directional_metrics must be null — no original direction."""
    raw = _make_raw_row("opp-dm", override={"directional_metrics": {"mfe": 0.01}})
    with pytest.raises(P1AError, match="directional_metrics must be null"):
        validate_rows([raw, *[_make_raw_row("opp-dm", h) for h in (24, 72)]],
                      expected_denominator=1)


# ---------------------------------------------------------------------------
# 7. market_low_return > 0 is impossible — rejected
# ---------------------------------------------------------------------------

def test_market_low_return_positive_rejected():
    """market_metrics.market_low_return > 0 is physically impossible."""
    bad_mm = _market_metrics()
    bad_mm["market_low_return"] = 0.002   # positive → impossible
    raw = _make_raw_row("opp-lowret", override={"market_metrics": bad_mm})
    with pytest.raises(P1AError, match="market_low_return > 0 is impossible"):
        validate_rows([raw, *[_make_raw_row("opp-lowret", h) for h in (24, 72)]],
                      expected_denominator=1)


# ---------------------------------------------------------------------------
# 8. Missing required row field
# ---------------------------------------------------------------------------

def test_missing_required_field():
    """A row missing 'availability' must raise P1AError."""
    raw = _make_raw_row("opp-miss")
    del raw["availability"]
    with pytest.raises(P1AError, match="availability"):
        validate_rows([raw, *[_make_raw_row("opp-miss", h) for h in (24, 72)]],
                      expected_denominator=1)


# ---------------------------------------------------------------------------
# 9. UNKNOWN availability accepted — null metrics expected
# ---------------------------------------------------------------------------

def test_unknown_coverage_accepted_with_null_metrics():
    """UNKNOWN availability with null metrics must pass validation."""
    rows = [_make_raw_row("opp-unk", h, availability="UNKNOWN") for h in (4, 24, 72)]
    parsed = validate_rows(rows, expected_denominator=1)
    assert all(r.availability == "UNKNOWN" for r in parsed)
    assert all(r.market_metrics is None for r in parsed)


# ---------------------------------------------------------------------------
# 10. Full N×3 slot validation — small N
# ---------------------------------------------------------------------------

def test_full_slots_small():
    """N opportunities × 3 horizons = N*3 rows; all parsed correctly."""
    N = 5
    rows = _make_all_rows(_n_opps(N))
    parsed = validate_rows(rows, expected_denominator=N)
    assert len(parsed) == N * 3
    for h in (4, 24, 72):
        assert len([r for r in parsed if r.horizon_hours == h]) == N


# ---------------------------------------------------------------------------
# 11. Aggregate summary — COMPLETE counts match
# ---------------------------------------------------------------------------

def test_aggregate_summary_complete_count():
    """Aggregate must count COMPLETE rows correctly per horizon."""
    N = 6
    rows: list[dict] = []
    for i in range(N):
        for h in (4, 24, 72):
            # Make last 2 opps CENSORED for 72h
            avail = "CENSORED" if (i >= 4 and h == 72) else "COMPLETE"
            rows.append(_make_raw_row(f"opp-{i:04d}", h, availability=avail))
    parsed = validate_rows(rows, expected_denominator=N)
    summary = aggregate_summary(parsed)
    assert summary["market_stats_by_horizon"][72]["complete_count"] == 4
    assert summary["market_stats_by_horizon"][4]["complete_count"] == 6


# ---------------------------------------------------------------------------
# 12. Deterministic renderer artifact SHA256
# ---------------------------------------------------------------------------

def test_deterministic_artifact_sha256():
    """build_artifact must produce the same renderer_content_sha256 on repeated calls."""
    N = 4
    rows = _make_all_rows(_n_opps(N))
    parsed = validate_rows(rows, expected_denominator=N)

    art1 = build_artifact(parsed, source_artifact_content_sha256=FAKE_SHA256,
                           generated_at_utc="2026-11-03T00:00:00Z",
                           work_code_sha=FAKE_WORK_SHA)
    art2 = build_artifact(parsed, source_artifact_content_sha256=FAKE_SHA256,
                           generated_at_utc="2026-11-03T00:00:00Z",
                           work_code_sha=FAKE_WORK_SHA)
    assert art1["renderer_content_sha256"] == art2["renderer_content_sha256"]


# ---------------------------------------------------------------------------
# 13. Shadow always NOT_EVALUABLE
# ---------------------------------------------------------------------------

def test_shadow_always_not_evaluable():
    """shadow_status must be NOT_EVALUABLE in summary and rendered Markdown."""
    N = 2
    rows = _make_all_rows(_n_opps(N))
    parsed = validate_rows(rows, expected_denominator=N)
    summary = aggregate_summary(parsed)
    assert summary["shadow_status"] == SHADOW_STATUS_REQUIRED

    art = build_artifact(parsed, source_artifact_content_sha256=FAKE_SHA256,
                          generated_at_utc="2026-11-03T00:00:00Z",
                          work_code_sha=FAKE_WORK_SHA)
    md = render_markdown_report(art)
    assert "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE" in md


# ---------------------------------------------------------------------------
# 14. F1 / G2 constants on every row
# ---------------------------------------------------------------------------

def test_f1_g2_constants_on_rows():
    """Every InboundRow must carry f1_status and g2_prospective_status constants."""
    rows = _make_all_rows(_n_opps(2))
    parsed = validate_rows(rows, expected_denominator=2)
    assert all(r.f1_status == F1_STATUS_REQUIRED for r in parsed)
    assert all(r.g2_prospective_status == G2_STATUS_REQUIRED for r in parsed)


# ---------------------------------------------------------------------------
# 15. Markdown report contains required scope and status labels
# ---------------------------------------------------------------------------

def test_markdown_contains_required_labels():
    """Markdown must contain RETROSPECTIVE_NON_PIT_DESCRIPTIVE scope label."""
    N = 3
    rows = _make_all_rows(_n_opps(N))
    parsed = validate_rows(rows, expected_denominator=N)
    art = build_artifact(parsed, source_artifact_content_sha256=FAKE_SHA256,
                          generated_at_utc="2026-11-03T00:00:00Z",
                          work_code_sha=FAKE_WORK_SHA)
    md = render_markdown_report(art)
    assert "RETROSPECTIVE_NON_PIT" in md
    assert "MISSING_ORIGINAL_CAPTURE" in md
    assert "NOT_CONNECTED" in md
    assert "NON_EXECUTABLE" in md


# ---------------------------------------------------------------------------
# 16. decision_ms < decision_cutoff_ms is impossible lookahead
# ---------------------------------------------------------------------------

def test_decision_ms_before_cutoff_rejected():
    """decision_ms < decision_cutoff_ms represents impossible lookahead."""
    raw = _make_raw_row("opp-la", override={"decision_ms": T0_MS - 1000})
    with pytest.raises(P1AError, match="impossible lookahead"):
        validate_rows([raw, *[_make_raw_row("opp-la", h) for h in (24, 72)]],
                      expected_denominator=1)


# ---------------------------------------------------------------------------
# 17. Missing horizon for one opportunity
# ---------------------------------------------------------------------------

def test_missing_horizon_for_one_opportunity():
    """An opportunity with only 2 horizons must be rejected."""
    rows = _make_all_rows(_n_opps(2))
    # Remove one horizon from opp-0001
    rows = [r for r in rows if not (r["opportunity_id"] == "opp-0001" and r["horizon_hours"] == 72)]
    with pytest.raises(P1AError, match="missing"):
        validate_rows(rows, expected_denominator=2)


# ---------------------------------------------------------------------------
# 18. Nonfinite metric value rejected (NaN / Inf)
# ---------------------------------------------------------------------------

def test_nonfinite_market_metric_rejected():
    """market_metrics containing NaN or Inf must be rejected fail-closed."""
    import math
    bad_mm = _market_metrics()
    bad_mm["market_high_return"] = math.nan
    raw = _make_raw_row("opp-nan", override={"market_metrics": bad_mm})
    with pytest.raises(P1AError, match="finite"):
        validate_rows([raw, *[_make_raw_row("opp-nan", h) for h in (24, 72)]],
                      expected_denominator=1)

    bad_mm2 = _market_metrics()
    bad_mm2["market_close_return"] = math.inf
    raw2 = _make_raw_row("opp-inf", override={"market_metrics": bad_mm2})
    with pytest.raises(P1AError, match="finite"):
        validate_rows([raw2, *[_make_raw_row("opp-inf", h) for h in (24, 72)]],
                      expected_denominator=1)


# ---------------------------------------------------------------------------
# 19. Disposition-stratified market stats present for each disposition
# ---------------------------------------------------------------------------

def test_disposition_stratified_stats_present():
    """market_stats_by_horizon_and_disposition must be keyed by disposition."""
    rows: list[dict] = []
    for i in range(4):
        disp = "NO_SIGNAL" if i < 3 else "REJECTED"
        for h in (4, 24, 72):
            rows.append(_make_raw_row(f"opp-{i:04d}", h, f3_disposition=disp))
    parsed = validate_rows(rows, expected_denominator=4)
    summary = aggregate_summary(parsed)

    dstats = summary["market_stats_by_horizon_and_disposition"]
    assert "NO_SIGNAL" in dstats
    assert "REJECTED" in dstats
    # NO_SIGNAL has 3 opps × 3 horizons = 9 COMPLETE rows
    assert dstats["NO_SIGNAL"][4]["complete_count"] == 3
    assert dstats["NO_SIGNAL"][24]["complete_count"] == 3
    assert dstats["NO_SIGNAL"][72]["complete_count"] == 3
    # REJECTED has 1 opp × 3 horizons
    assert dstats["REJECTED"][4]["complete_count"] == 1
    # Median is numeric (not None) when ≥ 2 samples
    assert dstats["NO_SIGNAL"][4]["market_high_return"]["median"] is not None
