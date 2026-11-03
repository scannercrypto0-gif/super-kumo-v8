"""Tests for G4 — screening.py: lifecycle pipeline and score computation."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tools.scanner_engine_offline.contracts import (
    STAGE_SCREENED, STAGE_QUALIFIED, STAGE_NOMINATED, STAGE_REJECTED,
)
from tools.scanner_engine_offline.features import compute_features
from tools.scanner_engine_offline.screening import (
    screen_candidate, screen_all_profiles, compute_score,
    PROFILE_INTRADAY, PROFILE_SWING, SUPPORTED_PROFILES,
    NOMINATION_THRESHOLD,
)
from tools.scanner_engine_offline.adapters import make_synthetic_bars

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

_FULL_TFS = ["5m", "30m", "1h", "4h", "1d"]


def _make_snapshot(symbol: str = "SOLUSDT", count: int = 35):
    bars = {tf: make_synthetic_bars(symbol, tf, T0, count=count) for tf in _FULL_TFS}
    return compute_features(symbol, T0, bars,
                            bid=Decimal("100"), ask=Decimal("100.02"))


class TestScreenCandidate:
    def test_unknown_profile_returns_rejected(self):
        snap = _make_snapshot()
        result = screen_candidate(snap, "BOGUS")
        assert result.stage == STAGE_REJECTED

    def test_no_bars_stays_screened(self):
        snap = compute_features("SOLUSDT", T0, {})
        result = screen_candidate(snap, PROFILE_INTRADAY)
        assert result.stage == STAGE_SCREENED

    def test_full_bars_reaches_at_least_qualified(self):
        snap = _make_snapshot()
        result = screen_candidate(snap, PROFILE_INTRADAY)
        assert result.stage in {STAGE_QUALIFIED, STAGE_NOMINATED}

    def test_nominated_has_score(self):
        snap = _make_snapshot()
        result = screen_candidate(snap, PROFILE_INTRADAY)
        if result.stage == STAGE_NOMINATED:
            assert result.score is not None
            assert result.score >= NOMINATION_THRESHOLD[PROFILE_INTRADAY]

    def test_score_status_set(self):
        snap = _make_snapshot()
        result = screen_candidate(snap, PROFILE_INTRADAY)
        assert result.score_status in {"SCORED", "SCORE_UNAVAILABLE"}

    def test_candidate_as_dict_complete(self):
        snap = _make_snapshot()
        result = screen_candidate(snap, PROFILE_INTRADAY)
        d = result.as_dict()
        for key in ("symbol", "profile", "stage", "score", "score_status",
                    "reasons", "coverage_ratio", "cutoff_at"):
            assert key in d

    def test_both_profiles_independent(self):
        snap = _make_snapshot()
        intra = screen_candidate(snap, PROFILE_INTRADAY)
        swing = screen_candidate(snap, PROFILE_SWING)
        # Stages may differ; both should complete without error
        assert intra.stage in {STAGE_SCREENED, STAGE_QUALIFIED, STAGE_NOMINATED}
        assert swing.stage in {STAGE_SCREENED, STAGE_QUALIFIED, STAGE_NOMINATED}


class TestScreenAllProfiles:
    def test_returns_all_supported_profiles(self):
        snap = _make_snapshot()
        results = screen_all_profiles(snap)
        assert set(results.keys()) == SUPPORTED_PROFILES

    def test_returns_selected_profiles(self):
        snap = _make_snapshot()
        results = screen_all_profiles(snap, profiles=[PROFILE_INTRADAY])
        assert list(results.keys()) == [PROFILE_INTRADAY]


class TestComputeScore:
    def test_no_bars_unavailable(self):
        snap = compute_features("SOLUSDT", T0, {})
        score, status, reasons = compute_score(snap, PROFILE_INTRADAY)
        assert score is None
        assert status == "SCORE_UNAVAILABLE"

    def test_full_bars_scored(self):
        snap = _make_snapshot()
        score, status, reasons = compute_score(snap, PROFILE_INTRADAY)
        if status == "SCORED":
            assert score is not None
            assert Decimal("0") <= score <= Decimal("100")

    def test_score_rounded_to_2dp(self):
        snap = _make_snapshot()
        score, status, _ = compute_score(snap, PROFILE_INTRADAY)
        if status == "SCORED" and score is not None:
            assert score == score.quantize(Decimal("0.01"))

    def test_unknown_profile_unavailable(self):
        snap = _make_snapshot()
        _, status, _ = compute_score(snap, "UNKNOWN_PROFILE")
        assert status == "SCORE_UNAVAILABLE"

    def test_score_deterministic(self):
        snap = _make_snapshot()
        s1, st1, _ = compute_score(snap, PROFILE_INTRADAY)
        s2, st2, _ = compute_score(snap, PROFILE_INTRADAY)
        assert s1 == s2
        assert st1 == st2
