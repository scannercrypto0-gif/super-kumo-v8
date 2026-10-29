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
