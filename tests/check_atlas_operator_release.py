"""Offline cross-platform acceptance of only the joined operator read path."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from aql.observation.contracts import digest
from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
from tools.atlas_operator_readback import publish
from tools.research_capacity_scale.runtime import catalog, store


def sealed(body):
    return {**body, "sha256": digest(body)}


def inputs(root):
    # Synthetic totals exercise the production contract without shipping saved owner data.
    definition = dict(strategy_id="fixture_sma3_12", strategy_version="v1", scope="RESEARCH_ONLY",
                      risk={"stop_fraction": "0.01"})
    strategy = digest(definition)
    counts = {"MODEL_ONLY": 2570, "UNKNOWN_END_OF_DATA": 7684, "UNKNOWN_FILL": 5127}
    cells = {
        f"TRAIN/CANDIDATE/TAKER/{policy}": dict(
            statuses={status: count}, expected=count, known_subset_gross="4" if policy == "A" else None,
            known_subset_net="3" if policy == "A" else None, known_subset_cost="1" if policy == "A" else None)
        for policy, (status, count) in zip("ABC", counts.items())
    }
    report = sealed(dict(
        grade="EXPLORATORY_STRATEGY_SLICE_PASS", evidence="OWNER_LOCAL_RETAINED_MODEL",
        strategy={"definition": definition, "digest": strategy}, strategy_sha256=strategy,
        source=[{"name": "GENERATED_FIXTURE"}], plan_sha256="1" * 64, result_file_sha256="2" * 64,
        factory_store_file_sha256="3" * 64, experiment_sha256="4" * 64, modeled_package_sha256="5" * 64,
        utc_split_ms=[0, 86400000, 172800000, 432000000, 518400000],
        populations={"cost_rows": sum(counts.values())}, outcome_counts=counts, cells=cells,
        cost_assumptions={"TAKER": {"fee_entry_bps": "10"}}, orders=0, actual_fills=None,
        secretary="WAIT", current_entry="NO_CURRENT_ENTRY", holdout="SEALED_UNOPENED",
        lab="NOT_ELIGIBLE_FOR_SCIENTIFIC_PIT_OOS",
    ))
    preflight = sealed(dict(schema="aql.scientific-promotion.preflight.v1",
                            scientific_status="REAL_PIT_OOS_BLOCKED", collection="NOT_ACTIVATED",
                            holdout="SEALED_UNOPENED", trading_authority="NONE", state_changed=False,
                            plan_sha256="6" * 64, independent_attestation="SKIPPED_BY_OWNER"))
    health = dict(schema="aql.recurring-runtime.health.v1", source_mode="TEST_ONLY",
                  market_feed_health="NOT_MEASURED", trading_authority="NONE", current_entry="NO_CURRENT_ENTRY",
                  observed_at_ms=100000, freshness_limit_ms=90000, tick_age_ms=1000,
                  cycle_evidence="RECENT_RESEARCH_RECEIPT", last_success={"receipts": ["7" * 64]},
                  last_failure={"reason": "RUNTIME_PIN_MISMATCH"})
    for name, value in (("strategy", report), ("health", health), ("preflight", preflight)):
        publish(root / (name + ".json"), value)
    checkpoint = root / "batch.sqlite"
    migrate_store_v2(checkpoint)
    pins = dict(plan_pin=report["plan_sha256"], result_file_pin=report["result_file_sha256"],
                store_file_pin=report["factory_store_file_sha256"], strategy_pin=strategy)
    task = digest(dict(input_pins=pins, report_sha256=report["sha256"]))
    store(checkpoint, dict(experiment_id="PLAN", schema="aql.saved-strategy.batch1.scope.v1",
                           task_sha256=task, report_sha256=report["sha256"]))
    store(checkpoint, dict(experiment_id="SAVED-" + task, schema="aql.saved-strategy.batch1.v1",
                           task_sha256=task, input_pins=pins, status="SUCCEEDED",
                           trading_authority="NONE", report=report))
    return report, health, preflight


def accept(root):
    report, health, preflight = inputs(root)
    inputs_on_disk = list(root.iterdir())
    before = {path.name: path.read_bytes() for path in inputs_on_disk}
    command = [sys.executable, "-B", "-m", "tools.atlas_operator_report",
               "--strategy", str(root / "strategy.json"), "--strategy-sha256", report["sha256"],
               "--health", str(root / "health.json"), "--health-sha256",
               sha256(before["health.json"]).hexdigest(),
               "--preflight", str(root / "preflight.json"), "--preflight-sha256", preflight["sha256"],
               "--batch-checkpoint", str(root / "batch.sqlite"), "--checkpoint", str(root / "operations.sqlite"),
               "--output", str(root / "output.json"), "--as-of-ms", "200000"]

    def invoke(changes=(), expected=None):
        cmd = command.copy()
        for flag, value in changes:
            cmd[cmd.index(flag) + 1] = str(value)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if expected:
            assert result.returncode != 0 and expected in result.stderr, result.stderr
        else:
            assert result.returncode == 0, result.stderr
        return result

    assert invoke().stdout == invoke().stdout
    result = json.loads((root / "output.json").read_bytes())
    assert result["strategy"]["accounting_cells"] == report["cells"]
    assert result["strategy"]["evidence_counts"] == report["outcome_counts"]
    assert result["strategy"]["trades"] == "NOT_AVAILABLE"
    assert result["runtime"]["cycle_evidence"] == "LAST_TICK_STALE"
    assert result["runtime"]["last_failure"]["reason"] == "RUNTIME_PIN_MISMATCH"
    assert result["scientific"]["status"] == "REAL_PIT_OOS_BLOCKED"
    assert result["secretary"] == "WAIT" and result["orders"] == 0 and result["telegram_delivery"] == "NOT_SENT"
    assert sum(key.startswith("PERFORMANCE-") for key in catalog(root / "operations.sqlite")) == 1
    invoke((("--strategy-sha256", "0" * 64),), "REPORT_PIN")
    invoke((("--health-sha256", "0" * 64),), "RUNTIME_HEALTH_PIN")
    invoke((("--preflight-sha256", "0" * 64),), "SCIENTIFIC_PREFLIGHT_PIN")
    invoke((("--batch-checkpoint", root / "absent.sqlite"),), "DETACHED_BATCH_REQUIRED")
    invoke((("--batch-checkpoint", root / "operations.sqlite"),
            ("--checkpoint", root / "other.sqlite")), "BATCH_REPORT_PARENT")
    bad = root / "bad-health.json"
    publish(bad, {**health, "schema": "aql.recurring-runtime.health.v0"})
    invoke((("--health", bad), ("--health-sha256", sha256(bad.read_bytes()).hexdigest())),
            "RUNTIME_HEALTH_CONTRACT")

    stage2 = dict(schema="atlas.stage2.saved-evidence-disposition.v1",
                  scope="PUBLISHED_SAVED_EVIDENCE_METADATA_ONLY",
                  status="STAGE2_SAVED_PARTIAL_EVIDENCE_BLOCKED",
                  scientific_status="REAL_PIT_OOS_BLOCKED",
                  secretary={"disposition": "WAIT_AUTHENTICATED_PARENTS", "dispatch": None},
                  orders=0, actual_fills=None, current_entry="NO_CURRENT_ENTRY",
                  selected=dict(retained_report_sha256=report["sha256"], strategy_sha256=report["strategy_sha256"],
                                plan_sha256=report["plan_sha256"], ordered_native_scanner_receipt_sha256=None,
                                native_core245_receipt_sha256=None, native_core253_receipt_sha256=None,
                                discoverer_membership_verified=False))
    evidence_path = root / "stage2.json"
    stage2_output = root / "stage2-output.json"
    evidence = sealed(stage2)
    publish(evidence_path, evidence)
    command.extend(("--stage2-evidence", str(evidence_path), "--stage2-evidence-sha256", evidence["sha256"]))
    output_choice = (("--output", stage2_output),)
    assert invoke(output_choice).stdout == invoke(output_choice).stdout
    joined = json.loads(stage2_output.read_bytes())
    assert joined["research_disposition"]["status"] == stage2["status"]
    assert joined["research_disposition"]["evidence_sha256"] == evidence["sha256"]
    assert joined["research_disposition"]["actionable_now"] is False
    assert joined["runtime"]["cycle_evidence"] == "LAST_TICK_STALE"
    assert joined["runtime"]["last_success"] == health["last_success"]
    assert joined["runtime"]["last_failure"] == health["last_failure"]
    assert joined["runtime"]["continuous_service"] == "NOT_ATTESTED"
    assert joined["notification_preview"]["actionable_now"] is False
    assert joined["notification_preview"]["delivery"] == "OFFLINE_PREVIEW_ONLY"
    assert joined["dispatch"] is None and joined["telegram_delivery"] == "NOT_SENT"
    previews = [row for key, row in catalog(root / "operations.sqlite").items() if key.startswith("PREVIEW-")]
    assert [row["sha256"] for row in previews] == [joined["notification_preview"]["receipt_sha256"]]

    foreign = sealed({**stage2, "selected": {**stage2["selected"], "plan_sha256": "0" * 64}})
    foreign_path = root / "foreign-stage2.json"
    publish(foreign_path, foreign)
    invoke((("--stage2-evidence", foreign_path),), "STAGE2_EVIDENCE_PIN")
    invoke((("--stage2-evidence", foreign_path), ("--stage2-evidence-sha256", foreign["sha256"])),
            "STAGE2_REPORT_PARENT")
    assert {path.name: path.read_bytes() for path in inputs_on_disk} == before
    print("SYNTHETIC_RELEASE_CONTRACT_PASS", result["sha256"])
    print("STAGE2_OPERATOR_VISIBILITY_PASS", joined["sha256"])


if __name__ == "__main__":
    with TemporaryDirectory() as folder:
        accept(Path(folder))
