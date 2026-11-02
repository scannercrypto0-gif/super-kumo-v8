"""
P2-B Regression Tests — Issue #215 Gate 4 (extended)
=====================================================
Targets bugs NOT covered by test_p2a_regression.py:

Bug P2-B-1: _guard_finite_closes does not guard against string (non-numeric)
  close values — math.isfinite("abc") raises TypeError instead of ValueError.
  Callers catching ValueError miss the error entirely.

Bug P2-B-2: _guard_finite_bar_prices uses getattr(bar, attr, None) and then
  checks `if v is not None` — meaning a bar with .high=None or a bar that
  LACKS the .high attribute entirely silently passes the guard, then ATR
  arithmetic crashes with TypeError or AttributeError (not ValueError).

Also documents (no fix required):
  - None close → already raises ValueError (guard works, explicit test added)
  - Legitimate warmup → bars before period is met return None without raising
  - Upstream validation gap → marked NOT_TESTED (requires integration harness)

FAIL→PASS cycle:
  RED  (SHA before fix): P2-B-1, P2-B-2 tests FAIL (wrong exception type / no raise)
  GREEN (SHA after fix): all tests in this file PASS

Classes: SMAIndicator, EMAIndicator, RSIIndicator, ATRIndicator
All _compute_values(closes, bars) — bars required for all indicators.

Run:
    cd /tmp/pr208-check && pytest tests/test_p2b_regression.py -v
"""
from __future__ import annotations

import math
from collections import namedtuple
from typing import List

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FakeBar = namedtuple("FakeBar", ["bar_open", "close", "high", "low"])


def _bars(closes: List) -> List[FakeBar]:
    """Build minimal FakeBar list — propagates non-numeric values as-is."""
    return [
        FakeBar(
            i * 1000,
            c,
            (c + 0.1) if isinstance(c, (int, float)) and math.isfinite(c) else c,
            (c - 0.1) if isinstance(c, (int, float)) and math.isfinite(c) else c,
        )
        for i, c in enumerate(closes)
    ]


def _valid_closes(n: int = 20, start: float = 100.0) -> List[float]:
    return [start + i * 0.5 for i in range(n)]


def _sma(period: int = 3):
    from research_wp_r0.indicator_library import SMAIndicator
    return SMAIndicator(period=period)


def _ema(period: int = 3):
    from research_wp_r0.indicator_library import EMAIndicator
    return EMAIndicator(period=period)


def _rsi(period: int = 14):
    from research_wp_r0.indicator_library import RSIIndicator
    return RSIIndicator(period=period)


def _atr(period: int = 3):
    from research_wp_r0.indicator_library import ATRIndicator
    return ATRIndicator(period=period)


# ---------------------------------------------------------------------------
# P2-B-NONE: None close → must raise ValueError (guard already handles this;
# explicit test ensures it stays covered under code changes)
# ---------------------------------------------------------------------------

class TestP2BNoneClose:
    """None in closes list must raise ValueError (not pass silently)."""

    def test_p2b_sma_none_close_raises_valueerror(self):
        """SMA: None close must raise ValueError (not TypeError, not silently pass)."""
        closes = _valid_closes(10)
        closes[4] = None
        with pytest.raises(ValueError):
            _sma(3)._compute_values(closes, _bars(closes))

    def test_p2b_ema_none_close_raises_valueerror(self):
        """EMA: None close must raise ValueError."""
        closes = _valid_closes(10)
        closes[0] = None
        with pytest.raises(ValueError):
            _ema(3)._compute_values(closes, _bars(closes))

    def test_p2b_rsi_none_close_raises_valueerror(self):
        """RSI: None close must raise ValueError."""
        closes = _valid_closes(20)
        closes[7] = None
        with pytest.raises(ValueError):
            _rsi(14)._compute_values(closes, _bars(closes))

    def test_p2b_atr_none_close_raises_valueerror(self):
        """ATR: None close must raise ValueError."""
        closes = _valid_closes(10)
        closes[2] = None
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, _bars(closes))


# ---------------------------------------------------------------------------
# P2-B-1: String close → Bug: raises TypeError instead of ValueError
# Fix required: _guard_finite_closes must check isinstance before math.isfinite
# ---------------------------------------------------------------------------

