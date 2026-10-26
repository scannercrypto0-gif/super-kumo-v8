"""Focused synthetic-only SF-BREAKOUT-PILOT-01 proof, not profitability."""
import copy
import math

import pytest

from research_wp_r0.sf_breakout_pilot import (
    COSTS, SPEC, PilotPlan, _version_events, run_pilot, synthetic_fixture, DELTA_MS)
from research_wp_r0.strategy_definition import digest


def pilot(rows=None):
    bars = synthetic_fixture() if rows is None else rows
    plan = PilotPlan(copy.deepcopy(SPEC))
    return run_pilot(bars, plan=plan, expected_plan_digest=plan.digest,
                     expected_data_digest=digest(bars))


def test_500_bar_fixture_and_deterministic_evidence():
    bars = synthetic_fixture()
    assert len(bars) == 500 and all(b[1] == b[0] + DELTA_MS - 1 for b in bars)
    result = pilot(bars)
    assert pilot(bars) == result
    assert result["actual_fills"] == "NOT_OBSERVED"
    assert result["oos"] == "NOT_OPENED"
    assert result["paper"] == "NOT_STARTED"


def test_breakout_levels_use_prior_bars_only_and_guard_15m():
    rows = synthetic_fixture()
    base = pilot(rows)["versions"]["BASE"]
    entries = [e for e in base["events"] if e["kind"] == "ENTRY_SIGNAL"]
    assert entries
    for e in entries:
        i = e["index"]
        assert rows[i][5] > max(b[3] for b in rows[i-20:i])
        assert rows[i-1][5] <= max(b[3] for b in rows[i-21:i-1])
        assert e["hypothetical_eligible_index"] == i + 2
        assert rows[i+2][0] == rows[i][1] + 1 + DELTA_MS
    exits = [e for e in base["events"] if e["kind"] == "EXIT_SIGNAL"]
    assert exits
    assert all(rows[e["index"]][5] < min(b[4] for b in rows[e["index"]-10:e["index"]])
               for e in exits)


def test_base_shadow_independent_volume_veto_and_entry():
    out = pilot()["versions"]
    base = out["BASE"]
    shadow = out["SHADOW"]
    assert len(base["trades"]) > len(shadow["trades"]) > 0
    assert any(e["kind"] == "SHADOW_VOLUME_VETO" for e in shadow["events"])
    assert base["events"] != shadow["events"]
    assert out["BASE"]["version"] != out["SHADOW"]["version"]
    assert base["accounting"] is not shadow["accounting"]
    assert base["trades"] != shadow["trades"]


def test_missing_shadow_essential_volume_blocks_only_shadow_entry():
    data = list(synthetic_fixture())
    row = list(data[24])
    row[6] = None
    data[24] = tuple(row)
    version = pilot(tuple(data))["versions"]
    assert any(e["kind"] == "BLOCKED_MISSING_REQUIRED_DATA"
               and e["value"] == "UNKNOWN" for e in version["SHADOW"]["events"])
    assert any(e["kind"] == "SIMULATED_ENTRY" for e in version["BASE"]["events"])
    assert not any(e["kind"] == "SIMULATED_ENTRY" and e["index"] == 26
                   for e in version["SHADOW"]["events"])


def test_base_stress_two_sided_account_and_no_deposits():
    result = pilot()["versions"]
    for version in result.values():
        first = version["trades"][0]
        entry, exit_price = first["entry_price"], first["exit_price"]
        for label, cfg in COSTS.items():
            f = cfg["fee_bps"]/10000
            s = cfg["slippage_bps"]/10000
            expected = exit_price*(1-s)*(1-f) - entry*(1+s)*(1+f)
            assert version["accounting"][label]["trades"][0]["net_quote"] == pytest.approx(expected)
        assert (version["accounting"]["STRESS_COST"]["realized_pnl_quote"]
                < version["accounting"]["BASE_COST"]["realized_pnl_quote"])
        assert all(x["entry_index"] + 1 < x["exit_index"] for x in version["trades"])


def test_gaps_invalid_essential_or_frozen_plan_fail_closed():
    rows = list(synthetic_fixture())
    plan = PilotPlan(copy.deepcopy(SPEC))
    with pytest.raises(ValueError, match="plan mismatch"):
        run_pilot(rows, plan=plan, expected_plan_digest="f"*64,
                  expected_data_digest=digest(rows))
    with pytest.raises(ValueError, match="data mismatch"):
        run_pilot(rows, plan=plan, expected_plan_digest=plan.digest,
                  expected_data_digest="0"*64)
    malformed = list(rows)
    z = list(malformed[240])
    z[0] += DELTA_MS
    malformed[240] = tuple(z)
    with pytest.raises(ValueError, match="candle"):
        pilot(tuple(malformed))
    broken = list(rows)
    z = list(broken[100])
    z[5] = math.nan
    broken[100] = tuple(z)
    with pytest.raises(ValueError, match="essential"):
        pilot(tuple(broken))
    alternative = copy.deepcopy(SPEC)
    alternative["entry_lookback"] = 10
    with pytest.raises(ValueError, match="cannot be optimized"):
        PilotPlan(alternative)


def test_last_open_position_is_marked_not_invented_exit():
    rows = list(synthetic_fixture())
    prev = rows[469][5]
    for i in range(470, 500):
        close = 100.0 if i < 495 else 102.0 + (i-495)*1.5
        opening = prev
        rows[i] = (rows[i][0], rows[i][1], opening,
                   max(opening, close)+.2, min(opening, close)-.2,
                   close, 150.0)
        prev = close
    res = pilot(tuple(rows))["versions"]["BASE"]
    assert res["open_position"] is not None
    assert res["accounting"]["BASE_COST"]["open_position_unrealized"]
    assert res["accounting"]["BASE_COST"]["open_position_mark_quote"] is not None
    assert all(t["exit_index"] < 500 for t in res["trades"])


def test_same_stream_changes_only_future_opportunities():
    rows = list(synthetic_fixture())
    original = _version_events(tuple(rows), shadow=False)
    previous = rows[400]
    opening = previous[2]
    rows[400] = (previous[0], previous[1], opening,
                 max(opening, 99)+.2, min(opening, 99)-.2, 99., previous[6])
    updated = _version_events(tuple(rows), shadow=False)
    assert [e for e in original["events"] if e["index"] < 400] == [
        e for e in updated["events"] if e["index"] < 400]
