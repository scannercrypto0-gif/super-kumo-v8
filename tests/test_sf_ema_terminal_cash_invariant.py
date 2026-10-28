"""Targeted independent cash/position invariant for legacy EMA development replay.

Engineering synthetic fixtures only. No OOS, issuer-time or trading validity.
"""
import math
import random

import pytest

from research_wp_r0.ema_development_replay import replay_ema_development


START = 1704067200000
SPAN = 60000
INITIAL = 100000.0


def _bars(prices):
    return tuple((START + i * SPAN, START + (i + 1) * SPAN - 1,
                  float(p), float(p) + 1, float(p) - 1, float(p), 10)
                 for i, p in enumerate(prices))


def _independent_equity(report, bars):
    """Independent cash ledger; uses only emitted entry/exit event identities.

    Does not call account_long_prices, replay's capital variables, or its marks.
    """
    fee = report["fee_bps_per_side"] / 10000
    slip = report["slippage_bps_per_side"] / 10000
    actions = {e["next_open_ms"]: e["status"]
               for e in report["opportunities"]
               if e["status"] in ("SIMULATED_ENTRY", "SIMULATED_EXIT")}
    cash, units = INITIAL, 0
    values = []
    for opening, closing, entry_open, _, _, close, _ in bars:
        action = actions.get(opening)
        if action == "SIMULATED_ENTRY":
            assert units == 0
            cash -= entry_open * (1 + slip) * (1 + fee)
            units = 1
        elif action == "SIMULATED_EXIT":
            assert units == 1
            cash += entry_open * (1 - slip) * (1 - fee)
            units = 0
        values.append((closing, cash + units * close * (1 - slip) * (1 - fee)))
    return values, cash, units


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("fee,slip", [(0, 0), (10, 5), (20, 10)])
def test_report_cash_and_terminal_open_conservation(seed, fee, slip):
    rng = random.Random(seed)
    prices = [100.0] * 24
    for i in range(80):
        segment = i // 10
        drift = (0.9 if segment % 2 == 0 else -0.8)
        prices.append(max(8.0, prices[-1] + drift + rng.uniform(-1.1, 1.1)))
    data = _bars(prices)
    split = data[-1][0] + SPAN
    report = replay_ema_development(
        data, split_cutoff_ms=split, fee_bps=fee, slippage_bps=slip)
    expected, cash, units = _independent_equity(report, data)
    assert len(report["equity_curve"]) == len(expected)
    for actual, (expected_ms, expected_value) in zip(report["equity_curve"], expected):
        assert actual[0] == expected_ms
        assert actual[1] == pytest.approx(expected_value, abs=2e-7)
    assert report["terminal_equity_quote"] == pytest.approx(expected[-1][1], abs=2e-7)
    assert report["portfolio_net_return_fraction"] == pytest.approx(
        expected[-1][1] / INITIAL - 1, abs=1e-11)
    assert (report["open_position"] is not None) == (units == 1)
    assert report["phase"] == "HISTORICAL_DEVELOPMENT"
    assert report["data_availability"] == "RETROSPECTIVE_NOT_CONFIRMED"
    assert report["oos"] == "LOCKED_NOT_EVALUATED"
    assert report["sample_limitation"] == "ONE_ENGINEERING_SAMPLE_NO_INFERENCE_NO_PROFITABILITY_EVIDENCE"
    if units == 0:
        assert expected[-1][1] == pytest.approx(cash, abs=2e-7)
    else:
        assert report["open_position"]["status"] == "OPEN_UNREALIZED"
