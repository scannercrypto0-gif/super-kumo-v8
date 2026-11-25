"""Bounded, explicit-input EARLY_OBSERVATION snapshot builder.

Consumes at most one history report, one optional sealed Registry snapshot,
one Daily health export, one Work-1 live report, and one previous snapshot.
It never searches directories, opens SQLite/raw archives, launches processes,
or changes source lanes. This profile is distinct from strict full-watchdog mode.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import time

import atlas_ops_watchdog as watchdog

PROFILE = "EARLY_OBSERVATION"
SCHEMA = "atlas.operator.early-observation.v1"
LANES = ("history", "daily", "live")
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 5
MAX_TOTAL_BYTES = MAX_FILE_BYTES * MAX_FILES
MAX_REFRESH_WALL_MS = 2_000
MAX_REFRESH_CPU_MS = 1_000
MIN_REFRESH_INTERVAL_MS = 300_000
MAX_PREVIOUS_AGE_MS = 1_800_000
MAX_SNAPSHOT_AGE_MS = 300_000


def require(ok, code):
    if not ok:
        raise ValueError(code)


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def read_bounded(path):
    """Read one caller-pinned regular file with identity and byte bounds."""
    given = Path(path)
    require(".." not in given.parts, "PATH_TRAVERSAL_DENIED")
    target = given.absolute()
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            st = item.lstat()
            require(not stat.S_ISLNK(st.st_mode)
                    and not (getattr(st, "st_file_attributes", 0) & 1024),
                    "INPUT_LINK_DENIED")
    before = target.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "INPUT_FILE_REQUIRED")
    require(0 < before.st_size <= MAX_FILE_BYTES, "INPUT_BUDGET_EXCEEDED")
    with target.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                and _identity(opened) == _identity(before), "INPUT_REPLACED")
        raw = stream.read(MAX_FILE_BYTES + 1)
    after = target.lstat()
    require(len(raw) == before.st_size and len(raw) <= MAX_FILE_BYTES
            and _identity(after) == _identity(before), "INPUT_REPLACED")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=watchdog.unique_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("JSON_NONFINITE")))
    require(type(value) is dict, "INPUT_OBJECT_REQUIRED")
    return value, watchdog.digest(raw), len(raw)


def _load(path):
    if path is None:
        return {"doc": None, "pin": None, "bytes": 0, "reason": "INPUT_NOT_SUPPLIED",
                "attempted": False}
    try:
        doc, pin, size = read_bounded(path)
    except ValueError as exc:
        if str(exc) in {"INPUT_BUDGET_EXCEEDED", "INPUT_REPLACED"}:
            raise
        return {"doc": None, "pin": None, "bytes": MAX_FILE_BYTES,
                "reason": "INPUT_UNTRUSTED", "attempted": True}
    except OSError:
        return {"doc": None, "pin": None, "bytes": MAX_FILE_BYTES,
                "reason": "INPUT_UNAVAILABLE", "attempted": True}
    return {"doc": doc, "pin": pin, "bytes": size, "reason": None, "attempted": True}


def _age_state(observed, now):
    if type(observed) is not int or observed < 0:
        return "UNKNOWN", "SOURCE_TIME_MISSING", None
    if observed > now:
        return "UNKNOWN", "SOURCE_TIME_IN_FUTURE", None
    age = now - observed
    if age > MAX_SNAPSHOT_AGE_MS:
        return "STALE", "SOURCE_REPORT_EXPIRED", age
    return None, None, age


def _input_meta(item, schema, observed):
    return {"present": item["doc"] is not None, "schema": schema,
            "file_sha256": item["pin"], "observed_at_ms": observed,
            "freshness_limit_ms": MAX_SNAPSHOT_AGE_MS, "reason": item["reason"]}


def _unknown(name, reason, item=None, schema=None, observed=None):
    item = item or {"doc": None, "pin": None, "reason": "INPUT_NOT_SUPPLIED"}
    return {"lane": name, "status": "UNKNOWN", "reason": reason,
            "observed_at_ms": observed, "source_schema": schema,
            "source_file_sha256": item["pin"], "freshness": "UNKNOWN",
            "age_ms": None, "progress_cursor": {}, "reported": {},
            "evidence_grade": "EARLY_OBSERVATION_UNVERIFIED"}


def _prior(snapshot, lane):
    lanes = snapshot.get("lanes", {}) if type(snapshot) is dict else {}
    value = lanes.get(lane) if type(lanes) is dict else None
    return value if type(value) is dict else None


def _history(item, registry_item, previous, now, clock_ok):
    doc = item["doc"]
    if doc is None:
        return _unknown("history", item["reason"], item)
    try:
        view = watchdog.history_view(doc)
        schema = doc.get("schema")
        require(schema in {"aql.warehouse.full-history-checkpoint.v1",
                           "aql.warehouse.full-history-continuation.v1"},
                "HISTORY_SCHEMA_INVALID")
        observed = next((doc.get(k) for k in
                         ("finished_ms", "observed_at_ms", "as_of_ms", "updated_at_ms")
                         if type(doc.get(k)) is int), None)
        state, reason, age = _age_state(observed, now)
        cursor = dict(view.get("counters", {}))
        registry = registry_item["doc"]
        reg_view = None
        if registry is not None:
            reg_view = watchdog.registry_view(registry)
            reg_age = registry.get("as_of_ms")
            rstate, _, _ = _age_state(reg_age, now)
            if rstate is not None:
                state, reason = rstate, "REGISTRY_REPORT_STALE_OR_UNTRUSTED"
            cursor.update(registry_event_watermark=reg_view["counters"]["event_watermark"],
                          physical_rows=reg_view["counters"]["physical_rows"],
                          source_count=reg_view["counters"]["source_count"],
                          last_open_ms=reg_view["counters"]["last_open_ms"],
                          registry_gaps=reg_view["gaps"],
                          registry_unavailable=reg_view["unavailable"],
                          registry_conflicts=reg_view["conflicts"])
        else:
            state, reason = "UNKNOWN", "REGISTRY_REPORT_NOT_SUPPLIED"
        if state is None:
            if reg_view and (reg_view["gaps"] or reg_view["unavailable"] or reg_view["conflicts"]
                             or reg_view["counters"]["source_count"] == 0):
                state, reason = "STALE", "REGISTRY_INCOMPLETE_OR_CONFLICTED"
            elif view.get("status") == "FULL_HISTORY_BLOCKED_EXACT_SOURCE":
                state, reason = "FAILED", "HISTORY_SOURCE_OR_IMPORT_FAILURE"
            elif view.get("unresolved_gaps", 0) or view.get("obstacles", 0):
                state, reason = "STALE", "HISTORY_GAPS_OR_OBSTACLES"
            elif view.get("status") in {"WAIT_FOR_SOURCE", "SOURCE_WAIT"}:
                next_check = doc.get("next_check_ms")
                state, reason = (("EXPECTED_WAIT", "HISTORY_SOURCE_WAIT")
                                 if type(next_check) is int and next_check >= now
                                 else ("UNKNOWN", "HISTORY_WAIT_CADENCE_UNVERIFIED"))
            else:
                old = _prior(previous, "history")
                old_cursor = old.get("progress_cursor", {}) if old else {}
                source_identity = view.get("continuation_ref_sha256")
                same_source = old and old.get("source_identity") == source_identity
                advanced = same_source and any(type(cursor.get(k)) is int and
                    cursor[k] > old_cursor.get(k, -1) for k in cursor if type(old_cursor.get(k)) is int)
                if advanced and clock_ok:
                    state, reason = "HEALTHY_PROGRESS", "COMMITTED_HISTORY_COUNTER_ADVANCED"
                else:
                    state, reason = "UNKNOWN", "SECOND_OBSERVATION_OR_SOURCE_LINK_REQUIRED"
        report = {"status": view.get("status"), "counters": cursor,
                  "unresolved_gaps": view.get("unresolved_gaps", 0),
                  "source_obstacles": view.get("obstacles", 0),
                  "registry_snapshot_sha256": reg_view["snapshot_sha256"] if reg_view else None}
        return {"lane": "history", "status": state, "reason": reason,
                "observed_at_ms": observed, "source_schema": schema,
                "source_file_sha256": item["pin"], "freshness": "FRESH" if age is not None and age <= MAX_SNAPSHOT_AGE_MS else state,
                "age_ms": age, "progress_cursor": cursor,
                "source_identity": view.get("continuation_ref_sha256"),
                "reported": report, "evidence_grade": "OWNER_SUPPLIED_SEALED_REPORT_NOT_RECONCILED"}
    except Exception:
        return _unknown("history", "HISTORY_EVIDENCE_UNTRUSTED", item,
                        doc.get("schema"), doc.get("finished_ms"))


def _daily(item, now):
    doc = item["doc"]
    if doc is None:
        return _unknown("daily", item["reason"], item)
    observed = doc.get("observed_at_ms")
    try:
        require(doc.get("schema") == "aql.recurring-runtime.health.v1"
                and doc.get("source_cadence") == "DAILY_UTC", "DAILY_SCHEMA_INVALID")
        state, reason, age = _age_state(observed, now)
        last = doc.get("last_success") if type(doc.get("last_success")) is dict else {}
        receipt = last.get("daily_worker_receipt_sha256")
        if receipt is not None:
            require(watchdog.HEX64.fullmatch(receipt) is not None, "DAILY_RECEIPT_PIN_INVALID")
        if state is None and doc.get("last_failure") is not None:
            state, reason = "FAILED", "DAILY_WORKER_FAILURE_REPORTED"
        if state is None and doc.get("source_freshness") == "STALE":
            state, reason = "STALE", "DAILY_SOURCE_REPORTED_STALE"
        if state is None and doc.get("cycle_evidence") == "WAIT_FOR_SOURCE":
            next_check = doc.get("next_check_ms")
            state, reason = (("EXPECTED_WAIT", "DAILY_SOURCE_WAIT")
                             if type(next_check) is int and next_check >= now
                             else ("UNKNOWN", "DAILY_WAIT_CADENCE_UNVERIFIED"))
        if state is None:
            state, reason = "UNKNOWN", "DAILY_IMPORT_REGISTRY_LINK_NOT_SUPPLIED"
        return {"lane": "daily", "status": state, "reason": reason,
                "observed_at_ms": observed, "source_schema": doc["schema"],
                "source_file_sha256": item["pin"], "freshness": "FRESH" if age is not None and age <= MAX_SNAPSHOT_AGE_MS else state,
                "age_ms": age, "progress_cursor": {},
                "source_identity": None,
                "reported": {"task_state": doc.get("task_state"),
                    "scheduler_state": doc.get("scheduler_state"),
                    "runtime_state": doc.get("runtime_state"),
                    "cycle_evidence": doc.get("cycle_evidence"),
                    "source_freshness": doc.get("source_freshness"),
                    "last_success_source_day_ms": last.get("source_day_ms"),
                    "worker_receipt_sha256": receipt},
                "evidence_grade": "OWNER_SUPPLIED_DAILY_WORKER_REPORT_IMPORT_UNVERIFIED"}
    except Exception:
        return _unknown("daily", "DAILY_EVIDENCE_UNTRUSTED", item, doc.get("schema"), observed)


def _live(item, previous, now, clock_ok):
    doc = item["doc"]
    if doc is None:
        return _unknown("live", item["reason"], item)
    try:
        view = watchdog.live_view(doc)
        observed = doc.get("as_of_ms")
        state, reason, age = _age_state(observed, now)
        config = doc.get("config_sha256")
        policy = doc.get("policy_sha256")
        identity = (config, policy) if watchdog.HEX64.fullmatch(config or "") and watchdog.HEX64.fullmatch(policy or "") else None
        cursor = {"last_committed_ms": view.get("last_committed_ms"),
                  "verified_receipts": view.get("verified_receipts"),
                  "last_receipt_sha256": view.get("last_receipt_sha256")}
        if state is None and (doc.get("hold_reason") or doc.get("status") in {"HELD", "HOLD"}):
            state, reason = "HELD", "LIVE_EXPLICIT_HOLD"
        if state is None and doc.get("status") in {"FAILED", "WS_OPERATOR_BLOCKED"}:
            state, reason = "FAILED", "LIVE_REPORT_FAILURE"
        if state is None and view.get("last_receipt_fresh") is False:
            state, reason = "STALE", "LIVE_LAST_RECEIPT_STALE"
        if state is None and doc.get("status") == "AWAITING_EXISTING_SCHEDULE":
            state, reason = "EXPECTED_WAIT", "LIVE_EXISTING_SCHEDULE_WAIT"
        if state is None:
            old = _prior(previous, "live")
            old_cursor = old.get("progress_cursor", {}) if old else {}
            same_source = old and identity is not None and old.get("source_identity") == list(identity)
            advanced = (same_source and type(cursor["last_committed_ms"]) is int
                        and type(old_cursor.get("last_committed_ms")) is int
                        and cursor["last_committed_ms"] > old_cursor["last_committed_ms"]
                        and cursor["verified_receipts"] >= old_cursor.get("verified_receipts", 0)
                        and cursor["last_receipt_sha256"] != old_cursor.get("last_receipt_sha256"))
            if advanced and clock_ok:
                state, reason = "HEALTHY_PROGRESS", "LIVE_COMMITTED_RECEIPT_ADVANCED"
            else:
                state, reason = "UNKNOWN", "SECOND_OBSERVATION_OR_SESSION_LINK_REQUIRED"
        return {"lane": "live", "status": state, "reason": reason,
                "observed_at_ms": observed, "source_schema": doc["schema"],
                "source_file_sha256": item["pin"], "freshness": "FRESH" if age is not None and age <= MAX_SNAPSHOT_AGE_MS else state,
                "age_ms": age, "progress_cursor": cursor,
                "source_identity": list(identity) if identity else None,
                "reported": {"source_class": doc.get("source_class"), "status": doc.get("status"),
                    "verified_receipts": view.get("verified_receipts"),
                    "last_committed_ms": view.get("last_committed_ms"),
                    "last_receipt_fresh": view.get("last_receipt_fresh"),
                    "missing_ranges": view.get("missing_ranges"),
                    "hold_reason": watchdog.safe_reason(doc.get("hold_reason")) if doc.get("hold_reason") else None},
                "evidence_grade": "OWNER_SUPPLIED_LIVE_REPORT_NOT_HOST_ATTESTED"}
    except Exception:
        return _unknown("live", "LIVE_EVIDENCE_UNTRUSTED", item, doc.get("schema"), doc.get("as_of_ms"))


def _overall(lanes):
    states = {lane["status"] for lane in lanes.values()}
    if "FAILED" in states:
        return "FAILED"
    if "HELD" in states:
        return "HELD"
    if "STALE" in states:
        return "STALE"
    if "UNKNOWN" in states:
        return "UNKNOWN"
    if "HEALTHY_PROGRESS" in states:
        return "HEALTHY_PROGRESS"
    return "EXPECTED_WAIT"


def build(paths, *, now_ms, monotonic_ns, boot_id, clock_uncertainty_ms,
          previous=None, started_ns=None, cpu_started_ns=None):
    started_ns = started_ns if started_ns is not None else time.perf_counter_ns()
    cpu_started_ns = cpu_started_ns if cpu_started_ns is not None else time.process_time_ns()
    loaded = {name: _load(paths.get(name)) for name in ("history", "registry", "daily", "live")}
    prev_item = _load(paths.get("previous")) if paths.get("previous") is not None else None
    total = sum(item["bytes"] for item in loaded.values())
    if prev_item:
        total += prev_item["bytes"]
    count = sum(item.get("attempted", item["doc"] is not None) for item in loaded.values()) + bool(prev_item and prev_item.get("attempted", True))
    require(count <= MAX_FILES and total <= MAX_TOTAL_BYTES, "INPUT_BUDGET_EXCEEDED")
    candidate = previous if previous is not None else (prev_item["doc"] if prev_item else None)
    if candidate is not None:
        try:
            watchdog.sealed_hash(candidate, "sha256", "PREVIOUS_SEAL_INVALID")
            require(candidate.get("schema") == SCHEMA and candidate.get("profile") == PROFILE,
                    "PREVIOUS_SCHEMA_INVALID")
            require(candidate.get("host_boot_id") == boot_id
                    and type(candidate.get("observed_monotonic_ns")) is int
                    and monotonic_ns >= candidate["observed_monotonic_ns"],
                    "PREVIOUS_CLOCK_INVALID")
            age = now_ms - candidate.get("observed_at_ms", now_ms + 1)
            require(age >= MIN_REFRESH_INTERVAL_MS, "REFRESH_INTERVAL_NOT_ELAPSED")
            previous = candidate if age <= MAX_PREVIOUS_AGE_MS else None
        except ValueError as exc:
            if str(exc) == "REFRESH_INTERVAL_NOT_ELAPSED":
                raise
            previous = None
        except Exception:
            previous = None
    clock_ok = type(clock_uncertainty_ms) is int and 0 <= clock_uncertainty_ms <= 5_000
    lanes = {
        "history": _history(loaded["history"], loaded["registry"], previous, now_ms, clock_ok),
        "daily": _daily(loaded["daily"], now_ms),
        "live": _live(loaded["live"], previous, now_ms, clock_ok),
    }
    # An untrusted wall clock cannot establish fresh progress or schedule waits.
    if not clock_ok:
        for lane in lanes.values():
            if lane["status"] in {"HEALTHY_PROGRESS", "EXPECTED_WAIT"}:
                lane.update(status="UNKNOWN", reason="CLOCK_QUALITY_UNVERIFIED")
    elapsed_ms = (time.perf_counter_ns() - started_ns) // 1_000_000
    cpu_ms = (time.process_time_ns() - cpu_started_ns) // 1_000_000
    require(elapsed_ms <= MAX_REFRESH_WALL_MS and cpu_ms <= MAX_REFRESH_CPU_MS,
            "REFRESH_RESOURCE_BUDGET_EXCEEDED")
    body = {"schema": SCHEMA, "profile": PROFILE, "version": 1,
        "observed_at_ms": now_ms, "observed_monotonic_ns": monotonic_ns,
        "host_boot_id": boot_id, "clock_uncertainty_ms": clock_uncertainty_ms,
        "state": _overall(lanes), "lanes": lanes,
        "inputs": {name: {"present": item["doc"] is not None,
                          "file_sha256": item["pin"], "bytes": item["bytes"],
                          "reason": item["reason"]}
                   for name, item in loaded.items()},
        "limits": {"max_explicit_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES,
                   "max_total_bytes": MAX_TOTAL_BYTES, "max_refresh_wall_ms": MAX_REFRESH_WALL_MS,
                   "max_refresh_cpu_ms": MAX_REFRESH_CPU_MS,
                   "minimum_refresh_interval_ms": MIN_REFRESH_INTERVAL_MS},
        "measurements": {"input_files": count, "input_bytes": total,
                         "refresh_wall_ms": elapsed_ms, "refresh_cpu_ms": cpu_ms},
        "source_paths_exposed": False, "raw_market_payload_included": False,
        "network_calls": 0, "source_mutations": 0, "trading_authority": "NONE"}
    return {**body, "sha256": watchdog.digest(watchdog.canonical(body))}


def publish(path, snapshot):
    given = Path(path)
    require(".." not in given.parts, "OUTPUT_PATH_TRAVERSAL")
    target = given.absolute()
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            st = item.lstat()
            require(not stat.S_ISLNK(st.st_mode)
                    and not (getattr(st, "st_file_attributes", 0) & 1024),
                    "OUTPUT_PATH_LINK_DENIED")
    require(target.parent.is_dir() and not target.exists(), "OUTPUT_CREATE_ONLY_PATH_REQUIRED")
    raw = watchdog.canonical(snapshot)
    require(len(raw) <= MAX_FILE_BYTES, "OUTPUT_BUDGET_EXCEEDED")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return watchdog.digest(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for lane in LANES:
        parser.add_argument("--" + lane, type=Path, help="One explicit sanitized report file; never a directory.")
    parser.add_argument("--registry", type=Path, help="One existing sealed Registry snapshot; no revalidation scan.")
    parser.add_argument("--previous", type=Path, help="One prior early snapshot for bounded two-observation comparison.")
    parser.add_argument("--output", required=True, type=Path, help="New local output path; create-only.")
    parser.add_argument("--clock-uncertainty-ms", type=int)
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in (*LANES, "registry", "previous")}
    now_ms = time.time_ns() // 1_000_000
    mono = time.monotonic_ns()
    result = build(paths, now_ms=now_ms, monotonic_ns=mono,
                   boot_id=watchdog.host_boot_id(),
                   clock_uncertainty_ms=args.clock_uncertainty_ms)
    pin = publish(args.output, result)
    print(json.dumps({"result": "EARLY_OBSERVATION_SNAPSHOT_CREATED",
                      "profile": PROFILE, "snapshot_sha256": result["sha256"],
                      "file_sha256": pin, "status": result["state"],
                      "measurements": result["measurements"]}, sort_keys=True))


if __name__ == "__main__":
    main()
