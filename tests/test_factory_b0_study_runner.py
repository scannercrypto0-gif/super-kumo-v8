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
    monkeypatch.setattr(runner, "replay_after_factory_start", lambda *a, **kw: called.append("replay"))
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
    monkeypatch.setattr(runner, "replay_after_factory_start", lambda *a, **kw: calls.append("replay"))
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
    monkeypatch.setattr(runner, "replay_after_factory_start", lambda *a, **kw: calls.append("replay"))
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
    monkeypatch.setattr(runner, "replay_after_factory_start", lambda *a, **kw: calls.append("replay"))
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

def test_engine_rejects_direct_original_source_replay():
    from research_wp_r0.historical_dev_exits_v1 import Config, replay
    source = {"version": "original-local-pair-v1"}
    with pytest.raises(PermissionError, match="PRODUCTION_REPLAY_REQUIRES_FACTORY_START_RECEIPT"):
        replay([], source=source, config=Config())


def test_engine_rejects_fabricated_or_missing_start_marker(tmp_path):
    from research_wp_r0.historical_dev_exits_v1 import Config, replay_after_factory_start
    source = {"version": "original-local-pair-v1"}
    fake = {
        "schema": "aql-owner-admission-start-v1",
        "max_runs": 1,
        "start_record_path": str(tmp_path / "missing.started"),
        "start_record_sha256": "a" * 64,
    }
    with pytest.raises(PermissionError, match="FACTORY_START_MARKER_UNREADABLE"):
        replay_after_factory_start([], source=source, config=Config(), start_receipt=fake)
