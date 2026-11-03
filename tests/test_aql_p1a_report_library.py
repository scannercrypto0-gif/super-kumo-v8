"""Unit tests for aql_p1a_report_library.py — P1-A consumer/renderer.

NO access to Work PR #220 private artifacts.
All fixtures are TEST_ONLY synthetic data satisfying the Work contract shape.

Test count: 56  (must stay in sync with CI workflow Verify step)

Coverage:
  Original 19 tests (T01–T19)
  Fix-1: validate_report()                           T20–T27
  Fix-2: cross-horizon identity + F3 consistency     T28–T34
  Fix-3: exact timing / bar-count / reason rules     T35–T46
  Fix-4: market_metrics reconciliation               T47–T54
  Whole-report fixture (TEST_ONLY)                   T55–T56
"""
from __future__ import annotations

import math
import pytest

from research_wp_r0.aql_p1a_report_library import (
    SCHEMA_VERSION,
    RENDERER_VERSION,
    SCOPE,
    SHADOW_STATUS_REQUIRED,
    DIRECTIONAL_STATUS_REQUIRED,
    F1_STATUS_REQUIRED,
    G2_STATUS_REQUIRED,
    REFERENCE_KIND_REQUIRED,
    EXPECTED_DENOMINATOR,
    InboundRow,
    P1AError,
    aggregate_summary,
    build_artifact,
    render_markdown_report,
    validate_report,
    validate_rows,
)

# ---------------------------------------------------------------------------
# TEST_ONLY shared fixtures
# ---------------------------------------------------------------------------

FAKE_SHA256 = "a" * 64
FAKE_WORK_SHA = "3d045048a1145dc58f919dc95849662f47019fb2"
T0_MS = 1_704_067_200_000          # 2024-01-01 00:00:00 UTC

_EXPECTED_BARS = {4: 16, 24: 96, 72: 288}


def _market_metrics(ref: float = 50_000.0) -> dict:
    """Valid market_metrics dict for COMPLETE rows."""
    return {
        "reference_price": ref,
        "observed_high":   ref * 1.006,
        "observed_low":    ref * 0.995,
        "market_high_return":  0.006,
        "market_low_return":  -0.005,
        "market_close_return": 0.001,
    }


def _make_raw_row(
    opp_id: str,
    horizon_hours: int = 4,
    f3_disposition: str = "NO_SIGNAL",
    availability: str = "COMPLETE",
    market_metrics: dict | None = None,
    *,
    override: dict | None = None,
) -> dict:
    """Build a valid TEST_ONLY raw row dict."""
    avail_reason = None if availability == "COMPLETE" else "ARCHIVE_END_CENSORED"
    obs_bars = _EXPECTED_BARS[horizon_hours] if availability == "COMPLETE" else None
    base = {
        "trial_id":           "trial-TEST",
        "opportunity_id":     opp_id,
        "producer_event_id":  f"evt-{opp_id}",
        "envelope_sha256":    FAKE_SHA256,
        "decision_cutoff_ms": T0_MS,
        "decision_ms":        T0_MS + 2000,
        "f3_disposition":     f3_disposition,
        "f3_reason":          None,
        "f3_reason_status":   "MISSING_FROM_ORIGINAL_RECEIPT",
        "horizon_hours":      horizon_hours,
        "window_end_exclusive_ms": T0_MS + horizon_hours * 3_600_000,
        "expected_bars":      _EXPECTED_BARS[horizon_hours],
        "observed_bars":      obs_bars,
        "availability":       availability,
        "availability_reason": avail_reason,
        "market_metrics":     (market_metrics if market_metrics is not None
                               else (_market_metrics() if availability == "COMPLETE" else None)),
        "directional_metrics": None,
        "direction":          None,
        "directional_status": DIRECTIONAL_STATUS_REQUIRED,
        "f1_status":          F1_STATUS_REQUIRED,
        "g2_prospective_status": G2_STATUS_REQUIRED,
        "reference_kind":     REFERENCE_KIND_REQUIRED,
        "w1_outcome_id":      f"w1-{opp_id}-{horizon_hours}h",
        "regime":             None,
        "regime_status":      "MISSING_ORIGINAL_REGIME",
    }
    if override:
        base.update(override)
    return base


