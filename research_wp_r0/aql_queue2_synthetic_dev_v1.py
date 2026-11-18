"""Native synthetic DEV source-to-paired-report integration for Queue 2.

The accepted Core D fixture supplies the only supported source. Validation and
holdout windows are reserved, never evaluated. Opportunity dispositions are
predeclared engineering fixtures, with no inferred strategy performance.
"""
from dataclasses import asdict
from pathlib import Path
import json
import platform

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    _check_seal, audit_store_layout, build_experiment, digest,
    read_experiment, register_experiment,
)
from research_wp_r0.aql_factory_h_research_package_v1 import _store_package
from research_wp_r0.aql_p2_core_producer import (
    BAR_MS, EMBARGO_MIN_MS, FrozenTrialV1, HistoricalBarV1,
    HistoricalSourceV1, P2HistoricalOpportunityV1, schedule_pair,
)
from research_wp_r0.aql_p2_factory_lab import HORIZONS, build_lab
from research_wp_r0.frozen_research_plan import (
    commit_research_plan, verify_research_plan,
)
from tools.scanner_strategy_d.core_query_adapter import _project

SCHEMA = "aql.queue2.synthetic-dev-package.v1"
EXPERIMENT = "QUEUE2-SYNTHETIC-PAIRED-DEV-v1"
ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ((16, "NO_SIGNAL"), (32, "REJECTED"), (64, "UNKNOWN"))


def require(condition, reason):
    if not condition:
        raise ValueError("QUEUE2_" + reason)


def code_identity():
    paths = (
        "research_wp_r0/aql_queue2_synthetic_dev_v1.py",
        "research_wp_r0/aql_p2_core_producer.py",
        "research_wp_r0/aql_p2_factory_lab.py",
        "research_wp_r0/frozen_research_plan.py",
        "research_wp_r0/aql_factory_e_research_results_store_v1.py",
        "research_wp_r0/aql_factory_h_research_package_v1.py",
        "research_wp_r0/aql_core_d_permitted_cohort_v1.py",
        "tools/scanner_strategy_d/core_query_adapter.py",
    )
    return digest({p: digest((ROOT / p).read_text(encoding="utf-8")) for p in paths})


def evaluate_cohort(core_root, cohort):
    """Verify actual Core reads before computing any descriptive report."""
    receipt = cohort["receipt"]
    _check_seal(receipt, "cohort_sha256")
    require(receipt["cohort_evidence_class"] == "SYNTHETIC_TEST_ONLY_NOT_PUBLISHER"
            and receipt["source_kind"] == "GENERATED_NATIVE_FORMAT_ZIP_NOT_AUTHENTIC_MARKET"
            and receipt["symbol"] == "AAA" and receipt["source_bars"] == 256,
            "SYNTHETIC_SOURCE_SCOPE")
    warehouse, native, local, mapping, witness = (
        cohort[k] for k in ("warehouse", "native", "local", "mapping", "witness")
    )
    require(receipt["source_zip_sha256"] == warehouse["source_zip_sha256"]
            and receipt["warehouse_receipt_sha256"] == warehouse["receipt_sha256"]
            and receipt["core_245_price_query_sha256"] == native["price_query_sha256"]
            and receipt["core_253_query_local_sha256"] == local["query_sha256"]
            and receipt["core_d_witness_sha256"] == witness["sha256"],
            "COHORT_PARENT_DRIFT")
    raw, _, _, projection = _project(
        core_root, warehouse, native, local, mapping, witness,
    )
    rows = json.loads(raw)["rows"]
    # Reserve disjoint later folds. This fixture evaluates development only.
    train_end = warehouse["end_exclusive_ms"]
    validation_start = train_end + EMBARGO_MIN_MS
    validation_end = validation_start + 96 * BAR_MS
    splits = {
        "train": [warehouse["start_ms"], train_end],
        "validation": [validation_start, validation_end],
        "holdout": [validation_end + EMBARGO_MIN_MS,
                    validation_end + EMBARGO_MIN_MS + 96 * BAR_MS],
        "embargo_ms": EMBARGO_MIN_MS,
        "validation_status": "RESERVED_UNEVALUATED",
        "holdout_status": "SEALED_UNOPENED",
    }
    definitions = {
        "BASE": digest({"fixture": "descriptive-base-v1"}),
        "SHADOW": digest({"fixture": "descriptive-shadow-v1"}),
    }
    trial = FrozenTrialV1.seal(
        trial_id=EXPERIMENT, hypothesis_sha256=digest(list(DECISIONS)),
        base_definition_sha256=definitions["BASE"],
        shadow_definition_sha256=definitions["SHADOW"],
        preregistration_sha256=digest({"decisions": DECISIONS, "splits": splits}),
        train_end_exclusive_ms=train_end,
        holdout_start_ms=splits["holdout"][0],
        holdout_end_exclusive_ms=splits["holdout"][1],
    )
    source = HistoricalSourceV1(
        source_id=warehouse["dataset_id"], exchange="SYNTHETIC", market="FIXTURE",
        symbol="AAA", source_package_sha256=warehouse["source_zip_sha256"],
        manifest_sha256=warehouse["manifest_integrity_sha256"],
        normalized_sha256=projection.data["scanner_raw_sha256"],
        correction_generation="fixture_v1",
    )
    plan_raw, plan_sha = commit_research_plan(
        "QUEUE2_SYNTHETIC_DEV", list(definitions.items()),
        protocol_digest=trial.protocol_sha256,
        dataset_digest=digest(asdict(source)), split_digest=digest(splits),
        baseline_digest=definitions["BASE"],
        metrics=["coverage_4h", "coverage_24h", "coverage_72h"],
        selection_rule={"rule": "PREDECLARED_ALL_ARMS_NO_WINNER"},
        cost_model={"scope": "DESCRIPTIVE_NO_FILLS_OR_PNL"},
    )
    plan = verify_research_plan(plan_raw, plan_sha)
    bars = tuple(HistoricalBarV1(
        open_ms=row["open_ms"], close_ms=row["close_ms"],
        content_sha256=digest(row), available_at_ms=row["available_ms"],
        availability_evidence_ref=witness["sha256"],
    ) for row in rows)
    opportunities = []
    for count, disposition in DECISIONS:
        cutoff = rows[count - 1]["close_ms"] + 1
        opportunities.append(P2HistoricalOpportunityV1(
            trial_id=trial.trial_id, opportunity_id="fixture-" + str(count),
            producer_event_id="synthetic-disposition-" + str(count),
            source_id=source.source_id, source_package_sha256=source.source_package_sha256,
            feature_prefix_sha256=digest([asdict(b) for b in bars[:count]]),
            policy_sha256=trial.hypothesis_sha256,
            decision_cutoff_ms=cutoff, decision_ms=cutoff,
            disposition=disposition, direction=None, direction_evidence_ref=None,
            regime=None, regime_source_sha256=None,
            reason_code="PREDECLARED_SYNTHETIC_DISPOSITION",
        ))
    schedule = schedule_pair(trial, source, bars, opportunities, test_only=True)
    observations = []
    for pair in schedule["pairs"]:
        cutoff = pair["opportunity"]["decision_cutoff_ms"]
        for horizon in HORIZONS:
            end = cutoff + horizon * 3_600_000
            complete = end <= train_end
            window = [r for r in rows if cutoff <= r["open_ms"] < end]
            reference = next(r["close"] for r in rows if r["close_ms"] + 1 == cutoff)
            metrics = None
            if complete:
                require(len(window) == horizon * 4, "OUTCOME_SOURCE_GAP")
                metrics = {"reference_price": reference,
                           "observed_high": max(r["high"] for r in window),
                           "observed_low": min(r["low"] for r in window)}
            for arm in ("BASE", "SHADOW"):
                observations.append({
                    "pair_id": pair["pair_id"], "arm": arm, "horizon_hours": horizon,
                    "availability": "COMPLETE" if complete else "CENSORED",
                    "availability_reason": None if complete else "SOURCE_WINDOW_END",
                    "market_metrics": metrics, "directional_metrics": None,
                    "execution_status": "NOT_OBSERVED",
                })
    lab = build_lab(schedule, observations)
    body = {
        "schema": SCHEMA, "experiment_id": EXPERIMENT,
        "source_class": "SYNTHETIC_FIXTURE_ONLY", "historical_pit": "NOT_ATTESTED",
        "cohort_receipt": receipt, "source_projection_sha256": projection.sha256,
        "plan": plan, "plan_sha256": plan_sha, "splits": splits,
        "schedule": schedule, "observations": observations, "lab": lab,
        "code_sha256": code_identity(), "trading_authority": "NONE",
        "environment": {"python_version": platform.python_version(),
                        "implementation": platform.python_implementation()},
        "strategy_secretary_state": "NOT_ENQUEUED", "factory_consumer_ack": None,
        "orders_created": 0, "paper_positions": 0, "dispatches": 0,
        "actual_fills": None, "winner": None,
    }
    return {**body, "sha256": digest(body)}


