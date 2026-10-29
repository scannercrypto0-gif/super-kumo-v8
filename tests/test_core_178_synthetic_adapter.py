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
        AdmissionDenied, _consume_owner_one_run_permit,
    )
    secret = b"test-only-secret-key-at-least-32-bytes"
    head = "f" * 40
    permit = _signed_b0_permit(secret, head=head)
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    admission = _consume_owner_one_run_permit(
        permit, admission_dir=tmp_path / "admissions", secret=secret,
        runtime_head=head, worktree_clean=True, preflight_report_sha256="a" * 64, now=now,
    )
    assert admission["state"] == "ADMITTED_NOT_STARTED"
    assert admission["max_runs"] == 1
    assert (tmp_path / "admissions" / "permit-test-0001.consumed.json").exists()
    with pytest.raises(AdmissionDenied, match="PERMIT_ALREADY_CONSUMED"):
        _consume_owner_one_run_permit(
            permit, admission_dir=tmp_path / "admissions", secret=secret,
            runtime_head=head, worktree_clean=True, preflight_report_sha256="a" * 64, now=now,
        )


def test_owner_permit_rejects_signature_head_and_dirty_checkout(tmp_path):
    from datetime import datetime, timezone
    from research_wp_r0.core_b0_admission import (
        AdmissionDenied, _consume_owner_one_run_permit,
    )
    secret = b"test-only-secret-key-at-least-32-bytes"
    head = "f" * 40
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    permit = _signed_b0_permit(secret, permit_id="permit-test-0002", head=head)
    tampered = {**permit, "scenario_ids": ["S00"]}
    with pytest.raises(AdmissionDenied, match="INVALID_PERMIT_SCENARIOS|PERMIT_SCENARIO_SET_MISMATCH|OWNER_SIGNATURE_INVALID"):
        _consume_owner_one_run_permit(
            tampered, admission_dir=tmp_path / "tampered", secret=secret,
            runtime_head=head, worktree_clean=True, preflight_report_sha256="a" * 64, now=now,
        )
    with pytest.raises(AdmissionDenied, match="CHECKOUT_HEAD_MISMATCH"):
        _consume_owner_one_run_permit(
            permit, admission_dir=tmp_path / "wrong-head", secret=secret,
            runtime_head="e" * 40, worktree_clean=True, preflight_report_sha256="a" * 64, now=now,
        )
    with pytest.raises(AdmissionDenied, match="WORKTREE_NOT_CLEAN"):
        _consume_owner_one_run_permit(
            permit, admission_dir=tmp_path / "dirty", secret=secret,
            runtime_head=head, worktree_clean=False, preflight_report_sha256="a" * 64, now=now,
        )


def test_entrypoint_requires_full_preflight_before_admission(monkeypatch):
    import research_wp_r0.core_b0_entrypoint as entry
    from research_wp_r0.core_b0_admission import AdmissionDenied
    permit = {"permit_id": "test-permit-0001"}
    monkeypatch.setattr(entry, "run_input_preflight", lambda **kwargs: {
        "status": "INPUT_PREFLIGHT_FAILED", "passed": 11, "failed": 1,
    })
    monkeypatch.setattr(
        "research_wp_r0.core_b0_admission.admit_current_checkout_one_run",
        lambda *args, **kwargs: pytest.fail("permit must not be consumed after failed preflight"),
    )
    with pytest.raises(AdmissionDenied, match="INPUT_PREFLIGHT_FAILED"):
        entry.admit_one_study_run(permit, archive_bytes=b"zip", issued_receipt_bytes=b"receipt")


def test_entrypoint_binds_admission_to_preflight_report(monkeypatch):
    import hashlib
    import json
    import research_wp_r0.core_b0_entrypoint as entry
    captured = {}
    report = {
        "status": "INPUT_PREFLIGHT_PASS_NOT_STUDY_AUTHORITY",
        "passed": 12, "failed": 0, "scenario_count": 12,
        "archive_sha256": "a" * 64, "issued_receipt_sha256": "b" * 64,
    }
    monkeypatch.setattr(entry, "run_input_preflight", lambda **kwargs: report)
    def fake_admit(permit, *, preflight_report_sha256):
        captured["permit"] = permit
        captured["preflight_report_sha256"] = preflight_report_sha256
        return {"state": "ADMITTED_NOT_STARTED"}
    monkeypatch.setattr(
        "research_wp_r0.core_b0_admission.admit_current_checkout_one_run", fake_admit,
    )
    result = entry.admit_one_study_run(
        {"permit_id": "test-permit-0002"}, archive_bytes=b"zip", issued_receipt_bytes=b"receipt"
    )
    expected = hashlib.sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")).hexdigest()
    assert result["state"] == "ADMITTED_NOT_STARTED"
    assert captured["permit"]["permit_id"] == "test-permit-0002"
    assert captured["preflight_report_sha256"] == expected


def test_factory_consumer_verifies_and_consumes_signed_admission_once(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import os
    import research_wp_r0.core_b0_admission as gate
    secret = b"test-only-secret-key-at-least-32-bytes"
    head = "f" * 40
    monkeypatch.setenv("AQL_B0_PERMIT_HMAC_KEY", secret.decode())
    monkeypatch.setattr(gate, "_runtime_identity", lambda expected: {
        "head_sha": head, "worktree_clean": True,
    })
    permit = _signed_b0_permit(secret, permit_id="permit-test-0003", head=head)
    admitted = gate._consume_owner_one_run_permit(
        permit, admission_dir=tmp_path / "admissions", secret=secret,
        runtime_head=head, worktree_clean=True, preflight_report_sha256="a" * 64,
        now=datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc),
    )
    started = gate.authorize_factory_execution(admitted["admission_record_path"])
    assert started["max_runs"] == 1
    assert started["admission_record_sha256"] == admitted["admission_record_sha256"]
    with pytest.raises(gate.AdmissionDenied, match="ADMISSION_ALREADY_STARTED"):
        gate.authorize_factory_execution(admitted["admission_record_path"])
