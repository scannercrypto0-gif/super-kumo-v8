"""Synthetic-only Core178 contract tests: never execute a historical study."""
import pytest
from research_wp_r0.core_dev_b0_adapter import (
    ExecutionDenied, build_synthetic_candidate, run_study, ENGINE_PIN)
from research_wp_r0.historical_dev_exits_v1 import Config, digest, verify_receipt

def fixture(n=260):
    bars = [dict(open_ms=i*60000, close_ms=(i+1)*60000-1,
                 open=100+i*.01, high=101+i*.01, low=99+i*.01,
                 close=100+i*.01, volume=1., available_ms=(i+1)*60000+1000,
                 modeled_quote=True) for i in range(n)]
    source = dict(version="synthetic-b0", reference="fixture:core178",
                  archive_sha256="a"*64, rows_sha256=digest(bars),
                  availability_evidence="UNKNOWN",
                  correction_evidence="PINNED_VERSION_ONLY")
    return bars, source

def test_explicit_252_and_three_paths():
    bars, source = fixture()
    result = build_synthetic_candidate(bars, source)
    assert result.engine_pin == ENGINE_PIN
    assert verify_receipt(result.receipt)
    assert result.receipt["config"]["warmup_bars"] == 252
    assert set(result.receipt["paths"]) == {"FACTUAL","TARGET_FIRST","STOP_FIRST"}
    assert all(s["bar_open_ms"] >= 252*60000 for s in result.receipt["signals"])

def test_refuse_non_synthetic_source_and_legacy_warmup():
    bars, source = fixture()
    with pytest.raises(ExecutionDenied):
        build_synthetic_candidate(bars, {**source, "version":"real"})
    with pytest.raises(ExecutionDenied):
        build_synthetic_candidate(bars, source, config=Config())

def test_study_always_denied():
    with pytest.raises(ExecutionDenied):
        run_study(approved=True)


def test_b0_entrypoint_study_gate_fails_closed():
    from research_wp_r0.core_b0_entrypoint import (
        B0AdmissionDenied, run_one_study, run_input_preflight,
    )
    with pytest.raises(B0AdmissionDenied, match="OWNER_AUTHENTICATED_SINGLE_USE_PERMIT_REQUIRED"):
        run_one_study(approved=True, permit=True, token="not-an-authenticated-permit")
    with pytest.raises(ValueError, match="MISSING_ORIGINAL_ARCHIVE_BYTES"):
        run_input_preflight(archive_bytes=b"", issued_receipt_bytes=b"receipt")
    with pytest.raises(ValueError, match="MISSING_ISSUED_RECEIPT_BYTES"):
        run_input_preflight(archive_bytes=b"archive", issued_receipt_bytes=b"")
