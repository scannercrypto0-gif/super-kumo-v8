import json
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests")]
import atlas_mcp_pilot as pilot
import atlas_ops_watchdog as watchdog
from test_atlas_ops_mcp_pilot import snapshot, write_fixture
from test_atlas_ops_watchdog import evidence, build


def healthy_snapshot():
    doc = snapshot()
    doc.update(observed_at_ms=1_000_000, clock_uncertainty_ms=50, state="HEALTHY_PROGRESS")
    doc["registry"].update(gaps=0, unavailable=0, conflicts=0)
    doc["registry"]["counters"].update(source_count=1, last_open_ms=999_000)
    doc["lanes"]["history"].update(state="HEALTHY_PROGRESS", finished_ms=1_000_000,
                                   unresolved_gaps=0, obstacles=0)
    doc["lanes"]["daily"].update(state="HEALTHY_PROGRESS", observed_at_ms=1_000_000,
                                 source_receipt_link_verified=True,
                                 last_success={"source_day_ms": 999_000, "source_rows": 100,
                                               "inserted_rows": 100})
    doc["lanes"]["live"].update(state="HEALTHY_PROGRESS", as_of_ms=1_000_000,
                                last_committed_ms=999_500, last_receipt_fresh=True,
                                hold_reason=None)
    return {**{k: v for k, v in doc.items() if k != "sha256"},
            "sha256": watchdog.digest(watchdog.canonical({k: v for k, v in doc.items() if k != "sha256"}))}


class FakeClock:
    def __init__(self, wall_ms):
        self.wall_ms = wall_ms
        self.mono_ns = 10_000_000_000

    def __call__(self):
        return self.wall_ms, self.mono_ns

    def advance(self, ms):
        self.wall_ms += ms
        self.mono_ns += ms * 1_000_000


class FreshnessTests(unittest.TestCase):
    def test_snapshot_becomes_stale_on_tools_and_resources_without_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, pin = write_fixture(Path(directory), healthy_snapshot())
            clock = FakeClock(1_001_000)
            server = pilot.MCPServer(pilot.SnapshotReader(manifest, pin), clock=clock)
            fresh = server.call_tool(1, {"name": "atlas.runtime.health", "arguments": {}}, False)
            self.assertEqual(fresh["result"]["structuredContent"]["status"], "HEALTHY")
            clock.advance(pilot.MAX_SNAPSHOT_AGE_MS + 1)
            stale = server.call_tool(2, {"name": "atlas.runtime.health", "arguments": {}}, False)
            self.assertEqual(stale["result"]["structuredContent"]["status"], "STALE")
            lane = server.call_tool(3, {"name": "atlas.lane.latest", "arguments": {"lane": "daily"}}, False)
            self.assertEqual(lane["result"]["structuredContent"]["status"], "STALE")
            resource = server.read_resource(4, {"uri": "atlas://runtime/health"}, False)
            self.assertEqual(json.loads(resource["result"]["contents"][0]["text"])["status"], "STALE")

    def test_future_snapshot_and_backwards_clock_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, pin = write_fixture(Path(directory), healthy_snapshot())
            future = pilot.MCPServer(pilot.SnapshotReader(manifest, pin), clock=FakeClock(999_999))
            result = future.call_tool(1, {"name": "atlas.runtime.health", "arguments": {}}, False)
            self.assertEqual(result["result"]["structuredContent"]["status"], "UNKNOWN")
            clock = FakeClock(1_001_000)
            server = pilot.MCPServer(pilot.SnapshotReader(manifest, pin), clock=clock)
            clock.wall_ms -= 1
            clock.mono_ns += 1_000_000
            result = server.call_tool(2, {"name": "atlas.runtime.health", "arguments": {}}, False)
            self.assertEqual(result["result"]["structuredContent"]["status"], "UNKNOWN")

    def test_same_path_snapshot_replacement_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, pin = write_fixture(root, healthy_snapshot())
            reader = pilot.SnapshotReader(manifest, pin)
            snap_path = root / "sealed-snapshot.json"
            altered = healthy_snapshot()
            altered["observed_at_ms"] += 1
            altered = {**{k: v for k, v in altered.items() if k != "sha256"},
                       "sha256": watchdog.digest(watchdog.canonical({k: v for k, v in altered.items() if k != "sha256"}))}
            snap_path.write_bytes(watchdog.canonical(altered))
            self.assertEqual(reader.read_pinned()["status"], "UNKNOWN")

    def test_registry_conflicts_block_builder_and_projection(self):
        values = list(evidence())
        first = build(values)
        values[0]["physical_rows"] += 1
        values[0]["sources"][0]["rows"] += 1
        values[0]["snapshot_sha256"] = watchdog.digest(watchdog.canonical(
            {k: v for k, v in values[0].items() if k != "snapshot_sha256"}))
        values[1]["inserted_rows"] += 1
        healthy = build(values, now=2_060_000, mono=60_000_000_010, prev=first)
        self.assertEqual(healthy["lanes"]["history"]["state"], "HEALTHY_PROGRESS")
        values[0]["conflicts"] = [{"reason": "synthetic-test"}]
        values[0]["snapshot_sha256"] = watchdog.digest(watchdog.canonical(
            {k: v for k, v in values[0].items() if k != "snapshot_sha256"}))
        produced = build(values, now=2_120_000, mono=120_000_000_010, prev=healthy)
        self.assertEqual(produced["lanes"]["history"]["state"], "UNKNOWN")
        self.assertEqual(produced["state"], "UNKNOWN")
        projected = healthy_snapshot()
        projected["registry"]["conflicts"] = 1
        projected = {**{k: v for k, v in projected.items() if k != "sha256"},
                     "sha256": watchdog.digest(watchdog.canonical({k: v for k, v in projected.items() if k != "sha256"}))}
        with tempfile.TemporaryDirectory() as directory:
            manifest, pin = write_fixture(Path(directory), projected)
            view = pilot.SnapshotReader(manifest, pin).view
        self.assertEqual(view["status"], "STALE")
        self.assertEqual(view["lanes"]["history"]["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
