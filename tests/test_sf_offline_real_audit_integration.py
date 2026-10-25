"""Positive end-to-end synthetic receipt integration, without audit mocks.

This proves library -> PIT input binding -> real auditor -> synthetic simulator.
It does NOT validate market-history provenance or production execution.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_sf_research_int_01 import inputs
from research_wp_r0.future_bar_evidence import FutureBarEvidence
from research_wp_r0.offline_input_audit import audit_offline_inputs
from research_wp_r0.offline_simulator import simulate_single_long


def test_real_library_receipt_audit_and_simulated_close():
    prepared = inputs()
    audit = audit_offline_inputs(prepared, expected_digest=prepared.digest)
    assert audit["status"] == "INPUTS_AUDITED_NOT_EVALUATED"

    spec = prepared.spec
    decision = spec["binding"]["binding"]["decision_cutoff_ms"]
    interval = 60000
    last_open = spec["bars"][-1]["bar_open"]
    first_open = last_open + ((decision - last_open) // interval + 1) * interval
    future = FutureBarEvidence({
        "schema_version": "research-future-bars-1",
        "inputs_digest": prepared.digest,
        "decision_cutoff_ms": decision,
        "symbol": spec["dataset_manifest"]["symbol"],
        "interval_ms": interval,
        "independent_custody": "NOT_VERIFIED",
        "bars": [
            {"open_ms": first_open, "close_ms": first_open + interval - 1,
             "open": 100, "high": 105, "low": 99, "close": 104,
             "volume": 10, "observed_at_ms": first_open + interval},
            {"open_ms": first_open + interval, "close_ms": first_open + 2 * interval - 1,
             "open": 105, "high": 110, "low": 104, "close": 109,
             "volume": 10, "observed_at_ms": first_open + 2 * interval},
        ],
    })
    # Fail closed when a separately stored future commitment is wrong.
    import pytest
    with pytest.raises(ValueError, match="future evidence digest"):
        simulate_single_long(prepared, expected_digest=prepared.digest,
                             signal=True, future=future,
                             expected_future_digest="f" * 64)
    # Fail closed on a separately retained input commitment mismatch.
    with pytest.raises(ValueError, match="Input commitment mismatch"):
        simulate_single_long(prepared, expected_digest="f" * 64,
                             signal=True, future=future,
                             expected_future_digest=future.digest)
    result = simulate_single_long(prepared, expected_digest=prepared.digest,
                                  signal=True, future=future,
                                  expected_future_digest=future.digest)
    assert result.spec["outcome"] == "SIMULATED_CLOSED"
    assert result.spec["entry_bar_open_ms"] == first_open
    assert result.spec["exit_bar_open_ms"] == first_open + interval
    assert abs(result.spec["gross_return_bps"] - 500) < 1e-7
    assert abs(result.spec["net_return_bps"] - 470) < 1e-7
    assert result.spec["independent_custody"] == "NOT_VERIFIED"

def test_real_auditor_no_signal_keeps_zero_exposure():
    prepared = inputs()
    result = simulate_single_long(prepared, expected_digest=prepared.digest,
                                  signal=False)
    assert result.spec["outcome"] == "NO_SIGNAL"
    assert result.spec["entry_bar_open_ms"] is None
    assert result.spec["net_return_bps"] is None


def test_real_auditor_missing_future_does_not_invent_execution():
    prepared = inputs()
    result = simulate_single_long(prepared, expected_digest=prepared.digest,
                                  signal=True)
    assert result.spec["outcome"] == "UNRESOLVED"
    assert result.spec["reason"] == "UNKNOWN"
    assert result.spec["entry_bar_open_ms"] is None
    assert result.spec["net_return_bps"] is None
