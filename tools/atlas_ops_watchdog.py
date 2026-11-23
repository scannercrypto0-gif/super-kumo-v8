"""Read-only, bounded ATLAS operations snapshot builder.

The watchdog consumes already-produced, sanitized lane reports. It never opens
market archives, executes acquisition code, queries the network, or mutates a
source lane. Missing evidence is reported as UNKNOWN.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

MAX_INPUT_BYTES = 8 * 1024 * 1024
STATES = {"HEALTHY_PROGRESS", "EXPECTED_WAIT", "SLOW_BUT_PROGRESSING", "STALLED",
          "HOLD", "FAILED", "COMPLETE_WITH_GAPS", "COMPLETE_VERIFIED", "UNKNOWN"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read_json(path: str | Path) -> tuple[dict, str]:
    target = Path(path).absolute()
    require(".." not in Path(path).parts, "PATH_TRAVERSAL_DENIED")
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            st = item.lstat()
            require(not item.is_symlink() and not getattr(st, "st_file_attributes", 0) & 1024,
                    "PATH_LINK_DENIED")
    require(target.is_file() and target.stat().st_nlink == 1, "INPUT_FILE_REQUIRED")
    require(target.stat().st_size <= MAX_INPUT_BYTES, "INPUT_BOUND")
    raw = target.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("JSON_NONFINITE")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INPUT_JSON_INVALID") from exc
    require(type(value) is dict, "INPUT_OBJECT_REQUIRED")
    return value, digest(raw)


def sealed_hash(doc: dict, field: str, code: str) -> None:
    body = {key: value for key, value in doc.items() if key != field}
    require(type(doc.get(field)) is str and doc[field] == digest(canonical(body)), code)


def registry_view(doc: dict) -> dict:
    sealed_hash(doc, "snapshot_sha256", "REGISTRY_SNAPSHOT_SEAL")
    require(doc.get("schema") == "aql.warehouse.registry-snapshot.v1"
            and doc.get("trading_authority") == "NONE"
            and doc.get("source_class") == "RETROSPECTIVE_NON_PIT", "REGISTRY_CONTRACT")
    for key in ("event_watermark", "physical_rows"):
        require(type(doc.get(key)) is int and doc[key] >= 0, "REGISTRY_COUNTER")
    sources = doc.get("sources")
    gaps = doc.get("internal_gaps")
    unavailable = doc.get("archive_unavailable_boundaries")
    conflicts = doc.get("conflicts")
    require(type(sources) is list and type(gaps) is list and type(unavailable) is list
            and type(conflicts) is list, "REGISTRY_COVERAGE_CONTRACT")
    require(all(type(row) is dict and HEX64.fullmatch(row.get("source_zip_sha256", ""))
                and HEX64.fullmatch(row.get("source_receipt_sha256", ""))
                and type(row.get("rows")) is int and row["rows"] >= 0 for row in sources),
            "REGISTRY_SOURCE_IDENTITY")
    counters = dict(event_watermark=doc["event_watermark"], physical_rows=doc["physical_rows"],
                    source_count=len(sources), last_open_ms=doc.get("last_open_ms"),
                    event_head_sha256=doc.get("event_head_sha256"))
    return dict(counters=counters, gaps=len(gaps), unavailable=len(unavailable),
                conflicts=len(conflicts), source_receipts=[row["source_receipt_sha256"] for row in sources[-4:]],
                snapshot_sha256=doc["snapshot_sha256"])


def history_view(doc: dict) -> dict:
    schema = doc.get("schema")
    require(schema in {"aql.warehouse.full-history-continuation.v1",
                       "aql.warehouse.full-history-checkpoint.v1"}
            and doc.get("trading_authority") == "NONE", "HISTORY_CONTRACT")
    if schema == "aql.warehouse.full-history-checkpoint.v1":
        require(doc.get("source_class") == "RETROSPECTIVE_NON_PIT"
                and type(doc.get("full_history_verified")) is bool
                and type(doc.get("accepted_prefix_unchanged")) is bool,
                "HISTORY_CHECKPOINT_CONTRACT")
        for key in ("archives_this_run", "inserted_rows_this_run"):
            require(type(doc.get(key)) is int and doc[key] >= 0, "HISTORY_COUNTER")
        return dict(status="CHECKPOINT_UNVERIFIED" if not doc["full_history_verified"]
                    else "CHECKPOINT_FULL_HISTORY_FLAGGED",
                    counters=dict(archives_imported=doc["archives_this_run"],
                                  inserted_rows=doc["inserted_rows_this_run"],
                                  full_history_verified=doc["full_history_verified"],
                                  accepted_prefix_unchanged=doc["accepted_prefix_unchanged"]),
                    unresolved_gaps=0, obstacles=0, started_ms=None, finished_ms=None,
                    continuation_ref_sha256=digest(str(doc.get("continuation_ref", "")).encode("utf-8")))
    require(doc.get("full_history_verified") is False, "HISTORY_CONTRACT")
    for key in ("started_ms", "finished_ms"):
        require(type(doc.get(key)) is int and doc[key] >= 0, "HISTORY_CLOCK")
    require(doc["finished_ms"] >= doc["started_ms"], "HISTORY_CLOCK_ORDER")
    counters = dict(archives_imported=doc.get("archives_imported"),
                    inserted_rows=doc.get("inserted_rows"),
                    all_published_partitions_ingested=doc.get("all_published_partitions_ingested"),
                    source_scan_exhausted=doc.get("source_scan_exhausted"),
                    latest_published_close_reached=doc.get("latest_published_close_reached"))
    return dict(status=doc.get("status"), counters=counters,
                unresolved_gaps=len(doc.get("unresolved_gap_ranges", [])),
                obstacles=len(doc.get("unresolved_source_obstacles", [])),
                started_ms=doc["started_ms"], finished_ms=doc["finished_ms"])


def daily_view(doc: dict, import_receipt: dict, source_receipt: dict,
               registry: dict, import_pin: str) -> dict:
    require(doc.get("schema") == "aql.recurring-runtime.health.v1"
            and doc.get("trading_authority") == "NONE"
            and doc.get("current_entry") == "NO_CURRENT_ENTRY", "DAILY_CONTRACT")
    observed = doc.get("observed_at_ms")
    require(type(observed) is int and observed >= 0, "DAILY_CLOCK")
    success = doc.get("last_success")
    imports = import_receipt.get("this_run") if type(import_receipt) is dict else None
    source_body = {key: value for key, value in source_receipt.items() if key != "receipt_sha256"} \
        if type(source_receipt) is dict else {}
    source_pin = source_receipt.get("source_zip_sha256") if type(source_receipt) is dict else None
    source_seal_ok = (type(source_pin) is str and HEX64.fullmatch(source_pin)
                      and source_receipt.get("receipt_sha256") == digest(canonical(source_body))
                      and source_receipt.get("publisher_integrity") == "ZIP_CHECKSUM_MATCH"
                      and type(source_receipt.get("checksum_sha256")) is str
                      and HEX64.fullmatch(source_receipt["checksum_sha256"]))
    if type(imports) is list:
        run_rows = [row for row in imports if type(row) is dict and row.get("status") == "ARCHIVE_IMPORTED"]
    elif type(import_receipt) is dict and import_receipt.get("status") == "ARCHIVE_IMPORTED":
        run_rows = [import_receipt]
    else:
        run_rows = []
    latest = run_rows[-1] if run_rows else None
    registry_link = any(row.get("source_zip_sha256") == source_pin
                        and row.get("source_receipt_sha256") == source_receipt.get("receipt_sha256")
                        for row in registry.get("sources", []))
    report_contract = (import_receipt.get("schema") == "aql.research.warehouse-report.v1"
                       or import_receipt.get("status") == "ARCHIVE_IMPORTED")
    receipt_link = (success.get("warehouse_receipt_sha256") == import_pin
                    if type(success) is dict and success.get("warehouse_receipt_sha256") is not None
                    else import_receipt.get("schema") == "aql.research.warehouse-report.v1")
    health_source_link = (type(success) is dict
                          and success.get("source_zip_sha256") == source_pin
                          and success.get("checksum_sha256") == source_receipt.get("checksum_sha256"))
    linked = bool(report_contract
                  and type(latest) is dict and latest.get("source_sha256") == source_pin
                  and latest.get("key") == source_receipt.get("key") and source_seal_ok
                  and registry_link and type(success) is dict
                  and type(success.get("source_day_ms")) is int and receipt_link and health_source_link)
    last_success = None
    if linked:
        last_success = dict(source_day_ms=success["source_day_ms"], source_zip_sha256=source_pin,
                            checksum_sha256=source_receipt["checksum_sha256"],
                            warehouse_receipt_sha256=source_receipt["receipt_sha256"],
                            source_rows=source_receipt.get("rows"), inserted_rows=latest.get("inserted_rows"))
    return dict(observed_at_ms=observed, cycle_evidence=doc.get("cycle_evidence"),
                tick_freshness=doc.get("tick_freshness"), source_freshness=doc.get("source_freshness"),
                last_success=last_success, source_receipt_link_verified=linked,
                next_check_ms=doc.get("next_check_ms"), last_failure=doc.get("last_failure"))


def live_view(doc: dict) -> dict:
    require(doc.get("schema") == "atlas.ws.continuous-report.v1"
            and doc.get("source_class") == "LIVE_CAPTURE"
            and doc.get("trading_authority") == "NONE" and doc.get("orders") == 0,
            "LIVE_CONTRACT")
    for key in ("as_of_ms", "verified_receipts"):
        require(type(doc.get(key)) is int and doc[key] >= 0, "LIVE_COUNTER")
    last = doc.get("last_committed_ms")
    require(last is None or (type(last) is int and 0 <= last <= doc["as_of_ms"]), "LIVE_CURSOR")
    receipts = doc.get("verified_receipt_sha256")
    require(type(receipts) is list and all(type(x) is str and HEX64.fullmatch(x) for x in receipts),
            "LIVE_RECEIPT_LIST")
    return dict(status=doc.get("status"), as_of_ms=doc["as_of_ms"],
                verified_receipts=doc["verified_receipts"], last_committed_ms=last,
                last_receipt_fresh=doc.get("last_receipt_fresh"),
                missing_ranges=len(doc.get("missing_open_ranges", [])),
                hold_reason=doc.get("hold_reason"), last_receipt_sha256=receipts[-1] if receipts else None)


def host_boot_id() -> str:
    """Stable, local boot identity without spawning a process or touching the network."""
    if os.name == "nt":
        uptime_ms = int(ctypes.windll.kernel32.GetTickCount64())
        estimated_boot_minute = (time.time_ns() // 1_000_000 - uptime_ms) // 60_000
        return "windows-boot-minute:" + str(estimated_boot_minute)
    boot_file = Path("/proc/sys/kernel/random/boot_id")
    if boot_file.is_file() and not boot_file.is_symlink():
        value = boot_file.read_text(encoding="ascii").strip().lower()
        require(bool(re.fullmatch(r"[0-9a-f-]{36}", value)), "BOOT_ID_INVALID")
        return "linux:" + value
    raise ValueError("HOST_BOOT_ID_UNAVAILABLE")


def lane_status(name: str, current: dict, previous: dict | None, now_ms: int,
                clock_uncertainty_ms: int | None, stall_after_ms: int) -> tuple[str, str]:
    if name == "live" and current.get("hold_reason"):
        return "HOLD", "EXPLICIT_LIVE_HOLD"
    if name == "history" and current.get("status") == "FULL_HISTORY_BLOCKED_EXACT_SOURCE":
        return "FAILED", "SOURCE_OR_IMPORT_FAILURE"
    if name == "history" and (current.get("obstacles", 0) or current.get("unresolved_gaps", 0)):
        return "COMPLETE_WITH_GAPS", "SOURCE_OBSTACLES_OR_GAPS_REMAIN"
    if previous is None:
        return "UNKNOWN", "BASELINE_REQUIRED"
    changed = current.get("fingerprint") != previous.get("fingerprint")
    if changed:
        return "HEALTHY_PROGRESS", "DURABLE_EVIDENCE_ADVANCED"
    if clock_uncertainty_ms is None or clock_uncertainty_ms > 5_000:
        return "UNKNOWN", "CLOCK_QUALITY_UNVERIFIED"
    since = previous.get("last_progress_at_ms")
    if type(since) is int and now_ms - since > stall_after_ms:
        eligible = current.get("eligible_work_pending") is True
        return ("STALLED", "ELIGIBLE_WORK_WITHOUT_DURABLE_PROGRESS") if eligible else (
            "EXPECTED_WAIT", "NO_PUBLISHED_OR_ELIGIBLE_WORK")
    if current.get("wait") is True:
        return "EXPECTED_WAIT", "SOURCE_OR_SCHEDULE_WAIT"
    if current.get("validating") is True:
        return "SLOW_BUT_PROGRESSING", "ARCHIVE_VALIDATION_HEARTBEAT_ONLY"
    return "UNKNOWN", "NO_SECOND_OBSERVATION_OR_PROGRESS_PROOF"


def build(registry: dict, history: dict, daily: dict, daily_import: dict,
          daily_source: dict, live: dict, *,
          registry_pin: str, history_pin: str, daily_pin: str, daily_import_pin: str,
          daily_source_pin: str, live_pin: str,
          now_ms: int, monotonic_ns: int, boot_id: str, deployed_sha: str,
          clock_uncertainty_ms: int | None, previous: dict | None = None,
          stall_after_ms: int = 1_800_000) -> dict:
    require(type(now_ms) is int and now_ms >= 0 and type(monotonic_ns) is int and monotonic_ns >= 0,
            "CLOCK_INPUT")
    require(type(boot_id) is str and 1 <= len(boot_id) <= 128, "BOOT_ID_REQUIRED")
    require(HEX40.fullmatch(deployed_sha), "DEPLOYED_SHA_REQUIRED")
    require(all(HEX64.fullmatch(pin) for pin in (registry_pin, history_pin, daily_pin,
                                                 daily_import_pin, daily_source_pin, live_pin)),
            "INPUT_PIN_REQUIRED")
    if clock_uncertainty_ms is not None:
        require(type(clock_uncertainty_ms) is int and 0 <= clock_uncertainty_ms <= 60_000,
                "CLOCK_UNCERTAINTY")
    if previous is not None:
        sealed_hash(previous, "sha256", "PREVIOUS_SNAPSHOT_SEAL")
        require(previous.get("schema") == "atlas.operator.health-snapshot.v1"
                and previous.get("host_boot_id") == boot_id, "PREVIOUS_SNAPSHOT_HOST")
        require(type(previous.get("observed_monotonic_ns")) is int
                and monotonic_ns >= previous["observed_monotonic_ns"], "MONOTONIC_CLOCK_RESET")

    rg, hi = registry_view(registry), history_view(history)
    dy = daily_view(daily, daily_import, daily_source, registry, daily_import_pin)
    lv = live_view(live)
    fingerprints = {
        "history": digest(canonical([rg["counters"], hi["counters"]])),
        "daily": digest(canonical([dy.get("last_success"), dy.get("cycle_evidence")])),
        "live": digest(canonical([lv["verified_receipts"], lv["last_committed_ms"], lv["last_receipt_sha256"]])),
    }
    progress_starts = {}
    lanes = {}
    for name, view in (("history", hi), ("daily", dy), ("live", lv)):
        prior_lane = previous.get("lanes", {}).get(name) if previous else None
        lane = dict(view, fingerprint=fingerprints[name])
        clock_ok = clock_uncertainty_ms is not None and clock_uncertainty_ms <= 5_000
        last_progress = (now_ms if clock_ok else None) if prior_lane is None else prior_lane.get("last_progress_at_ms")
        if prior_lane and lane["fingerprint"] != prior_lane.get("fingerprint") and clock_ok:
            last_progress = now_ms
        lane["last_progress_at_ms"] = last_progress
        if name == "history":
            lane["eligible_work_pending"] = bool(hi["counters"].get("all_published_partitions_ingested") is False
                                                  and hi["counters"].get("source_scan_exhausted") is not True)
            lane["wait"] = hi["status"] in {"WAIT_FOR_SOURCE", "SOURCE_WAIT"}
            lane["validating"] = hi["status"] == "LONG_ARCHIVE_VALIDATING"
        elif name == "daily":
            lane["eligible_work_pending"] = dy["source_freshness"] == "STALE"
            lane["wait"] = dy["cycle_evidence"] == "WAIT_FOR_SOURCE"
            lane["validating"] = False
        else:
            lane["eligible_work_pending"] = lv["last_receipt_fresh"] is True
            lane["wait"] = lv["status"] == "AWAITING_EXISTING_SCHEDULE"
            lane["validating"] = False
        state, reason = lane_status(name, lane, prior_lane, now_ms,
                                    clock_uncertainty_ms, stall_after_ms)
        if name == "daily" and not dy["source_receipt_link_verified"]:
            state, reason = "UNKNOWN", "DAILY_SOURCE_LINKAGE_UNPROVEN"
        lane.update(state=state, reason=reason)
        lanes[name] = lane

    state_values = {lane["state"] for lane in lanes.values()}
    overall = "FAILED" if "FAILED" in state_values else "HOLD" if "HOLD" in state_values else (
        "STALLED" if "STALLED" in state_values else "UNKNOWN" if "UNKNOWN" in state_values else
        "HEALTHY_PROGRESS" if "HEALTHY_PROGRESS" in state_values else "EXPECTED_WAIT")
    body = dict(schema="atlas.operator.health-snapshot.v1", version=1, observed_at_ms=now_ms,
                observed_monotonic_ns=monotonic_ns, host_boot_id=boot_id,
                clock_uncertainty_ms=clock_uncertainty_ms, deployed_sha=deployed_sha,
                source_pins=dict(registry=registry_pin, history=history_pin, daily=daily_pin,
                                 daily_import=daily_import_pin, daily_source=daily_source_pin,
                                 live=live_pin),
                registry=rg, lanes=lanes, state=overall, source_paths_exposed=False,
                raw_market_payload_included=False, network_calls=0, source_mutations=0,
                trading_authority="NONE")
    return {**body, "sha256": digest(canonical(body))}


def publish(path: str | Path, snapshot: dict) -> None:
    target = Path(path).absolute()
    require(".." not in Path(path).parts, "OUTPUT_PATH_TRAVERSAL")
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            st = item.lstat()
            require(not item.is_symlink() and not getattr(st, "st_file_attributes", 0) & 1024,
                    "OUTPUT_PATH_LINK_DENIED")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(snapshot)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(tmp, target)
        except FileExistsError:
            require(target.read_bytes() == raw, "OUTPUT_ALREADY_SEALED")
    finally:
        tmp.unlink()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    evidence_names = ("registry", "history", "daily", "daily-import", "daily-source", "live")
    for name in (*evidence_names, "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--deployed-sha", required=True)
    p.add_argument("--clock-uncertainty-ms", type=int)
    p.add_argument("--previous", type=Path)
    p.add_argument("--stall-after-ms", type=int, default=1_800_000)
    args = p.parse_args()
    inputs = {name: read_json(getattr(args, name.replace("-", "_"))) for name in evidence_names}
    pins = {name: inputs[name][1] for name in inputs}
    require(Path(args.registry).name == "snapshot-" + inputs["registry"][0].get("snapshot_sha256", "") + ".json",
            "REGISTRY_FILENAME_PIN")
    require(Path(args.history).stem == pins["history"], "HISTORY_FILENAME_PIN")
    require(Path(args.daily_import).stem == pins["daily-import"], "DAILY_RECEIPT_FILENAME_PIN")
    require(Path(args.daily_source).stem == inputs["daily-source"][0].get("source_zip_sha256"),
            "DAILY_SOURCE_FILENAME_PIN")
    previous = read_json(args.previous)[0] if args.previous else None
    now_ms = time.time_ns() // 1_000_000
    mono = time.monotonic_ns()
    boot = host_boot_id()
    result = build(*(inputs[name][0] for name in evidence_names),
                   registry_pin=pins["registry"], history_pin=pins["history"],
                   daily_pin=pins["daily"], daily_import_pin=pins["daily-import"],
                   daily_source_pin=pins["daily-source"], live_pin=pins["live"], now_ms=now_ms,
                   monotonic_ns=mono, boot_id=boot, deployed_sha=args.deployed_sha,
                   clock_uncertainty_ms=args.clock_uncertainty_ms, previous=previous,
                   stall_after_ms=args.stall_after_ms)
    publish(args.output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

