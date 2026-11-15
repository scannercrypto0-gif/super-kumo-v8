"""Persist one pinned saved strategy readback using the native capacity store."""
import argparse
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aql.observation.contracts import digest
from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
from tools.actual_research_batch_bridge.bridge import BUDGET
from tools.atlas_saved_research_disposition import publish, require
from tools.atlas_saved_strategy_report import build
from tools.research_capacity_scale.resources import enforce
from tools.research_capacity_scale.runtime import catalog, safe, store


def run(root, output, checkpoint, *, saved_only, expected_report_sha256, **pins):
    require(saved_only, "SAVED_READ_AUTHORITY_REQUIRED")
    root, output, checkpoint = map(safe, (root, output, checkpoint))
    require(output != checkpoint and all(path != root and root not in path.parents
                                        for path in (output, checkpoint)), "OUTPUT_SCOPE")
    require(all(type(pin) is str and len(pin) == 64
                and all(c in "0123456789abcdef" for c in pin)
                for pin in (*pins.values(), expected_report_sha256)), "INVALID_INPUT_PIN")
    bounds = {"market-plan.json": 100_000, "result.json": 5_000_000, "factory.sqlite": BUDGET["result_bytes"],
              "scanner-census.json": 5_000_000, "candidate.json": 5_000_000,
              "native-plan.json": 5_000_000, "discoverer-ledger.json": 5_000_000}
    for name, bound in bounds.items():
        path = safe(root / name)
        require(not path.exists() or (path.is_file() and path.stat().st_size <= bound), "SAVED_INPUT_BOUND")
    task = digest(dict(input_pins=pins, report_sha256=expected_report_sha256))
    scope = dict(schema="aql.saved-strategy.batch1.scope.v1", experiment_id="PLAN",
                 task_sha256=task, report_sha256=expected_report_sha256)
    if not checkpoint.exists():
        with TemporaryDirectory(dir=checkpoint.parent) as folder:
            stage = Path(folder) / "batch.sqlite"
            migrate_store_v2(stage)
            store(stage, scope)
            try:
                os.link(stage, checkpoint)
            except FileExistsError:
                pass
    require(checkpoint.is_file() and checkpoint.stat().st_size <= BUDGET["result_bytes"], "CHECKPOINT_BOUND")
    body = dict(schema="aql.saved-strategy.batch1.v1", experiment_id="SAVED-" + task,
                task_sha256=task, input_pins=pins, trading_authority="NONE")
    docs = catalog(checkpoint)
    require(docs.get("PLAN", {}).get("task_sha256") == task
            and set(docs) <= {"PLAN", body["experiment_id"]}, "BATCH_INPUT_CONFLICT")
    prior = docs.get(body["experiment_id"])
    if prior is None:
        try:
            report = build(root, saved_only=True, **pins)
            require(report["sha256"] == expected_report_sha256, "EXPECTED_REPORT_PIN")
        except ValueError as error:
            store(checkpoint, {**body, "status": "REJECTED", "reason": str(error)[:256]})
            raise
        except Exception:
            store(checkpoint, {**body, "status": "FAILED", "reason": "NATIVE_READBACK_FAILED"})
            raise
        prior, _ = store(checkpoint, {**body, "status": "SUCCEEDED", "report": report})
    require(prior["status"] == "SUCCEEDED", f"TERMINAL_{prior['status']}")
    report = prior["report"]
    require(report["sha256"] == expected_report_sha256
            == digest({key: value for key, value in report.items() if key != "sha256"})
            and all(report[key] == pins[pin] for key, pin in (
                ("plan_sha256", "plan_pin"), ("result_file_sha256", "result_file_pin"),
                ("factory_store_file_sha256", "store_file_pin"), ("strategy_sha256", "strategy_pin"))),
            "CHECKPOINT_REPORT_PIN")
    publish(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("saved", "output", "checkpoint"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("plan", "result-file", "store-file", "strategy", "report"):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--saved-only", action="store_true")
    args = parser.parse_args()
    enforce(BUDGET, os.getppid())
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        report = run(args.saved, args.output, args.checkpoint, saved_only=args.saved_only,
                     expected_report_sha256=args.report_sha256,
                     plan_pin=args.plan_sha256, result_file_pin=args.result_file_sha256,
                     store_file_pin=args.store_file_sha256, strategy_pin=args.strategy_sha256)
    print(report["sha256"])


if __name__ == "__main__":
    main()
