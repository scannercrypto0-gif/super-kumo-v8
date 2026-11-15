"""Join pinned saved strategy operations, runtime health and scientific preflight."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_saved_research_disposition import publish, require, without_seal
from tools.atlas_strategy_operations import run as strategy_operations
from tools.research_capacity_scale.runtime import catalog, safe


def load(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "OPERATOR_INPUT_BOUND")
    return raw, json.loads(raw.decode("utf-8-sig"))


def runtime_view(path, pin, as_of_ms):
    raw, health = load(path, 65_536)
    require(sha256(raw).hexdigest() == pin, "RUNTIME_HEALTH_PIN")
    require(health["schema"] == "aql.recurring-runtime.health.v1"
            and health["source_mode"] in {"TEST_ONLY", "AUTHORIZED_RETAINED_ARCHIVE"}
            and health["market_feed_health"] == "NOT_MEASURED"
            and health["trading_authority"] == "NONE"
            and health["current_entry"] == "NO_CURRENT_ENTRY", "RUNTIME_HEALTH_CONTRACT")
    observed, limit, tick_age = (health[key] for key in (
        "observed_at_ms", "freshness_limit_ms", "tick_age_ms"))
    require(type(observed) is type(as_of_ms) is int and 0 <= observed <= as_of_ms
            and (limit is None or (type(limit) is int and 0 < limit <= 3_630_000))
            and (tick_age is None or (type(tick_age) is int and tick_age >= 0)),
            "RUNTIME_CLOCK")
    snapshot_age = as_of_ms - observed
    age = None if tick_age is None else tick_age + snapshot_age
    freshness = "NOT_AVAILABLE" if age is None or limit is None else "STALE" if age > limit else "RECENT"
    state = health["cycle_evidence"]
    if state == "RECENT_RESEARCH_RECEIPT" and freshness != "RECENT":
        state = "LAST_TICK_STALE" if freshness == "STALE" else "CADENCE_UNVERIFIED"
    return {**health, "cycle_evidence": state, "tick_freshness": freshness,
            "tick_age_at_report_ms": age, "snapshot_age_ms": snapshot_age, "health_file_sha256": pin}


def batch_parent(strategy, strategy_pin, checkpoint):
    _, report = load(strategy, 5_000_000)
    require(report.get("sha256") == strategy_pin == without_seal(report), "REPORT_PIN")
    require(checkpoint.is_file() and checkpoint.stat().st_size <= 32 * 1024**2
            and all(not sidecar.exists() or sidecar.stat().st_size == 0
                    for sidecar in (Path(str(checkpoint) + suffix) for suffix in ("-wal", "-journal"))),
            "DETACHED_BATCH_REQUIRED")
    with TemporaryDirectory() as folder:
        staged = Path(folder) / "batch.sqlite"
        shutil.copyfile(checkpoint, staged)
        records = catalog(staged)
    pins = {pin: report[key] for pin, key in (
        ("plan_pin", "plan_sha256"), ("result_file_pin", "result_file_sha256"),
        ("store_file_pin", "factory_store_file_sha256"), ("strategy_pin", "strategy_sha256"))}
    task = digest(dict(input_pins=pins, report_sha256=strategy_pin))
    scope = records.get("PLAN", {})
    item = records.get("SAVED-" + task, {})
    require(len(records) == 2 and scope.get("schema") == "aql.saved-strategy.batch1.scope.v1"
            and scope.get("task_sha256") == task and scope.get("report_sha256") == strategy_pin
            and item.get("schema") == "aql.saved-strategy.batch1.v1"
            and item.get("task_sha256") == task and item.get("input_pins") == pins
            and item.get("status") == "SUCCEEDED" and item.get("trading_authority") == "NONE"
            and item.get("report") == report, "BATCH_REPORT_PARENT")
    return item["sha256"]


def build(strategy, strategy_pin, health, health_pin, preflight, preflight_pin, checkpoint, output, as_of_ms,
          *, batch_checkpoint):
    strategy, health, preflight, checkpoint, output, batch_checkpoint = map(
        safe, (strategy, health, preflight, checkpoint, output, batch_checkpoint))
    require(len({strategy, health, preflight, checkpoint, output, batch_checkpoint}) == 6, "OPERATOR_PATH_SCOPE")
    runtime = runtime_view(health, health_pin, as_of_ms)
    _, science = load(preflight, 65_536)
    require(science.get("sha256") == preflight_pin == without_seal(science), "SCIENTIFIC_PREFLIGHT_PIN")
    require(science["schema"] == "aql.scientific-promotion.preflight.v1"
            and science["scientific_status"] == "REAL_PIT_OOS_BLOCKED"
            and science["collection"] == "NOT_ACTIVATED" and science["holdout"] == "SEALED_UNOPENED"
            and science["trading_authority"] == "NONE" and science["state_changed"] is False,
            "SCIENTIFIC_PREFLIGHT_CONTRACT")
    batch_pin = batch_parent(strategy, strategy_pin, batch_checkpoint)
    operations, _ = strategy_operations(strategy, strategy_pin, checkpoint, None)
    rows = [row for row in operations["strategies"] if row["source_report_sha256"] == strategy_pin]
    require(len(rows) == 1, "STRATEGY_OPERATIONS_PARENT")
    body = dict(schema="aql.operator-report.v1", as_of_ms=as_of_ms, strategy=rows[0],
                batch_result_sha256=batch_pin, strategy_operations_sha256=operations["sha256"], runtime=runtime,
                scientific={"preflight_sha256": preflight_pin, "future_plan_sha256": science["plan_sha256"],
                            "status": science["scientific_status"], "holdout": science["holdout"],
                            "independent_attestation": science["independent_attestation"]},
                secretary="WAIT", dispatch=None, current_entry="NO_CURRENT_ENTRY",
                trading_authority="NONE", orders=0, telegram_delivery="NOT_SENT")
    report = {**body, "sha256": digest(body)}
    publish(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("strategy", "health", "preflight", "batch-checkpoint", "checkpoint", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("strategy", "health", "preflight"):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--as-of-ms", type=int, required=True)
    args = parser.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        report = build(args.strategy, args.strategy_sha256, args.health, args.health_sha256,
                       args.preflight, args.preflight_sha256, args.checkpoint, args.output, args.as_of_ms,
                       batch_checkpoint=args.batch_checkpoint)
    print(report["sha256"])


if __name__ == "__main__":
    main()
