import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import atlas_ops_watchdog as watchdog
import atlas_mcp_pilot as pilot


def seal(value, key):
    body = {k: v for k, v in value.items() if k != key}
    return {**body, key: watchdog.digest(watchdog.canonical(body))}


def snapshot():
    return seal({
        "schema": "atlas.operator.health-snapshot.v1", "version": 1,
        "observed_at_ms": 1795499204274, "state": "HOLD",
        "source_pins": {k: str(i) * 64 for i, k in enumerate(
            ("registry", "history", "daily", "daily_import", "daily_source", "live"), 1)},
        "registry": {"gaps": 2, "unavailable": 1, "conflicts": 0,
                     "counters": {"event_watermark": 4, "physical_rows": 100}},
        "lanes": {
            "history": {"state": "UNKNOWN", "reason": "BASELINE_REQUIRED", "finished_ms": None,
                         "counters": {"archives_imported": 2, "inserted_rows": 400,
                                      "full_history_verified": False, "source_scan_exhausted": False},
                         "unresolved_gaps": 0, "obstacles": 0, "fingerprint": "a" * 64},
            "daily": {"state": "UNKNOWN", "reason": "DAILY_SOURCE_LINKAGE_UNPROVEN", "observed_at_ms": 1795499204274,
                      "source_receipt_link_verified": False, "last_success": None, "fingerprint": "b" * 64},
            "live": {"state": "HOLD", "reason": "EXPLICIT_LIVE_HOLD", "hold_reason": "PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED",
                     "as_of_ms": 1795499204274, "verified_receipts": 50, "last_committed_ms": 1795481100103,
                     "last_receipt_fresh": False, "missing_ranges": 1, "fingerprint": "c" * 64},
        },
        "source_paths_exposed": False, "raw_market_payload_included": False,
        "network_calls": 0, "source_mutations": 0, "trading_authority": "NONE",
        "private_path": "C:\\private\\must-not-leak", "raw_candles": [{"close": 123}],
    }, "sha256")


def write_fixture(root, snap=None):
    snap = snap or snapshot()
    snap_path = root / "sealed-snapshot.json"
    snap_path.write_bytes(watchdog.canonical(snap))
    manifest = seal({"schema": "atlas.mcp.source-manifest.v1", "snapshot_path": str(snap_path),
                     "snapshot_file_sha256": watchdog.digest(snap_path.read_bytes())}, "manifest_sha256")
    manifest_path = root / "source-manifest.json"
    manifest_path.write_bytes(watchdog.canonical(manifest))
    return manifest_path, watchdog.digest(manifest_path.read_bytes())


