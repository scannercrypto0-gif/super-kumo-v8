"""Adversarial tests for the single supported production Factory entrypoint."""
from pathlib import Path
import pytest
from research_wp_r0 import factory_b0_study_runner as runner


def _files(tmp_path):
    archive = tmp_path / "market.zip"
    receipt = tmp_path / "receipt.json"
    store = tmp_path / "store"
    archive.write_bytes(b"pinned archive bytes")
    receipt.write_bytes(b"issued receipt bytes")
    store.mkdir()
    return archive, receipt, store


def test_missing_inputs_fail_before_admission_or_engine(tmp_path, monkeypatch):
    archive, receipt, store = _files(tmp_path)
    archive.unlink()
    called = []
    monkeypatch.setattr(runner, "admit_one_study_run", lambda **kw: called.append("admit"))
    monkeypatch.setattr(runner, "authorize_factory_execution", lambda *a: called.append("start"))
    monkeypatch.setattr(runner, "replay", lambda *a, **kw: called.append("replay"))
    with pytest.raises(FileNotFoundError):
        runner.run_authorized_b0_study(permit={}, archive_path=archive,
            issued_receipt_path=receipt, result_store=store, experiment_id="AQL-DEV-FIRST-01")
    assert called == []


def test_admission_failure_stops_before_start_replay_and_persistence(tmp_path, monkeypatch):
    archive, receipt, store = _files(tmp_path)
    calls = []
    def denied(*args, **kwargs):
        calls.append("admission")
        raise PermissionError("denied")
    monkeypatch.setattr(runner, "admit_one_study_run", denied)
    monkeypatch.setattr(runner, "authorize_factory_execution", lambda *a: calls.append("start"))
    monkeypatch.setattr(runner, "replay", lambda *a, **kw: calls.append("replay"))
    monkeypatch.setattr(runner, "persist_bundle", lambda *a, **kw: calls.append("persist"))
    with pytest.raises(PermissionError):
        runner.run_authorized_b0_study(permit={}, archive_path=archive,
            issued_receipt_path=receipt, result_store=store, experiment_id="AQL-DEV-FIRST-01")
    assert calls == ["admission"]


def test_start_authorization_failure_stops_before_replay_and_persistence(tmp_path, monkeypatch):
    archive, receipt, store = _files(tmp_path)
    calls = []
    monkeypatch.setattr(runner, "admit_one_study_run",
                        lambda **kw: {"admission_record_path": "signed.json"})
    def denied(path):
        calls.append(("start", path))
        raise PermissionError("start denied")
    monkeypatch.setattr(runner, "authorize_factory_execution", denied)
    monkeypatch.setattr(runner, "replay", lambda *a, **kw: calls.append("replay"))
    monkeypatch.setattr(runner, "persist_bundle", lambda *a, **kw: calls.append("persist"))
    with pytest.raises(PermissionError):
        runner.run_authorized_b0_study(permit={}, archive_path=archive,
            issued_receipt_path=receipt, result_store=store, experiment_id="AQL-DEV-FIRST-01")
    assert calls == [("start", "signed.json")]


def test_invalid_start_receipt_fails_closed(tmp_path, monkeypatch):
    archive, receipt, store = _files(tmp_path)
    calls = []
    monkeypatch.setattr(runner, "admit_one_study_run",
                        lambda **kw: {"admission_record_path": "signed.json"})
    monkeypatch.setattr(runner, "authorize_factory_execution",
                        lambda path: {"state": "NOT_STARTED"})
    monkeypatch.setattr(runner, "replay", lambda *a, **kw: calls.append("replay"))
    with pytest.raises(runner.FactoryStudyDenied, match="FACTORY_START_AUTHORIZATION_INVALID"):
        runner.run_authorized_b0_study(permit={}, archive_path=archive,
            issued_receipt_path=receipt, result_store=store, experiment_id="AQL-DEV-FIRST-01")
    assert calls == []


def test_experiment_id_is_validated_before_side_effects(tmp_path, monkeypatch):
    archive, receipt, store = _files(tmp_path)
    called = []
    monkeypatch.setattr(runner, "admit_one_study_run", lambda **kw: called.append("admit"))
    with pytest.raises(ValueError, match="INVALID_EXPERIMENT_ID"):
        runner.run_authorized_b0_study(permit={}, archive_path=archive,
            issued_receipt_path=receipt, result_store=store, experiment_id="../escape")
    assert called == []