class TestP2BStringClose:
    """
    P2-B-1 BUG: string in closes raises TypeError from math.isfinite("abc"),
    not ValueError. Callers catching ValueError miss the error.
    Fix: add isinstance(c, (int, float)) check before math.isfinite(c).
    """

    def test_p2b_sma_string_close_raises_valueerror(self):
        """SMA: string close must raise ValueError (not TypeError)."""
        closes = _valid_closes(10)
        closes[3] = "bad"
        with pytest.raises(ValueError):
            _sma(3)._compute_values(closes, _bars(closes))

    def test_p2b_ema_string_close_raises_valueerror(self):
        """EMA: string close must raise ValueError (not TypeError)."""
        closes = _valid_closes(10)
        closes[1] = "not_a_price"
        with pytest.raises(ValueError):
            _ema(3)._compute_values(closes, _bars(closes))

    def test_p2b_rsi_string_close_raises_valueerror(self):
        """RSI: string close must raise ValueError (not TypeError)."""
        closes = _valid_closes(20)
        closes[10] = "nan_str"
        with pytest.raises(ValueError):
            _rsi(14)._compute_values(closes, _bars(closes))

    def test_p2b_atr_string_close_raises_valueerror(self):
        """ATR: string close must raise ValueError (not TypeError)."""
        closes = _valid_closes(10)
        closes[5] = "price_missing"
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, _bars(closes))


# ---------------------------------------------------------------------------
# P2-B-2a: ATR bar.high = None → Bug: guard skips (v is None), then TypeError
# Fix required: treat None bar attribute values as invalid (ValueError)
# ---------------------------------------------------------------------------

class TestP2BATRBarHighNone:
    """
    P2-B-2a BUG: _guard_finite_bar_prices skips v=None (via `if v is not None`),
    then ATR arithmetic crashes with TypeError from None - float.
    Fix: treat None bar attribute as ValueError, not a silent pass.
    """

    def test_p2b_atr_bar_high_none_raises_valueerror(self):
        """ATR with bar.high=None must raise ValueError (not TypeError)."""
        closes = _valid_closes(10)
        bars = list(FakeBar(i * 1000, closes[i], closes[i] + 0.5, closes[i] - 0.5)
                    for i in range(10))
        bars = list(bars)
        bars[2] = FakeBar(bars[2].bar_open, bars[2].close, None, bars[2].low)
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2b_atr_bar_low_none_raises_valueerror(self):
        """ATR with bar.low=None must raise ValueError (not TypeError)."""
        closes = _valid_closes(10)
        bars = [FakeBar(i * 1000, closes[i], closes[i] + 0.5, closes[i] - 0.5)
                for i in range(10)]
        bars[5] = FakeBar(bars[5].bar_open, bars[5].close, bars[5].high, None)
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2b_atr_bar_close_none_raises_valueerror(self):
        """ATR with bar.close=None must raise ValueError (not pass silently)."""
        closes = _valid_closes(10)
        bars = [FakeBar(i * 1000, closes[i], closes[i] + 0.5, closes[i] - 0.5)
                for i in range(10)]
        bars[4] = FakeBar(bars[4].bar_open, None, bars[4].high, bars[4].low)
        # Note: closes guard catches None close first; bar guard is second defense
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)


# ---------------------------------------------------------------------------
# P2-B-2b: ATR bar missing .high attribute → Bug: getattr returns None,
# guard skips silently, then AttributeError from bar.high in ATR code
# Fix required: use sentinel to detect missing attribute → ValueError
# ---------------------------------------------------------------------------

class TestP2BATRMissingAttribute:
    """
    P2-B-2b BUG: getattr(bar, 'high', None) returns None if 'high' is missing.
    Guard silently skips. ATR computation then raises AttributeError (wrong type).
    Fix: use sentinel object to distinguish missing attr from None.
    """

    def test_p2b_atr_missing_high_raises_valueerror(self):
        """ATR with bar missing .high attribute entirely must raise ValueError."""
        BarNoHigh = namedtuple("BarNoHigh", ["bar_open", "close", "low"])
        closes = _valid_closes(10)
        bars = [BarNoHigh(i * 1000, closes[i], closes[i] - 0.5) for i in range(10)]
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2b_atr_missing_low_raises_valueerror(self):
        """ATR with bar missing .low attribute entirely must raise ValueError."""
        BarNoLow = namedtuple("BarNoLow", ["bar_open", "close", "high"])
        closes = _valid_closes(10)
        bars = [BarNoLow(i * 1000, closes[i], closes[i] + 0.5) for i in range(10)]
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)


