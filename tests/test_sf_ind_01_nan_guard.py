"""
Regression tests for F-01: NaN/Inf propagation guard in indicator_library.py

All four indicators (SMA_v1, EMA_v1, RSI_v1, ATR_v1) must raise ValueError
when any close price is NaN or Inf. They must NOT silently propagate non-finite
values to IndicatorResult.value.

Stage 3 — AQL-CLAUDE-RESEARCH-FOUNDATION-HARDENING-001
"""
import math
import pytest
from collections import namedtuple
from research_wp_r0.indicator_library import (
    SMAIndicator,
    EMAIndicator,
    RSIIndicator,
    ATRIndicator,
)

FakeBar = namedtuple("FakeBar", ["bar_open", "close", "high", "low"])


def _bars(closes):
    return [FakeBar(i * 1000, c, c + 0.1 if math.isfinite(c) else c,
                    c - 0.1 if math.isfinite(c) else c) for i, c in enumerate(closes)]


# ---------------------------------------------------------------------------
# Helpers for valid baseline computations
# ---------------------------------------------------------------------------

def _valid_closes(n=20, start=100.0):
    return [start + i * 0.5 for i in range(n)]


# ---------------------------------------------------------------------------
# SMA_v1 guard tests
# ---------------------------------------------------------------------------

class TestSMANaNGuard:
    def test_nan_close_raises(self):
        closes = _valid_closes(10)
        closes[5] = float("nan")
        sma = SMAIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            sma._compute_values(closes, _bars(closes))

    def test_inf_close_raises(self):
        closes = _valid_closes(10)
        closes[3] = float("inf")
        sma = SMAIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            sma._compute_values(closes, _bars(closes))

    def test_neg_inf_close_raises(self):
        closes = _valid_closes(10)
        closes[0] = float("-inf")
        sma = SMAIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            sma._compute_values(closes, _bars(closes))

    def test_valid_closes_pass(self):
        closes = _valid_closes(10)
        sma = SMAIndicator(period=5)
        result = sma._compute_values(closes, _bars(closes))
        # First 4 slots are None (warmup); rest must be finite
        for i, v in enumerate(result):
            if v is not None:
                assert math.isfinite(v), f"index {i}: got non-finite {v}"

    def test_warmup_boundary(self):
        """Exactly period-1 bars → all None, no computation, no error."""
        closes = _valid_closes(4)
        sma = SMAIndicator(period=5)
        result = sma._compute_values(closes, _bars(closes))
        assert all(v is None for v in result)


# ---------------------------------------------------------------------------
# EMA_v1 guard tests
# ---------------------------------------------------------------------------

class TestEMANaNGuard:
    def test_nan_close_raises(self):
        closes = _valid_closes(10)
        closes[0] = float("nan")
        ema = EMAIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            ema._compute_values(closes, _bars(closes))

    def test_inf_close_raises(self):
        closes = _valid_closes(10)
        closes[7] = float("inf")
        ema = EMAIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            ema._compute_values(closes, _bars(closes))

    def test_valid_closes_pass(self):
        closes = _valid_closes(20)
        ema = EMAIndicator(period=5)
        result = ema._compute_values(closes, _bars(closes))
        for i, v in enumerate(result):
            if v is not None:
                assert math.isfinite(v)

    def test_warmup_boundary(self):
        """Fewer than period bars → all None."""
        closes = _valid_closes(3)
        ema = EMAIndicator(period=5)
        result = ema._compute_values(closes, _bars(closes))
        assert all(v is None for v in result)

    def test_nan_after_warmup_raises(self):
        """NaN introduced after warmup window must still be rejected."""
        closes = _valid_closes(15)
        closes[12] = float("nan")
        ema = EMAIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            ema._compute_values(closes, _bars(closes))


# ---------------------------------------------------------------------------
# RSI_v1 guard tests
# ---------------------------------------------------------------------------

