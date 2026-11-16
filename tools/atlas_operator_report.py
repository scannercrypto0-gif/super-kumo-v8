"""Join pinned saved strategy operations, runtime health and scientific preflight."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import socket
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_saved_research_disposition import publish, require, without_seal
from tools.atlas_strategy_operations import run as strategy_operations
from tools.research_capacity_scale.runtime import catalog, safe


def live_windows_view(snapshot):
    """Saved-only Factory E projection, with explicit cadence and recovery evidence."""
    now = snapshot["as_of_ms"]
    previous = None
    receipts = snapshot["receipts"]
    missing = 0
    errors = []
    for receipt in receipts:
        row = receipt["observation"]
        slot = row["slot"]
        require(receipt["sha256"] == without_seal(receipt)
                and receipt["factory"]["sha256"] == without_seal(receipt["factory"])
                and receipt["retention"] == "SANITIZED_RECEIPTS_ONLY"
                and receipt["orders"] == 0 and receipt["dispatch"] is None
                and receipt["secretary"] == "WAIT" and receipt["telegram"] == "NOT_SENT",
                "LIVE_OPERATOR_RECEIPT_SCOPE")
        closed = slot + 900_000
        require(slot % 900_000 == 0 and closed - 1 <= row["event_ms"]
                <= row["received_ms"] <= row["committed_ms"] <= receipt["heartbeat_ms"] <= now,
                "LIVE_OPERATOR_RECEIPT_CLOCK")
        if previous:
            delta = slot - previous["observation"]["slot"]
            require(previous["sha256"] == receipt["previous_sha256"] and delta > 0
                    and delta // 900_000 - 1 == receipt["missing_slots"], "LIVE_OPERATOR_RECEIPT_CHAIN")
        missing += receipt["missing_slots"]
        previous = receipt
    for item in snapshot["supervisor"]:
        if item["status"] == "FAILED":
            errors.append(dict(reason=item["reason"], at=item["utc"],
                               recovery="OPERATOR_DIAGNOSIS_REQUIRED", unresolved=True))
    interruptions = [item for item in snapshot["transport"] if item["status"] == "TRANSPORT_INTERRUPTED"]
    recovered = False
    for item in interruptions:
        resumed = any(receipt["last_failure"] == {"error": item["error"], "utc_ms": item["utc_ms"]}
                      and receipt["connection_attempts"] > 1 for receipt in receipts)
        recovered |= resumed
        errors.append(dict(reason=item["error"], at=item["utc_ms"],
                           recovery="FINAL_RECEIPT_AFTER_RECONNECT" if resumed else "NO_MATCHING_FINAL_RECEIPT",
                           unresolved=not resumed))
    heartbeat = snapshot["last_heartbeat_ms"]
    started = [item["slot_ms"] for item in snapshot["supervisor"] if item["status"] == "STARTED"]
    completed = [item["slot_ms"] for item in snapshot["supervisor"] if item["status"] == "COMPLETE"]
    rollover = any(old < new and any(r["observation"]["slot"] >= new for r in receipts)
                   for old in completed for new in started)
    cadence = "RECENT" if previous and 0 <= now - (previous["observation"]["slot"] + 900_000) <= 930_000 else "STALE_OR_NO_FINAL"
    recent_heartbeat = type(heartbeat) is int and 0 <= now - heartbeat <= 95_000
    hold = snapshot["hold"]
    status = ("HELD" if hold else "STOP_REQUESTED" if snapshot["stop_requested"]
              else "ACTIVE_RESEARCH_ONLY" if snapshot["task_state"] == "Running"
              and recent_heartbeat and cadence == "RECENT" else "CHECK_SCHEDULER_OR_CADENCE")
    if status == "CHECK_SCHEDULER_OR_CADENCE":
        errors.append(dict(reason="STALE_OR_MISSING_WORKER_HEARTBEAT" if not recent_heartbeat else
                           "STALE_OR_MISSING_FINAL" if cadence != "RECENT" else "SCHEDULER_NOT_RUNNING",
                           recovery="NO_RECOVERY_AT_SNAPSHOT", unresolved=True))
    report = dict(schema="atlas.factory-e.live-windows-saved-report.v1", as_of_ms=now, status=status,
                  task_state=snapshot["task_state"], task_enabled=snapshot["task_enabled"],
                  writer_policy=snapshot["writer_policy"], last_task_result=snapshot["last_task_result"],
                  hold=hold, rollback_marker_present=snapshot["stop_requested"],
                  last_heartbeat_ms=heartbeat, final_cadence=cadence, missing_slots_in_window=missing,
                  accepted_receipts=len(receipts), latest_success=previous, errors=errors,
                  segment_rollover="ATTESTED_BY_FINAL_RECEIPT" if rollover else "NOT_YET_ATTESTED",
                  recovery="REAL_RECONNECT_ATTESTED" if recovered else "REAL_RECOVERY_NOT_ATTESTED",
                  supervisor_history=snapshot["supervisor"], daily=snapshot["daily"],
                  source_config_sha256=snapshot["config_sha256"],
                  orders=0, secretary="WAIT", dispatch=None, telegram="NOT_SENT")
    return {**report, "sha256": digest(report)}


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
    if sys.argv[1:] == ["--live-windows-saved"]:
        print(json.dumps(live_windows_view(json.load(sys.stdin)), sort_keys=True))
        return
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
