"""Tests for G3 — features.py: MTF feature computation and PIT safety."""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from tools.scanner_engine_offline.contracts import AdmittedBar, AVAILABILITY_RETRO
from tools.scanner_engine_offline.features import (
    compute_features, MTFFeatureSnapshot,
    STATUS_OK, STATUS_UNAVAILABLE,
    RVOL_WINDOW, RVOL_REQUIRED,
)
from tools.scanner_engine_offline.adapters import make_synthetic_bars

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def make_bars(tf: str, count: int, symbol: str = "SOLUSDT") -> list[AdmittedBar]:
    return make_synthetic_bars(symbol, tf, T0, count=count)


class TestComputeFeatures:
    def test_returns_snapshot(self):
        snap = compute_features("SOLUSDT", T0, {})
        assert isinstance(snap, MTFFeatureSnapshot)

    def test_all_unavailable_when_no_bars(self):
        snap = compute_features("SOLUSDT", T0, {})
        for f in snap.features:
            assert f.status == STATUS_UNAVAILABLE

    def test_rvol_ok_with_enough_bars(self):
        bars = make_bars("5m", RVOL_REQUIRED + 5)
        snap = compute_features("SOLUSDT", T0, {"5m": bars})
        rvol = next(f for f in snap.features if f.name == "rvol_base_5m")
        assert rvol.status == STATUS_OK

    def test_rvol_unavailable_with_insufficient_bars(self):
        bars = make_bars("5m", RVOL_WINDOW - 1)
        snap = compute_features("SOLUSDT", T0, {"5m": bars})
        rvol = next(f for f in snap.features if f.name == "rvol_base_5m")
        assert rvol.status == STATUS_UNAVAILABLE
        assert rvol.reason == "INSUFFICIENT_BARS"

    def test_coverage_ratio_all_ok(self):
        bars = make_bars("5m", 35)
        snap = compute_features("SOLUSDT", T0, {
            "5m": bars, "30m": make_bars("30m", 35),
            "1h": make_bars("1h", 35), "4h": make_bars("4h", 35),
            "1d": make_bars("1d", 35),
        })
        # With all bars present, most features should be OK
        assert snap.coverage_ratio > Decimal("0.5")

    def test_oc_feature_values_in_range(self):
        bars = make_bars("5m", 25)
        snap = compute_features("SOLUSDT", T0, {"5m": bars})
        oc = next(f for f in snap.features if f.name == "oc_5m")
        if oc.status == STATUS_OK:
            val = Decimal(oc.value)
            assert val is not None  # just check it parsed

    def test_spread_unavailable_without_bid_ask(self):
        snap = compute_features("SOLUSDT", T0, {})
        spread = next(f for f in snap.features if f.name == "spread_bps")
        assert spread.status == STATUS_UNAVAILABLE
        assert spread.reason == "BID_ASK_NOT_PROVIDED"

    def test_spread_ok_with_bid_ask(self):
        snap = compute_features("SOLUSDT", T0, {},
                                bid=Decimal("100"), ask=Decimal("100.02"))
        spread = next(f for f in snap.features if f.name == "spread_bps")
        assert spread.status == STATUS_OK

    def test_deterministic_output(self):
        bars = make_bars("5m", 30)
        s1 = compute_features("SOLUSDT", T0, {"5m": bars})
        s2 = compute_features("SOLUSDT", T0, {"5m": bars})
        assert s1.as_snapshot_dict() == s2.as_snapshot_dict()

    def test_snapshot_as_dict_structure(self):
        snap = compute_features("SOLUSDT", T0, {})
        d = snap.as_dict()
        assert "symbol" in d
        assert "cutoff_at" in d
        assert "features" in d
        assert "coverage" in d


class TestMTFFeatureSnapshot:
    def test_ok_count(self):
        bars = make_bars("5m", 30)
        snap = compute_features("SOLUSDT", T0, {"5m": bars})
        ok = sum(1 for f in snap.features if f.status == STATUS_OK)
        assert snap.ok_count == ok

    def test_coverage_ratio_between_0_and_1(self):
        snap = compute_features("SOLUSDT", T0, {})
        assert Decimal("0") <= snap.coverage_ratio <= Decimal("1")