def _make_rows_all_horizons(
    opp_id: str,
    f3_disposition: str = "NO_SIGNAL",
    availability_4h:  str = "COMPLETE",
    availability_24h: str = "COMPLETE",
    availability_72h: str = "COMPLETE",
) -> list[dict]:
    return [
        _make_raw_row(opp_id, h, f3_disposition, av)
        for h, av in ((4, availability_4h), (24, availability_24h), (72, availability_72h))
    ]


def _parsed_row_kwargs(raw: dict) -> dict:
    return {k: raw[k] for k in InboundRow.__dataclass_fields__}


# ---------------------------------------------------------------------------
# Original 19 tests (T01–T19)
# ---------------------------------------------------------------------------

def test_T01_valid_complete_row():
    raw = _make_raw_row("opp-0001")
    row = InboundRow(**_parsed_row_kwargs(raw))
    assert row.opportunity_id == "opp-0001"
    assert row.availability == "COMPLETE"


def test_T02_bad_sha():
    raw = _make_raw_row("opp-X", override={"envelope_sha256": "not-a-sha"})
    with pytest.raises(P1AError, match="envelope_sha256"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T03_censored_with_metrics():
    raw = _make_raw_row("opp-X", availability="CENSORED",
                        market_metrics=_market_metrics())
    with pytest.raises(P1AError, match="non-COMPLETE"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T04_nan_metric():
    mm = _market_metrics()
    mm["market_high_return"] = float("nan")
    raw = _make_raw_row("opp-X", market_metrics=mm)
    with pytest.raises(P1AError, match="finite"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T05_direction_not_none():
    raw = _make_raw_row("opp-X", override={"direction": "LONG"})
    with pytest.raises(P1AError, match="direction"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T06_directional_metrics_not_none():
    raw = _make_raw_row("opp-X", override={"directional_metrics": {"x": 1}})
    with pytest.raises(P1AError, match="directional_metrics"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T07_bad_f1_status():
    raw = _make_raw_row("opp-X", override={"f1_status": "SOMETHING_ELSE"})
    with pytest.raises(P1AError, match="f1_status"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T08_bad_g2_status():
    raw = _make_raw_row("opp-X",
                        override={"g2_prospective_status": "SOMETHING_ELSE"})
    with pytest.raises(P1AError, match="g2_prospective_status"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T09_bad_reference_kind():
    raw = _make_raw_row("opp-X",
                        override={"reference_kind": "LIMIT_AT_OPEN"})
    with pytest.raises(P1AError, match="reference_kind"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T10_missing_metric_key():
    mm = _market_metrics()
    del mm["observed_high"]
    raw = _make_raw_row("opp-X", market_metrics=mm)
    with pytest.raises(P1AError, match="market_metrics missing key"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T11_zero_reference_price():
    mm = _market_metrics(ref=0.0)
    raw = _make_raw_row("opp-X", market_metrics=mm)
    with pytest.raises(P1AError, match="reference_price"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T12_positive_low_return():
    mm = _market_metrics()
    mm["market_low_return"] = 0.001
    raw = _make_raw_row("opp-X", market_metrics=mm)
    with pytest.raises(P1AError, match="market_low_return"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T13_duplicate_slot():
    rows = _make_rows_all_horizons("opp-DUP")
    rows.append(_make_raw_row("opp-DUP", horizon_hours=4))
    with pytest.raises(P1AError, match="duplicate"):
        validate_rows(rows, expected_denominator=1)


def test_T14_wrong_denominator():
    rows = _make_rows_all_horizons("opp-ONLY")
    with pytest.raises(P1AError, match="denominator"):
        validate_rows(rows, expected_denominator=2)


def test_T15_missing_horizon():
    rows = [_make_raw_row("opp-M", 4), _make_raw_row("opp-M", 24)]
    with pytest.raises(P1AError):
        validate_rows(rows, expected_denominator=1)


def test_T16_f3_counts():
    rows_raw = _make_rows_all_horizons("opp-0001", "NO_SIGNAL")
    rows_raw += _make_rows_all_horizons("opp-0002", "TRIGGERED")
    parsed = validate_rows(rows_raw, expected_denominator=2)
    summary = aggregate_summary(parsed)
    assert summary["f3_disposition_counts"]["NO_SIGNAL"] == 1
    assert summary["f3_disposition_counts"]["TRIGGERED"] == 1


def test_T17_censored_count():
    rows_raw = _make_rows_all_horizons("opp-C1",
                                       availability_4h="CENSORED",
                                       availability_24h="CENSORED",
                                       availability_72h="CENSORED")
    parsed = validate_rows(rows_raw, expected_denominator=1)
    summary = aggregate_summary(parsed)
    for h in (4, 24, 72):
        assert summary["coverage_by_horizon"][h].get("CENSORED", 0) == 1
        assert summary["coverage_by_horizon"][h].get("COMPLETE", 0) == 0


def test_T18_build_artifact():
    rows_raw = _make_rows_all_horizons("opp-BA")
    parsed = validate_rows(rows_raw, expected_denominator=1)
    artifact = build_artifact(
        parsed,
        source_artifact_content_sha256=FAKE_SHA256,
        generated_at_utc="2026-11-03T10:00:00Z",
        work_code_sha=FAKE_WORK_SHA,
    )
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["scope"] == SCOPE
    assert "renderer_content_sha256" in artifact
    assert len(artifact["renderer_content_sha256"]) == 64


def test_T19_render_markdown():
    rows_raw = _make_rows_all_horizons("opp-MD")
    parsed = validate_rows(rows_raw, expected_denominator=1)
    artifact = build_artifact(
        parsed,
        source_artifact_content_sha256=FAKE_SHA256,
        generated_at_utc="2026-11-03T10:00:00Z",
        work_code_sha=FAKE_WORK_SHA,
    )
    md = render_markdown_report(artifact)
    assert "RETROSPECTIVE_NON_PIT_DESCRIPTIVE" in md
    assert "MISSING_ORIGINAL_CAPTURE" in md
    assert "renderer content sha256" in md.lower()


# ---------------------------------------------------------------------------
# FIX-1: validate_report() — T20–T27
# ---------------------------------------------------------------------------

def _make_valid_artifact(opp_id: str = "opp-VR") -> dict:
    rows_raw = _make_rows_all_horizons(opp_id)
    parsed = validate_rows(rows_raw, expected_denominator=1)
    return build_artifact(
        parsed,
        source_artifact_content_sha256=FAKE_SHA256,
        generated_at_utc="2026-11-03T10:00:00Z",
        work_code_sha=FAKE_WORK_SHA,
    )


def test_T20_validate_report_happy_path():
    artifact = _make_valid_artifact()
    validate_report(artifact)


def test_T21_wrong_schema_version():
    artifact = _make_valid_artifact()
    artifact["schema_version"] = "aql-p1-WRONG.v99"
    with pytest.raises(P1AError, match="schema_version"):
        validate_report(artifact)


def test_T22_wrong_scope():
    artifact = _make_valid_artifact()
    artifact["scope"] = "WRONG_SCOPE"
    with pytest.raises(P1AError, match="scope"):
        validate_report(artifact)


def test_T23_tampered_hash():
    artifact = _make_valid_artifact()
    artifact["renderer_content_sha256"] = "b" * 64
    with pytest.raises(P1AError, match="renderer_content_sha256"):
        validate_report(artifact)


def test_T24_mutated_content():
    artifact = _make_valid_artifact()
    artifact["summary"]["denominator"] = 999
    with pytest.raises(P1AError, match="renderer_content_sha256"):
        validate_report(artifact)


def test_T25_missing_hash_key():
    artifact = _make_valid_artifact()
    del artifact["renderer_content_sha256"]
    with pytest.raises(P1AError, match="renderer_content_sha256"):
        validate_report(artifact)


def test_T26_bad_hash_format():
    artifact = _make_valid_artifact()
    artifact["renderer_content_sha256"] = "not-a-hash"
    with pytest.raises(P1AError, match="renderer_content_sha256"):
        validate_report(artifact)


def test_T27_render_validates_before_render():
    artifact = _make_valid_artifact()
    artifact["renderer_content_sha256"] = "c" * 64
    with pytest.raises(P1AError):
        render_markdown_report(artifact)


# ---------------------------------------------------------------------------
# FIX-2: cross-horizon identity + F3 consistency — T28–T34
# ---------------------------------------------------------------------------

def test_T28_consistent_cross_horizon():
    rows = _make_rows_all_horizons("opp-CONS")
    parsed = validate_rows(rows, expected_denominator=1)
    assert len(parsed) == 3


@pytest.mark.parametrize("field,bad_value,match_str", [
    ("trial_id",          "DIFFERENT-TRIAL",  "trial_id"),
    ("producer_event_id", "DIFFERENT-EVT",    "producer_event_id"),
    ("envelope_sha256",   "b" * 64,           "envelope_sha256"),
    ("f3_disposition",    "TRIGGERED",        "f3_disposition"),
])
def test_T29_to_T32_cross_horizon_field_inconsistency(field, bad_value, match_str):
    rows = _make_rows_all_horizons("opp-INCONS")
    # Mutate the 24h row
    r = dict(rows[1])
    r[field] = bad_value
    rows[1] = r
    with pytest.raises(P1AError, match=match_str):
        validate_rows(rows, expected_denominator=1)


def test_T33_cross_horizon_cutoff_inconsistency():
    """T33 — decision_cutoff_ms changes between horizons → cross-horizon error."""
    rows = _make_rows_all_horizons("opp-CUT")
    # Shift cutoff in 24h row; keep row-level invariants consistent
    new_cutoff = T0_MS + 1000
    r = dict(rows[1])
    r["decision_cutoff_ms"]        = new_cutoff
    r["decision_ms"]               = new_cutoff + 2000
    r["window_end_exclusive_ms"]   = new_cutoff + 24 * 3_600_000
    rows[1] = r
    with pytest.raises(P1AError, match="decision_cutoff_ms"):
        validate_rows(rows, expected_denominator=1)


def test_T34_cross_horizon_decision_ms_inconsistency():
    """T34 — decision_ms changes between horizons → cross-horizon error."""
    rows = _make_rows_all_horizons("opp-DEC")
    new_cutoff = T0_MS + 2000
    r = dict(rows[2])  # 72h row
    r["decision_cutoff_ms"]        = new_cutoff
    r["decision_ms"]               = new_cutoff + 2000
    r["window_end_exclusive_ms"]   = new_cutoff + 72 * 3_600_000
    rows[2] = r
    with pytest.raises(P1AError, match="decision_cutoff_ms"):
        validate_rows(rows, expected_denominator=1)


# ---------------------------------------------------------------------------
# FIX-3: exact timing / bar-count / availability-reason rules — T35–T46
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_decision_ms,match_str", [
    (T0_MS,        "decision_ms"),
    (T0_MS + 1000, "decision_ms"),
    (T0_MS + 3000, "decision_ms"),
])
def test_T35_to_T37_bad_decision_ms(bad_decision_ms, match_str):
    raw = _make_raw_row("opp-DM", override={"decision_ms": bad_decision_ms})
    with pytest.raises(P1AError, match=match_str):
        InboundRow(**_parsed_row_kwargs(raw))


@pytest.mark.parametrize("h,bad_end", [
    (4,  T0_MS + 3 * 3_600_000),
    (24, T0_MS + 4 * 3_600_000),
    (72, T0_MS + 24 * 3_600_000),
])
def test_T38_to_T40_bad_window_end(h, bad_end):
    raw = _make_raw_row("opp-WE", h,
                        override={"window_end_exclusive_ms": bad_end})
    with pytest.raises(P1AError, match="window_end"):
        InboundRow(**_parsed_row_kwargs(raw))


@pytest.mark.parametrize("h,bad_expected_bars", [
    (4,  15),
    (24, 97),
    (72, 289),
])
def test_T41_to_T43_bad_expected_bars(h, bad_expected_bars):
    raw = _make_raw_row("opp-EB", h,
                        override={"expected_bars": bad_expected_bars})
    with pytest.raises(P1AError, match="expected_bars"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T44_complete_with_reason():
    raw = _make_raw_row("opp-AR",
                        override={"availability_reason": "ARCHIVE_END_CENSORED"})
    with pytest.raises(P1AError, match="availability_reason"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T45_censored_without_reason():
    raw = _make_raw_row("opp-AR2", availability="CENSORED",
                        override={"availability_reason": None})
    with pytest.raises(P1AError, match="availability_reason"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T46_unknown_without_reason():
    raw = _make_raw_row("opp-AR3", availability="UNKNOWN",
                        override={"availability_reason": None})
    with pytest.raises(P1AError, match="availability_reason"):
        InboundRow(**_parsed_row_kwargs(raw))


# ---------------------------------------------------------------------------
# FIX-4: market_metrics reconciliation — T47–T54
# ---------------------------------------------------------------------------

def test_T47_observed_high_below_ref():
    mm = _market_metrics(ref=50_000.0)
    mm["observed_high"] = 49_000.0
    raw = _make_raw_row("opp-HR", market_metrics=mm)
    with pytest.raises(P1AError, match="observed_high"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T48_high_return_below_low_return():
    mm = _market_metrics()
    mm["market_high_return"] = -0.010
    mm["market_low_return"]  = -0.005
    raw = _make_raw_row("opp-RL", market_metrics=mm)
    with pytest.raises(P1AError, match="market_high_return"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T49_equal_returns_flat_bar_valid():
    ref = 50_000.0
    mm = {
        "reference_price":     ref,
        "observed_high":       ref,
        "observed_low":        ref,
        "market_high_return":  0.0,
        "market_low_return":   0.0,
        "market_close_return": 0.0,
    }
    raw = _make_raw_row("opp-FL", market_metrics=mm)
    row = InboundRow(**_parsed_row_kwargs(raw))
    assert row.market_metrics["market_high_return"] == 0.0


def test_T50_inf_metric():
    mm = _market_metrics()
    mm["market_close_return"] = math.inf
    raw = _make_raw_row("opp-INF", market_metrics=mm)
    with pytest.raises(P1AError, match="finite"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T51_negative_reference_price():
    mm = _market_metrics(ref=-1.0)
    raw = _make_raw_row("opp-NR", market_metrics=mm)
    with pytest.raises(P1AError, match="reference_price"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T52_positive_low_return_impossible():
    mm = _market_metrics()
    mm["market_low_return"] = 0.001
    raw = _make_raw_row("opp-PLR", market_metrics=mm)
    with pytest.raises(P1AError, match="market_low_return"):
        InboundRow(**_parsed_row_kwargs(raw))


def test_T53_high_zero_low_negative_valid():
    ref = 40_000.0
    mm = {
        "reference_price":     ref,
        "observed_high":       ref,
        "observed_low":        ref * 0.995,
        "market_high_return":  0.0,
        "market_low_return":  -0.005,
        "market_close_return": -0.002,
    }
    raw = _make_raw_row("opp-HZ", market_metrics=mm)
    row = InboundRow(**_parsed_row_kwargs(raw))
    assert row.market_metrics["market_high_return"] == 0.0


def test_T54_nan_observed_high():
    mm = _market_metrics()
    mm["observed_high"] = float("nan")
    raw = _make_raw_row("opp-NAN", market_metrics=mm)
    with pytest.raises(P1AError, match="finite"):
        InboundRow(**_parsed_row_kwargs(raw))


# ---------------------------------------------------------------------------
# Whole-report fixture (TEST_ONLY synthetic) — T55–T56
# ---------------------------------------------------------------------------

def test_T55_end_to_end_small():
    """T55 — End-to-end: 2 opportunities, mixed F3/coverage, validate_report passes."""
    rows_raw = (
        _make_rows_all_horizons("opp-A", "NO_SIGNAL",
                                availability_72h="CENSORED") +
        _make_rows_all_horizons("opp-B", "TRIGGERED")
    )
    parsed = validate_rows(rows_raw, expected_denominator=2)
    artifact = build_artifact(
        parsed,
        source_artifact_content_sha256=FAKE_SHA256,
        generated_at_utc="2026-11-03T10:00:00Z",
        work_code_sha=FAKE_WORK_SHA,
    )

    validate_report(artifact)

    s = artifact["summary"]
    assert s["denominator"] == 2
    assert s["total_horizon_slots"] == 6
    assert s["f3_disposition_counts"]["NO_SIGNAL"] == 1
    assert s["f3_disposition_counts"]["TRIGGERED"] == 1

    cov_72 = s["coverage_by_horizon"][72]
    assert cov_72.get("COMPLETE", 0) == 1
    assert cov_72.get("CENSORED", 0) == 1

    md = render_markdown_report(artifact)
    assert SCHEMA_VERSION in md
    assert SCOPE in md
    assert "NOT_EVALUABLE_MISSING_ORIGINAL_DIRECTION" in md
    assert "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE" in md


def test_T56_deterministic_sha():
    """T56 — Two identical builds produce the same renderer_content_sha256."""
    rows_raw = _make_rows_all_horizons("opp-DET")

    def _build():
        parsed = validate_rows(rows_raw, expected_denominator=1)
        return build_artifact(
            parsed,
            source_artifact_content_sha256=FAKE_SHA256,
            generated_at_utc="2026-11-03T10:00:00Z",
            work_code_sha=FAKE_WORK_SHA,
        )

    a1 = _build()
    a2 = _build()
    assert a1["renderer_content_sha256"] == a2["renderer_content_sha256"]