# ---------------------------------------------------------------------------
# P2-B-WARMUP: Legitimate warmup slots return None without raising
# (no fix required — documenting correct existing behavior)
# ---------------------------------------------------------------------------

class TestP2BWarmup:
    """
    Legitimate warmup: indicators return None for slots before period is met.
    No exception must be raised for valid inputs during warmup.
    """

    def test_p2b_sma_warmup_returns_none(self):
        """SMA period=5, only 3 closes → all results None, no exception."""
        closes = _valid_closes(3)
        bars = [FakeBar(i * 1000, c, c + 0.5, c - 0.5) for i, c in enumerate(closes)]
        result = _sma(5)._compute_values(closes, bars)
        assert all(v is None for v in result), f"Expected all None warmup, got {result}"

    def test_p2b_ema_warmup_returns_none(self):
        """EMA: fewer than period closes → all None."""
        closes = _valid_closes(2)
        bars = [FakeBar(i * 1000, c, c + 0.5, c - 0.5) for i, c in enumerate(closes)]
        result = _ema(5)._compute_values(closes, bars)
        assert all(v is None for v in result)

    def test_p2b_rsi_warmup_returns_none(self):
        """RSI: exactly period closes → all None (needs period+1 for first value)."""
        closes = _valid_closes(14)
        bars = [FakeBar(i * 1000, c, c + 0.5, c - 0.5) for i, c in enumerate(closes)]
        result = _rsi(14)._compute_values(closes, bars)
        assert all(v is None for v in result)

    def test_p2b_atr_warmup_returns_none(self):
        """ATR: fewer than period closes → all None."""
        closes = _valid_closes(2)
        bars = [FakeBar(i * 1000, c, c + 0.5, c - 0.5) for i, c in enumerate(closes)]
        result = _atr(5)._compute_values(closes, bars)
        assert all(v is None for v in result)

    def test_p2b_sma_first_value_after_warmup(self):
        """SMA period=3: first non-None result appears at index 2, is finite."""
        closes = _valid_closes(10)
        bars = [FakeBar(i * 1000, c, c + 0.5, c - 0.5) for i, c in enumerate(closes)]
        result = _sma(3)._compute_values(closes, bars)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None
        assert math.isfinite(result[2])

    def test_p2b_none_bar_slots_do_not_raise(self):
        """None bar SLOTS (warmup placeholders) must not raise — only bar values."""
        closes = _valid_closes(10)
        # Inject None bar slots in the first 2 positions (warmup placeholder pattern)
        bars = [None, None] + [
            FakeBar(i * 1000, closes[i], closes[i] + 0.5, closes[i] - 0.5)
            for i in range(2, 10)
        ]
        # SMA skips None bar slots (guard has `if bar is None: continue`)
        try:
            _sma(3)._compute_values(closes, bars)
        except ValueError:
            raise AssertionError(
                "SMA raised ValueError on None bar slots — warmup None bars must be allowed"
            )


# ---------------------------------------------------------------------------
# NOT_TESTED: Upstream validation gap
# ---------------------------------------------------------------------------
#
# Upstream validation refers to: does validate_bars() in historical_library
# catch invalid bar data BEFORE it reaches indicator _compute_values()?
# This is the intended architecture (guards are defense-in-depth).
#
# NOT_TESTED: This session does not have access to the integration path that
# calls validate_bars() → build_closes() → indicator._compute_values().
# Testing this requires loading historical_library and a mock data pipeline
# that is outside the authorized scope of this Gate 4 focused fix.
#
# Mitigation: The guards in _guard_finite_closes and _guard_finite_bar_prices
# act as defense-in-depth and will catch invalid data even if upstream
# validate_bars() is bypassed or has a gap.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FAIL→PASS audit note
# ---------------------------------------------------------------------------
#
# P2-B-1 (string close): RED on SHA before fix (TypeError raised, test expects
#   ValueError → FAIL). GREEN after isinstance check added to _guard_finite_closes.
#
# P2-B-2a (bar.high/low=None): RED on SHA before fix (TypeError from None-float
#   arithmetic → FAIL). GREEN after guard treats None attr as ValueError.
#
# P2-B-2b (bar missing attr): RED on SHA before fix (AttributeError from ATR
#   code → FAIL). GREEN after sentinel check in _guard_finite_bar_prices.
#
# P2-B-NONE and P2-B-WARMUP: Expected PASS on both pre- and post-fix SHAs
#   (guard already handles these correctly; tests add explicit coverage).
# ---------------------------------------------------------------------------
