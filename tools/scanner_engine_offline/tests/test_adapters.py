"""Tests for G6 — adapters.py: synthetic fixtures and envelope adapter."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tools.scanner_engine_offline.contracts import (
    SourceManifest, AVAILABILITY_RETRO, SCHEMA_VERSION,
    sha256_hex, canonical_bytes,
)
from tools.scanner_engine_offline.universe import STATUS_ELIGIBLE, STATUS_REJECTED
from tools.scanner_engine_offline.features import compute_features
from tools.scanner_engine_offline.screening import screen_candidate, PROFILE_INTRADAY
from tools.scanner_engine_offline.adapters import (
    make_synthetic_bars, make_synthetic_market, make_synthetic_universe,
    candidate_to_envelope,
)

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


class TestMakeSyntheticBars:
    def test_returns_requested_count(self):
        bars = make_synthetic_bars("SOLUSDT", "5m", T0, count=25)
        assert len(bars) == 25

    def test_bars_are_pit_clean(self):
        bars = make_synthetic_bars("SOLUSDT", "5m", T0, count=25)
        for bar in bars:
            errs = bar.validate_pit(T0)
            assert errs == [], f"PIT violation: {errs}"

    def test_bars_sorted_ascending(self):
        bars = make_synthetic_bars("SOLUSDT", "5m", T0, count=20)
        open_times = [b.open_at for b in bars]
        assert open_times == sorted(open_times)

    def test_deterministic(self):
        b1 = make_synthetic_bars("SOLUSDT", "5m", T0, count=10)
        b2 = make_synthetic_bars("SOLUSDT", "5m", T0, count=10)
        for a, b in zip(b1, b2):
            assert a.close == b.close

    def test_different_symbols_differ(self):
        b1 = make_synthetic_bars("SOLUSDT", "5m", T0, count=5)
        b2 = make_synthetic_bars("AVAXUSDT", "5m", T0, count=5)
        closes_1 = [bar.close for bar in b1]
        closes_2 = [bar.close for bar in b2]
        assert closes_1 != closes_2

    def test_unsupported_timeframe_raises(self):
        with pytest.raises(ValueError, match="UNSUPPORTED_TIMEFRAME"):
            make_synthetic_bars("SOLUSDT", "3m", T0)

    def test_all_supported_timeframes(self):
        for tf in ("5m", "30m", "1h", "4h", "1d", "1w"):
            bars = make_synthetic_bars("SOLUSDT", tf, T0, count=5)
            assert len(bars) > 0


class TestMakeSyntheticMarket:
    def test_eligible_market(self):
        from tools.scanner_engine_offline.universe import classify_symbol
        m = make_synthetic_market("SOLUSDT", T0, eligible=True)
        item = classify_symbol(m, T0)
        assert item.status == STATUS_ELIGIBLE

    def test_ineligible_market(self):
        from tools.scanner_engine_offline.universe import classify_symbol
        m = make_synthetic_market("SHIBUSDT", T0, eligible=False)
        item = classify_symbol(m, T0)
        assert item.status == STATUS_REJECTED


class TestMakeSyntheticUniverse:
    def test_returns_snapshot(self):
        from tools.scanner_engine_offline.universe import UniverseSnapshot
        snap = make_synthetic_universe(["SOLUSDT", "AVAXUSDT"], T0)
        assert isinstance(snap, UniverseSnapshot)
        assert len(snap.items) == 2

    def test_ineligible_symbols_rejected(self):
        snap = make_synthetic_universe(
            ["SOLUSDT", "SHIBUSDT"], T0, ineligible_symbols=["SHIBUSDT"])
        eligible = [x.symbol for x in snap.eligible]
        assert "SOLUSDT" in eligible
        assert "SHIBUSDT" not in eligible


class TestCandidateToEnvelope:
    def _make_candidate_and_snapshot(self):
        tfs = ["5m", "30m", "1h", "4h", "1d"]
        bars = {tf: make_synthetic_bars("SOLUSDT", tf, T0, count=35) for tf in tfs}
        snap = compute_features("SOLUSDT", T0, bars,
                                bid=Decimal("100"), ask=Decimal("100.02"))
        candidate = screen_candidate(snap, PROFILE_INTRADAY)
        manifest = SourceManifest("D", sha256_hex(b"test"), SCHEMA_VERSION, T0, T0)
        return candidate, snap, manifest

    def test_envelope_created(self):
        candidate, snap, manifest = self._make_candidate_and_snapshot()
        env = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        assert env is not None

    def test_envelope_sealed(self):
        candidate, snap, manifest = self._make_candidate_and_snapshot()
        env = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        assert env.digest is not None and len(env.digest) == 64

    def test_publishable_always_false(self):
        candidate, snap, manifest = self._make_candidate_and_snapshot()
        env = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        assert env.publishable is False
        assert env.as_dict()["publishable"] is False

    def test_delivery_authorized_always_false(self):
        candidate, snap, manifest = self._make_candidate_and_snapshot()
        env = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        assert env.delivery_authorized is False

    def test_availability_class_retro(self):
        candidate, snap, manifest = self._make_candidate_and_snapshot()
        env = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        assert env.availability_class == AVAILABILITY_RETRO

    def test_deterministic_digest(self):
        candidate, snap, manifest = self._make_candidate_and_snapshot()
        env1 = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        env2 = candidate_to_envelope(candidate, snap, manifest, "SCANNER-1")
        assert env1.digest == env2.digest
