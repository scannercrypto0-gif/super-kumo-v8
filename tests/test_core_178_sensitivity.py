"""Synthetic-only proposed S00-S11 contract checks; no historical study."""
import math

from research_wp_r0.core_dev_b0_sensitivity import SENSITIVITY, build_synthetic_sensitivity
from research_wp_r0.historical_dev_exits_v1 import (
    Config, digest, replay_contract_fixture, verify_receipt,
)


def fixture(n=700):
    """Create deterministic oscillating bars with post-warmup EMA crossings."""
    bars = []
    for i in range(n):
        close = 100.0 + 5.0 * math.sin(i * 0.15)
        opening = 100.0 + 5.0 * math.sin((i - 0.5) * 0.15)
        bars.append({
            "open_ms": i * 60000,
            "close_ms": (i + 1) * 60000 - 1,
            "open": opening,
            "high": max(opening, close) + 1.0,
            "low": min(opening, close) - 1.0,
            "close": close,
            "volume": 1.0,
            "available_ms": (i + 1) * 60000 + 1000,
            "modeled_quote": True,
        })
    source = {
        "version": "synthetic-b0",
        "reference": "fixture:core178-sensitivity",
        "archive_sha256": "a" * 64,
        "rows_sha256": digest(bars),
        "availability_evidence": "UNKNOWN",
        "correction_evidence": "PINNED_VERSION_ONLY",
    }
    return bars, source


def test_twelve_independent_cases_apply_timing_costs_warmup_and_denominator():
    bars, source = fixture()
    original = [dict(bar) for bar in bars]
    results = build_synthetic_sensitivity(bars, source)

    assert set(results) == set(SENSITIVITY)
    assert sum(len(case.candidate.receipt["paths"]) for case in results.values()) == 36
    assert bars == original, "scenario builder must not mutate caller input"

    for sid, (source_lag, execution_lag, spread, slip, fee) in SENSITIVITY.items():
        case = results[sid]
        receipt = case.candidate.receipt
        assert case.source_lag_ms == source_lag
        assert case.execution_lag_ms == execution_lag
        assert verify_receipt(receipt)
        assert receipt["config"]["warmup_bars"] == 252
        assert receipt["config"]["quantity"] == 0.001
        assert receipt["config"]["initial_cash"] == 1000
        assert receipt["config"]["latency_ms"] == execution_lag
        assert receipt["config"]["spread_bps"] == spread
        assert receipt["config"]["slippage_bps"] == slip
        assert receipt["config"]["fee_bps"] == fee
        assert all(row["available_ms"] == row["close_ms"] + 1 + source_lag
                   for row in receipt["input_rows"])
        assert all(signal["bar_open_ms"] >= 252 * 60000
                   for signal in receipt["signals"])
        assert len(receipt["signals"]) > 0, "fixture must exercise post-warmup signals"
        assert set(receipt["paths"]) == {"FACTUAL", "TARGET_FIRST", "STOP_FIRST"}

        for path in receipt["paths"].values():
            assert path["scheduled_denominator"] == len(receipt["signals"])
            assert len(path["opportunities"]) == path["scheduled_denominator"]
            assert all(op["scored_return"] is None for op in path["opportunities"])

        # Every scheduled time is computed from source-ready time plus the
        # separate execution latency, rounded up to the next eligible grid OPEN.
        for signal in receipt["signals"]:
            ready = signal["available_ms"] + execution_lag
            expected_open = ((ready + 60000 - 1) // 60000) * 60000
            for path in receipt["paths"].values():
                matching = [op for op in path["opportunities"]
                            if op["bar_open_ms"] == signal["bar_open_ms"]]
                assert len(matching) == 1
                assert matching[0]["scheduled_ms"] == expected_open

    assert results["S10"].candidate.receipt["config"]["fee_bps"] == 0
    assert results["S10"].candidate.receipt["config"]["spread_bps"] == 0
    assert results["S10"].candidate.receipt["config"]["slippage_bps"] == 0
    assert results["S11"].candidate.receipt["config"]["slippage_bps"] == 50


def test_terminal_unfilled_entry_preserves_unknown_and_full_denominator():
    bars, source = fixture(260)
    signal_bar = bars[-2]
    signal = {
        "bar_open_ms": signal_bar["open_ms"],
        "action": "ENTER_LONG",
        "available_ms": signal_bar["available_ms"],
    }
    receipt = replay_contract_fixture(
        bars, source=source, signals=[signal],
        config=Config(initial_cash=1000, quantity=0.001, latency_ms=1000),
    )
    assert verify_receipt(receipt)

    for path in receipt["paths"].values():
        assert path["scheduled_denominator"] == 1
        assert len(path["opportunities"]) == 1
        assert path["opportunities"][0]["status"] == "UNKNOWN_NO_ELIGIBLE_OPEN"
        assert path["opportunities"][0]["scored_return"] is None
        assert path["status"] == "UNKNOWN_UNRESOLVED"
        assert path["realized_pnl"] is None
        assert path["modeled_equity_return"] is None