class TestRSINaNGuard:
    def test_nan_close_raises(self):
        closes = _valid_closes(20)
        closes[5] = float("nan")
        rsi = RSIIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            rsi._compute_values(closes, _bars(closes))

    def test_inf_close_raises(self):
        closes = _valid_closes(20)
        closes[10] = float("inf")
        rsi = RSIIndicator(period=5)
        with pytest.raises(ValueError, match="non-finite"):
            rsi._compute_values(closes, _bars(closes))

    def test_valid_closes_pass(self):
        closes = _valid_closes(20)
        rsi = RSIIndicator(period=5)
        result = rsi._compute_values(closes, _bars(closes))
        for i, v in enumerate(result):
            if v is not None:
                assert 0.0 <= v <= 100.0, f"RSI out of range at {i}: {v}"
                assert math.isfinite(v)

    def test_warmup_boundary(self):
        """Exactly period bars → all None (needs period+1 bars for first result)."""
        closes = _valid_closes(5)
        rsi = RSIIndicator(period=5)
        result = rsi._compute_values(closes, _bars(closes))
        assert all(v is None for v in result)

    def test_flat_prices_no_nan(self):
        """All closes equal → 0 avg_gain, 0 avg_loss → RSI=100 by convention; must be finite."""
        closes = [100.0] * 20
        rsi = RSIIndicator(period=5)
        result = rsi._compute_values(closes, _bars(closes))
        for v in result:
            if v is not None:
                assert math.isfinite(v)
                assert v == 100.0


# ---------------------------------------------------------------------------
# ATR_v1 guard tests
# ---------------------------------------------------------------------------

class TestATRNaNGuard:
    def _atr_bars(self, closes):
        return [FakeBar(i * 1000, c, c + 0.5 if math.isfinite(c) else c,
                        c - 0.5 if math.isfinite(c) else c)
                for i, c in enumerate(closes)]

    def test_nan_close_raises(self):
        closes = _valid_closes(20)
        closes[5] = float("nan")
        atr = ATRIndicator(period=5)
        bars = self._atr_bars(closes)
        with pytest.raises(ValueError, match="non-finite"):
            atr._compute_values(closes, bars)

    def test_nan_bar_high_raises(self):
        closes = _valid_closes(20)
        atr = ATRIndicator(period=5)
        bars = self._atr_bars(closes)
        # Inject NaN into bar.high
        bad = FakeBar(bars[8].bar_open, bars[8].close, float("nan"), bars[8].low)
        bars[8] = bad
        with pytest.raises(ValueError, match="non-finite"):
            atr._compute_values(closes, bars)

    def test_nan_bar_low_raises(self):
        closes = _valid_closes(20)
        atr = ATRIndicator(period=5)
        bars = self._atr_bars(closes)
        bad = FakeBar(bars[3].bar_open, bars[3].close, bars[3].high, float("nan"))
        bars[3] = bad
        with pytest.raises(ValueError, match="non-finite"):
            atr._compute_values(closes, bars)

    def test_inf_bar_high_raises(self):
        closes = _valid_closes(20)
        atr = ATRIndicator(period=5)
        bars = self._atr_bars(closes)
        bad = FakeBar(bars[1].bar_open, bars[1].close, float("inf"), bars[1].low)
        bars[1] = bad
        with pytest.raises(ValueError, match="non-finite"):
            atr._compute_values(closes, bars)

    def test_valid_bars_pass(self):
        closes = _valid_closes(20)
        atr = ATRIndicator(period=5)
        bars = self._atr_bars(closes)
        result = atr._compute_values(closes, bars)
        for i, v in enumerate(result):
            if v is not None:
                assert math.isfinite(v) and v >= 0.0, f"ATR invalid at {i}: {v}"

    def test_warmup_boundary(self):
        """Exactly period bars → all None."""
        closes = _valid_closes(5)
        atr = ATRIndicator(period=5)
        bars = self._atr_bars(closes)
        result = atr._compute_values(closes, bars)
        assert all(v is None for v in result)
