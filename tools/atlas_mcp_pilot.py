"""Local stdio-only, read-only MCP adapter for sealed ATLAS watchdog snapshots.

The adapter reads one explicitly pinned watchdog snapshot. It has no network,
process-control, scheduler, arbitrary-file, or source-lane write capability.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import atlas_ops_watchdog as watchdog

SERVER_NAME = "atlas-readonly-pilot"
SERVER_VERSION = "1.0.0"
MODERN = "2026-07-28"
LEGACY = "2025-11-25"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER = "io.modelcontextprotocol/serverInfo"
MAX_LINE_BYTES = 1_048_576
LANES = ("history", "daily", "live")
SAFE_CODE = re.compile(r"[A-Z0-9_]{1,96}\Z")
SAFE_STOP = re.compile(r"PILOT_STOP_[A-Z0-9_]{1,80}\Z")

EARLY_ENUMS = {
    "task_state": {"Ready", "Running", "Disabled", "Queued", "Unknown", "Completed"},
    "scheduler_state": {"Ready", "Running", "Disabled", "Queued", "Unknown", "Completed"},
    "runtime_state": {"PIN_VERIFIED", "CONFIG_PIN_MISMATCH", "UNVERIFIED", "UNKNOWN",
                      "ERROR", "NOT_RUNNING", "READY"},
    "cycle_evidence": {"WAIT_FOR_SOURCE", "RECENT_RESEARCH_RECEIPT", "COMPLETE", "FAILED",
                       "UNKNOWN", "NO_CURRENT_ENTRY"},
    "source_freshness": {"LATEST_DUE_DAY_RECEIVED", "STALE", "UNKNOWN",
                         "WAITING_FOR_DUE_DAY", "NOT_MEASURED", "NO_CURRENT_ENTRY"},
    "live_status": {"HELD", "HOLD", "FAILED", "WS_OPERATOR_BLOCKED",
                    "AWAITING_EXISTING_SCHEDULE", "OBSERVING_CONTINUOUS_ACCEPTANCE",
                    "OBSERVING", "HEALTHY", "STALE", "UNKNOWN"},
}
EARLY_REASON_CODES = {
    "INPUT_NOT_SUPPLIED", "INPUT_UNTRUSTED", "INPUT_UNAVAILABLE",
    "SOURCE_TIME_MISSING", "SOURCE_TIME_IN_FUTURE", "SOURCE_REPORT_EXPIRED",
    "REGISTRY_REPORT_NOT_SUPPLIED", "REGISTRY_REPORT_STALE_OR_UNTRUSTED",
    "REGISTRY_INCOMPLETE_OR_CONFLICTED", "HISTORY_SOURCE_OR_IMPORT_FAILURE",
    "HISTORY_GAPS_OR_OBSTACLES", "HISTORY_SOURCE_WAIT", "HISTORY_WAIT_CADENCE_UNVERIFIED",
    "COMMITTED_HISTORY_COUNTER_ADVANCED", "SECOND_OBSERVATION_OR_SOURCE_LINK_REQUIRED",
    "DAILY_WORKER_FAILURE_REPORTED", "DAILY_SOURCE_REPORTED_STALE", "DAILY_SOURCE_WAIT",
    "DAILY_WAIT_CADENCE_UNVERIFIED", "DAILY_IMPORT_REGISTRY_LINK_NOT_SUPPLIED",
    "LIVE_EXPLICIT_HOLD", "LIVE_REPORT_FAILURE", "LIVE_LAST_RECEIPT_STALE",
    "LIVE_EXISTING_SCHEDULE_WAIT", "LIVE_COMMITTED_RECEIPT_ADVANCED",
    "SECOND_OBSERVATION_OR_SESSION_LINK_REQUIRED", "CLOCK_QUALITY_UNVERIFIED",
    "CLOCK_OR_TIMESTAMP_UNTRUSTED", "SNAPSHOT_TTL_EXCEEDED",
}



def utc(ms):
    if type(ms) is not int or ms < 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def safe_reason(value):
    if type(value) is not str:
        return None
    if SAFE_CODE.fullmatch(value) or SAFE_STOP.fullmatch(value):
        return value
    return "REFUSAL_REDACTED"


def is_sha256(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def bounded_int(value):
    return value if type(value) is int and value >= 0 else None


def early_enum(value, key):
    allowed = EARLY_ENUMS.get(key, set())
    return value if type(value) is str and value in allowed else "UNRECOGNIZED"


def early_ranges(value):
    if type(value) is not list:
        return []
    return [pair for pair in value[:32]
            if type(pair) is list and len(pair) == 2
            and all(type(x) is int and x >= 0 for x in pair)
            and pair[0] < pair[1]]


def map_state(state, lane):
    if lane == "live" and state == "HOLD":
        return "HELD"
    return {
        "HEALTHY_PROGRESS": "HEALTHY", "COMPLETE_VERIFIED": "HEALTHY",
        "EXPECTED_WAIT": "EXPECTED_WAIT", "SLOW_BUT_PROGRESSING": "EXPECTED_WAIT",
        "STALLED": "STALE", "COMPLETE_WITH_GAPS": "STALE", "FAILED": "FAILED",
        "UNKNOWN": "UNKNOWN", "HOLD": "HELD",
    }.get(state, "UNKNOWN")


def make_lane(name, lane, *, observed_ms=None, registry_last_open_ms=None, registry_gaps=0,
              registry_unavailable=0, registry_conflicts=0, registry_source_count=None):
    source_ms = None
    lane_observed_ms = None
    committed = {}
    gaps = {}
    if name == "history":
        source_ms = registry_last_open_ms
        lane_observed_ms = lane.get("finished_ms")
        counters = lane.get("counters") if type(lane.get("counters")) is dict else {}
        committed = {"archives_imported": bounded_int(counters.get("archives_imported")),
                     "inserted_rows": bounded_int(counters.get("inserted_rows")),
                     "full_history_verified": counters.get("full_history_verified") is True,
                     "source_scan_exhausted": counters.get("source_scan_exhausted") is True}
        gaps = {"unresolved_ranges": bounded_int(lane.get("unresolved_gaps")) or 0,
                "source_obstacles": bounded_int(lane.get("obstacles")) or 0}
    elif name == "daily":
        lane_observed_ms = lane.get("observed_at_ms")
        success = lane.get("last_success") if type(lane.get("last_success")) is dict else {}
        linked = lane.get("source_receipt_link_verified") is True
        if linked:
            source_ms = success.get("source_day_ms")
        committed = {"source_time_utc": utc(success.get("source_day_ms")) if linked else None,
                     "source_rows": bounded_int(success.get("source_rows")) if linked else None,
                     "inserted_rows": bounded_int(success.get("inserted_rows")) if linked else None,
                     "receipt_link_verified": linked}
        gaps = {"receipt_link_missing": not linked}
    else:
        lane_observed_ms = lane.get("as_of_ms")
        source_ms = lane.get("last_committed_ms")
        committed = {"verified_receipts": bounded_int(lane.get("verified_receipts")),
                     "last_committed_time_utc": utc(lane.get("last_committed_ms")),
                     "last_receipt_fresh": lane.get("last_receipt_fresh") is True}
        gaps = {"missing_ranges": bounded_int(lane.get("missing_ranges")) or 0}
    raw_state = lane.get("state")
    status = map_state(raw_state, name)
    reason = safe_reason(lane.get("reason"))
    if name == "history" and (registry_gaps or registry_unavailable or registry_conflicts or
                              registry_source_count == 0 or registry_source_count is None or
                              gaps.get("unresolved_ranges", 0) or gaps.get("source_obstacles", 0)):
        if status in {"HEALTHY", "EXPECTED_WAIT"}:
            status, reason = "STALE", "REGISTRY_INCOMPLETE_OR_CONFLICTED"
    if name == "daily":
        if lane.get("source_receipt_link_verified") is not True:
            status, reason = "UNKNOWN", "DAILY_SOURCE_LINKAGE_UNPROVEN"
        elif lane.get("source_freshness") == "STALE" and status not in {"FAILED", "HELD"}:
            status, reason = "STALE", "DAILY_SOURCE_STALE"
        elif lane.get("last_failure") is not None and status not in {"FAILED", "HELD"}:
            status, reason = "FAILED", "DAILY_IMPORT_FAILURE"
    if name == "live" and lane.get("last_receipt_fresh") is False and status not in {"FAILED", "HELD"}:
        status, reason = "STALE", "LIVE_LAST_RECEIPT_STALE"
    refusal = safe_reason(lane.get("hold_reason")) if lane.get("hold_reason") else None
    if name == "live" and status == "HELD":
        refusal = safe_reason(lane.get("hold_reason")) or "LIVE_HOLD_REASON_REDACTED"
    elif status in {"FAILED", "STALE"}:
        refusal = reason
    source_age_ms = observed_ms - source_ms if type(observed_ms) is int and type(source_ms) is int and 0 <= source_ms <= observed_ms else None
    return {"lane": name, "status": status, "progress_state": safe_reason(raw_state) or "UNKNOWN",
            "reason": reason, "refusal_reason": refusal, "source_time_utc": utc(source_ms),
            "observed_at_utc": utc(lane_observed_ms),
            "last_validated_committed_progress": committed,
            "freshness": {"last_progress_time_utc": utc(lane.get("last_progress_at_ms")),
                          "source_age_ms_at_snapshot": source_age_ms,
                          "source_state": safe_reason(lane.get("source_freshness")) or (
                              "FRESH" if name == "live" and lane.get("last_receipt_fresh") is True else
                              "STALE" if name == "live" and lane.get("last_receipt_fresh") is False else None),
                          "expected_wait": status == "EXPECTED_WAIT"},
            "gaps": gaps,
            "provenance": {"fingerprint_sha256": lane.get("fingerprint") if is_sha256(lane.get("fingerprint")) else None,
                           "source_receipt_link_verified": lane.get("source_receipt_link_verified") is True if name == "daily" else None},
            "scientific_authority": "RETROSPECTIVE_NON_PIT" if name == "history" else
                                   "LIVE_CAPTURE_OBSERVATION" if name == "live" else "ARCHIVE_INGESTION_ONLY",
            "trading_authority": "NONE"}


class SnapshotReader:
    def __init__(self, manifest_path, expected_manifest_sha):
        self.profile = "strict"
        self.view = self.unavailable("EVIDENCE_UNAVAILABLE")
        self.manifest_path = Path(manifest_path)
        self.expected_manifest_sha = expected_manifest_sha
        self.snapshot_path = None
        self.snapshot_file_sha = None
        try:
            manifest, raw_manifest_sha = watchdog.read_json(self.manifest_path)
            if raw_manifest_sha != expected_manifest_sha:
                raise ValueError("MANIFEST_PIN_MISMATCH")
            watchdog.sealed_hash(manifest, "manifest_sha256", "MANIFEST_SEAL_INVALID")
            manifest_schema = manifest.get("schema")
            if manifest_schema == "atlas.mcp.source-manifest.v1":
                self.profile = "strict"
                expected_snapshot_schema = "atlas.operator.health-snapshot.v1"
            elif manifest_schema == "atlas.mcp.early-source-manifest.v1":
                self.profile = "early"
                expected_snapshot_schema = "atlas.operator.early-observation.v1"
            else:
                raise ValueError("MANIFEST_SCHEMA_INVALID")
            snapshot_path = manifest.get("snapshot_path")
            pinned_sha = manifest.get("snapshot_file_sha256")
            if type(snapshot_path) is not str or not Path(snapshot_path).is_absolute() or not is_sha256(pinned_sha):
                raise ValueError("MANIFEST_SOURCE_INVALID")
            self.snapshot_path = Path(snapshot_path)
            self.snapshot_file_sha = pinned_sha
            snapshot, snapshot_file_sha = watchdog.read_json(self.snapshot_path)
            if snapshot_file_sha != pinned_sha:
                raise ValueError("SNAPSHOT_PIN_MISMATCH")
            watchdog.sealed_hash(snapshot, "sha256", "SNAPSHOT_SEAL_INVALID")
            if snapshot.get("schema") != expected_snapshot_schema:
                raise ValueError("SNAPSHOT_PROFILE_MISMATCH")
            self.view = self._project(snapshot, snapshot_file_sha)
        except Exception as exc:  # never return paths or exception text to the MCP client
            code = str(exc) if type(exc) is ValueError else "EVIDENCE_UNAVAILABLE"
            self.view = self.unavailable(code if SAFE_CODE.fullmatch(code) else "EVIDENCE_UNAVAILABLE",
                                          early=self.profile == "early")

    def _project(self, snapshot, file_sha):
        return (self.project_early(snapshot, file_sha) if self.profile == "early"
                else self.project(snapshot, file_sha))

    def read_pinned(self):
        try:
            if self.snapshot_path is None:
                return self.view
            manifest, manifest_sha = watchdog.read_json(self.manifest_path)
            if manifest_sha != self.expected_manifest_sha:
                raise ValueError("MANIFEST_PIN_MISMATCH")
            watchdog.sealed_hash(manifest, "manifest_sha256", "MANIFEST_SEAL_INVALID")
            expected_manifest_schema = ("atlas.mcp.early-source-manifest.v1" if self.profile == "early"
                                        else "atlas.mcp.source-manifest.v1")
            expected_snapshot_schema = ("atlas.operator.early-observation.v1" if self.profile == "early"
                                        else "atlas.operator.health-snapshot.v1")
            if (manifest.get("schema") != expected_manifest_schema
                    or manifest.get("snapshot_path") != str(self.snapshot_path)
                    or manifest.get("snapshot_file_sha256") != self.snapshot_file_sha):
                raise ValueError("MANIFEST_PIN_MISMATCH")
            snapshot, raw_sha = watchdog.read_json(self.snapshot_path)
            if raw_sha != self.snapshot_file_sha:
                raise ValueError("SNAPSHOT_PIN_MISMATCH")
            watchdog.sealed_hash(snapshot, "sha256", "SNAPSHOT_SEAL_INVALID")
            if snapshot.get("schema") != expected_snapshot_schema:
                raise ValueError("SNAPSHOT_PROFILE_MISMATCH")
            return self._project(snapshot, raw_sha)
        except Exception as exc:
            code = str(exc) if type(exc) is ValueError else "EVIDENCE_UNAVAILABLE"
            return self.unavailable(code if SAFE_CODE.fullmatch(code) else "EVIDENCE_UNAVAILABLE",
                                    early=self.profile == "early")

    @staticmethod
    def unavailable(reason, early=False):
        if early:
            return {"schema": "atlas.mcp.early-observation.v1", "profile": "EARLY_OBSERVATION",
                    "status": "UNKNOWN", "reason": "EVIDENCE_UNAVAILABLE",
                    "refusal_reason": safe_reason(reason), "observed_at_utc": None,
                    "observed_at_ms": None, "clock_uncertainty_ms": None,
                    "evidence_grade": "UNAVAILABLE",
                    "lanes": {name: {"lane": name, "status": "UNKNOWN", "reason": "EVIDENCE_UNAVAILABLE",
                                     "refusal_reason": None, "trading_authority": "NONE"}
                              for name in LANES},
                    "gaps": {}, "provenance": {"snapshot_sha256": None, "source_pins": {},
                                               "host_attested": False},
                    "scientific_authority": "NONE", "trading_authority": "NONE"}
        return {"schema": "atlas.mcp.health.v1", "status": "UNKNOWN", "reason": "EVIDENCE_UNAVAILABLE",
                "refusal_reason": safe_reason(reason), "observed_at_utc": None, "evidence_grade": "UNAVAILABLE",
                "lanes": {name: make_lane(name, {"state": "UNKNOWN"}) for name in LANES},
                "gaps": {"history_registry_gaps": 0, "history_unresolved_ranges": 0,
                         "history_source_obstacles": 0, "daily_receipt_link_missing": True,
                         "live_missing_ranges": 0},
                "provenance": {"snapshot_sha256": None, "source_pins": {}, "host_attested": False},
                "scientific_authority": "NONE", "trading_authority": "NONE"}

    @staticmethod
    def project(snapshot, file_sha):
        if snapshot.get("schema") != "atlas.operator.health-snapshot.v1":
            raise ValueError("SNAPSHOT_SCHEMA_INVALID")
        observed = snapshot.get("observed_at_ms")
        if type(observed) is not int or observed < 0:
            raise ValueError("SNAPSHOT_CLOCK_INVALID")
        if snapshot.get("source_paths_exposed") is not False or snapshot.get("raw_market_payload_included") is not False:
            raise ValueError("SNAPSHOT_REDACTION_CONTRACT")
        if snapshot.get("network_calls") != 0 or snapshot.get("source_mutations") != 0:
            raise ValueError("SNAPSHOT_READ_ONLY_CONTRACT")
        if snapshot.get("trading_authority") != "NONE":
            raise ValueError("TRADING_AUTHORITY_CONTRACT")
        raw_lanes = snapshot.get("lanes")
        if type(raw_lanes) is not dict or any(type(raw_lanes.get(name)) is not dict for name in LANES):
            raise ValueError("LANE_EVIDENCE_MISSING")
        for name, time_key in (("daily", "observed_at_ms"), ("live", "as_of_ms"), ("history", "finished_ms")):
            lane_time = raw_lanes[name].get(time_key)
            if lane_time is not None and (type(lane_time) is not int or lane_time < 0 or lane_time > observed):
                raise ValueError("LANE_TIMESTAMP_CONFLICT")
        raw_states = {raw_lanes[name].get("state") for name in LANES}
        if any(state not in watchdog.STATES for state in raw_states):
            raise ValueError("LANE_STATE_INVALID")
        expected_state = ("FAILED" if "FAILED" in raw_states else "HOLD" if "HOLD" in raw_states else
                          "STALLED" if "STALLED" in raw_states else "UNKNOWN" if "UNKNOWN" in raw_states else
                          "HEALTHY_PROGRESS" if "HEALTHY_PROGRESS" in raw_states else "EXPECTED_WAIT")
        if snapshot.get("state") != expected_state:
            raise ValueError("OVERALL_LANE_STATE_CONFLICT")
        registry = snapshot.get("registry") if type(snapshot.get("registry")) is dict else {}
        for key in ("gaps", "unavailable", "conflicts"):
            if type(registry.get(key)) is not int or registry[key] < 0:
                raise ValueError("REGISTRY_COVERAGE_INVALID")
        registry_counters = registry.get("counters") if type(registry.get("counters")) is dict else {}
        registry_blocked = bool(registry.get("gaps") or registry.get("unavailable") or registry.get("conflicts")
                                or registry_counters.get("source_count") == 0
                                or registry_counters.get("source_count") is None)
        watermark = registry_counters.get("event_watermark")
        if type(watermark) is not int or watermark < 0:
            raise ValueError("REGISTRY_WATERMARK_INVALID")
        if type(registry_counters.get("physical_rows")) is not int or registry_counters["physical_rows"] < 0:
            raise ValueError("REGISTRY_COUNTER_INVALID")
        registry_last_open_ms = registry_counters.get("last_open_ms")
        registry_source_count = registry_counters.get("source_count")
        if registry_source_count is not None and (type(registry_source_count) is not int or registry_source_count < 0):
            raise ValueError("REGISTRY_COUNTER_INVALID")
        if registry_last_open_ms is not None and (type(registry_last_open_ms) is not int or
                                                   registry_last_open_ms < 0 or registry_last_open_ms > observed):
            raise ValueError("REGISTRY_TIMESTAMP_CONFLICT")
        daily_success = raw_lanes["daily"].get("last_success")
        daily_observed = raw_lanes["daily"].get("observed_at_ms")
        if type(daily_success) is dict and daily_success.get("source_day_ms") is not None:
            source_day = daily_success["source_day_ms"]
            if type(source_day) is not int or source_day < 0 or (type(daily_observed) is int and source_day > daily_observed):
                raise ValueError("DAILY_SOURCE_TIMESTAMP_CONFLICT")
        lanes = {name: make_lane(name, raw_lanes[name], observed_ms=observed,
                                 registry_last_open_ms=registry_last_open_ms,
                                 registry_gaps=bounded_int(registry.get("gaps")) or 0,
                                 registry_unavailable=bounded_int(registry.get("unavailable")) or 0,
                                 registry_conflicts=bounded_int(registry.get("conflicts")) or 0,
                                 registry_source_count=registry_source_count)
                 for name in LANES}
        if any(not is_sha256(raw_lanes[name].get("fingerprint")) for name in LANES):
            raise ValueError("LANE_FINGERPRINT_INVALID")
        states = {lane["status"] for lane in lanes.values()}
        overall = ("FAILED" if "FAILED" in states else "HELD" if "HELD" in states else
                   "STALE" if registry_blocked else "STALE" if "STALE" in states else "UNKNOWN" if "UNKNOWN" in states else
                   "HEALTHY" if "HEALTHY" in states else "EXPECTED_WAIT")
        source_pins = snapshot.get("source_pins") if type(snapshot.get("source_pins")) is dict else {}
        required_pins = {"registry", "history", "daily", "daily_import", "daily_source", "live"}
        if not required_pins.issubset(source_pins) or any(not is_sha256(source_pins[k]) for k in required_pins):
            raise ValueError("SOURCE_PIN_SET_INVALID")
        gaps = {"history_registry_gaps": bounded_int(registry.get("gaps")) or 0,
                "history_unavailable_boundaries": bounded_int(registry.get("unavailable")) or 0,
                "history_conflicts": bounded_int(registry.get("conflicts")) or 0,
                "history_unresolved_ranges": lanes["history"]["gaps"]["unresolved_ranges"],
                "history_source_obstacles": lanes["history"]["gaps"]["source_obstacles"],
                "daily_receipt_link_missing": lanes["daily"]["gaps"]["receipt_link_missing"],
                "live_missing_ranges": lanes["live"]["gaps"]["missing_ranges"]}
        pins = {k: v for k, v in source_pins.items()
                if k in {"registry", "history", "daily", "daily_import", "daily_source", "live"} and is_sha256(v)}
        return {"schema": "atlas.mcp.health.v1", "status": overall,
                "reason": safe_reason(snapshot.get("state")) or "UNKNOWN",
                "refusal_reason": lanes["live"]["refusal_reason"] if lanes["live"]["status"] == "HELD" else None,
                "observed_at_utc": utc(observed), "observed_at_ms": observed,
                "clock_uncertainty_ms": bounded_int(snapshot.get("clock_uncertainty_ms")) if bounded_int(snapshot.get("clock_uncertainty_ms")) is not None and snapshot.get("clock_uncertainty_ms") <= MAX_CLOCK_DRIFT_MS else None,
                "evidence_grade": "SEALED_LOCAL_SNAPSHOT_NOT_HOST_ATTESTED", "lanes": lanes, "gaps": gaps,
                "provenance": {"snapshot_sha256": file_sha, "source_pins": pins,
                               "registry_event_watermark": watermark, "host_attested": False},
                "scientific_authority": "RETROSPECTIVE_NON_PIT_ONLY", "trading_authority": "NONE"}

    @staticmethod
    def project_early(snapshot, file_sha):
        allowed = {"HEALTHY_PROGRESS": "HEALTHY", "EXPECTED_WAIT": "EXPECTED_WAIT",
                   "STALE": "STALE", "HELD": "HELD", "FAILED": "FAILED", "UNKNOWN": "UNKNOWN"}
        if (snapshot.get("schema") != "atlas.operator.early-observation.v1"
                or snapshot.get("profile") != "EARLY_OBSERVATION"):
            raise ValueError("EARLY_PROFILE_INVALID")
        if (snapshot.get("source_paths_exposed") is not False
                or snapshot.get("raw_market_payload_included") is not False
                or snapshot.get("network_calls") != 0
                or snapshot.get("source_mutations") != 0
                or snapshot.get("trading_authority") != "NONE"):
            raise ValueError("EARLY_READ_ONLY_CONTRACT")
        observed = snapshot.get("observed_at_ms")
        if type(observed) is not int or observed < 0:
            raise ValueError("EARLY_CLOCK_INVALID")
        raw_lanes = snapshot.get("lanes")
        if type(raw_lanes) is not dict or set(raw_lanes) != set(LANES):
            raise ValueError("EARLY_LANES_INVALID")
        lanes = {}
        for name in LANES:
            raw = raw_lanes[name]
            if type(raw) is not dict or raw.get("lane") != name or raw.get("status") not in allowed:
                raise ValueError("EARLY_LANE_INVALID")
            pin = raw.get("source_file_sha256")
            if pin is not None and not is_sha256(pin):
                raise ValueError("EARLY_SOURCE_PIN_INVALID")
            report = raw.get("reported") if type(raw.get("reported")) is dict else {}
            if name == "history":
                counters = report.get("counters") if type(report.get("counters")) is dict else {}
                gaps = {"unresolved_ranges": bounded_int(report.get("unresolved_gaps")) or 0,
                        "unresolved_gap_ranges": early_ranges(report.get("unresolved_gap_ranges")),
                        "source_obstacles": bounded_int(report.get("source_obstacles")) or 0,
                        "registry_gaps": bounded_int(counters.get("registry_gaps")) or 0,
                        "registry_gap_ranges": early_ranges(report.get("registry_gap_ranges")),
                        "registry_unavailable_ranges": early_ranges(report.get("registry_unavailable_ranges"))}
                progress = {key: value for key, value in counters.items()
                            if key in {"archives_imported", "inserted_rows", "event_watermark",
                                       "physical_rows", "source_count", "last_open_ms",
                                       "full_history_verified", "accepted_prefix_unchanged",
                                       "all_published_partitions_ingested", "source_scan_exhausted",
                                       "latest_published_close_reached"}
                            and type(value) in (int, bool)}
            elif name == "daily":
                progress = {key: early_enum(report.get(key), key) for key in
                            ("task_state", "scheduler_state", "runtime_state", "cycle_evidence",
                             "source_freshness")}
                progress["last_success_source_day_ms"] = bounded_int(report.get("last_success_source_day_ms"))
                receipt = report.get("worker_receipt_sha256")
                progress["worker_receipt_sha256"] = receipt if is_sha256(receipt) else None
                gaps = {"import_registry_link_missing": True}
            else:
                progress = {"source_class": "LIVE_CAPTURE",
                            "status": early_enum(report.get("status"), "live_status"),
                            "verified_receipts": bounded_int(report.get("verified_receipts")),
                            "last_committed_ms": bounded_int(report.get("last_committed_ms")),
                            "last_receipt_fresh": report.get("last_receipt_fresh")
                                if type(report.get("last_receipt_fresh")) is bool else None,
                            "missing_ranges": bounded_int(report.get("missing_ranges")) or 0,
                            "missing_open_ranges": early_ranges(report.get("missing_open_ranges")),
                            "hold_reason": "LIVE_HOLD_REASON_REPORTED" if report.get("hold_reason") else None}
                gaps = {"missing_ranges": bounded_int(report.get("missing_ranges")) or 0,
                        "missing_open_ranges": early_ranges(report.get("missing_open_ranges"))}
            status = allowed[raw["status"]]
            raw_reason = raw.get("reason")
            reason = raw_reason if type(raw_reason) is str and raw_reason in EARLY_REASON_CODES else "EARLY_EVIDENCE_UNTRUSTED"
            age = bounded_int(raw.get("age_ms"))
            lanes[name] = {"lane": name, "status": status, "progress_state": raw["status"],
                "reason": reason, "refusal_reason": reason if status in {"HELD", "FAILED", "STALE"} else None,
                "source_time_utc": utc(raw.get("observed_at_ms")),
                "observed_at_utc": utc(raw.get("observed_at_ms")),
                "last_validated_committed_progress": progress,
                "freshness": {"source_state": raw.get("freshness") if raw.get("freshness") in {"FRESH", "STALE", "UNKNOWN"} else "UNKNOWN",
                              "source_age_ms_at_snapshot": age,
                              "max_snapshot_age_ms": 300_000,
                              "expected_wait": status == "EXPECTED_WAIT"},
                "gaps": gaps, "scope": {"history": "REPORT_ONLY_NO_PHYSICAL_REVALIDATION",
                    "daily": "WORKER_REPORT_IMPORT_REGISTRY_LINK_UNVERIFIED",
                    "live": "WORK1_HANDOFF_REPORT_ONLY"}[name],
                "provenance": {"source_schema": raw.get("source_schema")
                    if (name == "history" and raw.get("source_schema") in {
                        "aql.warehouse.full-history-checkpoint.v1",
                        "aql.warehouse.full-history-continuation.v1"})
                    or (name == "daily" and raw.get("source_schema") == "aql.recurring-runtime.health.v1")
                    or (name == "live" and raw.get("source_schema") == "atlas.ws.continuous-report.v1")
                    else "UNRECOGNIZED_SCHEMA",
                               "source_file_sha256": pin,
                               "source_identity": raw.get("source_identity")
                                  if name == "live" and type(raw.get("source_identity")) is dict
                                  and is_sha256(raw["source_identity"].get("config_sha256"))
                                  and is_sha256(raw["source_identity"].get("policy_sha256")) else None,
                               "evidence_grade": {"history": "OWNER_SUPPLIED_SEALED_REPORT_NOT_RECONCILED",
                    "daily": "OWNER_SUPPLIED_DAILY_WORKER_REPORT_IMPORT_UNVERIFIED",
                    "live": "OWNER_SUPPLIED_LIVE_REPORT_NOT_HOST_ATTESTED"}[name]},
                "scientific_authority": "NONE", "trading_authority": "NONE"}
        statuses = {item["status"] for item in lanes.values()}
        expected = ("FAILED" if "FAILED" in statuses else "HELD" if "HELD" in statuses else
                    "STALE" if "STALE" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else
                    "HEALTHY" if "HEALTHY" in statuses else "EXPECTED_WAIT")
        if snapshot.get("state") not in allowed or allowed[snapshot["state"]] != expected:
            raise ValueError("EARLY_OVERALL_STATE_CONFLICT")
        inputs = snapshot.get("inputs") if type(snapshot.get("inputs")) is dict else {}
        pins = {name: item.get("file_sha256") for name, item in inputs.items()
                if name in {"history", "registry", "daily", "live"}
                and type(item) is dict and is_sha256(item.get("file_sha256"))}
        return {"schema": "atlas.mcp.early-observation.v1", "profile": "EARLY_OBSERVATION",
                "status": expected, "reason": "EARLY_OBSERVATION_PROFILE",
                "observed_at_utc": utc(observed), "observed_at_ms": observed,
                "clock_uncertainty_ms": (bounded_int(snapshot.get("clock_uncertainty_ms")) if snapshot.get("clock_uncertainty_ms") is None or bounded_int(snapshot.get("clock_uncertainty_ms")) is not None else None),
                "evidence_grade": "EARLY_OBSERVATION_NOT_HOST_ATTESTED",
                "lanes": lanes, "gaps": {name: lanes[name]["gaps"] for name in LANES},
                "provenance": {"snapshot_sha256": file_sha, "source_pins": pins,
                               "host_attested": False},
                "scientific_authority": "NONE", "trading_authority": "NONE"}



def tool_specs():
    return [
        {"name": "atlas.runtime.health", "description": "Read the latest sanitized overall ATLAS watchdog snapshot. No arguments; read-only.",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "atlas.lane.latest", "description": "Read one sanitized latest lane status, committed progress, gaps, source time and provenance. No writes.",
         "inputSchema": {"type": "object", "properties": {"lane": {"type": "string", "enum": list(LANES)}},
                         "required": ["lane"], "additionalProperties": False}},
    ]


def resource_specs():
    return [{"uri": "atlas://runtime/health", "name": "ATLAS overall health", "mimeType": "application/json",
             "description": "Latest sanitized sealed watchdog snapshot projection."},
            *[{"uri": f"atlas://lane/{lane}", "name": f"ATLAS {lane} lane", "mimeType": "application/json",
               "description": f"Latest sanitized {lane} lane status and provenance."} for lane in LANES]]


MAX_SNAPSHOT_AGE_MS = 300_000
MAX_CLOCK_DRIFT_MS = 5_000


class MCPServer:
    def __init__(self, reader, clock=None):
        self.reader = reader
        self.protocol = None
        self.clock = clock or (lambda: (time.time_ns() // 1_000_000, time.monotonic_ns()))
        self._anchor = self.clock()
        self._last_clock = self._anchor
        self._clock_poisoned = False

    def current_view(self):
        try:
            wall_ms, mono_ns = self.clock()
            anchor_wall, anchor_mono = self._anchor
            last_wall, last_mono = self._last_clock
            if (type(wall_ms) is not int or type(mono_ns) is not int or wall_ms < last_wall
                    or mono_ns < last_mono or mono_ns < anchor_mono):
                self._clock_poisoned = True
            elif abs((wall_ms - anchor_wall) - (mono_ns - anchor_mono) // 1_000_000) > MAX_CLOCK_DRIFT_MS:
                self._clock_poisoned = True
            self._last_clock = (wall_ms, mono_ns)
            base = self.reader.read_pinned() if hasattr(self.reader, "read_pinned") else self.reader.view
            data = json.loads(json.dumps(base))
            observed = data.get("observed_at_ms")
            age = wall_ms - observed if type(observed) is int else None
            early_profile = getattr(self.reader, "profile", "strict") == "early"
            protected_status = data.get("status") in {"HELD", "FAILED"}
            uncertainty = data.get("clock_uncertainty_ms")
            clock_bad = (self._clock_poisoned or age is None or age < 0 or
                         type(uncertainty) is not int or uncertainty > MAX_CLOCK_DRIFT_MS)
            stale = age is not None and age > MAX_SNAPSHOT_AGE_MS
            data["request_freshness"] = {"checked_at_ms": wall_ms, "snapshot_age_ms": age,
                "max_snapshot_age_ms": MAX_SNAPSHOT_AGE_MS, "clock_valid": not clock_bad}
            claim_states = {"HEALTHY", "EXPECTED_WAIT", "HEALTHY_PROGRESS"}
            if (not protected_status and early_profile and stale):
                data.update(status="STALE", reason="SNAPSHOT_TTL_EXCEEDED",
                            refusal_reason="SNAPSHOT_TTL_EXCEEDED")
            elif not protected_status and data.get("status") in claim_states and clock_bad:
                data.update(status="UNKNOWN", reason="CLOCK_OR_TIMESTAMP_UNTRUSTED",
                            refusal_reason="EVIDENCE_UNAVAILABLE")
            elif not protected_status and data.get("status") in claim_states and stale:
                data.update(status="STALE", reason="SNAPSHOT_TTL_EXCEEDED",
                            refusal_reason="SNAPSHOT_TTL_EXCEEDED")
            for lane in data.get("lanes", {}).values():
                if lane.get("status") in {"HELD", "FAILED"}:
                    continue
                if clock_bad and lane.get("status") in claim_states:
                    lane.update(status="UNKNOWN", reason="CLOCK_OR_TIMESTAMP_UNTRUSTED",
                                refusal_reason="EVIDENCE_UNAVAILABLE")
                elif stale and (lane.get("status") in claim_states or
                                (early_profile and lane.get("source_file_sha256"))):
                    lane.update(status="STALE", reason="SNAPSHOT_TTL_EXCEEDED",
                                refusal_reason="SNAPSHOT_TTL_EXCEEDED")
            return data
        except Exception:
            return self.reader.unavailable("EVIDENCE_UNAVAILABLE",
                                              early=getattr(self.reader, "profile", "strict") == "early")

    @staticmethod
    def error(request_id, code, message, data=None):
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": err}

    @staticmethod
    def result(request_id, result, modern=False):
        if modern:
            result = dict(result)
            result["resultType"] = "complete"
            result["_meta"] = {META_SERVER: {"name": SERVER_NAME, "version": SERVER_VERSION}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def dispatch(self, request):
        if type(request) is not dict or request.get("jsonrpc") != "2.0" or type(request.get("method")) is not str:
            return self.error(request.get("id") if type(request) is dict else None, -32600, "Invalid Request")
        method, request_id = request["method"], request.get("id")
        if "id" not in request:  # notifications receive no response
            return None
        params = request.get("params") or {}
        if type(params) is not dict:
            return self.error(request_id, -32602, "Invalid params")
        meta = params.get("_meta") if type(params.get("_meta")) is dict else {}
        modern = meta.get(META_VERSION) == MODERN
        if method == "server/discover":
            if not modern or type(meta.get(META_CAPABILITIES)) is not dict:
                return self.error(request_id, -32602, "Modern protocol metadata required")
            return self.result(request_id, {"resultType": "complete", "supportedVersions": [MODERN],
                "capabilities": {"tools": {}, "resources": {}},
                "instructions": "Read-only local ATLAS status consumer. Evidence may be unknown and is not host-attested.",
                "ttlMs": 0, "cacheScope": "private"}, modern=True)
        if modern:
            if self.protocol not in (None, MODERN):
                return self.error(request_id, -32602, "Protocol version changed on an active stdio connection")
            if type(meta.get(META_CAPABILITIES)) is not dict:
                return self.error(request_id, -32602, "Missing client capabilities")
            self.protocol = MODERN
        elif method == "initialize":
            if self.protocol not in (None, LEGACY):
                return self.error(request_id, -32602, "Protocol version changed on an active stdio connection")
            requested = params.get("protocolVersion")
            versions = {LEGACY, "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"}
            negotiated = requested if requested in versions else LEGACY
            self.protocol = negotiated
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": negotiated, "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Read-only local ATLAS status consumer. Evidence may be unknown and is not host-attested."}}
        elif self.protocol == MODERN:
            return self.error(request_id, -32602, "Modern protocol metadata required")
        if method == "ping":
            return self.result(request_id, {}, modern=modern)
        if method == "tools/list":
            return self.result(request_id, {"tools": tool_specs(), "ttlMs": 0, "cacheScope": "private"}, modern=modern)
        if method == "resources/list":
            return self.result(request_id, {"resources": resource_specs(), "ttlMs": 0, "cacheScope": "private"}, modern=modern)
        if method == "tools/call":
            return self.call_tool(request_id, params, modern)
        if method == "resources/read":
            return self.read_resource(request_id, params, modern)
        return self.error(request_id, -32601, "Method not found")

    def call_tool(self, request_id, params, modern):
        name, args = params.get("name"), params.get("arguments", {})
        if type(args) is not dict:
            return self.error(request_id, -32602, "Invalid params")
        view = self.current_view()
        if name == "atlas.runtime.health" and not args:
            data = view
        elif name == "atlas.lane.latest" and set(args) == {"lane"} and args.get("lane") in LANES:
            data = view["lanes"][args["lane"]]
        else:
            return self.error(request_id, -32602, "Unknown tool or invalid arguments")
        result = {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True, separators=(",", ":"))}],
                  "structuredContent": data, "isError": data.get("status") == "UNKNOWN"}
        return self.result(request_id, result, modern=modern)

    def read_resource(self, request_id, params, modern):
        uri = params.get("uri")
        view = self.current_view()
        if uri == "atlas://runtime/health":
            data = view
        elif type(uri) is str and uri in {f"atlas://lane/{lane}" for lane in LANES}:
            data = view["lanes"][uri.rsplit("/", 1)[1]]
        else:
            return self.error(request_id, -32602, "Resource not found")
        result = {"contents": [{"uri": uri, "mimeType": "application/json",
                               "text": json.dumps(data, sort_keys=True, separators=(",", ":"))}],
                  "ttlMs": 0, "cacheScope": "private"}
        return self.result(request_id, result, modern=modern)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Local sealed source manifest; never an MCP argument.")
    parser.add_argument("--manifest-sha256", required=True, help="Out-of-band SHA-256 pin for manifest bytes.")
    args = parser.parse_args()
    if not is_sha256(args.manifest_sha256):
        parser.error("--manifest-sha256 must be lowercase SHA-256")
    server = MCPServer(SnapshotReader(args.manifest, args.manifest_sha256))
    for raw in sys.stdin.buffer:
        if len(raw) > MAX_LINE_BYTES:
            response = server.error(None, -32700, "Request exceeds size bound")
        else:
            try:
                request = json.loads(raw.decode("utf-8"), object_pairs_hook=watchdog.unique_pairs)
                response = server.dispatch(request)
            except Exception:
                response = server.error(None, -32700, "Invalid JSON-RPC message")
        if response is not None:
            sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

