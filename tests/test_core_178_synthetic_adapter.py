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


def _signed_b0_permit(secret, *, permit_id="permit-test-0001", head="f"*40):
    import hashlib
    import hmac
    import json
    unsigned = {
        "schema": "aql-owner-single-run-permit-v1",
        "permit_id": permit_id,
        "issued_at": "2026-10-29T00:00:00Z",
        "expires_at": "2026-10-30T00:00:00Z",
        "max_runs": 1,
        "head_sha": head,
        "policy_id": "DEV-B0-v1",
        "symbol": "BTCUSDT",
        "interval_ms": 60000,
        "start_ms": 1704067200000,
        "end_exclusive_ms": 1704153600000,
        "scenario_ids": [f"S{i:02d}" for i in range(12)],
    }
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    return {**unsigned, "signature": hmac.new(secret, canonical, hashlib.sha256).hexdigest()}


def test_owner_permit_is_signed_pinned_and_single_use(tmp_path):
    from datetime import datetime, timezone
    from research_wp_r0.core_b0_admission import (
        AdmissionDenied, consume_owner_one_run_permit,
    )
    secret = b"test-only-secret-key-at-least-32-bytes"
    head = "f" * 40
    permit = _signed_b0_permit(secret, head=head)
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    admission = consume_owner_one_run_permit(
        permit, admission_dir=tmp_path / "admissions", secret=secret,
        runtime_head=head, worktree_clean=True, now=now,
    )
    assert admission["state"] == "ADMITTED_NOT_STARTED"
    assert admission["max_runs"] == 1
    assert (tmp_path / "admissions" / "permit-test-0001.consumed.json").exists()
    with pytest.raises(AdmissionDenied, match="PERMIT_ALREADY_CONSUMED"):
        consume_owner_one_run_permit(
            permit, admission_dir=tmp_path / "admissions", secret=secret,
            runtime_head=head, worktree_clean=True, now=now,
        )


def test_owner_permit_rejects_signature_head_and_dirty_checkout(tmp_path):
    from datetime import datetime, timezone
    from research_wp_r0.core_b0_admission import (
        AdmissionDenied, consume_owner_one_run_permit,
    )
    secret = b"test-only-secret-key-at-least-32-bytes"
    head = "f" * 40
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    permit = _signed_b0_permit(secret, permit_id="permit-test-0002", head=head)
    tampered = {**permit, "scenario_ids": ["S00"]}
    with pytest.raises(AdmissionDenied, match="INVALID_PERMIT_SCENARIOS|PERMIT_SCENARIO_SET_MISMATCH|OWNER_SIGNATURE_INVALID"):
        consume_owner_one_run_permit(
            tampered, admission_dir=tmp_path / "tampered", secret=secret,
            runtime_head=head, worktree_clean=True, now=now,
        )
    with pytest.raises(AdmissionDenied, match="CHECKOUT_HEAD_MISMATCH"):
        consume_owner_one_run_permit(
            permit, admission_dir=tmp_path / "wrong-head", secret=secret,
            runtime_head="e" * 40, worktree_clean=True, now=now,
        )
    with pytest.raises(AdmissionDenied, match="WORKTREE_NOT_CLEAN"):
        consume_owner_one_run_permit(
            permit, admission_dir=tmp_path / "dirty", secret=secret,
            runtime_head=head, worktree_clean=False, now=now,
        )
