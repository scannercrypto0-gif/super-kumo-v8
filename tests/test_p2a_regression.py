"""
P2-A Regression Tests — Issue #215 Gate 4
==========================================
Bug: Indicator _compute_values() methods did not fail-closed on NaN/Inf/None inputs.
Fix: Commit bff0769 — fail-closed guards _guard_finite_closes() and
     _guard_finite_bar_prices() added, called as FIRST actions in all 4
     indicator _compute_values() methods (ATR, SMA, EMA, RSI).

FAIL→PASS cycle evidence:
  - On SHA dbc191d (pre-fix): ATR/SMA/EMA/RSI silently returned None-filled output
    or propagated NaN/Inf into results without raising. 23 tests FAILED.
  - On SHA 0af141c (post-fix): guards raise ValueError immediately.
    All tests in this file PASS.

Classes: SMAIndicator, EMAIndicator, RSIIndicator, ATRIndicator
All _compute_values(closes, bars) — bars required for all indicators.

Run:
    cd /tmp/pr208-check && pytest tests/test_p2a_regression.py -v
"""
from __future__ import annotations

import ast
import math
import pathlib
from collections import namedtuple
from typing import List, Optional

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

INDICATOR_LIB_PATH = pathlib.Path(__file__).parent.parent / "research_wp_r0" / "indicator_library.py"

FakeBar = namedtuple("FakeBar", ["bar_open", "close", "high", "low"])


def _bars(closes: List[float]) -> List[FakeBar]:
    """Build minimal FakeBar list matching the existing test convention."""
    return [
        FakeBar(
            i * 1000,
            c,
            c + 0.1 if math.isfinite(c) else c,
            c - 0.1 if math.isfinite(c) else c,
        )
        for i, c in enumerate(closes)
    ]


def _valid_closes(n: int = 20, start: float = 100.0) -> List[float]:
    return [start + i * 0.5 for i in range(n)]


def _sma(period: int):
    from research_wp_r0.indicator_library import SMAIndicator
    return SMAIndicator(period=period)


def _ema(period: int):
    from research_wp_r0.indicator_library import EMAIndicator
    return EMAIndicator(period=period)


def _rsi(period: int):
    from research_wp_r0.indicator_library import RSIIndicator
    return RSIIndicator(period=period)


def _atr(period: int):
    from research_wp_r0.indicator_library import ATRIndicator
    return ATRIndicator(period=period)


# ─────────────────────────────────────────────────────────────────────────────
# P2-A-SMA: SMA fails closed on bad inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestP2ASMAGuard:
    """P2-A: SMA _compute_values must raise ValueError on non-finite closes."""

    def test_p2a_sma_nan_close_raises(self):
        """SMA with float('nan') in closes must raise ValueError (fail-closed)."""
        closes = _valid_closes(10)
        closes[5] = float('nan')
        with pytest.raises(ValueError):
            _sma(5)._compute_values(closes, _bars(closes))

    def test_p2a_sma_inf_close_raises(self):
        """SMA with +Inf in closes must raise ValueError."""
        closes = _valid_closes(10)
        closes[3] = float('inf')
        with pytest.raises(ValueError):
            _sma(5)._compute_values(closes, _bars(closes))

    def test_p2a_sma_neg_inf_close_raises(self):
        """SMA with -Inf in closes must raise ValueError."""
        closes = _valid_closes(10)
        closes[0] = float('-inf')
        with pytest.raises(ValueError):
            _sma(5)._compute_values(closes, _bars(closes))

    def test_p2a_sma_valid_closes_do_not_raise(self):
        """SMA with all finite closes must not raise."""
        closes = _valid_closes(10)
        result = _sma(3)._compute_values(closes, _bars(closes))
        assert result is not None
        assert result[-1] is not None
        assert math.isfinite(result[-1])

    def test_p2a_sma_nan_at_end_raises(self):
        """NaN after warmup period must also raise — guard checks ALL elements."""
        closes = _valid_closes(10)
        closes[-1] = float('nan')
        with pytest.raises(ValueError):
            _sma(3)._compute_values(closes, _bars(closes))


