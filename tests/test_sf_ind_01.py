"""
SF-IND-01 Test Suite — Unified Research Indicator Library V1
============================================================
Issue #59 acceptance tests.

Coverage areas
--------------
T1  Frozen dataclass & provenance hash integrity
T2  IndicatorResult.from_dict() tamper rejection
T3  IndicatorManifest create / verify
T4  SMA reference vectors
T5  EMA reference vectors
T6  RSI reference vectors (Wilder's smoothing)
T7  ATR reference vectors (Wilder's smoothing)
T8  PIT correctness — lookahead bar excluded by decision_cutoff_ms
T9  PIT correctness — decision_cutoff_ms shift changes results
T10 Warmup policy — min_warmup_bars consumed, not emitted
T11 Gap / missing bar policy (fail-closed)
T12 Partial coverage opt-in (require_complete=False)
T13 IndicatorLibrary registry
T14 Parameter validation errors
T15 Computation hash covers all results in bar_open_ms order
T16 HistoricalBar high/low/close field access (ATR)
T17 Platform independence (stdlib only)
"""
from __future__ import annotations

import dataclasses
import os
import sys
import unittest
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup — run from repo root or tests/ directory
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research_wp_r0.historical_library import (
    BarQuality,
    CustodyAccessor,
    DataAvailabilityKind,
    DatasetManifest,
    HistoricalBar,
    HistoricalDataError,
    HistoricalLibrary,
    SourceType,
    make_test_bar,
    validate_bars,
)
from research_wp_r0.indicator_library import (
    ATRIndicator,
    EMAIndicator,
    IndicatorLibrary,
    IndicatorManifest,
    IndicatorResult,
    RSIIndicator,
    SMAIndicator,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SYMBOL = "BTCUSDT"
INTERVAL = "1m"
BASE_MS = 1_700_000_000_000
IMS = 60_000  # 1-minute bar in ms

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _bars(
    n: int,
    base: int = BASE_MS,
    start_close: float = 100.0,
    step: float = 0.0,
    hl_range: float = 1.0,
) -> List[HistoricalBar]:
    """
    Build n synthetic CONFIRMED bars.  close = start_close + i*step.
    high = close + hl_range, low = close - hl_range.
    """
    result = []
    for i in range(n):
        c = start_close + i * step
        h = c + hl_range
        lo = max(c - hl_range, 0.01)
        interval_ms = IMS
        bar_open = base + i * interval_ms
        bar_close_ms = bar_open + interval_ms - 1
        obs = bar_close_ms + 1
        result.append(
            HistoricalBar(
                symbol=SYMBOL,
                interval=INTERVAL,
                bar_open=bar_open,
                bar_close=bar_close_ms,
                open=c,
                high=h,
                low=lo,
                close=c,
                volume=1000.0 + i,
                quality=BarQuality.FINAL,
                source=SourceType.SYNTHETIC,
                source_label="synthetic",
                observation_cutoff_ms=obs,
                ingest_time_ms=None,
                availability_kind=DataAvailabilityKind.CONFIRMED,
            )
        )
    return result


def _lib_with(
    bars: List[HistoricalBar],
    dataset_id: str = "BTC1M",
    version: int = 1,
) -> Tuple[HistoricalLibrary, CustodyAccessor]:
    """Register bars in a fresh HistoricalLibrary and return (lib, accessor)."""
    lib = HistoricalLibrary()
    validated, manifest = validate_bars(bars, SYMBOL, INTERVAL)
    manifest = dataclasses.replace(
        manifest,
        dataset_id=dataset_id,
        exchange="binance",
        market="spot",
    )
    # Override version if needed (validate_bars defaults to 1)
    if manifest.version != version:
        manifest = dataclasses.replace(manifest, version=version)
    lib.register(dataset_id, validated, manifest)
    return lib, CustodyAccessor(lib)


def _closes(n: int, start: float = 100.0, step: float = 1.0) -> List[float]:
    return [round(start + i * step, 6) for i in range(n)]


def _sma_ref(closes: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        out[i] = sum(closes[i - period + 1 : i + 1]) / period
    return out


def _ema_ref(
    closes: List[float], period: int, smoothing: float = 2.0
) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return out
    k = smoothing / (period + 1)
    ema = sum(closes[:period]) / period
    out[period - 1] = ema
    for i in range(period, len(closes)):
        ema = closes[i] * k + ema * (1 - k)
        out[i] = ema
    return out


def _rsi_ref(closes: List[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, period + 1)]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, period + 1)]
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period

    def rsi(g: float, lo: float) -> float:
        return 100.0 if lo == 0 else 100.0 - 100.0 / (1.0 + g / lo)

    out[period] = rsi(avg_g, avg_l)
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = max(diff, 0.0)
        l = max(-diff, 0.0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        out[i] = rsi(avg_g, avg_l)
    return out


def _atr_ref(bars: List[HistoricalBar], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    if len(bars) <= period:
        return out

    def tr(b: HistoricalBar, prev_c: float) -> float:
        return max(b.high - b.low, abs(b.high - prev_c), abs(b.low - prev_c))

    trs = [tr(bars[i], bars[i - 1].close) for i in range(1, period + 1)]
    atr = sum(trs) / period
    out[period] = atr
    for i in range(period + 1, len(bars)):
        t = tr(bars[i], bars[i - 1].close)
        atr = (atr * (period - 1) + t) / period
        out[i] = atr
    return out


def _run(
    ind,
    bars: List[HistoricalBar],
    dataset_id: str = "BTC1M",
    *,
    cutoff_override: Optional[int] = None,
    require_complete: bool = True,
    version: int = 1,
):
    lib, accessor = _lib_with(bars, dataset_id, version)
    cutoff = cutoff_override if cutoff_override is not None else bars[-1].observation_cutoff_ms + 1
    return ind.compute(
        accessor, dataset_id,
        bars[0].bar_open, bars[-1].bar_open,
        cutoff, version=version, require_complete=require_complete,
    )


# ===========================================================================
# T1 — Frozen dataclass & provenance hash
# ===========================================================================
class TestIndicatorResultFrozen(unittest.TestCase):
    def _make(self) -> IndicatorResult:
        return IndicatorResult.create(
            indicator_id="SMA_v1", version="1",
            dataset_id="DS1", dataset_version=1, dataset_manifest_hash="abc123",
            bar_open_ms=1_000, decision_cutoff_ms=2_000,
            value=42.0, parameters=(("period", 5),),
            warmup_bars_consumed=4, partial_coverage=False,
        )

    def test_frozen(self):
        r = self._make()
        # Normal attribute assignment must be blocked
        with self.assertRaises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            r.value = 99.0  # type: ignore[misc]

    def test_verify_passes(self):
        self.assertTrue(self._make().verify_integrity())

    def test_tamper_fails(self):
        r = self._make()
        tampered = IndicatorResult(
            **{**dataclasses.asdict(r), "value": 999.0, "provenance_hash": r.provenance_hash}
        )
        self.assertFalse(tampered.verify_integrity())


# ===========================================================================
# T2 — from_dict tamper rejection
# ===========================================================================
class TestFromDict(unittest.TestCase):
    def _dict(self) -> dict:
        return IndicatorResult.create(
            indicator_id="EMA_v1", version="1",
            dataset_id="DS1", dataset_version=1, dataset_manifest_hash="mh1",
            bar_open_ms=1000, decision_cutoff_ms=2000, value=50.5,
            parameters=(("period", 10), ("smoothing", 2.0)),
            warmup_bars_consumed=9, partial_coverage=False,
        ).to_dict()

    def test_roundtrip(self):
        self.assertTrue(IndicatorResult.from_dict(self._dict()).verify_integrity())

    def test_tampered_value_raises(self):
        d = self._dict(); d["value"] = 9999.0
        with self.assertRaises(ValueError):
            IndicatorResult.from_dict(d)

    def test_tampered_hash_raises(self):
        d = self._dict(); d["provenance_hash"] = "0" * 64
        with self.assertRaises(ValueError):
            IndicatorResult.from_dict(d)


# ===========================================================================
# T3 — IndicatorManifest
# ===========================================================================
class TestIndicatorManifest(unittest.TestCase):
    def _rs(self, n: int = 5) -> List[IndicatorResult]:
        return [
            IndicatorResult.create(
                indicator_id="SMA_v1", version="1",
                dataset_id="DS1", dataset_version=1, dataset_manifest_hash="mh",
                bar_open_ms=BASE_MS + i * IMS,
                decision_cutoff_ms=BASE_MS + 9999 * IMS,
                value=float(i), parameters=(("period", 3),),
                warmup_bars_consumed=2, partial_coverage=False,
            )
            for i in range(n)
        ]

    def test_create_and_verify(self):
        rs = self._rs()
        m = IndicatorManifest.create(
            indicator_id="SMA_v1", dataset_id="DS1", dataset_version=1,
            dataset_manifest_hash="mh", decision_cutoff_ms=99999,
            parameter_set=(("period", 3),), warmup_policy=2, results=rs,
        )
        self.assertTrue(m.verify(rs))

    def test_extra_result_fails(self):
        rs = self._rs()
        m = IndicatorManifest.create(
            indicator_id="SMA_v1", dataset_id="DS1", dataset_version=1,
            dataset_manifest_hash="mh", decision_cutoff_ms=99999,
            parameter_set=(("period", 3),), warmup_policy=2, results=rs,
        )
        self.assertFalse(m.verify(rs + [rs[0]]))

    def test_roundtrip(self):
        rs = self._rs(3)
        m = IndicatorManifest.create(
            indicator_id="SMA_v1", dataset_id="DS1", dataset_version=1,
            dataset_manifest_hash="mh", decision_cutoff_ms=99999,
            parameter_set=(("period", 3),), warmup_policy=2, results=rs,
        )
        m2 = IndicatorManifest.from_dict(m.to_dict())
        self.assertEqual(m.computation_hash, m2.computation_hash)
        self.assertTrue(m2.verify(rs))


# ===========================================================================
# T4 — SMA reference vectors
# ===========================================================================
class TestSMA(unittest.TestCase):
    def test_rising(self):
        closes = _closes(20, step=1.0)
        bars = _bars(20, step=1.0)
        results, _ = _run(SMAIndicator(period=5), bars)
        ref = [v for v in _sma_ref(closes, 5) if v is not None]
        self.assertEqual(len(results), len(ref))
        for r, e in zip(results, ref):
            self.assertAlmostEqual(r.value, e, places=9)

    def test_constant_closes(self):
        bars = _bars(10, start_close=50.0)
        results, _ = _run(SMAIndicator(period=3), bars)
        for r in results:
            self.assertAlmostEqual(r.value, 50.0, places=9)

    def test_warmup_count(self):
        bars = _bars(10)
        results, _ = _run(SMAIndicator(period=4), bars)
        self.assertEqual(len(results), 7)  # 10 - 3
        for r in results:
            self.assertEqual(r.warmup_bars_consumed, 3)

    def test_manifest_matches(self):
        bars = _bars(15)
        results, manifest = _run(SMAIndicator(period=5), bars)
        self.assertEqual(manifest.result_count, len(results))
        self.assertTrue(manifest.verify(results))

    def test_period_1_invalid(self):
        with self.assertRaises(ValueError):
            SMAIndicator(period=1)


# ===========================================================================
# T5 — EMA reference vectors
# ===========================================================================
class TestEMA(unittest.TestCase):
    def test_rising(self):
        closes = _closes(30, step=0.5)
        bars = _bars(30, step=0.5)
        results, _ = _run(EMAIndicator(period=10), bars)
        ref = [v for v in _ema_ref(closes, 10) if v is not None]
        self.assertEqual(len(results), len(ref))
        for r, e in zip(results, ref):
            self.assertAlmostEqual(r.value, e, places=8)

    def test_seed_equals_sma(self):
        period = 5
        closes = _closes(20, step=1.0)
        bars = _bars(20, step=1.0)
        results, _ = _run(EMAIndicator(period=period), bars)
        seed = sum(closes[:period]) / period
        self.assertAlmostEqual(results[0].value, seed, places=9)

    def test_warmup(self):
        bars = _bars(15)
        results, _ = _run(EMAIndicator(period=6), bars)
        self.assertEqual(len(results), 10)  # 15 - 5
        for r in results:
            self.assertEqual(r.warmup_bars_consumed, 5)


# ===========================================================================
# T6 — RSI reference vectors
# ===========================================================================
class TestRSI(unittest.TestCase):
    def _random_closes(self, n: int = 50, seed: int = 42) -> Tuple[List[float], List[HistoricalBar]]:
        import random
        random.seed(seed)
        closes = [round(100.0 + random.gauss(0, 2), 6) for _ in range(n)]
        bars = _bars(n)
        # patch closes into bars
        patched = []
        for i, b in enumerate(bars):
            c = closes[i]
            patched.append(dataclasses.replace(b, open=c, high=c + 1, low=max(c - 1, 0.01), close=c))
        return closes, patched

    def test_reference(self):
        closes, bars = self._random_closes(50)
        results, _ = _run(RSIIndicator(period=14), bars)
        ref = [v for v in _rsi_ref(closes, 14) if v is not None]
        self.assertEqual(len(results), len(ref))
        for r, e in zip(results, ref):
            self.assertAlmostEqual(r.value, e, places=7)

    def test_all_gains_100(self):
        closes = [float(i + 1) for i in range(20)]
        bars = _bars(20, step=1.0)
        results, _ = _run(RSIIndicator(period=5), bars)
        self.assertAlmostEqual(results[-1].value, 100.0, places=6)

    def test_all_losses_0(self):
        closes = [float(20 - i) for i in range(20)]
        bars = _bars(20, step=-1.0, start_close=20.0)
        results, _ = _run(RSIIndicator(period=5), bars)
        self.assertAlmostEqual(results[-1].value, 0.0, places=6)

    def test_bounds(self):
        import random
        random.seed(7)
        closes = [round(100.0 + random.gauss(0, 5), 6) for _ in range(40)]
        bars = _bars(40)
        patched = [
            dataclasses.replace(b, open=c, high=c + 1, low=max(c - 1, 0.01), close=c)
            for b, c in zip(bars, closes)
        ]
        results, _ = _run(RSIIndicator(period=7), patched)
        for r in results:
            self.assertGreaterEqual(r.value, 0.0)
            self.assertLessEqual(r.value, 100.0)


# ===========================================================================
# T7 — ATR reference vectors
# ===========================================================================
class TestATR(unittest.TestCase):
    def _atr_bars(self, n: int = 40, seed: int = 12345) -> List[HistoricalBar]:
        import random
        random.seed(seed)
        out = []
        c = 100.0
        for i in range(n):
            dc = random.gauss(0, 1.5)
            c = max(c + dc, 1.0)
            h = c + abs(random.gauss(0, 0.8))
            lo = max(c - abs(random.gauss(0, 0.8)), 0.01)
            bar_open = BASE_MS + i * IMS
            bar_close_ms = bar_open + IMS - 1
            out.append(HistoricalBar(
                symbol=SYMBOL, interval=INTERVAL,
                bar_open=bar_open, bar_close=bar_close_ms,
                open=c, high=round(h, 6), low=round(lo, 6), close=round(c, 6),
                volume=1000.0,
                quality=BarQuality.FINAL,
                source=SourceType.SYNTHETIC,
                source_label="synthetic",
                observation_cutoff_ms=bar_close_ms + 1,
                ingest_time_ms=None,
                availability_kind=DataAvailabilityKind.CONFIRMED,
            ))
        return out

    def test_reference(self):
        bars = self._atr_bars(40)
        results, _ = _run(ATRIndicator(period=14), bars)
        ref = [v for v in _atr_ref(bars, 14) if v is not None]
        self.assertEqual(len(results), len(ref))
        for r, e in zip(results, ref):
            self.assertAlmostEqual(r.value, e, places=7)

    def test_positive(self):
        bars = self._atr_bars(30)
        results, _ = _run(ATRIndicator(period=7), bars)
        for r in results:
            self.assertGreater(r.value, 0.0)


# ===========================================================================
# T8 — PIT correctness: lookahead excluded by cutoff
# ===========================================================================
class TestPITLookahead(unittest.TestCase):
    def test_excluded_bars(self):
        """
        When decision_cutoff_ms falls before the last bars' observation_cutoff,
        those bars are not yet observable and must be excluded.  We set
        end_ms to the last observable bar so require_complete=True can pass,
        then verify the result count matches only the visible window.
        """
        n = 20
        excluded = 3
        bars = _bars(n)
        visible_idx = n - excluded - 1   # last bar that IS observable
        cutoff = bars[visible_idx].observation_cutoff_ms + 1  # exactly after it
        period = 5
        visible = visible_idx + 1  # number of observable bars

        # Use require_complete=False because we're querying the full range
        # but restricting via decision_cutoff_ms (simulating PIT exclusion).
        lib, accessor = _lib_with(bars)
        results, _ = SMAIndicator(period=period).compute(
            accessor, "BTC1M",
            bars[0].bar_open, bars[-1].bar_open,
            cutoff, version=1, require_complete=False,
        )
        self.assertEqual(len(results), visible - (period - 1))

    def test_cutoff_recorded(self):
        bars = _bars(10)
        cutoff = bars[-1].observation_cutoff_ms + 1
        results, _ = _run(SMAIndicator(period=3), bars, cutoff_override=cutoff)
        for r in results:
            self.assertEqual(r.decision_cutoff_ms, cutoff)


# ===========================================================================
# T9 — PIT: shifting cutoff changes results
# ===========================================================================
class TestPITShift(unittest.TestCase):
    def test_earlier_cutoff_fewer_results(self):
        bars = _bars(25, step=0.5)
        period = 5
        full = bars[-1].observation_cutoff_ms + 1
        early = bars[14].observation_cutoff_ms + 1
        lib, accessor = _lib_with(bars)
        r_full, _ = SMAIndicator(period=period).compute(
            accessor, "BTC1M", bars[0].bar_open, bars[-1].bar_open,
            full, version=1, require_complete=True,
        )
        r_early, _ = SMAIndicator(period=period).compute(
            accessor, "BTC1M", bars[0].bar_open, bars[-1].bar_open,
            early, version=1, require_complete=False,  # partial OK
        )
        self.assertGreater(len(r_full), len(r_early))

    def test_last_values_differ(self):
        bars = _bars(20, step=2.0)
        period = 3
        ca = bars[-1].observation_cutoff_ms + 1
        cb = bars[9].observation_cutoff_ms + 1
        lib, accessor = _lib_with(bars)
        ra, _ = SMAIndicator(period=period).compute(
            accessor, "BTC1M", bars[0].bar_open, bars[-1].bar_open,
            ca, version=1, require_complete=True,
        )
        rb, _ = SMAIndicator(period=period).compute(
            accessor, "BTC1M", bars[0].bar_open, bars[-1].bar_open,
            cb, version=1, require_complete=False,
        )
        self.assertNotAlmostEqual(ra[-1].value, rb[-1].value, places=6)


# ===========================================================================
# T10 — Warmup policy
# ===========================================================================
class TestWarmup(unittest.TestCase):
    def test_warmup_not_emitted(self):
        n = 15
        period = 7
        bars = _bars(n)
        results, _ = _run(SMAIndicator(period=period), bars)
        self.assertEqual(len(results), n - (period - 1))
        self.assertEqual(results[0].bar_open_ms, bars[period - 1].bar_open)

    def test_warmup_field(self):
        bars = _bars(10)
        for period in (2, 3, 5):
            results, _ = _run(SMAIndicator(period=period), bars)
            for r in results:
                self.assertEqual(r.warmup_bars_consumed, period - 1)


# ===========================================================================
# T11 — Gap / fail-closed
# ===========================================================================
class TestFailClosed(unittest.TestCase):
    def test_gap_raises(self):
        bars = _bars(20, step=1.0)
        # Only register a subset (with gap in the middle)
        subset = bars[:8] + bars[12:]
        try:
            lib, accessor = _lib_with(subset, "GAPPED")
        except Exception:
            # validate_bars itself may reject non-contiguous bars
            return  # gap detected at ingestion — acceptable

        cutoff = bars[-1].observation_cutoff_ms + 1
        with self.assertRaises(Exception):
            SMAIndicator(period=5).compute(
                accessor, "GAPPED",
                bars[0].bar_open, bars[-1].bar_open, cutoff,
                version=1, require_complete=True,
            )


# ===========================================================================
# T12 — Partial coverage opt-in
# ===========================================================================
class TestPartial(unittest.TestCase):
    def test_partial_flag_true(self):
        bars = _bars(20)
        results, _ = _run(SMAIndicator(period=5), bars, require_complete=False)
        for r in results:
            self.assertTrue(r.partial_coverage)

    def test_default_not_partial(self):
        bars = _bars(20)
        results, _ = _run(SMAIndicator(period=5), bars, require_complete=True)
        for r in results:
            self.assertFalse(r.partial_coverage)


# ===========================================================================
# T13 — IndicatorLibrary registry
# ===========================================================================
class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.lib = IndicatorLibrary()

    def test_all_four_available(self):
        for name in ("SMA_v1", "EMA_v1", "RSI_v1", "ATR_v1"):
            self.assertIn(name, self.lib.available())

    def test_get_sma(self):
        self.assertIsInstance(self.lib.get("SMA_v1", period=10), SMAIndicator)

    def test_get_ema(self):
        self.assertIsInstance(self.lib.get("EMA_v1", period=20), EMAIndicator)

    def test_get_rsi(self):
        self.assertIsInstance(self.lib.get("RSI_v1", period=14), RSIIndicator)

    def test_get_atr(self):
        self.assertIsInstance(self.lib.get("ATR_v1", period=14), ATRIndicator)

    def test_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.lib.get("UNKNOWN_v99")


# ===========================================================================
# T14 — Parameter validation
# ===========================================================================
class TestValidation(unittest.TestCase):
    def test_sma_period_0(self):
        with self.assertRaises(ValueError): SMAIndicator(period=0)

    def test_sma_period_1(self):
        with self.assertRaises(ValueError): SMAIndicator(period=1)

    def test_ema_period_1(self):
        with self.assertRaises(ValueError): EMAIndicator(period=1)

    def test_ema_smoothing_0(self):
        with self.assertRaises(ValueError): EMAIndicator(period=5, smoothing=0.0)

    def test_rsi_period_1(self):
        with self.assertRaises(ValueError): RSIIndicator(period=1)

    def test_atr_period_1(self):
        with self.assertRaises(ValueError): ATRIndicator(period=1)


# ===========================================================================
# T15 — Computation hash order
# ===========================================================================
class TestComputationHash(unittest.TestCase):
    """
    Computation hash determinism.

    ``manifest_integrity_hash`` includes ``created_at_ms`` (set to wall-clock
    at validate_bars time).  Two independent library builds therefore produce
    different manifest hashes even for identical bars, which propagates to
    provenance_hash and computation_hash.

    The correct same-hash invariant is:
        *same accessor* (same manifest) + *same dataset_id* + *same bars*
        → same computation_hash.

    For the different-hash test we can use independent libraries; the bars
    differ (different step) so closes differ, making provenance_hash differ
    regardless of manifest_integrity_hash.
    """

    def test_same_input_same_hash(self):
        """Calling compute() twice on the same accessor yields the same hash."""
        DS = "BTC1M_SAME"
        bars = _bars(15, step=1.0)
        lib, accessor = _lib_with(bars, DS, 1)
        cutoff = bars[-1].observation_cutoff_ms + 1
        ind = SMAIndicator(period=5)
        _, m1 = ind.compute(accessor, DS, bars[0].bar_open, bars[-1].bar_open,
                            cutoff, version=1)
        _, m2 = ind.compute(accessor, DS, bars[0].bar_open, bars[-1].bar_open,
                            cutoff, version=1)
        self.assertEqual(m1.computation_hash, m2.computation_hash)

    def test_different_input_different_hash(self):
        """Different close prices produce a different computation_hash."""
        DS = "BTC1M_DIFF"
        bars1 = _bars(15, step=1.0)
        bars2 = _bars(15, step=2.0)
        _, m1 = _run(SMAIndicator(period=5), bars1, dataset_id=DS)
        _, m2 = _run(SMAIndicator(period=5), bars2, dataset_id=DS)
        self.assertNotEqual(m1.computation_hash, m2.computation_hash)

    def test_order_matters(self):
        bars = _bars(15, step=1.0)
        results, manifest = _run(SMAIndicator(period=5), bars, dataset_id="BTC1M_OM2")
        self.assertFalse(manifest.verify(list(reversed(results))))


# ===========================================================================
# T16 — ATR uses high/low/close from HistoricalBar
# ===========================================================================
class TestATRFields(unittest.TestCase):
    def _atr_bars_range(self, n: int, hl: float) -> List[HistoricalBar]:
        c = 100.0
        out = []
        for i in range(n):
            bar_open = BASE_MS + i * IMS
            bar_close_ms = bar_open + IMS - 1
            out.append(HistoricalBar(
                symbol=SYMBOL, interval=INTERVAL,
                bar_open=bar_open, bar_close=bar_close_ms,
                open=c, high=c + hl, low=max(c - hl, 0.01), close=c,
                volume=1000.0,
                quality=BarQuality.FINAL, source=SourceType.SYNTHETIC,
                source_label="synthetic",
                observation_cutoff_ms=bar_close_ms + 1,
                ingest_time_ms=None,
                availability_kind=DataAvailabilityKind.CONFIRMED,
            ))
        return out

    def test_wider_range_higher_atr(self):
        narrow = self._atr_bars_range(25, 0.5)
        wide = self._atr_bars_range(25, 5.0)
        r_n, _ = _run(ATRIndicator(period=5), narrow, dataset_id="NARROW")
        r_w, _ = _run(ATRIndicator(period=5), wide, dataset_id="WIDE")
        self.assertGreater(r_w[-1].value, r_n[-1].value)


# ===========================================================================
# T17 — Platform independence (stdlib only)
# ===========================================================================
class TestPlatform(unittest.TestCase):
    def test_no_external_deps(self):
        import pathlib
        src = (
            pathlib.Path(__file__).parent.parent
            / "research_wp_r0"
            / "indicator_library.py"
        ).read_text(encoding="utf-8")
        for pkg in ("numpy", "pandas", "scipy", "matplotlib"):
            self.assertNotIn(pkg, src, msg=f"Must not import {pkg}")

    def test_hash_deterministic(self):
        r1 = IndicatorResult.create(
            indicator_id="SMA_v1", version="1", dataset_id="DS",
            dataset_version=1, dataset_manifest_hash="h",
            bar_open_ms=1000, decision_cutoff_ms=2000, value=42.5,
            parameters=(("period", 5),), warmup_bars_consumed=4,
            partial_coverage=False,
        )
        r2 = IndicatorResult.create(
            indicator_id="SMA_v1", version="1", dataset_id="DS",
            dataset_version=1, dataset_manifest_hash="h",
            bar_open_ms=1000, decision_cutoff_ms=2000, value=42.5,
            parameters=(("period", 5),), warmup_bars_consumed=4,
            partial_coverage=False,
        )
        self.assertEqual(r1.provenance_hash, r2.provenance_hash)


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