class McpPilotTests(unittest.TestCase):
    def test_owner_reported_hold_gap_and_no_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, pin = write_fixture(Path(directory))
            result = pilot.SnapshotReader(manifest, pin).view
        self.assertEqual(result["status"], "HELD")
        self.assertEqual(result["evidence_grade"], "SEALED_LOCAL_SNAPSHOT_NOT_HOST_ATTESTED")
        self.assertEqual(result["lanes"]["live"]["status"], "HELD")
        self.assertEqual(result["lanes"]["live"]["refusal_reason"], "PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED")
        self.assertEqual(result["gaps"]["live_missing_ranges"], 1)
        self.assertEqual(result["lanes"]["history"]["last_validated_committed_progress"]["full_history_verified"], False)
        self.assertFalse(result["provenance"]["host_attested"])
        self.assertEqual(result["trading_authority"], "NONE")
        serialized = json.dumps(result)
        self.assertNotIn("C:\\private", serialized)
        self.assertNotIn("raw_candles", serialized)
        self.assertNotIn("123", serialized)

    def test_missing_and_bad_manifest_pin_fail_closed_without_path_disclosure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            absent = pilot.SnapshotReader(root / "secret-path-missing.json", "a" * 64).view
            manifest, pin = write_fixture(root)
            mismatch = pilot.SnapshotReader(manifest, "f" * 64).view
        for result in (absent, mismatch):
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["reason"], "EVIDENCE_UNAVAILABLE")
            self.assertNotIn("secret-path", json.dumps(result))

    def test_tampered_snapshot_and_manifest_seals_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, pin = write_fixture(root)
            snap_path = root / "sealed-snapshot.json"
            doc = json.loads(snap_path.read_text(encoding="utf-8"))
            doc["observed_at_ms"] += 10
            snap_path.write_text(json.dumps(doc), encoding="utf-8")
            # Re-seal the manifest to its new byte pin; the embedded snapshot seal remains invalid.
            manifest_doc = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_doc["snapshot_file_sha256"] = watchdog.digest(snap_path.read_bytes())
            manifest_doc = seal(manifest_doc, "manifest_sha256")
            manifest.write_bytes(watchdog.canonical(manifest_doc))
            result = pilot.SnapshotReader(manifest, watchdog.digest(manifest.read_bytes())).view
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["refusal_reason"], "SNAPSHOT_SEAL_INVALID")

    def test_timestamp_watermark_and_overall_state_conflicts_fail_closed(self):
        for mutate, code in (
            (lambda doc: doc["lanes"]["daily"].update(observed_at_ms=doc["observed_at_ms"] + 1),
             "LANE_TIMESTAMP_CONFLICT"),
            (lambda doc: doc["registry"]["counters"].update(event_watermark=-1),
             "REGISTRY_WATERMARK_INVALID"),
            (lambda doc: doc.update(state="HEALTHY_PROGRESS"), "OVERALL_LANE_STATE_CONFLICT"),
        ):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                doc = snapshot()
                body = {k: v for k, v in doc.items() if k != "sha256"}
                mutate(body)
                manifest, pin = write_fixture(root, seal(body, "sha256"))
                result = pilot.SnapshotReader(manifest, pin).view
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["refusal_reason"], code)

    def test_expected_wait_and_stale_never_promote_to_healthy(self):
        lanes = snapshot()["lanes"]
        self.assertEqual(pilot.map_state("EXPECTED_WAIT", "daily"), "EXPECTED_WAIT")
        self.assertEqual(pilot.map_state("STALLED", "history"), "STALE")
        self.assertEqual(pilot.map_state("COMPLETE_WITH_GAPS", "history"), "STALE")
        self.assertEqual(pilot.map_state("CHECKPOINT_UNVERIFIED", "history"), "UNKNOWN")
        self.assertEqual(pilot.map_state("HEALTHY_PROGRESS", "live"), "HEALTHY")
        self.assertIsInstance(lanes, dict)

    def test_modern_and_legacy_protocol_read_only_surface(self):
        server = pilot.MCPServer(type("Reader", (), {"view": pilot.SnapshotReader.unavailable("TEST")}))
        modern_meta = {pilot.META_VERSION: pilot.MODERN, pilot.META_CAPABILITIES: {}}
        discover = server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                                   "params": {"_meta": modern_meta}})
        self.assertEqual(discover["result"]["supportedVersions"], [pilot.MODERN])
        self.assertEqual(discover["result"]["resultType"], "complete")
        listed = server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                                  "params": {"_meta": modern_meta}})
        self.assertEqual([x["name"] for x in listed["result"]["tools"]],
                         ["atlas.runtime.health", "atlas.lane.latest"])
        self.assertEqual(listed["result"]["ttlMs"], 0)
        called = server.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                  "params": {"name": "atlas.lane.latest", "arguments": {"lane": "live"},
                                             "_meta": modern_meta}})
        self.assertEqual(called["result"]["structuredContent"]["status"], "UNKNOWN")
        self.assertEqual(called["result"]["resultType"], "complete")
        denied = server.dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                  "params": {"name": "filesystem.read", "arguments": {"path": "C:\\"},
                                             "_meta": modern_meta}})
        self.assertEqual(denied["error"]["code"], -32602)
        legacy_server = pilot.MCPServer(type("Reader", (), {"view": pilot.SnapshotReader.unavailable("TEST")}))
        init = legacy_server.dispatch({"jsonrpc": "2.0", "id": 5, "method": "initialize",
                                       "params": {"protocolVersion": pilot.LEGACY, "capabilities": {},
                                                  "clientInfo": {"name": "fixture", "version": "1"}}})
        self.assertEqual(init["result"]["protocolVersion"], pilot.LEGACY)
        self.assertIsNone(legacy_server.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_only_fixed_resources_are_readable(self):
        server = pilot.MCPServer(type("Reader", (), {"view": pilot.SnapshotReader.unavailable("TEST")}))
        good = server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                                "params": {"uri": "atlas://lane/live"}})
        bad = server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                               "params": {"uri": "file:///secret"}})
        self.assertEqual(good["result"]["contents"][0]["uri"], "atlas://lane/live")
        self.assertEqual(bad["error"]["code"], -32602)
        self.assertNotIn("shutdown", json.dumps(pilot.tool_specs()))


if __name__ == "__main__":
    unittest.main()