def run_synthetic_dev(core_root, cohort, store_path):
    """Persist one immutable package, then register its sealed readback identity.

    Both existing store operations are idempotent. A failed registration leaves
    an isolated immutable package that the same input can safely finish on retry.
    Invalid source inputs are rejected before opening the results store.
    """
    package = evaluate_cohort(core_root, cohort)
    require(audit_store_layout(store_path)["layout_version"] == 2, "EXISTING_STORE_V2")
    source = package["cohort_receipt"]
    attempts = [{"attempt_id": p["pair_id"], "candidate_id": p["opportunity"]["opportunity_id"],
                 "state": "NOT_VERIFIED", "source_receipt_sha256": source["cohort_sha256"]}
                for p in package["schedule"]["pairs"]]
    record = build_experiment(
        experiment_id=EXPERIMENT, lane="HISTORICAL_SOURCE",
        source_status="SYNTHETIC_ENGINEERING_PASS",
        source_sha256=source["source_zip_sha256"],
        source_query_245_sha256=source["core_245_price_query_sha256"],
        source_query_253_sha256=source["core_253_query_local_sha256"],
        strategy_definition_sha256=package["schedule"]["protocol"]["base_definition_sha256"],
        config_sha256=package["plan_sha256"], code_sha256=package["code_sha256"],
        environment_sha256=digest(package["environment"]),
        parent_receipt_sha256=source["cohort_sha256"], attempts=attempts,
        lab_receipt_sha256=package["lab"]["artifact_sha256"], result_sha256=package["sha256"],
    )
    body = {k: v for k, v in package.items() if k != "sha256"}
    package_sha, status = _store_package(store_path, body)
    require(package_sha == package["sha256"], "PACKAGE_SEAL_DRIFT")
    register_experiment(store_path, record)
    require(read_experiment(store_path, EXPERIMENT) == record, "EXPERIMENT_READBACK")
    result = {"schema": "aql.queue2.synthetic-dev-receipt.v1",
              "package_sha256": package_sha, "experiment_sha256": record["sha256"],
              "lab_sha256": package["lab"]["artifact_sha256"], "store_status": status,
              "source_class": package["source_class"], "trading_authority": "NONE"}
    return {**result, "sha256": digest(result)}