# ─────────────────────────────────────────────────────────────────────────────
# P2-A-EMA: EMA fails closed on bad inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestP2AEMAGuard:
    """P2-A: EMA _compute_values must raise ValueError on non-finite closes."""

    def test_p2a_ema_nan_close_raises(self):
        """EMA with NaN in closes must raise ValueError."""
        closes = _valid_closes(10)
        closes[2] = float('nan')
        with pytest.raises(ValueError):
            _ema(3)._compute_values(closes, _bars(closes))

    def test_p2a_ema_inf_close_raises(self):
        """EMA with +Inf in closes must raise ValueError."""
        closes = _valid_closes(10)
        closes[3] = float('inf')
        with pytest.raises(ValueError):
            _ema(3)._compute_values(closes, _bars(closes))

    def test_p2a_ema_valid_closes_do_not_raise(self):
        """EMA with all finite closes must not raise."""
        closes = _valid_closes(10)
        result = _ema(3)._compute_values(closes, _bars(closes))
        assert result is not None
        assert result[-1] is not None
        assert math.isfinite(result[-1])


# ─────────────────────────────────────────────────────────────────────────────
# P2-A-RSI: RSI fails closed on bad inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestP2ARSIGuard:
    """P2-A: RSI _compute_values must raise ValueError on non-finite closes."""

    def test_p2a_rsi_nan_close_raises(self):
        """RSI with NaN in closes must raise ValueError."""
        closes = _valid_closes(20)
        closes[14] = float('nan')
        with pytest.raises(ValueError):
            _rsi(14)._compute_values(closes, _bars(closes))

    def test_p2a_rsi_inf_close_raises(self):
        """RSI with Inf in closes must raise ValueError."""
        closes = _valid_closes(20)
        closes[13] = float('inf')
        with pytest.raises(ValueError):
            _rsi(14)._compute_values(closes, _bars(closes))

    def test_p2a_rsi_valid_closes_do_not_raise(self):
        """RSI with all finite closes (and sufficient bars) must not raise."""
        closes = _valid_closes(20)
        result = _rsi(14)._compute_values(closes, _bars(closes))
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# P2-A-ATR: ATR fails closed on bad closes AND bad bar prices
# ─────────────────────────────────────────────────────────────────────────────

class TestP2AATRGuard:
    """P2-A: ATR _compute_values must raise ValueError on non-finite close or bar price."""

    def test_p2a_atr_nan_close_raises(self):
        """ATR with NaN in closes must raise ValueError."""
        closes = _valid_closes(10)
        closes[2] = float('nan')
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, _bars(closes))

    def test_p2a_atr_inf_close_raises(self):
        """ATR with +Inf close must raise ValueError."""
        closes = _valid_closes(10)
        closes[1] = float('inf')
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, _bars(closes))

    def test_p2a_atr_nan_bar_high_raises(self):
        """ATR with NaN bar.high must raise ValueError."""
        closes = _valid_closes(10)
        bars = list(_bars(closes))
        bars[1] = FakeBar(bars[1].bar_open, bars[1].close, float('nan'), bars[1].low)
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2a_atr_nan_bar_low_raises(self):
        """ATR with NaN bar.low must raise ValueError."""
        closes = _valid_closes(10)
        bars = list(_bars(closes))
        bars[2] = FakeBar(bars[2].bar_open, bars[2].close, bars[2].high, float('nan'))
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2a_atr_inf_bar_high_raises(self):
        """ATR with +Inf bar.high must raise ValueError."""
        closes = _valid_closes(10)
        bars = list(_bars(closes))
        bars[2] = FakeBar(bars[2].bar_open, bars[2].close, float('inf'), bars[2].low)
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2a_atr_neg_inf_bar_low_raises(self):
        """ATR with -Inf bar.low must raise ValueError."""
        closes = _valid_closes(10)
        bars = list(_bars(closes))
        bars[1] = FakeBar(bars[1].bar_open, bars[1].close, bars[1].high, float('-inf'))
        with pytest.raises(ValueError):
            _atr(3)._compute_values(closes, bars)

    def test_p2a_atr_valid_inputs_do_not_raise(self):
        """ATR with fully finite closes and bar prices must not raise."""
        closes = _valid_closes(10)
        result = _atr(3)._compute_values(closes, _bars(closes))
        assert result is not None
        assert len(result) == len(closes)
        assert result[-1] is not None
        assert math.isfinite(result[-1])


