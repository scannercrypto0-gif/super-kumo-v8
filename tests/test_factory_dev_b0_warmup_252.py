"""Focused synthetic warmup regression; no historical study."""
import pytest
from research_wp_r0.historical_dev_exits_v1 import Config, _signals

def bars(n=300):
    return [dict(open_ms=i*60000, close_ms=(i+1)*60000-1,
                 open=100.0+i*.01, high=101.0+i*.01,
                 low=99.0+i*.01, close=100.0+i*.01,
                 volume=1.0, available_ms=(i+1)*60000+1000,
                 modeled_quote=True) for i in range(n)]

def test_warmup_252_boundary():
    signals = _signals(bars(), Config(warmup_bars=252))
    assert len(signals)==48
    assert signals[0]["bar_open_ms"]==252*60000

def test_default_22_compatibility():
    original=_signals(bars(), Config())
    # Legacy emits the index-21 decision; explicit 22 suppresses it.
    assert original[0]["bar_open_ms"] == 21 * 60000
    assert _signals(bars(), Config(warmup_bars=22)) == original[1:]
    assert _signals(bars(), Config(warmup_bars=252)) == original[231:]

@pytest.mark.parametrize("bad", [0,21,-1,22.0,True,"252"])
def test_bad_warmup(bad):
    with pytest.raises(ValueError, match="INVALID_WARMUP_BARS"):
        Config(warmup_bars=bad).validate()

def test_short_prefix_no_scored_signals():
    assert _signals(bars(251),Config(warmup_bars=252))==[]
