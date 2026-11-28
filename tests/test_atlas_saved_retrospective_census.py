"""Generated native v1 Factory/Scanner files. This suite has no source access."""
import json
from pathlib import Path

import pytest

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, build_experiment, digest, read_experiment, register_experiment,
)
from tools.atlas_saved_retrospective_census import STEP, read_saved_census


@pytest.fixture
def native(tmp_path):
    path = tmp_path / "factory.sqlite"
    receipt_path = tmp_path / "scanner-census.json"
    experiment = build_experiment(
        experiment_id="FIRST-CYCLE-294", lane="SCANNER",
        source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT", source_sha256="a" * 64,
        source_query_245_sha256="b" * 64, source_query_253_sha256="c" * 64,
        strategy_definition_sha256="d" * 64, config_sha256="e" * 64, code_sha256="f" * 64,
        environment_sha256="1" * 64, parent_receipt_sha256="2" * 64,
        attempts=[dict(attempt_id="attempt294", candidate_id="sma3_8", state="NOT_VERIFIED",
                       source_receipt_sha256="2" * 64)], evidence_class="RETROSPECTIVE_NON_PIT")
    register_experiment(path, experiment)
    rows = [dict(open_ms=i * STEP, decision_cutoff_ms=(i + 1) * STEP,
                 source_row_sha256="3" * 64, known_at_ms=None,
                 availability="RETROSPECTIVE_NON_PIT", strategy_sha256="d" * 64,
                 state="UNKNOWN" if i else "ENTRY_SIGNAL", features_sha256=None)
            for i in range(2)]
    receipt = dict(schema="aql.first-cycle.scanner-census-receipt.v1",
                   decision_census_sha256=digest(rows), plan_sha256="4" * 64,
                   source_sha256="a" * 64, source_class="SIMULATED_ADAPTER_TEST", rights={},
                   availability="RETROSPECTIVE_NON_PIT", known_at_status="UNKNOWN",
                   core_receipt_id=None, core_link_status="SOURCE_BLOCKED", strategy_sha256="d" * 64,
                   config_sha256="e" * 64, candidate_id="sma3_8", candidate_package_sha256="2" * 64,
                   attempt_id="attempt294", factory_experiment_id="FIRST-CYCLE-294",
                   factory_experiment_sha256=experiment["sha256"], result_store_sha256="5" * 64,
                   decisions=rows)
    return path, receipt_path, receipt, experiment["sha256"]


def evaluate(native):
    path, receipt_path, receipt, experiment_pin = native
    receipt_path.write_bytes(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return read_saved_census(receipt_path, path, receipt_pin=digest(receipt), experiment_pin=experiment_pin)


def test_readonly_saved_roundtrip(native):
    path, _, _, _ = native
    db_before = path.read_bytes()
    report = evaluate(native)
    assert report == evaluate(native)
    assert report["counts"] == {"ENTRY_SIGNAL": 1, "UNKNOWN": 1}
    assert report["core"] == "SOURCE_BLOCKED" and report["known_at"] == "UNKNOWN"
    assert report["secretary"] == "WAIT" and report["orders"] == 0 and report["dispatch"] is None
    assert path.read_bytes() == db_before


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("source_sha256", "9" * 64, "CENSUS_FACTORY_PARENT"),
    ("attempt_id", "substituted", "CENSUS_ATTEMPT_PARENT"),
    ("core_receipt_id", "unsupported", "CENSUS_SCOPE"),
])
def test_foreign_parent_or_authority_fails_even_with_new_receipt_pin(native, field, value, reason):
    native[2][field] = value
    with pytest.raises(ValueError, match=reason):
        evaluate(native)


def test_out_of_order_rows_fail_even_with_new_census_pin(native):
    receipt = native[2]
    receipt["decisions"].reverse()
    receipt["decision_census_sha256"] = digest(receipt["decisions"])
    with pytest.raises(ValueError, match="CENSUS_ORDER_OR_AUTHORITY"):
        evaluate(native)


def test_invalid_snapshot_has_no_reader_side_effects(native, tmp_path):
    path = native[0]
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(ResultsStoreError, match="STORE_PATH"):
        read_experiment(missing, "FIRST-CYCLE-294")
    assert not missing.exists()
    journal = Path(str(path) + "-journal")
    journal.write_bytes(b"fixture incomplete rollback")
    with pytest.raises(ResultsStoreError, match="SNAPSHOT_JOURNAL_NOT_CHECKPOINTED"):
        evaluate(native)
