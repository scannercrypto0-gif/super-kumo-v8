"""
AQL G1-WP01 Pipeline entry point.

Orchestrates: BinanceCollector → DurableJournal → OperationalStore + GapRecovery.

Usage (live 10-min run):
    python -m aql.pipeline --symbol BTCUSDT --interval 1m --duration 600
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from .collector.binance_collector import BinanceCollector
from .journal.durable_journal import DurableJournal
from .recovery.gap_recovery import recover_gap
from .storage.operational_store import OperationalStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("aql.pipeline")


def run_pipeline(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    duration_s: float = 600,
    data_dir: str = "./data",
) -> dict:
    """
    Run the full G1-WP01 MVP pipeline.
    Returns a result dict suitable for the execution report.
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    journal_path = str(data_path / "journal.sqlite")
    store_path = str(data_path / "operational.sqlite")

    journal = DurableJournal(journal_path)
    store = OperationalStore(store_path)

    logger.info(
        "Pipeline start: symbol=%s interval=%s duration=%.0fs",
        symbol, interval, duration_s,
    )
    logger.info("Journal: %s", journal_path)
    logger.info("Store: %s", store_path)
    logger.info("Supabase: NOT_TESTED (SQLite fallback active)")

    collector = BinanceCollector(
        symbol=symbol,
        interval=interval,
        journal=journal,
        store=store,
    )

    t_start = time.time()
    metrics = collector.run(timeout_s=duration_s)
    elapsed = time.time() - t_start

    # --- Gap Recovery ---
    gap_report = None
    if collector.gap_start_ms is not None and collector.gap_end_ms is not None:
        logger.info("Running gap recovery...")
        existing_keys = store.get_stored_keys(symbol, interval)
        recovered_bars, gap_report = recover_gap(
            symbol=symbol,
            interval=interval,
            gap_start_ms=collector.gap_start_ms,
            gap_end_ms=collector.gap_end_ms,
            existing_keys={b for b in existing_keys},
        )
        if recovered_bars:
            bulk_result = store.bulk_upsert(recovered_bars)
            for bar in recovered_bars:
                journal.commit(bar)
                journal.mark_persisted(bar.stable_key())
            logger.info("Gap recovery upsert: %s", bulk_result)

    # --- Final counts ---
    journal_counts = journal.count_by_state()
    store_count = store.count(symbol, interval)
    min_open, max_open = store.get_range(symbol, interval)

    result = {
        "symbol": symbol,
        "interval": interval,
        "elapsed_s": round(elapsed, 1),
        "ws_messages": metrics.ws_message_count,
        "final_bars_received": metrics.final_bar_count,
        "non_final_bars": metrics.non_final_bar_count,
        "journal_committed": metrics.journal_commit_count,
        "duplicates": metrics.duplicate_count,
        "store_inserted": metrics.store_insert_count,
        "store_total": store_count,
        "errors": metrics.error_count,
        "reconnects": metrics.reconnect_count,
        "avg_latency_ws_to_commit_ms": metrics.avg_latency_ws_to_commit_ms(),
        "journal_state_counts": journal_counts,
        "bar_range": {
            "min_open_ms": min_open,
            "max_open_ms": max_open,
        },
        "gap_recovery": (
            {
                "status": gap_report.status,
                "expected": gap_report.expected_bars,
                "recovered": gap_report.recovered_bars,
                "unresolved": gap_report.unresolved,
                "weight_used": gap_report.weight_used,
            }
            if gap_report else None
        ),
        "supabase_status": OperationalStore.SUPABASE_STATUS,
    }

    logger.info("Pipeline complete: %s", result)
    return result


def main():
    parser = argparse.ArgumentParser(description="AQL G1-WP01 Pipeline")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--duration", type=float, default=600, help="Seconds to run")
    parser.add_argument("--data-dir", default="./data")
    args = parser.parse_args()

    result = run_pipeline(
        symbol=args.symbol,
        interval=args.interval,
        duration_s=args.duration,
        data_dir=args.data_dir,
    )

    import json
    print("\n=== PIPELINE RESULT ===")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
