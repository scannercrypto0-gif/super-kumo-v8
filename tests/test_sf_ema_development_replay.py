"""Development-only EMA replay regression fixtures (not market data)."""
import pytest

from research_wp_r0.ema_development_replay import replay_ema_development


def bars(prices):
    start = 1704067200000
    return tuple((start + i * 60000, start + (i + 1) * 60000 - 1,
                  p, p + 1, p - 1, p, 10) for i, p in enumerate(prices))


def test_deterministic_next_open_and_reserved_oos():
    prices = [100.0] * 24 + [105.0] * 6 + [90.0] * 7 + [110.0] * 5
    data = bars(prices)
    split = data[37][0]
    report = replay_ema_development(data, split_cutoff_ms=split)
    assert report == replay_ema_development(data, split_cutoff_ms=split)
    assert report["phase"] == "HISTORICAL_DEVELOPMENT"
    assert report["oos"] == "LOCKED_NOT_EVALUATED"
    assert all(t["exit_open_ms"] < split for t in report["trades"])
    assert all(t["cost_bps"] > 0 for t in report["trades"])
    assert all(e["next_open_ms"] == e["decision_cutoff_ms"] for e in report["opportunities"])
    assert any(e["status"] == "SIMULATED_ENTRY" for e in report["opportunities"])
    assert any(e["status"] == "SIMULATED_EXIT" for e in report["opportunities"])


def test_future_oos_candles_cannot_change_dev_report():
    prices = [100.0] * 24 + [105.0] * 6 + [90.0] * 7
    prefix = bars(prices)
    split = prefix[-1][0] + 60000
    a = replay_ema_development(prefix, split_cutoff_ms=split)
    b = replay_ema_development(bars(prices + [1000.0] * 10),
                               split_cutoff_ms=split)
    assert a == b


def test_boundary_requires_whole_candles():
    data = bars([100.0] * 30)
    with pytest.raises(ValueError, match="crosses"):
        replay_ema_development(data, split_cutoff_ms=data[-1][0] + 1000)
