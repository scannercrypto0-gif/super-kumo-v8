"""
Gate 4 Regression Tests — Issue #215
======================================
PM requirement (Issue #215 Gate 4):
  Verify _guard_finite_bar_prices rejects nonnumeric high/low/close as ValueError.

Bug on 9800137: _guard_finite_bar_prices checks math.isfinite(v) without first
checking isinstance(v, (int, float)).  When v is a string, math.isfinite(v)
raises TypeError, not ValueError.  _guard_finite_closes already has the fix
(P2-B-1); _guard_finite_bar_prices is missing it.

RED on 9800137:
  G4-NONNUMERIC-1/2/3/4/5 → TypeError raised instead of ValueError (FAIL)

GREEN after fix:
  All 9 tests PASS (isinstance check raises ValueError for nonnumeric attrs)

Run:
    PYTHONPATH=/home/claude/super-kumo-v8 pytest research_wp_r0/test_g4_nonnumeric_regression.py -v
"""
from __future__ import annotations
import math
import pytest
from research_wp_r0.indicator_library import _guard_finite_bar_prices


class _Bar:
    """Minimal bar stub for testing attr guards."""
    def __init__(self, high, low, close):
        self.high = high
        self.low = low
        self.close = close


class TestG4NonnumericBarPricesRaisesValueError:
    """
    Gate 4 defect: _guard_finite_bar_prices must raise ValueError (not TypeError)
    for nonnumeric high/low/close.  On 9800137 math.isfinite('str') raises TypeError.
    """

    def test_string_high_raises_value_error(self):
        """
        G4-NONNUMERIC-1: string high must raise ValueError, not TypeError.
        Bug: math.isfinite('not_a_number') raises TypeError on 9800137.
        """
        bar = _Bar(high="not_a_number", low=100.0, close=101.0)
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])

    def test_string_low_raises_value_error(self):
        """G4-NONNUMERIC-2: string low must raise ValueError, not TypeError."""
        bar = _Bar(high=100.0, low="bad_low", close=101.0)
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])

    def test_string_close_raises_value_error(self):
        """G4-NONNUMERIC-3: string close must raise ValueError, not TypeError."""
        bar = _Bar(high=100.0, low=99.0, close="bad_close")
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])

    def test_list_high_raises_value_error(self):
        """G4-NONNUMERIC-4: list value for high must raise ValueError, not TypeError."""
        bar = _Bar(high=[1, 2, 3], low=100.0, close=101.0)
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])

    def test_dict_close_raises_value_error(self):
        """G4-NONNUMERIC-5: dict value for close must raise ValueError, not TypeError."""
        bar = _Bar(high=100.0, low=99.0, close={"price": 100.0})
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])

    # -- compatibility: existing behavior must be preserved ------------------

    def test_valid_float_bar_passes(self):
        """G4-COMPAT-1: valid float high/low/close must not raise."""
        bar = _Bar(high=101.5, low=99.0, close=100.0)
        _guard_finite_bar_prices([bar])  # must not raise

    def test_valid_int_bar_passes(self):
        """G4-COMPAT-2: integer high/low/close are numeric and must not raise."""
        bar = _Bar(high=101, low=99, close=100)
        _guard_finite_bar_prices([bar])  # must not raise

    def test_none_high_still_raises_value_error(self):
        """G4-REGRESSION-1: None must still raise ValueError (existing behavior)."""
        bar = _Bar(high=None, low=100.0, close=101.0)
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])

    def test_nan_high_still_raises_value_error(self):
        """G4-REGRESSION-2: NaN must still raise ValueError (existing behavior)."""
        bar = _Bar(high=float("nan"), low=100.0, close=101.0)
        with pytest.raises(ValueError):
            _guard_finite_bar_prices([bar])
