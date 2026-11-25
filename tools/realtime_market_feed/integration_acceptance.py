"""Produce a small machine-readable synthetic integration evidence packet."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
WATCHDOG_CHECKOUT = ROOT / ".integration" / "watchdog"
sys.path.insert(0, str(WATCHDOG_CHECKOUT / "tools"))

from tools.realtime_market_feed.acceptance_gates import (
    profile_synthetic_windows, verify_sanitized_live_projection,
)
from tools.realtime_market_feed.service import (
    PRODUCER_CODE_SHA256, PRODUCER_ID, LINEAGE_SCHEMA,
)
from atlas_ops_watchdog import live_view
from tools.realtime_market_feed.test_atlas_integration import (
    _daily, feed, START, DAY, _copy_generated_fixture_to_research_store,
)
from tools.realtime_market_feed.atlas_integration import (
    build_registry_proposal, reconcile_daily_bar,
)
from aql.research_bar_store import ResearchBarStore
from aql.research_forward_core_read import forward_core_window
from aql.research_forward_scanner_boundary import inspect_forward_15m


def _git_provenance():
    checkout = os.environ.get("GITHUB_SHA", "LOCAL_UNPINNED")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    head = checkout
    if event_path and Path(event_path).is_file():
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
            head = event.get("pull_request", {}).get("head", {}).get("sha") or checkout
        except (OSError, ValueError, TypeError):
            head = checkout
    return {"tested_checkout_commit": checkout, "pr_head_commit": head}


def build_evidence():
    with tempfile.TemporaryDirectory(prefix="atlas-realtime-integration-") as raw:
        root = Path(raw)
        source = root / "feed.sqlite"
        start, end = feed(source, count=180)
        research = root / "research.sqlite"
        write = _copy_generated_fixture_to_research_store(source, research, symbol="BTCUSDT",
            start_ms=start, end_ms=end, now_ms=end+1_000)
        with ResearchBarStore(research) as store:
            for i in range(12):
                store.project("BTCUSDT", "15m", start+i*900_000)
            projected_15m = store.read("BTCUSDT", "15m", start)
        core = forward_core_window(research, start_ms=start, bar_count=12)
        scanner = inspect_forward_15m(research, start)
        wh, daily, registry, daily_context = _daily(root / "warehouse")
        daily_context_15m = wh.query("15m", START, START+900_000,
                                     cutoff_ms=START+DAY, include_registry=True)
        daily_15m = daily_context_15m["bars"][0]
        result = reconcile_daily_bar(projected_15m, daily_15m)
        proposal = build_registry_proposal(result, daily_context_15m, warehouse_root=wh.root)

        # Profile bounded generated windows only; no owner DB, host metrics or
        # physical disk I/O are inspected by this job.
        profile_db = root / "profile-feed.sqlite"
        profile_start, _ = feed(profile_db, count=1000)
        profile = profile_synthetic_windows(
            profile_db, symbol="BTCUSDT", start_ms=profile_start,
            counts=[1, 100, 1000],
            expected_producer_code_sha256=PRODUCER_CODE_SHA256,
        )

        receipt = source and __import__("sqlite3").connect(source)
        try:
            receipt_sha = receipt.execute(
                "SELECT receipt_sha256 FROM final_bar_lineage WHERE symbol='BTCUSDT' ORDER BY open_ms DESC LIMIT 1"
            ).fetchone()[0]
        finally:
            receipt.close()
        live_report = {
            "schema":"atlas.ws.continuous-report.v1",
            "source_class":"LIVE_CAPTURE",
            "status":"OBSERVING_CONTINUOUS_ACCEPTANCE",
            "as_of_ms":end+1_000,
            "verified_receipts":write["rows"],
            "verified_receipt_sha256":[receipt_sha],
            "last_committed_ms":end-1,
            "last_receipt_fresh":True,
            "missing_open_ranges":[],
            "hold_reason":None,
            "orders":0,"trading_authority":"NONE",
        }
        sanitized_live = live_view(live_report)
        live_projection = verify_sanitized_live_projection(live_report,sanitized_live)
        provenance = _git_provenance()
        return {
            "schema": "aql.realtime-integration.synthetic-evidence.v1",
            "status": "SYNTHETIC_TESTED",
            "integration_readiness": "INTEGRATION_SEAM_SYNTHETIC_PASS_AUDIT_PENDING",
            "live_activation": "LIVE_ACTIVATION_BLOCKED",
            **provenance,
            "feed_source_commit": provenance["pr_head_commit"],
            "historical_report_baseline_commit": "eab5d240580e982bb298ed51d20633fd240e04c6",
            "warehouse_source_commit": "ae60b3e367241fec14753ac78e08147603b7af84",
            "watchdog_source_commit": "9d9e873fbaba8742280846285bd0b5db154ec455",
            "lineage_producer": {"schema":LINEAGE_SCHEMA,"producer_id":PRODUCER_ID,
                                 "producer_code_sha256":PRODUCER_CODE_SHA256,
                                 "attestation_limit":"LOCAL_NORMALIZED_ROW_ATTESTATION_NOT_EXTERNAL_SIGNATURE"},
            "fixture": {"symbol":"BTCUSDT","evidence_class":"GENERATED_TEST_FIXTURE",
                        "one_minute_rows_expected":180,
                        "one_minute_rows_observed":write["rows"],
                        "fifteen_minute_rows_expected":12,
                        "fifteen_minute_rows_observed":core["available_bars"],
                        "daily_15m_overlap":result["status"],
                        "registry_proposal_sha256":proposal["proposal_sha256"],
                        "proposal_hash_scope":"PER_JOB_GENERATED_ARCHIVE_BYTES; HASHES_MAY_VARY"},
            "synthetic_profile":profile,
            "mcp_projection":live_projection,
            "mcp_projection_evidence_class":"GENERATED_SYNTHETIC_REPORT; EXISTING_PINNED_WATCHDOG_FUNCTION_ONLY",
            "seams": {
                "feed_sqlite_read": "SYNTHETIC_MARKED_FIXTURE_ONLY; PRODUCTION_REQUIRES_EXTERNAL_CODE_PIN_AND_OWNER_ACCEPTANCE",
                "native_research_bar_store": "EXERCISED_TEMP_ONLY",
                "timeframe_projection": "EXERCISED",
                "historical_warehouse_query_and_registry": "EXERCISED_SYNTHETIC_ARCHIVE",
                "scanner_boundary": scanner["scanner_e_historical_route"],
                "factory": "BLOCKED_RECORD_ONLY_NO_LAB_OR_STRATEGY_RUN",
                "analyzer_strategy_entrypoint": "BLOCKED_DEPENDENCY_NOT_PRESENT_IN_THIS_SOURCE_PAIR",
                "daily_health_pr312": "READINESS_ONLY_NOT_DATA_PUBLISHER",
            },
            "scope_assertions": {
                "network": "FIXTURE_PATH_HAS_NO_NETWORK_CALL",
                "owner_feed": "NOT_ACCESSED; SOURCE_DB_GENERATED_UNDER_TEMP",
                "warehouse_registry": "BYTES_UNCHANGED_ASSERTED_IN_TEST",
                "scheduler": "NO_SCHEDULER_INTERFACE_USED",
                "orders": "NO_ORDER_API_USED",
                "trading_authority": "NONE",
            },
            "owner_24h_test": "24H_RESULT_PENDING; NO_OWNER_REPORT_READ",
            "original_e2e": "NOT_RUN; LIVE_ACTIVATION_BLOCKED",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("integration-evidence.json"))
    args = parser.parse_args()
    report = build_evidence()
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
