"""Local stdio-only, read-only MCP adapter for sealed ATLAS watchdog snapshots.

The adapter reads one explicitly pinned watchdog snapshot. It has no network,
process-control, scheduler, arbitrary-file, or source-lane write capability.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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


def map_state(state, lane):
    if lane == "live" and state == "HOLD":
        return "HELD"
    return {
        "HEALTHY_PROGRESS": "HEALTHY", "COMPLETE_VERIFIED": "HEALTHY",
        "EXPECTED_WAIT": "EXPECTED_WAIT", "SLOW_BUT_PROGRESSING": "EXPECTED_WAIT",
        "STALLED": "STALE", "COMPLETE_WITH_GAPS": "STALE", "FAILED": "FAILED",
        "UNKNOWN": "UNKNOWN", "HOLD": "HELD",
    }.get(state, "UNKNOWN")


def make_lane(name, lane):
    source_time = None
    committed = {}
    gaps = {}
    if name == "history":
        source_time = utc(lane.get("finished_ms"))
        counters = lane.get("counters") if type(lane.get("counters")) is dict else {}
        committed = {"archives_imported": bounded_int(counters.get("archives_imported")),
                     "inserted_rows": bounded_int(counters.get("inserted_rows")),
                     "full_history_verified": counters.get("full_history_verified") is True,
                     "source_scan_exhausted": counters.get("source_scan_exhausted") is True}
        gaps = {"unresolved_ranges": bounded_int(lane.get("unresolved_gaps")) or 0,
                "source_obstacles": bounded_int(lane.get("obstacles")) or 0}
    elif name == "daily":
        source_time = utc(lane.get("observed_at_ms"))
        success = lane.get("last_success") if type(lane.get("last_success")) is dict else {}
        committed = {"source_time_utc": utc(success.get("source_day_ms")),
                     "source_rows": bounded_int(success.get("source_rows")),
                     "inserted_rows": bounded_int(success.get("inserted_rows")),
                     "receipt_link_verified": lane.get("source_receipt_link_verified") is True}
        gaps = {"receipt_link_missing": lane.get("source_receipt_link_verified") is not True}
    else:
        source_time = utc(lane.get("as_of_ms"))
        committed = {"verified_receipts": bounded_int(lane.get("verified_receipts")),
                     "last_committed_time_utc": utc(lane.get("last_committed_ms")),
                     "last_receipt_fresh": lane.get("last_receipt_fresh") is True}
        gaps = {"missing_ranges": bounded_int(lane.get("missing_ranges")) or 0}
    raw_state = lane.get("state")
    status = map_state(raw_state, name)
    reason = safe_reason(lane.get("reason"))
    refusal = safe_reason(lane.get("hold_reason")) if lane.get("hold_reason") else None
    if name == "live" and status == "HELD":
        refusal = safe_reason(lane.get("hold_reason")) or "LIVE_HOLD_REASON_REDACTED"
    elif status in {"FAILED", "STALE"}:
        refusal = reason
    return {"lane": name, "status": status, "progress_state": safe_reason(raw_state) or "UNKNOWN",
            "reason": reason, "refusal_reason": refusal, "source_time_utc": source_time,
            "last_validated_committed_progress": committed,
            "freshness": {"last_progress_time_utc": utc(lane.get("last_progress_at_ms")),
                          "expected_wait": status == "EXPECTED_WAIT"},
            "gaps": gaps,
            "provenance": {"fingerprint_sha256": lane.get("fingerprint") if is_sha256(lane.get("fingerprint")) else None,
                           "source_receipt_link_verified": lane.get("source_receipt_link_verified") is True if name == "daily" else None},
            "scientific_authority": "RETROSPECTIVE_NON_PIT" if name == "history" else
                                   "LIVE_CAPTURE_OBSERVATION" if name == "live" else "ARCHIVE_INGESTION_ONLY",
            "trading_authority": "NONE"}


class SnapshotReader:
    def __init__(self, manifest_path, expected_manifest_sha):
        self.view = self.unavailable("EVIDENCE_UNAVAILABLE")
        try:
            manifest, raw_manifest_sha = watchdog.read_json(manifest_path)
            if raw_manifest_sha != expected_manifest_sha:
                raise ValueError("MANIFEST_PIN_MISMATCH")
            watchdog.sealed_hash(manifest, "manifest_sha256", "MANIFEST_SEAL_INVALID")
            if manifest.get("schema") != "atlas.mcp.source-manifest.v1":
                raise ValueError("MANIFEST_SCHEMA_INVALID")
            snapshot_path = manifest.get("snapshot_path")
            pinned_sha = manifest.get("snapshot_file_sha256")
            if type(snapshot_path) is not str or not Path(snapshot_path).is_absolute() or not is_sha256(pinned_sha):
                raise ValueError("MANIFEST_SOURCE_INVALID")
            snapshot, snapshot_file_sha = watchdog.read_json(snapshot_path)
            if snapshot_file_sha != pinned_sha:
                raise ValueError("SNAPSHOT_PIN_MISMATCH")
            watchdog.sealed_hash(snapshot, "sha256", "SNAPSHOT_SEAL_INVALID")
            self.view = self.project(snapshot, snapshot_file_sha)
        except Exception as exc:  # never return paths or exception text to the MCP client
            code = str(exc) if type(exc) is ValueError else "EVIDENCE_UNAVAILABLE"
            self.view = self.unavailable(code if SAFE_CODE.fullmatch(code) else "EVIDENCE_UNAVAILABLE")

    @staticmethod
    def unavailable(reason):
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
        expected_state = ("FAILED" if "FAILED" in raw_states else "HOLD" if "HOLD" in raw_states else
                          "STALLED" if "STALLED" in raw_states else "UNKNOWN" if "UNKNOWN" in raw_states else
                          "HEALTHY_PROGRESS" if "HEALTHY_PROGRESS" in raw_states else "EXPECTED_WAIT")
        if snapshot.get("state") != expected_state:
            raise ValueError("OVERALL_LANE_STATE_CONFLICT")
        lanes = {name: make_lane(name, raw_lanes[name]) for name in LANES}
        states = {lane["status"] for lane in lanes.values()}
        overall = ("FAILED" if "FAILED" in states else "HELD" if "HELD" in states else
                   "STALE" if "STALE" in states else "UNKNOWN" if "UNKNOWN" in states else
                   "HEALTHY" if "HEALTHY" in states else "EXPECTED_WAIT")
        registry = snapshot.get("registry") if type(snapshot.get("registry")) is dict else {}
        registry_counters = registry.get("counters") if type(registry.get("counters")) is dict else {}
        watermark = registry_counters.get("event_watermark")
        if type(watermark) is not int or watermark < 0:
            raise ValueError("REGISTRY_WATERMARK_INVALID")
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
                "observed_at_utc": utc(observed),
                "evidence_grade": "SEALED_LOCAL_SNAPSHOT_NOT_HOST_ATTESTED", "lanes": lanes, "gaps": gaps,
                "provenance": {"snapshot_sha256": file_sha, "source_pins": pins,
                               "registry_event_watermark": watermark, "host_attested": False},
                "scientific_authority": "RETROSPECTIVE_NON_PIT_ONLY", "trading_authority": "NONE"}


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


class MCPServer:
    def __init__(self, reader):
        self.reader = reader
        self.protocol = None

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
        if name == "atlas.runtime.health" and not args:
            data = self.reader.view
        elif name == "atlas.lane.latest" and set(args) == {"lane"} and args.get("lane") in LANES:
            data = self.reader.view["lanes"][args["lane"]]
        else:
            return self.error(request_id, -32602, "Unknown tool or invalid arguments")
        result = {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True, separators=(",", ":"))}],
                  "structuredContent": data, "isError": data.get("status") == "UNKNOWN"}
        return self.result(request_id, result, modern=modern)

    def read_resource(self, request_id, params, modern):
        uri = params.get("uri")
        if uri == "atlas://runtime/health":
            data = self.reader.view
        elif type(uri) is str and uri in {f"atlas://lane/{lane}" for lane in LANES}:
            data = self.reader.view["lanes"][uri.rsplit("/", 1)[1]]
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

