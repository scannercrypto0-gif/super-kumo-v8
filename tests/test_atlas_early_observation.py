"""Bounded EARLY_OBSERVATION profile and local stdio contract tests."""
import json
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import atlas_early_observation as early
import atlas_ops_watchdog as watchdog


NOW = 172_800_000
BOOT = "synthetic-test-boot"


def sealed(doc, field):
    body = dict(doc)
    body.pop(field, None)
    doc[field] = watchdog.digest(watchdog.canonical(body))
    return doc


def registry(now=NOW, watermark=10, rows=100):
    return sealed({
        "schema": "aql.warehouse.registry-snapshot.v1",
        "version": 1,
        "as_of_ms": now,
        "event_watermark": watermark,
        "event_head_sha256": "1" * 64,
        "physical_rows": rows,
        "first_open_ms": now - rows * 60_000,
        "last_open_ms": now - 60_000,
        "internal_gaps": [],
        "archive_unavailable_boundaries": [],
        "conflicts": [],
        "sources": [{"source_zip_sha256": "2" * 64, "source_receipt_sha256": "3" * 64,
                     "rows": rows, "first_open_ms": now - rows * 60_000,
                     "last_open_ms": now - 60_000}],
        "source_class": "RETROSPECTIVE_NON_PIT",
        "trading_authority": "NONE",
    }, "snapshot_sha256")


def history(now=NOW, archives=4, rows=100):
    return {
        "schema": "aql.warehouse.full-history-continuation.v1",
        "trading_authority": "NONE",
        "full_history_verified": False,
        "started_ms": now - 60_000,
        "finished_ms": now,
        "archives_imported": archives,
        "inserted_rows": rows,
        "all_published_partitions_ingested": False,
        "source_scan_exhausted": False,
        "latest_published_close_reached": False,
        "unresolved_gap_ranges": [],
        "unresolved_source_obstacles": [],
        "continuation_ref": "immutable-continuation-token",
        "status": "CONTINUING",
    }


def daily(now=NOW, *, wait=False):
    return {
        "schema": "aql.recurring-runtime.health.v1",
        "source_cadence": "DAILY_UTC",
        "trading_authority": "NONE",
        "current_entry": "NO_CURRENT_ENTRY",
        "observed_at_ms": now,
        "task_state": "Ready",
        "scheduler_state": "Ready",
        "runtime_state": "PIN_VERIFIED",
        "cycle_evidence": "WAIT_FOR_SOURCE" if wait else "RECENT_RESEARCH_RECEIPT",
        "source_freshness": "LATEST_DUE_DAY_RECEIVED",
        "next_check_ms": now + 60_000 if wait else None,
        "last_failure": None,
        "last_success": {"status": "COMPLETE", "exit_code": 0, "source_day_ms": now - 86_400_000,
                         "daily_worker_receipt_sha256": "4" * 64},
    }



def daily_linked(now=NOW, *, source_zip="2" * 64, source_day=None):
    report = daily(now)
    day = now - 86_400_000 if source_day is None else source_day
    worker_receipt = "4" * 64
    report["last_success"].update({
        "source_day_ms": day,
        "daily_source_evidence_status": "VERIFIED",
        "daily_worker_receipt_sha256": worker_receipt,
        "receipts": [worker_receipt],
        "source_zip_sha256": source_zip,
        "checksum_sha256": "8" * 64,
    })
    return report


def live(now=NOW, *, hold=False, committed=None, receipts=2, receipt="5" * 64,
         config="6" * 64):
    return {
        "schema": "atlas.ws.continuous-report.v1",
        "source_class": "LIVE_CAPTURE",
        "trading_authority": "NONE",
        "orders": 0,
        "status": "HELD" if hold else "OBSERVING_CONTINUOUS_ACCEPTANCE",
        "hold_reason": "PILOT_STOP_SAMPLE_HOLD" if hold else None,
        "as_of_ms": now,
        "verified_receipts": receipts,
        "last_committed_ms": committed if committed is not None else now - 60_000,
        "last_receipt_fresh": not hold,
        "verified_receipt_sha256": [receipt] * receipts,
        "missing_open_ranges": [],
        "config_sha256": config,
        "policy_sha256": "7" * 64,
    }


