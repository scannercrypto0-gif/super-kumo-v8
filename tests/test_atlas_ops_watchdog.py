import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import atlas_ops_watchdog as watchdog
import atlas_mcp_pilot as mcp


def seal_doc(body, field):
    return {**body, field: watchdog.digest(watchdog.canonical(body))}


def evidence():
    source = seal_doc(dict(schema="aql.research.warehouse-source.v1",
                           key="data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-1970-01-02.zip",
                           source_zip_sha256="c" * 64, checksum_sha256="f" * 64, rows=100,
                           publisher_integrity="ZIP_CHECKSUM_MATCH", trading_authority="NONE"),
                      "receipt_sha256")
    registry = seal_doc(dict(
        schema="aql.warehouse.registry-snapshot.v1", version=1,
        dataset_id="BINANCE_VISION:SPOT:BTCUSDT:1m:RETROSPECTIVE_NON_PIT",
        event_watermark=4, event_head_sha256="a" * 64, as_of_ms=2_000_000,
        physical_interval="1m", physical_rows=100, first_open_ms=1_000_000,
        last_open_ms=6_940_000, covered_intervals=[[1_000_000, 7_000_000]],
        internal_gaps=[], archive_unavailable_boundaries=[], conflicts=[],
        sources=[dict(source_receipt_sha256=source["receipt_sha256"], source_zip_sha256="c" * 64,
                      key=source["key"],
                      rows=100, first_open_ms=1_000_000, last_open_ms=6_940_000,
                      derivation=None)], physical_data_bytes={}, storage_accounting="DATA_FILES_ONLY",
        projected_intervals={}, projections_physically_stored=False,
        source_class="RETROSPECTIVE_NON_PIT", forward_status="FORWARD_UNQUALIFIED",
        scientific_status="REAL_PIT_OOS_BLOCKED", research_eligibility="RETROSPECTIVE_COVERED_WINDOWS_ONLY",
        trading_authority="NONE"), "snapshot_sha256")
    history = dict(schema="aql.warehouse.full-history-continuation.v1", status="BOUNDED_PROGRESS_MORE_PARTITIONS_PENDING",
                   trading_authority="NONE", full_history_verified=False,
                   started_ms=1_000_000, finished_ms=1_500_000,
                   archives_imported=3, inserted_rows=100,
                   all_published_partitions_ingested=False, source_scan_exhausted=False,
                   latest_published_close_reached=False, unresolved_gap_ranges=[],
                   unresolved_source_obstacles=[], receipt_file="d" * 64 + ".json")
    daily = dict(schema="aql.recurring-runtime.health.v1", source_cadence="DAILY_UTC", trading_authority="NONE",
                 current_entry="NO_CURRENT_ENTRY", observed_at_ms=100_000_000,
                 cycle_evidence="RECENT_RESEARCH_RECEIPT", tick_freshness="RECENT",
                 source_freshness="LATEST_DUE_DAY_RECEIVED", next_check_ms=300_000_000,
                  last_success=dict(source_day_ms=86_400_000, source_zip_sha256="c" * 64,
                                    checksum_sha256="f" * 64,
                                    daily_source_evidence_status="VERIFIED",
                                    daily_worker_receipt_sha256="2" * 64,
                                    receipts=["2" * 64]),
                  last_failure=None)
    daily_import = dict(status="ARCHIVE_IMPORTED", source_sha256="c" * 64,
                        key=source["key"], inserted_rows=100)
    live = dict(schema="atlas.ws.continuous-report.v1", status="OBSERVING_CONTINUOUS_ACCEPTANCE",
                source_class="LIVE_CAPTURE", trading_authority="NONE", orders=0,
                as_of_ms=2_000_000, verified_receipts=3, last_committed_ms=1_800_000,
                last_receipt_fresh=True, verified_receipt_sha256=["2" * 64],
                missing_open_ranges=[], hold_reason=None)
    return registry, history, daily, daily_import, source, live


def pins(values):
    return [watchdog.digest(watchdog.canonical(value)) for value in values]


