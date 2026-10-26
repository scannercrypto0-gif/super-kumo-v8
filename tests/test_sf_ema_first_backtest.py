"""P0 causal EMA research acceptance: no future leakage, frozen plan."""
import pytest

from research_wp_r0.ema_first_backtest import ema_crossover_decisions, frozen_ema_plan


def bars(prices):
    start = 1704067200000
    return tuple((start + i*60000, start + (i+1)*60000 - 1,
                  p, p+1, p-1, p, 10) for i, p in enumerate(prices))


def test_prefix_invariance_and_no_same_bar_entry():
    prices = [100.0]*24 + [105.0]*5 + [90.0]*5
    full = ema_crossover_decisions(bars(prices))
    prefix = ema_crossover_decisions(bars(prices[:29]))
    assert full[:len(prefix)] == prefix
    assert all(d.decision_cutoff_ms > d.bar_open_ms for d in full)
    assert any(d.signal == "ENTER_LONG" for d in full)
    assert any(d.signal == "EXIT_LONG" for d in full)


def test_reject_warmup_and_gaps():
    with pytest.raises(ValueError, match="warmup"):
        ema_crossover_decisions(bars([100]*21))
    broken = list(bars([100]*25))
    del broken[3]
    with pytest.raises(ValueError, match="grid"):
        ema_crossover_decisions(broken)


def test_plan_commitment_is_deterministic_and_split_is_explicit():
    args = dict(archive_sha256="a"*64, source_reference="Binance public spot archive",
                split_cutoff_ms=1705000000000)
    plan, sha = frozen_ema_plan(**args)
    assert frozen_ema_plan(**args)[1] == sha
    assert plan["oos_state"] == "LOCKED_NOT_EVALUATED"
    assert frozen_ema_plan(**{**args, "split_cutoff_ms":1706000000000})[1] != sha