def write_doc(root, name, doc):
    path = root / f"{name}.json"
    path.write_bytes(watchdog.canonical(doc))
    return path


def paths_for(root, *, hist=None, reg=None, day=None, ws=None, previous=None):
    return {
        "history": write_doc(root, "history", hist) if hist is not None else None,
        "registry": write_doc(root, "registry", reg) if reg is not None else None,
        "daily": write_doc(root, "daily", day) if day is not None else None,
        "live": write_doc(root, "live", ws) if ws is not None else None,
        "previous": previous,
    }


class EarlyObservationTests(unittest.TestCase):
    def build(self, paths, now=NOW, mono=1_000_000_000, previous=None, uncertainty=100):
        return early.build(paths, now_ms=now, monotonic_ns=mono, boot_id=BOOT,
                           clock_uncertainty_ms=uncertainty, previous=previous)

    def test_missing_reports_are_absence_unknown_not_fake_pins(self):
        result = self.build({})
        self.assertEqual(result["profile"], "EARLY_OBSERVATION")
        self.assertEqual(result["state"], "UNKNOWN")
        for lane in result["lanes"].values():
            self.assertEqual(lane["status"], "UNKNOWN")
            self.assertIsNone(lane["source_file_sha256"])
        self.assertEqual(result["trading_authority"], "NONE")
        self.assertFalse(result["source_paths_exposed"])

    def test_worker_success_without_import_registry_link_stays_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), day=daily(wait=False))
            result = self.build(paths)
        self.assertEqual(result["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertEqual(result["lanes"]["daily"]["reason"], "DAILY_IMPORT_REGISTRY_LINK_NOT_SUPPLIED")

    def test_disabled_daily_task_cannot_be_healthy(self):
        report = daily_linked()
        report["task_state"] = "Disabled"
        with tempfile.TemporaryDirectory() as folder:
            result = self.build(paths_for(Path(folder), day=report, reg=registry()))
        self.assertEqual(result["lanes"]["daily"]["status"], "FAILED")
        self.assertEqual(result["lanes"]["daily"]["reason"], "DAILY_SCHEDULER_DISABLED")

    def test_daily_success_requires_verified_source_and_registry_link(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), day=daily_linked(), reg=registry())
            result = self.build(paths)
        lane = result["lanes"]["daily"]
        self.assertEqual(lane["status"], "HEALTHY_PROGRESS")
        self.assertEqual(lane["reason"], "DAILY_SOURCE_RECEIPT_LINKED_TO_REGISTRY")
        self.assertEqual(lane["reported"]["registry_link"]["registry_source_receipt_sha256"], "3" * 64)
        self.assertEqual(lane["reported"]["registry_link"]["source_zip_sha256"], "2" * 64)
        self.assertEqual(lane["reported"]["source_age_ms"], 86_400_000)

    def test_daily_verified_source_without_matching_registry_stays_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), day=daily_linked(source_zip="9" * 64), reg=registry())
            result = self.build(paths)
        lane = result["lanes"]["daily"]
        self.assertEqual(lane["status"], "UNKNOWN")
        self.assertEqual(lane["reason"], "DAILY_REGISTRY_APPEND_NOT_VERIFIED")

    def test_daily_verified_source_with_stale_registry_stays_stale(self):
        stale_registry = registry(now=NOW - early.MAX_SNAPSHOT_AGE_MS - 1)
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), day=daily_linked(), reg=stale_registry)
            result = self.build(paths)
        lane = result["lanes"]["daily"]
        self.assertEqual(lane["status"], "STALE")
        self.assertEqual(lane["reason"], "DAILY_REGISTRY_REPORT_STALE_OR_UNTRUSTED")

    def test_expected_wait_requires_valid_next_check_and_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), day=daily(wait=True))
            result = self.build(paths)
            self.assertEqual(result["lanes"]["daily"]["status"], "EXPECTED_WAIT")
            uncertain = self.build(paths, uncertainty=None)
        self.assertEqual(uncertain["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertEqual(uncertain["state"], "UNKNOWN")

    def test_expired_and_future_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            stale_paths = paths_for(Path(folder), day=daily(now=NOW - early.MAX_SNAPSHOT_AGE_MS - 1))
            stale = self.build(stale_paths)
        self.assertEqual(stale["lanes"]["daily"]["status"], "STALE")
        with tempfile.TemporaryDirectory() as folder:
            future_paths = paths_for(Path(folder), day=daily(now=NOW + 1))
            future = self.build(future_paths)
        self.assertEqual(future["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertEqual(future["lanes"]["daily"]["reason"], "SOURCE_TIME_IN_FUTURE")

    def test_live_wait_requires_a_bounded_schedule(self):
        report = live()
        report["status"] = "AWAITING_EXISTING_SCHEDULE"
        with tempfile.TemporaryDirectory() as folder:
            unknown = self.build(paths_for(Path(folder), ws=report))
        self.assertEqual(unknown["lanes"]["live"]["status"], "UNKNOWN")
        self.assertEqual(unknown["lanes"]["live"]["reason"], "LIVE_WAIT_CADENCE_UNVERIFIED")
        report["next_check_ms"] = NOW + 60_000
        with tempfile.TemporaryDirectory() as folder:
            expected = self.build(paths_for(Path(folder), ws=report))
        self.assertEqual(expected["lanes"]["live"]["status"], "EXPECTED_WAIT")

    def test_mcp_projection_redacts_untrusted_snapshot_fields(self):
        import copy
        import atlas_mcp_pilot as pilot

        secret = r"C:\\private\\credential.txt"
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), hist=history(), reg=registry(),
                              day=daily(), ws=live())
            snapshot = self.build(paths)
        snapshot = copy.deepcopy(snapshot)
        daily_report = snapshot["lanes"]["daily"]["reported"]
        daily_report["task_state"] = secret
        daily_report["cycle_evidence"] = {"credential": secret}
        daily_report["last_success_source_day_ms"] = {"raw": secret}
        live_report = snapshot["lanes"]["live"]["reported"]
        live_report["status"] = secret
        live_report["hold_reason"] = secret
        snapshot["lanes"]["live"]["scope"] = secret
        snapshot["lanes"]["live"]["source_schema"] = secret
        snapshot["lanes"]["live"]["freshness"] = secret
        snapshot["lanes"]["live"]["reason"] = secret
        snapshot["clock_uncertainty_ms"] = secret
        view = pilot.SnapshotReader.project_early(snapshot, "a" * 64)
        encoded = json.dumps(view, sort_keys=True)
        self.assertNotIn(secret, encoded)
        self.assertEqual(view["lanes"]["daily"]["last_validated_committed_progress"]["task_state"],
                         "UNRECOGNIZED")
        self.assertIsNone(view["lanes"]["daily"]["last_validated_committed_progress"]["last_success_source_day_ms"])
        self.assertEqual(view["lanes"]["live"]["last_validated_committed_progress"]["status"],
                         "UNRECOGNIZED")
        self.assertEqual(view["lanes"]["live"]["scope"], "WORK1_HANDOFF_REPORT_ONLY")
        self.assertEqual(view["lanes"]["live"]["provenance"]["source_schema"], "UNRECOGNIZED_SCHEMA")
        self.assertIsNone(view["clock_uncertainty_ms"])

    def test_untrusted_report_fields_are_allowlisted_before_snapshot(self):
        secret = r"C:\\private\\credentials\\access_token.txt"
        daily_report = daily()
        daily_report["task_state"] = secret
        daily_report["scheduler_state"] = {"token": "secret"}
        daily_report["runtime_state"] = "sk_live_untrusted"
        daily_report["cycle_evidence"] = {"payload": secret}
        daily_report["source_freshness"] = [secret]
        daily_report["last_success"]["source_day_ms"] = {"secret": secret}
        history_report = history()
        history_report["status"] = secret
        live_report = live()
        live_report["status"] = secret
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), hist=history_report, reg=registry(),
                              day=daily_report, ws=live_report)
            snapshot = self.build(paths)
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("sk_live_untrusted", encoded)
        self.assertEqual(snapshot["lanes"]["daily"]["reported"]["task_state"], "UNRECOGNIZED")
        self.assertIsNone(snapshot["lanes"]["daily"]["reported"]["last_success_source_day_ms"])
        self.assertEqual(snapshot["lanes"]["history"]["reported"]["status"], "UNRECOGNIZED")
        self.assertEqual(snapshot["lanes"]["live"]["reported"]["status"], "UNRECOGNIZED")

    def test_wait_beyond_one_day_stays_unknown(self):
        report = daily(wait=True)
        report["next_check_ms"] = NOW + early.MAX_EXPECTED_WAIT_MS + 1
        with tempfile.TemporaryDirectory() as folder:
            result = self.build(paths_for(Path(folder), day=report))
        self.assertEqual(result["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertEqual(result["lanes"]["daily"]["reason"], "DAILY_WAIT_CADENCE_UNVERIFIED")

    def test_cli_refuses_inputs_outside_approved_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_root = root / "input"
            output_root = root / "output"
            input_root.mkdir()
            output_root.mkdir()
            outside = write_doc(root, "outside-report", daily())
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools" / "atlas_early_observation.py"),
                "--approved-input-root", str(input_root),
                "--approved-output-root", str(output_root),
                "--daily", str(outside), "--output", str(output_root / "snapshot.json"),
            ], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INPUT_OUTSIDE_APPROVED_ROOT", result.stderr)

    def test_reported_daily_failure_is_failed_and_sanitized(self):
        report = daily()
        report["last_failure"] = {"reason": "DAILY_IMPORT_FAILED"}
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), day=report)
            result = self.build(paths)
        lane = result["lanes"]["daily"]
        self.assertEqual(lane["status"], "FAILED")
        self.assertEqual(lane["reported"]["last_failure_reason"], "DAILY_FAILURE_REASON_REPORTED")

    def test_held_live_precedence_survives_other_unknown_lanes(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), ws=live(hold=True))
            result = self.build(paths)
        self.assertEqual(result["lanes"]["live"]["status"], "HELD")
        self.assertEqual(result["state"], "HELD")

    def test_two_observations_report_only_committed_progress_for_same_sources(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_paths = paths_for(Path(first_dir), hist=history(), reg=registry(),
                                    day=daily(wait=True), ws=live())
            first = self.build(first_paths)
            now2 = NOW + early.MIN_REFRESH_INTERVAL_MS
            second_paths = paths_for(Path(second_dir),
                hist=history(now2, archives=5, rows=140),
                reg=registry(now2, watermark=11, rows=140),
                day=daily(now2, wait=True),
                ws=live(now2, committed=now2 - 30_000, receipts=3, receipt="8" * 64))
            second = self.build(second_paths, now=now2, mono=2_000_000_000,
                                previous=first)
        self.assertEqual(second["lanes"]["history"]["status"], "HEALTHY_PROGRESS")
        self.assertEqual(second["lanes"]["live"]["status"], "HEALTHY_PROGRESS")
        self.assertEqual(second["lanes"]["daily"]["status"], "EXPECTED_WAIT")
        self.assertEqual(second["state"], "HEALTHY_PROGRESS")

    def test_live_source_change_is_not_same_session_progress(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_paths = paths_for(Path(first_dir), ws=live())
            first = self.build(first_paths)
            now2 = NOW + early.MIN_REFRESH_INTERVAL_MS
            second_paths = paths_for(Path(second_dir),
                ws=live(now2, committed=now2 - 1_000, receipts=3, receipt="9" * 64, config="a" * 64))
            second = self.build(second_paths, now=now2, mono=2_000_000_000, previous=first)
        self.assertEqual(second["lanes"]["live"]["status"], "UNKNOWN")
        self.assertEqual(second["lanes"]["live"]["reason"], "SECOND_OBSERVATION_OR_SESSION_LINK_REQUIRED")

    def test_malformed_duplicate_key_is_unknown_without_untrusted_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "daily.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            result = self.build({"daily": path})
        self.assertEqual(result["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertIsNone(result["lanes"]["daily"]["source_file_sha256"])

    def test_input_and_total_budgets_refuse_oversized_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "large.json"
            path.write_bytes(b" " * (early.MAX_FILE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "INPUT_BUDGET_EXCEEDED"):
                self.build({"daily": path})

    def test_create_only_output_and_profile_manifest_stdio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_root = root / "approved-input"
            output_root = root / "approved-output"
            input_root.mkdir()
            output_root.mkdir()
            snapshot = self.build({}, now=time.time_ns() // 1_000_000)
            snap_path = output_root / "early.json"
            early.publish(snap_path, snapshot)
            with self.assertRaisesRegex(ValueError, "OUTPUT_CREATE_ONLY_PATH_REQUIRED"):
                early.publish(snap_path, snapshot)
            manifest = output_root / "manifest.json"
            made = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "atlas_mcp_manifest.py"),
                                   "--profile", "early", "--approved-output-root", str(output_root),
                                   "--snapshot", str(snap_path), "--output", str(manifest)], capture_output=True, text=True, timeout=10)
            self.assertEqual(made.returncode, 0, made.stderr)
            pin = made.stdout.strip()
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                            "clientInfo": {"name": "early-fixture", "version": "1"}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "atlas.runtime.health", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                 "params": {"name": "atlas.lane.latest", "arguments": {"lane": "live"}}},
                {"jsonrpc": "2.0", "id": 6, "method": "resources/read",
                 "params": {"uri": "atlas://runtime/health"}},
                {"jsonrpc": "2.0", "id": 7, "method": "resources/read",
                 "params": {"uri": "atlas://lane/history"}},
                {"jsonrpc": "2.0", "id": 8, "method": "resources/read",
                 "params": {"uri": "atlas://lane/daily"}},
                {"jsonrpc": "2.0", "id": 9, "method": "resources/read",
                 "params": {"uri": "atlas://lane/live"}},
                {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                 "params": {"name": "atlas.source.write", "arguments": {"path": "private-file"}}},
                {"jsonrpc": "2.0", "id": 11, "method": "resources/read",
                 "params": {"uri": "file:///private/credential.txt"}},
            ]
            proc = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "atlas_mcp_pilot.py"),
                                   "--profile", "early", "--approved-output-root", str(output_root),
                                   "--manifest", str(manifest), "--manifest-sha256", pin],
                                  input="".join(json.dumps(x) + "\n" for x in requests),
                                  capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(len(responses), 11)
        listed_tools = {item["name"] for item in responses[1]["result"]["tools"]}
        self.assertEqual(listed_tools, {"atlas.runtime.health", "atlas.lane.latest"})
        listed_resources = {item["uri"] for item in responses[2]["result"]["resources"]}
        self.assertEqual(listed_resources, {
            "atlas://runtime/health", "atlas://lane/history",
            "atlas://lane/daily", "atlas://lane/live"})
        self.assertEqual(responses[3]["result"]["structuredContent"]["schema"],
                         "atlas.mcp.early-observation.v1")
        self.assertEqual(responses[3]["result"]["structuredContent"]["status"], "UNKNOWN")
        self.assertEqual(responses[3]["result"]["structuredContent"]["trading_authority"], "NONE")
        self.assertEqual(responses[4]["result"]["structuredContent"]["lane"], "live")
        self.assertEqual({responses[i]["result"]["contents"][0]["uri"] for i in range(5, 9)},
                         listed_resources)
        self.assertIn("error", responses[9])
        self.assertIn("error", responses[10])

    def test_mcp_request_ttl_stales_early_progress_but_keeps_absence_unknown(self):
        import atlas_mcp_pilot as pilot

        class Reader:
            profile = "early"

            def read_pinned(self):
                return {
                    "schema": "atlas.mcp.early-observation.v1",
                    "profile": "EARLY_OBSERVATION",
                    "status": "HEALTHY_PROGRESS",
                    "observed_at_ms": NOW,
                    "clock_uncertainty_ms": 10,
                    "lanes": {
                        "history": {"status": "HEALTHY_PROGRESS", "source_file_sha256": "a" * 64},
                        "daily": {"status": "UNKNOWN", "source_file_sha256": None},
                        "live": {"status": "EXPECTED_WAIT", "source_file_sha256": "b" * 64},
                    },
                }

        tick = [NOW + early.MAX_SNAPSHOT_AGE_MS + 1, 5_000_000_000]
        server = pilot.MCPServer(Reader(), clock=lambda: (tick[0], tick[1]))
        view = server.current_view()
        self.assertEqual(view["status"], "STALE")
        self.assertEqual(view["lanes"]["history"]["status"], "STALE")
        self.assertEqual(view["lanes"]["live"]["status"], "STALE")
        self.assertEqual(view["lanes"]["daily"]["status"], "UNKNOWN")

    def test_mcp_request_error_preserves_early_schema(self):
        import atlas_mcp_pilot as pilot

        class BrokenReader:
            profile = "early"

            def read_pinned(self):
                raise ValueError("SYNTHETIC_READER_FAILURE")

            @staticmethod
            def unavailable(reason, early=False):
                return pilot.SnapshotReader.unavailable(reason, early=early)

        server = pilot.MCPServer(BrokenReader(), clock=lambda: (NOW, 1_000_000_000))
        view = server.current_view()
        self.assertEqual(view["schema"], "atlas.mcp.early-observation.v1")
        self.assertEqual(view["status"], "UNKNOWN")

    def test_symlink_input_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = write_doc(root, "daily-real", daily())
            link = root / "daily-link.json"
            try:
                link.symlink_to(original)
            except OSError:
                self.skipTest("symlinks unavailable on this runner")
            result = self.build({"daily": link})
        self.assertEqual(result["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertIsNone(result["lanes"]["daily"]["source_file_sha256"])

    def test_replacement_between_stat_and_open_is_rejected(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = write_doc(root, "daily", daily())
            replacement = write_doc(root, "replacement", daily(NOW - 1))
            original_open = Path.open
            replaced = False

            def replace_before_open(path, *args, **kwargs):
                nonlocal replaced
                if path == target and not replaced:
                    replacement.replace(target)
                    replaced = True
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", replace_before_open):
                with self.assertRaisesRegex(ValueError, "INPUT_REPLACED"):
                    early.read_bounded(target)

    def test_fixture_resource_budget_is_measured_and_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = paths_for(Path(folder), hist=history(), reg=registry(),
                              day=daily(wait=True), ws=live())
            tracemalloc.start()
            started = time.perf_counter_ns()
            result = self.build(paths)
            elapsed_ms = (time.perf_counter_ns() - started) // 1_000_000
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        self.assertLessEqual(elapsed_ms, early.MAX_REFRESH_WALL_MS)
        self.assertLessEqual(result["measurements"]["refresh_cpu_ms"], early.MAX_REFRESH_CPU_MS)
        self.assertLess(peak, 32 * 1024 * 1024)
        self.assertLessEqual(result["measurements"]["input_bytes"], early.MAX_TOTAL_BYTES)
        print("EARLY_RESOURCE_METRICS " + json.dumps({
            "input_files": result["measurements"]["input_files"],
            "input_bytes": result["measurements"]["input_bytes"],
            "refresh_wall_ms": elapsed_ms,
            "refresh_cpu_ms": result["measurements"]["refresh_cpu_ms"],
            "python_peak_bytes": peak,
            "fixture_limit_python_peak_bytes": 32 * 1024 * 1024,
        }, sort_keys=True))

    def test_linked_inputs_and_path_traversal_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = write_doc(root, "daily-original", daily())
            hard = root / "daily-hardlink.json"
            try:
                hard.hardlink_to(original)
            except OSError:
                self.skipTest("hard links unavailable on this runner")
            result = self.build({"daily": hard})
            self.assertEqual(result["lanes"]["daily"]["status"], "UNKNOWN")
            self.assertIsNone(result["lanes"]["daily"]["source_file_sha256"])
            with self.assertRaisesRegex(ValueError, "OUTPUT_PATH_TRAVERSAL"):
                early.publish(Path("..") / "escape.json", self.build({}))

    def test_early_profile_contains_no_filesystem_or_market_database_access(self):
        source = (ROOT / "tools" / "atlas_early_observation.py").read_text(encoding="utf-8")
        for denied in ("sqlite3", "subprocess", "socket", "os.walk", "glob("):
            self.assertNotIn(denied, source)


if __name__ == "__main__":
    unittest.main()
