"""Focused synthetic-only local result retention; no original source or study."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import pytest

from research_wp_r0.historical_dev_exits_v1 import (
    Config, digest, replay_contract_fixture,
)
from research_wp_r0.dev_result_bundle import persist_bundle, verify_bundle


def receipt(with_terminal=False):
    rows = [
        {"open_ms": i * 60000, "close_ms": (i + 1) * 60000 - 1,
         "open": 100., "high": 101., "low": 99., "close": 100.,
         "volume": 1., "available_ms": (i + 1) * 60000 + 1000,
         "modeled_quote": True}
        for i in range(22)
    ]
    src = {"version": "synthetic", "reference": "fixture:localbundle",
           "archive_sha256": "a" * 64, "rows_sha256": digest(rows),
           "availability_evidence": "UNKNOWN",
           "correction_evidence": "PINNED_VERSION_ONLY"}
    signals = ([{"bar_open_ms": rows[-1]["open_ms"],
                 "action": "ENTER_LONG",
                 "available_ms": rows[-1]["available_ms"]}]
               if with_terminal else [])
    return replay_contract_fixture(
        rows, source=src, signals=signals, config=Config())


def evidence(result=None):
    result = receipt() if result is None else result
    return {
        "policy_id": "DEV-B0-v1",
        "policy_sha256": digest({"policy_id": "DEV-B0-v1", "engine_config": result["config"]}),
        "source_zip_sha256": result["source"]["archive_sha256"],
        "issued_receipt_sha256": "3" * 64,
        "code_sha": "a" * 40,
        "input_prefix_sha256": digest(result["input_rows"]),
        "scenario_id": "S00",
        "warmup_bars": 22,
        "experiment_id": "AQL-DEV-FIRST-01",
    }


def test_local_roundtrip_and_nonoverwrite():
    with TemporaryDirectory() as d:
        manifest = persist_bundle(d, run_id="run-001",
                                  receipt=receipt(), evidence=evidence())
        assert manifest["state"] == "COMPLETE_LOCAL_COPY_NOT_IMMUTABLE_CUSTODY"
        assert verify_bundle(d, "run-001")
        with pytest.raises(FileExistsError):
            persist_bundle(d, run_id="run-001",
                           receipt=receipt(), evidence=evidence())


def test_corrupted_data_fails_closed():
    with TemporaryDirectory() as d:
        persist_bundle(d, run_id="run-a", receipt=receipt(),
                       evidence=evidence())
        f = Path(d) / "run-a" / "receipt.json"
        data = json.loads(f.read_text())
        data["claims"]["actual_fills"] = True
        f.write_text(json.dumps(data))
        assert verify_bundle(d, "run-a") is False


def test_invalid_path_and_commitments_are_denied():
    with TemporaryDirectory() as d:
        with pytest.raises(ValueError):
            persist_bundle(d, run_id="../bad", receipt=receipt(), evidence=evidence())
        e = evidence()
        e["source_zip_sha256"] = "UNPINNED"
        with pytest.raises(ValueError, match="BAD_SHA"):
            persist_bundle(d, run_id="run", receipt=receipt(), evidence=e)
        assert not (Path(d) / "run").exists()


def test_terminal_unknown_remains_null_and_in_denominator():
    with TemporaryDirectory() as d:
        out = receipt(with_terminal=True)
        assert out["paths"]["FACTUAL"]["status"] == "UNKNOWN_UNRESOLVED"
        manifest = persist_bundle(d, run_id="unknown-1",
                                  receipt=out, evidence=evidence(out))
        assert manifest["files"]["receipt.json"]["bytes"] > 0
        assert verify_bundle(d, "unknown-1")
        saved = json.loads((Path(d) / "unknown-1" / "receipt.json").read_text())
        path = saved["paths"]["FACTUAL"]
        assert path["scheduled_denominator"] == 1
        assert path["realized_pnl"] is None
        assert path["modeled_equity_return"] is None


@pytest.mark.parametrize("field,value,error", [
    ("source_zip_sha256", "f"*64, "SOURCE_ARCHIVE_SHA_MISMATCH"),
    ("input_prefix_sha256", "f"*64, "INPUT_PREFIX_SHA_MISMATCH"),
    ("policy_sha256", "f"*64, "POLICY_CONFIG_SHA_MISMATCH"),
    ("warmup_bars", 252, "WARMUP_CONFIG_MISMATCH"),
])
def test_well_formed_but_wrong_claim_is_refused(field, value, error):
    with TemporaryDirectory() as d:
        e = evidence()
        e[field] = value
        with pytest.raises(ValueError, match=error):
            persist_bundle(d, run_id="mismatch", receipt=receipt(), evidence=e)
        assert not (Path(d) / "mismatch").exists()


def test_resolvable_synthetic_trade_result_is_saved_without_nulling_scored_pnl(tmp_path):
    rows = []
    for i in range(24):
        t = i * 60000
        px = 100.0 + i
        rows.append({"open_ms": t, "close_ms": t + 59999,
                     "open": px, "high": px + 1, "low": px - 1,
                     "close": px, "volume": 1.0,
                     "available_ms": t + 61000, "modeled_quote": True})
    source = {"version": "synthetic", "reference": "fixture:resolved-trade",
              "archive_sha256": "b" * 64, "rows_sha256": digest(rows),
              "availability_evidence": "UNKNOWN",
              "correction_evidence": "PINNED_VERSION_ONLY"}
    signals = [
        {"bar_open_ms": rows[20]["open_ms"], "action": "ENTER_LONG",
         "available_ms": rows[20]["available_ms"]},
        {"bar_open_ms": rows[21]["open_ms"], "action": "EXIT_LONG",
         "available_ms": rows[21]["available_ms"]},
    ]
    result = replay_contract_fixture(rows, source=source, signals=signals,
                                     config=Config())
    factual = result["paths"]["FACTUAL"]
    assert factual["status"] == "SETTLED_MODELED"
    assert factual["realized_pnl"] is not None
    assert factual["realized_pnl"] > 0
    e = {"policy_id": "DEV-B0-v1",
         "policy_sha256": digest({"policy_id": "DEV-B0-v1",
                                  "engine_config": result["config"]}),
         "source_zip_sha256": source["archive_sha256"],
         "issued_receipt_sha256": "5" * 64, "code_sha": "a" * 40,
         "input_prefix_sha256": digest(result["input_rows"]),
         "scenario_id": "S00", "warmup_bars": 22,
         "experiment_id": "AQL-SYNTHETIC-RESOLVED-01"}
    persist_bundle(str(tmp_path), run_id="resolved-run", receipt=result, evidence=e)
    assert verify_bundle(str(tmp_path), "resolved-run")
    saved = json.loads((tmp_path / "resolved-run" / "receipt.json").read_text())
    assert saved["paths"]["FACTUAL"]["realized_pnl"] == factual["realized_pnl"]
    assert saved["paths"]["FACTUAL"]["scheduled_denominator"] == 2


# Production orchestration bypass-resistance regressions are included in this
# already-required cross-platform CI target.
from research_wp_r0 import factory_b0_study_runner as _b0_runner


def _b0_runner_files(tmp_path):
    archive = tmp_path / "market.zip"
    receipt_file = tmp_path / "issued-receipt.json"
    store = tmp_path / "store"
    archive.write_bytes(b"fixture archive bytes")
    receipt_file.write_bytes(b"fixture receipt bytes")
    store.mkdir()
    return archive, receipt_file, store


def test_b0_orchestrator_admission_failure_stops_all_downstream_work(tmp_path, monkeypatch):
    archive, receipt_file, store = _b0_runner_files(tmp_path)
    calls = []
    def denied(**kwargs):
        calls.append("admission")
        raise PermissionError("denied")
    monkeypatch.setattr(_b0_runner, "admit_one_study_run", denied)
    monkeypatch.setattr(_b0_runner, "authorize_factory_execution", lambda *a: calls.append("start"))
    monkeypatch.setattr(_b0_runner, "replay_after_factory_start", lambda *a, **kw: calls.append("replay"))
    monkeypatch.setattr(_b0_runner, "persist_bundle", lambda *a, **kw: calls.append("persist"))
    with pytest.raises(PermissionError):
        _b0_runner.run_authorized_b0_study(
            permit={}, archive_path=archive, issued_receipt_path=receipt_file,
            result_store=store, experiment_id="AQL-DEV-FIRST-01")
    assert calls == ["admission"]


def test_b0_orchestrator_start_failure_stops_replay_and_persistence(tmp_path, monkeypatch):
    archive, receipt_file, store = _b0_runner_files(tmp_path)
    calls = []
    monkeypatch.setattr(_b0_runner, "admit_one_study_run",
                        lambda **kw: {"admission_record_path": "signed.json"})
    def denied(path):
        calls.append(("start", path))
        raise PermissionError("start denied")
    monkeypatch.setattr(_b0_runner, "authorize_factory_execution", denied)
    monkeypatch.setattr(_b0_runner, "replay_after_factory_start", lambda *a, **kw: calls.append("replay"))
    monkeypatch.setattr(_b0_runner, "persist_bundle", lambda *a, **kw: calls.append("persist"))
    with pytest.raises(PermissionError):
        _b0_runner.run_authorized_b0_study(
            permit={}, archive_path=archive, issued_receipt_path=receipt_file,
            result_store=store, experiment_id="AQL-DEV-FIRST-01")
    assert calls == [("start", "signed.json")]


def test_direct_original_pair_replay_is_denied():
    from research_wp_r0.historical_dev_exits_v1 import replay, Config
    with pytest.raises(PermissionError, match="PRODUCTION_REPLAY_REQUIRES_FACTORY_START_RECEIPT"):
        replay([], source={"version": "original-local-pair-v1"}, config=Config())


def test_b0_production_replay_requires_real_start_marker(tmp_path):
    from research_wp_r0.historical_dev_exits_v1 import replay_after_factory_start, Config
    fake = {
        "schema": "aql-owner-admission-start-v1",
        "max_runs": 1,
        "start_record_path": str(tmp_path / "missing.started"),
        "start_record_sha256": "a" * 64,
    }
    with pytest.raises(PermissionError, match="FACTORY_START_MARKER_UNREADABLE"):
        replay_after_factory_start(
            [], source={"version": "original-local-pair-v1"},
            config=Config(), start_receipt=fake)
