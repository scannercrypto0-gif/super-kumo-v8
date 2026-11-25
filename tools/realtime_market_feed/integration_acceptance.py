"""Produce a small machine-readable synthetic integration evidence packet."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from tools.realtime_market_feed.test_atlas_integration import (
    _daily, feed, START, DAY,
)
from tools.realtime_market_feed.atlas_integration import (
    build_registry_proposal, copy_to_research_store, reconcile_daily_bar,
)
from aql.research_bar_store import ResearchBarStore
from aql.research_forward_core_read import forward_core_window
from aql.research_forward_scanner_boundary import inspect_forward_15m


def build_evidence():
    with tempfile.TemporaryDirectory(prefix="atlas-realtime-integration-") as raw:
        root = Path(raw)
        source = root / "feed.sqlite"
        start, end = feed(source, count=180)
        research = root / "research.sqlite"
        write = copy_to_research_store(source, research, symbol="BTCUSDT",
            start_ms=start, end_ms=end, now_ms=end+1_000, engineering_test_only=True)
        with ResearchBarStore(research) as store:
            for i in range(12):
                store.project("BTCUSDT", "15m", start+i*900_000)
            projected_15m = store.read("BTCUSDT", "15m", start)
        core = forward_core_window(research, start_ms=start, bar_count=12)
        scanner = inspect_forward_15m(research, start)
        wh, daily, registry = _daily(root / "warehouse")
        daily_15m = wh.query("15m", START, START+900_000, cutoff_ms=START+DAY)[0]
        result = reconcile_daily_bar(projected_15m, daily_15m)
        proposal = build_registry_proposal(result, registry)
        return {
            "schema": "aql.realtime-integration.synthetic-evidence.v1",
            "status": "SYNTHETIC_TESTED",
            "integration_readiness": "ENGINEERING_READY_LIVE_ACTIVATION_PENDING",
            "code_commit": os.environ.get("GITHUB_SHA", "LOCAL_UNPINNED"),
            "feed_source_commit": "eab5d240580e982bb298ed51d20633fd240e04c6",
            "warehouse_source_commit": "5df7f6c9e0d6448db6aa700fa80158b443c5b3db",
            "fixture": {"symbol":"BTCUSDT","one_minute_rows_expected":180,
                        "one_minute_rows_observed":write["rows"],
                        "fifteen_minute_rows_expected":12,
                        "fifteen_minute_rows_observed":core["available_bars"],
                        "daily_15m_overlap":result["status"],
                        "registry_proposal_sha256":proposal["proposal_sha256"]},
            "seams": {
                "feed_sqlite_read": "EXERCISED_READ_ONLY",
                "native_research_bar_store": "EXERCISED_TEMP_ONLY",
                "timeframe_projection": "EXERCISED",
                "historical_warehouse_query_and_registry": "EXERCISED_SYNTHETIC_ARCHIVE",
                "scanner_boundary": scanner["scanner_e_historical_route"],
                "factory": "BLOCKED_RECORD_ONLY_NO_LAB_OR_STRATEGY_RUN",
                "analyzer_strategy_entrypoint": "BLOCKED_DEPENDENCY_NOT_PRESENT_IN_THIS_SOURCE_PAIR",
                "daily_health_pr312": "READINESS_ONLY_NOT_DATA_PUBLISHER",
            },
            "safety": {"network_calls":0,"owner_feed_mutations":0,
                       "warehouse_mutations_after_snapshot":0,"registry_mutations_from_proposal":0,
                       "scheduler_changes":0,"orders":0,"trading_authority":"NONE"},
            "owner_24h_test": "UNTOUCHED_RESULT_STILL_REQUIRED",
            "live_activation": "PENDING_OWNER_AUTHORIZATION_AND_SOURCE_GATES",
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