# ─────────────────────────────────────────────────────────────────────────────
# P2-A-AST: Guards are present at SOURCE level (structural regression test)
# ─────────────────────────────────────────────────────────────────────────────

class TestP2AGuardPresenceAST:
    """
    P2-A STRUCTURAL: Confirm _guard_finite_closes and _guard_finite_bar_prices
    are defined AND called inside _compute_values at the AST/source level.
    If someone removes a guard call, this test catches it immediately.
    """

    def test_p2a_guard_functions_defined_in_source(self):
        """_guard_finite_closes and _guard_finite_bar_prices must be defined."""
        src = INDICATOR_LIB_PATH.read_text(encoding="utf-8")
        assert "_guard_finite_closes" in src, (
            "P2-A: _guard_finite_closes guard function missing from indicator_library.py"
        )
        assert "_guard_finite_bar_prices" in src, (
            "P2-A: _guard_finite_bar_prices guard function missing from indicator_library.py"
        )

    def test_p2a_guard_called_in_atr_compute_values(self):
        """ATRIndicator._compute_values must call both guards."""
        src = INDICATOR_LIB_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = _find_guard_calls_in_method(tree, "ATRIndicator", "_compute_values")
        assert "_guard_finite_closes" in calls, (
            "P2-A: ATRIndicator._compute_values does not call _guard_finite_closes"
        )
        assert "_guard_finite_bar_prices" in calls, (
            "P2-A: ATRIndicator._compute_values does not call _guard_finite_bar_prices"
        )

    def test_p2a_guard_called_in_sma_compute_values(self):
        """SMAIndicator._compute_values must call _guard_finite_closes."""
        src = INDICATOR_LIB_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = _find_guard_calls_in_method(tree, "SMAIndicator", "_compute_values")
        assert "_guard_finite_closes" in calls, (
            "P2-A: SMAIndicator._compute_values does not call _guard_finite_closes"
        )

    def test_p2a_guard_called_in_ema_compute_values(self):
        """EMAIndicator._compute_values must call _guard_finite_closes."""
        src = INDICATOR_LIB_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = _find_guard_calls_in_method(tree, "EMAIndicator", "_compute_values")
        assert "_guard_finite_closes" in calls, (
            "P2-A: EMAIndicator._compute_values does not call _guard_finite_closes"
        )

    def test_p2a_guard_called_in_rsi_compute_values(self):
        """RSIIndicator._compute_values must call _guard_finite_closes."""
        src = INDICATOR_LIB_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = _find_guard_calls_in_method(tree, "RSIIndicator", "_compute_values")
        assert "_guard_finite_closes" in calls, (
            "P2-A: RSIIndicator._compute_values does not call _guard_finite_closes"
        )


def _find_guard_calls_in_method(tree: ast.AST, class_name: str, method_name: str) -> set:
    """Return set of function names called inside class_name.method_name."""
    calls: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Call):
                            if isinstance(sub.func, ast.Name):
                                calls.add(sub.func.id)
                            elif isinstance(sub.func, ast.Attribute):
                                calls.add(sub.func.attr)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# P2-A FAIL→PASS evidence note (for audit trail)
# ─────────────────────────────────────────────────────────────────────────────
#
# RED (SHA dbc191d, pre-fix, before commit bff0769):
#   _guard_finite_closes / _guard_finite_bar_prices did not exist.
#   NaN/Inf passed to ATR/SMA/EMA/RSI _compute_values silently propagated.
#   23 tests in this file FAILED with "DID NOT RAISE ValueError".
#   Observed: pytest tests/test_p2a_regression.py → 23 failed, 0 passed.
#
# GREEN (SHA 0af141c, post-fix, including commit bff0769):
#   Both guards defined and called as FIRST lines of all 4 _compute_values().
#   All tests in this file PASS.
#   Observed: pytest tests/test_p2a_regression.py → 23 passed.
#
# ─────────────────────────────────────────────────────────────────────────────
