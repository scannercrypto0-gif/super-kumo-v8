"""New producer/consumer boundaries, failed publication retry and sealed readback."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from research_wp_r0 import aql_queue2_synthetic_dev_v1 as dev
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest, migrate_store_v2,
)
from tools.atlas_factory_pkg02_execution_smoke import fixture_packet
from research_wp_r0.aql_factory_h_execution_comparison_v1 import (
    evaluate_execution_exit_comparison,
)


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    if sys.platform == "win32":
        pytest.skip("RAW fixture uses POSIX flock; Windows runs sealed native readback in CI")
    from research_wp_r0.aql_core_d_permitted_cohort_v1 import create_permitted_synthetic_cohort
    root = tmp_path_factory.mktemp("queue2-source")
    specs = json.loads((dev.ROOT / "tools/strategy_service_offline/fixtures/strategies.json").read_text())
    result = create_permitted_synthetic_cohort(root / "core", root / "vault", specs, count=256)
    return root / "core", result


def test_source_to_paired_report_preserves_real_core_parents_and_reserved_folds(cohort):
    root, source = cohort
    package = dev.evaluate_cohort(root, source)
    assert package == dev.evaluate_cohort(root, source)
    assert package["source_class"] == "SYNTHETIC_FIXTURE_ONLY"
    assert package["lab"]["observation_slots"] == 18
    assert package["lab"]["market_coverage_by_horizon"]["72"]["CENSORED"] == 3
    assert package["schedule"]["source"]["source_package_sha256"] == source["receipt"]["source_zip_sha256"]
    splits = package["splits"]
    assert splits["train"][1] + splits["embargo_ms"] <= splits["validation"][0]
    assert splits["validation"][1] + splits["embargo_ms"] <= splits["holdout"][0]
    assert package["lab"]["fills_pnl_alpha"] == "NOT_COMPUTED"
    assert package["factory_consumer_ack"] is None
    assert package["orders_created"] == package["paper_positions"] == package["dispatches"] == 0


@pytest.mark.parametrize("change", ["original_scope", "source_sha", "query_sha"])
def test_invalid_source_rejected_before_creating_results_store(cohort, tmp_path, change):
    root, source = cohort
    bad = deepcopy(source)
    if change == "original_scope":
        bad["receipt"]["cohort_evidence_class"] = "ORIGINAL_MARKET"
    elif change == "source_sha":
        bad["receipt"]["source_zip_sha256"] = "0" * 64
    else:
        bad["local"]["query_sha256"] = "0" * 64
    bad["receipt"]["cohort_sha256"] = digest({
        k: v for k, v in bad["receipt"].items() if k != "cohort_sha256"
    })
    path = tmp_path / "must-not-exist.sqlite"
    with pytest.raises(ValueError):
        dev.run_synthetic_dev(root, bad, path)
    assert not path.exists()


def test_failed_registration_can_resume_same_immutable_package(cohort, tmp_path, monkeypatch):
    root, source = cohort
    path = tmp_path / "results.sqlite"
    migrate_store_v2(path)
    original = dev.register_experiment

    def interrupted(*args):
        raise RuntimeError("simulated interruption before registry publication")

    monkeypatch.setattr(dev, "register_experiment", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        dev.run_synthetic_dev(root, source, path)
    monkeypatch.setattr(dev, "register_experiment", original)
    resumed = dev.run_synthetic_dev(root, source, path)
    assert resumed["store_status"] == "REPLAY_IDENTICAL"
    assert resumed == dev.run_synthetic_dev(root, source, path)


def test_resealed_execution_input_rejects_stale_source_batch_parent():
    packet = fixture_packet()
    packet["scanner_entry_batch_sha256"] = "0" * 64
    packet["sha256"] = digest({k: v for k, v in packet.items() if k != "sha256"})
    with pytest.raises(ValueError, match="ENTRY_BATCH_PARENT_DRIFT"):
        evaluate_execution_exit_comparison(packet)
