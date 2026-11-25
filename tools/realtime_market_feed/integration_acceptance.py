"""Produce a small machine-readable synthetic integration evidence packet."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

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
        provenance = _git_provenance()
        return {
            "schema": "aql.realtime-integration.synthetic-evidence.v1",
            "status": "SYNTHETIC_TESTED",
            "integration_readiness": "INTEGRATION_SEAM_SYNTHETIC_PASS_AUDIT_PENDING",
            "live_activation": "LIVE_ACTIVATION_BLOCKED",
            **provenance,
            "feed_source_commit": provenance["pr_head_commit"],
            "historical_report_baseline_commit": "eab5d240580e982bb298ed51d20633fd240e04c6",
            "warehouse_source_commit": "5df7f6c9e0d6448db6aa700fa80158b443c5b3db",
            "fixture": {"symbol":"BTCUSDT","evidence_class":"GENERATED_TEST_FIXTURE",
                        "one_minute_rows_expected":180,
                        "one_minute_rows_observed":write["rows"],
                        "fifteen_minute_rows_expected":12,
                        "fifteen_minute_rows_observed":core["available_bars"],
                        "daily_15m_overlap":result["status"],
                        "registry_proposal_sha256":proposal["proposal_sha256"],
                        "proposal_hash_scope":"PER_JOB_GENERATED_ARCHIVE_BYTES; HASHES_MAY_VARY"},
            "seams": {
                "feed_sqlite_read": "SYNTHETIC_MARKED_FIXTURE_ONLY; PRODUCTION_RAW_EVENT_LINEAGE_BLOCKED",
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
            "owner_24h_test": "UNTOUCHED_RESULT_STILL_REQUIRED",
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
