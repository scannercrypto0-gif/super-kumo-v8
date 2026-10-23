"""
AQL G1-WP01 Pipeline entry point.

Orchestrates: BinanceCollector → DurableJournal → OperationalStore + GapRecovery.

Usage (live 10-min run):
    python -m aql.pipeline --symbol BTCUSDT --interval 1m --duration 600
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from .collector.binance_collector import BinanceCollector
from .health import take_snapshot
from .journal.durable_journal import DurableJournal
from .recovery.gap_recovery import recover_gap
from .storage.operational_store import OperationalStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("aql.pipeline")


def _run_gap_recovery(
    journal: DurableJournal,
    store: OperationalStore,
    symbol: str,
    interval: str,
    gap_start_ms: int,
    gap_end_ms: int,
) -> dict:
    """
    Recover bars for a gap window.

    Sequence (mandatory, per G1-WP01 fix order):
      1. journal.commit(bar)        — durable local record first
      2. store.upsert(bar)          — write to operational store
      3. journal.mark_persisted()   — ONLY if upsert confirmed insertion/presence

    mark_persisted is never called if upsert raises or returns False due to
    an unconfirmed row.  (Note: upsert returns False for duplicates, which
    are already in the store; we still mark those persisted since the data
    IS durably stored — we just didn't add a new row.)
    """
    logger.info(
        "Running gap recovery: %s %s gap=[%d, %d] duration_s=%.0f",
        symbol, interval, gap_start_ms, gap_end_ms,
        (gap_end_ms - gap_start_ms) / 1000,
    )
    existing_keys = store.get_stored_keys(symbol, interval)
    recovered_bars, gap_report = recover_gap(
        symbol=symbol,
        interval=interval,
        gap_start_ms=gap_start_ms,
        gap_end_ms=gap_end_ms,
        existing_keys=existing_keys,
    )

    inserted = 0
    skipped_dup = 0
    errors = 0

    for bar in recovered_bars:
        # Step 1: Journal commit (durable local record)
        try:
            journal.commit(bar)
        except Exception as exc:
            logger.error(
                "Journal commit failed for recovered bar %s: %s",
                bar.stable_key(), exc,
            )
            errors += 1
            continue

        # Step 2: Operational store upsert
        upserted = False
        try:
            upserted = store.upsert(bar)
        except Exception as exc:
            logger.error(
                "Store upsert failed for recovered bar %s: %s",
                bar.stable_key(), exc,
            )
            errors += 1
            # Do NOT call mark_persisted — store write unconfirmed
            continue

        # Step 3: Mark persisted — only when store write is confirmed.
        # upsert() returns True for new rows, False for duplicates (already present).
        # In both cases the data IS in the store, so mark as PERSISTED.
        try:
            journal.mark_persisted(bar.stable_key())
        except Exception as exc:
            logger.warning(
                "mark_persisted failed for %s (non-fatal): %s",
                bar.stable_key(), exc,
            )

        if upserted:
            inserted += 1
        else:
            skipped_dup += 1

    return {
        "gap_report": gap_report,
        "recovery_inserted": inserted,
        "recovery_skipped_dup": skipped_dup,
        "recovery_errors": errors,
    }


def run_pipeline(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    duration_s: float = 600,
    data_dir: str = "./data",
    now_ms_fn=None,
) -> dict:
    """
    Run the full G1-WP01 MVP pipeline.
    Returns a result dict suitable for the execution report.

    Parameters
    ----------
    now_ms_fn : callable, optional
        ``() -> int`` returning the current epoch-millisecond timestamp.
        Passed through to ``take_snapshot``; defaults to wall clock when
        ``None`` (no operational behaviour change).  Intended for
        deterministic health assertions in tests only.
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

    # --- Startup reconciliation (handles clean restarts AND SIGKILL recovery) ---
    # This runs before WebSocket connection so any gap from the previous process
    # is detected and recovered, even if _on_close was never called.
    startup_recovery_results: list = []
    startup_reconcile_error: str | None = None
    startup_replay_inserted: int = 0
    startup_replay_errors: int = 0
    startup_bars_replayed: int = 0
    try:
        (startup_bars_replayed,
         startup_replay_inserted,
         startup_replay_errors,
         startup_gaps) = journal.startup_reconcile(
            store=store,
            symbol=symbol,
            interval=interval,
        )
        logger.info(
            "Startup reconciliation complete: bars_replayed=%d "
            "replay_inserted=%d replay_errors=%d gaps_detected=%d",
            startup_bars_replayed, startup_replay_inserted, startup_replay_errors,
            len(startup_gaps),
        )
        if startup_replay_errors > 0:
            logger.error(
                "Startup reconciliation: %d bar(s) failed to replay into store — "
                "unresolved backlog exists",
                startup_replay_errors,
            )
        # Run REST recovery for every detected gap (internal + trailing).
        # A failed REST fetch is captured in the RecoveryReport (status=HTTP_ERROR)
        # and carried in startup_recovery_results — never silently swallowed.
        for gap_start, gap_end in startup_gaps:
            gr = _run_gap_recovery(
                journal=journal,
                store=store,
                symbol=symbol,
                interval=interval,
                gap_start_ms=gap_start,
                gap_end_ms=gap_end,
            )
            startup_recovery_results.append(gr)
    except Exception as exc:
        startup_reconcile_error = str(exc)
        logger.error("Startup reconciliation FAILED: %s", startup_reconcile_error)

    # --- WebSocket collection ---
    collector = BinanceCollector(
        symbol=symbol,
        interval=interval,
        journal=journal,
        store=store,
    )

    t_start = time.time()
    metrics = collector.run(timeout_s=duration_s)
    elapsed = time.time() - t_start

    # --- Post-collection gap recovery (handles WS disconnects during run) ---
    ws_recovery_result = None
    if collector.gap_start_ms is not None and collector.gap_end_ms is not None:
        ws_recovery_result = _run_gap_recovery(
            journal=journal,
            store=store,
            symbol=symbol,
            interval=interval,
            gap_start_ms=collector.gap_start_ms,
            gap_end_ms=collector.gap_end_ms,
        )

    # --- Final counts ---
    journal_counts = journal.count_by_state()
    store_count = store.count(symbol, interval)
    min_open, max_open = store.get_range(symbol, interval)

    # --- Health snapshot (read-only; does not affect acquisition or trading) ---
    # Fix-1: aggregate ALL recovery reports (startup + WS) so that any mandatory
    # failure in any report is detected, even if a later report succeeded.
    # Fix-3: pass startup_reconcile_error so it surfaces as UNHEALTHY.
    _all_recovery_reports = [r["gap_report"] for r in startup_recovery_results]
    if ws_recovery_result is not None:
        _all_recovery_reports.append(ws_recovery_result["gap_report"])
    health = take_snapshot(
        journal=journal,
        store=store,
        symbol=symbol,
        interval=interval,
        recovery_reports=_all_recovery_reports,
        replay_errors=startup_replay_errors,
        reconcile_error=startup_reconcile_error,
        now_ms_fn=now_ms_fn,
    )

    def _report_from(recovery_result: dict | None) -> dict | None:
        if recovery_result is None:
            return None
        gr = recovery_result["gap_report"]
        return {
            "status": gr.status,
            "expected": gr.expected_bars,
            "recovered": gr.recovered_bars,
            "unresolved": gr.unresolved,
            "missing_opens": gr.missing_opens,
            "http_error": gr.http_error,
            "weight_cost": gr.weight_cost,
            "last_seen_window_weight": gr.last_seen_window_weight,
            "inserted": recovery_result["recovery_inserted"],
            "skipped_dup": recovery_result["recovery_skipped_dup"],
            "errors": recovery_result["recovery_errors"],
        }

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
        "startup_gap_recovery": [_report_from(r) for r in startup_recovery_results] if startup_recovery_results else None,
        "startup_reconcile": {
            "bars_replayed": startup_bars_replayed,
            "replay_inserted": startup_replay_inserted,
            "replay_errors": startup_replay_errors,
            "error": startup_reconcile_error,
            # Machine-readable: any non-zero value here means unresolved backlog
            "unresolved_backlog": startup_replay_errors > 0 or startup_reconcile_error is not None,
        },
        "ws_gap_recovery": _report_from(ws_recovery_result),
        "supabase_status": OperationalStore.SUPABASE_STATUS,
        "health_snapshot": health.to_dict(),
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