def build(values, *, now=200_000_000, mono=10, prev=None):
    p = pins(values)
    return watchdog.build(*values, registry_pin=p[0], history_pin=p[1], daily_pin=p[2],
                          daily_import_pin=p[3], daily_source_pin=p[4], live_pin=p[5],
                          now_ms=now, monotonic_ns=mono, boot_id="boot-test", deployed_sha="3" * 40,
                          clock_uncertainty_ms=50, previous=prev)


class WatchdogTests(unittest.TestCase):
    def test_first_observation_is_unknown_and_redacted(self):
        values = evidence()
        result = build(values)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertTrue(all(lane["state"] == "UNKNOWN" for lane in result["lanes"].values()))
        self.assertEqual(result["registry"]["gaps"], 0)
        self.assertFalse(result["source_paths_exposed"])
        self.assertNotIn("E:\\", json.dumps(result))


    def test_second_observation_detects_durable_progress(self):
        values = evidence()
        first = build(values)
        values[0]["physical_rows"] += 5
        values[0]["sources"][0]["rows"] += 5
        values[0]["snapshot_sha256"] = watchdog.digest(watchdog.canonical(
            {k: v for k, v in values[0].items() if k != "snapshot_sha256"}))
        values[1]["inserted_rows"] += 5
        second = build(values, now=200_060_000, mono=60_000_000_010, prev=first)
        self.assertEqual(second["lanes"]["history"]["state"], "HEALTHY_PROGRESS")


    def test_malformed_registry_fails_closed(self):
        values = evidence()
        values[0]["physical_rows"] += 1
        with self.assertRaisesRegex(ValueError, "REGISTRY_SNAPSHOT_SEAL"):
            build(values)


    def test_existing_history_checkpoint_is_read_as_unverified_progress_evidence(self):
        view = watchdog.history_view(dict(
            schema="aql.warehouse.full-history-checkpoint.v1",
            source_class="RETROSPECTIVE_NON_PIT", trading_authority="NONE",
            full_history_verified=False, accepted_prefix_unchanged=True,
            archives_this_run=198, inserted_rows_this_run=4_266_757,
            continuation_ref="https://github.com/example/repo/pull/330#issuecomment-1"))
        self.assertEqual(view["status"], "CHECKPOINT_UNVERIFIED")
        self.assertEqual(view["counters"]["inserted_rows"], 4_266_757)


    def test_daily_native_report_links_worker_receipt_import_and_registry(self):
        values = evidence()
        result = build(values)
        self.assertTrue(result["lanes"]["daily"]["source_receipt_link_verified"])
        success = result["lanes"]["daily"]["last_success"]
        self.assertEqual(success["daily_worker_receipt_sha256"], "2" * 64)
        self.assertEqual(success["source_receipt_sha256"], values[4]["receipt_sha256"])
        self.assertEqual(success["warehouse_receipt_sha256"],
                         watchdog.digest(watchdog.canonical(values[3])))


    def test_daily_native_report_without_verified_worker_receipt_is_unknown(self):
        values = list(evidence())
        values[2]["last_success"].pop("daily_source_evidence_status")
        first = build(values)
        second = build(values, now=2_060_000, mono=60_000_000_010, prev=first)
        self.assertFalse(second["lanes"]["daily"]["source_receipt_link_verified"])
        self.assertEqual(second["lanes"]["daily"]["state"], "UNKNOWN")

    def assert_worker_proof_required(self, values):
        first = build(values)
        second = build(values, now=200_060_000, mono=60_000_000_010, prev=first)
        self.assertFalse(second["lanes"]["daily"]["source_receipt_link_verified"])
        self.assertEqual(second["lanes"]["daily"]["state"], "UNKNOWN")
        self.assertEqual(second["state"], "UNKNOWN")
        projected = mcp.SnapshotReader.project(second, "e" * 64)
        self.assertEqual(projected["lanes"]["daily"]["status"], "UNKNOWN")
        self.assertNotEqual(projected["status"], "HEALTHY")
        self.assertEqual(projected["trading_authority"], "NONE")

    def test_legacy_import_pin_cannot_replace_daily_worker_proof(self):
        values = list(evidence())
        values[2]["last_success"]["warehouse_receipt_sha256"] = watchdog.digest(
            watchdog.canonical(values[3]))
        values[2]["last_success"].pop("daily_source_evidence_status")
        values[2]["last_success"].pop("daily_worker_receipt_sha256")
        values[2]["last_success"]["receipts"] = []
        self.assert_worker_proof_required(values)

    def test_warehouse_report_schema_cannot_replace_daily_worker_proof(self):
        values = list(evidence())
        imported = dict(status="ARCHIVE_IMPORTED", source_sha256=values[4]["source_zip_sha256"],
                        key=values[4]["key"], inserted_rows=100)
        values[3] = dict(schema="aql.research.warehouse-report.v1", this_run=[imported])
        values[2]["last_success"].pop("daily_source_evidence_status")
        values[2]["last_success"].pop("daily_worker_receipt_sha256")
        values[2]["last_success"]["receipts"] = []
        self.assert_worker_proof_required(values)

    def test_daily_source_day_must_match_archive_utc_date(self):
        values = list(evidence())
        values[2]["last_success"]["source_day_ms"] += 86_400_000
        first = build(values)
        second = build(values, now=200_060_000, mono=60_000_000_010, prev=first)
        self.assertFalse(second["lanes"]["daily"]["source_receipt_link_verified"])
        self.assertEqual(second["lanes"]["daily"]["state"], "UNKNOWN")
        self.assertNotEqual(second["state"], "HEALTHY_PROGRESS")

    def test_daily_missing_original_to_commit_link_is_unknown(self):
        values = evidence()
        values[4].pop("checksum_sha256")
        first = build(values)
        second = build(values, now=2_060_000, mono=60_000_000_010, prev=first)
        self.assertEqual(second["lanes"]["daily"]["state"], "UNKNOWN")
        self.assertEqual(second["lanes"]["daily"]["reason"], "DAILY_SOURCE_LINKAGE_UNPROVEN")


    def test_live_hold_is_never_reported_healthy(self):
        values = evidence()
        values[5]["hold_reason"] = "PILOT_STOP_ConnectionResetError"
        first = build(values)
        second = build(values, now=2_060_000, mono=60_000_000_010, prev=first)
        self.assertEqual(second["lanes"]["live"]["state"], "HOLD")


    def test_snapshot_is_create_only_and_input_unchanged(self):
        before = evidence()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for i, value in enumerate(before):
                path = root / f"input-{i}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            raw_before = [p.read_bytes() for p in paths]
            result = build(before)
            output = root / "health.json"
            watchdog.publish(output, result)
            self.assertEqual(output.read_bytes(), watchdog.canonical(result))
            self.assertEqual([p.read_bytes() for p in paths], raw_before)
            with self.assertRaisesRegex(ValueError, "OUTPUT_ALREADY_SEALED"):
                watchdog.publish(output, {**result, "state": "FAILED"})

    def test_cli_uses_only_explicit_pinned_files(self):
        values = evidence()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, history, daily, daily_import, daily_source, live = values
            inputs = {
                "registry": ("snapshot-" + registry["snapshot_sha256"] + ".json", registry),
                "history": (None, history),
                "daily": ("daily-health.json", daily),
                "daily-import": (None, daily_import),
                "daily-source": (daily_source["source_zip_sha256"] + ".json", daily_source),
                "live": ("live-report.json", live),
            }
            args = [sys.executable, "-B", str(ROOT / "tools" / "atlas_ops_watchdog.py")]
            for name, (filename, value) in inputs.items():
                raw = watchdog.canonical(value)
                if filename is None:
                    filename = watchdog.digest(raw) + ".json"
                path = root / filename
                path.write_bytes(raw)
                args.extend(("--" + name, str(path)))
            output = root / "operator" / "health.json"
            args.extend(("--output", str(output), "--deployed-sha", "3" * 40))
            result = subprocess.run(args, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["schema"], "atlas.operator.health-snapshot.v1")
            self.assertEqual(snapshot["source_mutations"], 0)

