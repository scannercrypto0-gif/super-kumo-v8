"""Tests for G7 — engine.py: full offline scan run."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tools.scanner_engine_offline.contracts import (
    SourceManifest, SCHEMA_VERSION, sha256_hex, canonical_bytes,
    STAGE_NOMINATED,
)
from tools.scanner_engine_offline.engine import OfflineScannerEngine, ScanRunConfig
from tools.scanner_engine_offline.adapters import (
    make_synthetic_bars, make_synthetic_universe,
)

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

SYMBOLS = ["SOLUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT"]
TFS = ["5m", "30m", "1h", "4h", "1d"]


def _make_manifest() -> SourceManifest:
    return SourceManifest(
        dataset_id="TEST-DS",
        dataset_sha=sha256_hex(canonical_bytes({"test": True})),
        schema_version=SCHEMA_VERSION,
        cutoff_at=T0,
        created_at=T0,
    )


def _make_bars(symbols: list[str], count: int = 35) -> dict:
    return {
        sym: {tf: make_synthetic_bars(sym, tf, T0, count=count) for tf in TFS}
        for sym in symbols
    }


def _make_engine(limit: int = 5, offset: int = 0) -> OfflineScannerEngine:
    config = ScanRunConfig(
        scanner_id="TEST-SCANNER-001",
        candidate_limit=limit,
        candidate_offset=offset,
    )
    return OfflineScannerEngine(config, _make_manifest())


class TestScanRun:
    def test_run_completes(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        assert run is not None

    def test_run_id_deterministic(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        r1 = engine.scan(universe, bars)
        r2 = engine.scan(universe, bars)
        assert r1.run_id == r2.run_id

    def test_no_network_calls(self):
        # Engine must complete without any real network dependencies
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        assert len(run.errors) == 0

    def test_envelopes_produced(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        assert len(run.envelopes) > 0

    def test_publishable_always_false(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        for env in run.envelopes:
            assert not env.publishable

    def test_delivery_authorized_always_false(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        for env in run.envelopes:
            assert not env.delivery_authorized

    def test_receipts_in_spool(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        assert len(run.spool) > 0

    def test_nominated_subset_of_all(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        nom_digests = {e.digest for e in run.nominated_envelopes}
        all_digests = {e.digest for e in run.envelopes}
        assert nom_digests.issubset(all_digests)

    def test_rotating_offset_produces_different_symbols(self):
        # Build a universe of at least 3 distinct symbols so offset shift is visible
        extra = ["BNBUSDT", "ETHUSDT", "XRPUSDT", "ADAUSDT", "TRXUSDT"]
        all_symbols = SYMBOLS + extra
        universe = make_synthetic_universe(all_symbols, T0)
        bars = _make_bars(all_symbols)
        e0 = _make_engine(limit=2, offset=0)
        e2 = _make_engine(limit=2, offset=2)
        r0 = e0.scan(universe, bars)
        r2 = e2.scan(universe, bars)
        assert r0.symbols_attempted != r2.symbols_attempted

    def test_summary_structure(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS, T0)
        bars = _make_bars(SYMBOLS)
        run = engine.scan(universe, bars)
        s = run.summary()
        for key in ("run_id", "scanner_id", "cutoff_at", "symbols_attempted",
                    "envelopes_produced", "nominated_count", "receipts_in_spool"):
            assert key in s

    def test_empty_universe_no_error(self):
        from tools.scanner_engine_offline.universe import build_universe_snapshot
        universe = build_universe_snapshot([], T0)
        engine = _make_engine()
        run = engine.scan(universe, {})
        assert run.envelopes == []
        assert run.errors == []

    def test_missing_bars_produces_unavailable_scores(self):
        engine = _make_engine()
        universe = make_synthetic_universe(SYMBOLS[:2], T0)
        run = engine.scan(universe, {})  # no bars supplied
        for env in run.envelopes:
            assert env.score_status == "SCORE_UNAVAILABLE"


class TestDemoRun:
    def test_demo_completes(self):
        from tools.scanner_engine_offline.demo import run_demo
        result = run_demo()
        assert "run_id" in result
        assert result["publishable_check"] is True
        assert result["delivery_authorized_check"] is True
        assert "errors" in result
