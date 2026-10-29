"""Synthetic-only proposed S00-S11 contract checks."""
from research_wp_r0.core_dev_b0_sensitivity import SENSITIVITY, build_synthetic_sensitivity
from research_wp_r0.historical_dev_exits_v1 import verify_receipt
from test_core_178_synthetic_adapter import fixture

def test_twelve_independent_cases_and_36_paths():
    bars, source = fixture(260)
    results = build_synthetic_sensitivity(bars,source)
    assert set(results)==set(SENSITIVITY)
    assert sum(len(case.candidate.receipt["paths"]) for case in results.values()) == 36
    for sid,case in results.items():
        receipt=case.candidate.receipt
        assert verify_receipt(receipt)
        assert receipt["config"]["warmup_bars"] == 252
        assert receipt["config"]["quantity"] == .001
        assert receipt["input_rows"][0]["available_ms"] == bars[0]["close_ms"]+1+SENSITIVITY[sid][0]
        assert set(receipt["paths"]) == {"FACTUAL","TARGET_FIRST","STOP_FIRST"}
    assert results["S10"].candidate.receipt["config"]["fee_bps"] == 0
    assert results["S11"].candidate.receipt["config"]["slippage_bps"] == 50
