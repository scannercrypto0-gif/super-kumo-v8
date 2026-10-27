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
import threading
from pathlib import Path

from .collector.binance_collector import BinanceCollector
from .health import take_snapshot
from .lanes import BackgroundLane, JournalConsumer
from .g1_integrity import ContentConflictError, propagate_conflict
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
    stop_event=None,
) -> dict:
    """
    Recover bars for a gap window.

    Sequence (mandatory, per G1-WP01 fix order):
      1. journal.commit(bar, background=True) - durable local record first
      2. store.upsert(bar)          — write to operational store
      3. journal.mark_persisted()   — ONLY if upsert confirmed insertion/presence

    mark_persisted is never called if upsert raises or returns False due to
    an unconfirmed row.  (Note: upsert returns False for duplicates, which
    are already in the store; we still mark those persisted since the data
    IS durably stored — we just didn't add a new row.)
    """
    # Legacy recovery is not a registered v2 writer. Refuse before reading
    # unrelated store coverage or issuing REST, even for matching source rows.
    from .delivery.authority import register_legacy_writer
    register_legacy_writer(journal, 'gap-recovery')
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
        include_existing=True,
    )

    inserted = 0
    skipped_dup = 0
    errors = 0

    for bar in recovered_bars:
        if stop_event is not None and stop_event.is_set():
            errors += 1
            break
        # Step 1: Journal commit (durable local record)
        try:
            journal.commit(bar, background=True)
        except ContentConflictError as exc:
            propagate_conflict(exc,journal,store)
            errors += 1
            continue
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
        except ContentConflictError as exc:
            propagate_conflict(exc,journal,store)
            errors += 1
            continue
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
        except ContentConflictError as exc:
            propagate_conflict(exc,journal,store)
            errors += 1
            continue
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
    after_persisted=None,
) -> dict:
    """
    Run the full G1-WP01 MVP pipeline.
    Returns a result dict suitable for the execution report.

    Parameters
    ----------
    after_persisted : callable, optional
        Opt-in post-ACK observer for committed journal/store bars. Observer
        failure is isolated and never constitutes provider/PIT evidence.
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
    # Freeze the durable pre-collection journal population, not market timestamps.
    # Recovery stays asynchronous; newly collected rows are not startup backlog.
    startup_max_entry_id = journal.startup_entry_boundary()
    recovery_lane = BackgroundLane()
    startup_ready = threading.Event()
    consumer = JournalConsumer(journal, store, symbol, interval, ready=startup_ready,
                               after_persisted=after_persisted)

    logger.info(
        "Pipeline start: symbol=%s interval=%s duration=%.0fs",
        symbol, interval, duration_s,
    )
    logger.info("Journal: %s", journal_path)
    logger.info("Store: %s", store_path)
    logger.info("Supabase: NOT_TESTED (SQLite fallback active)")

    # --- Startup reconciliation (handles clean restarts AND SIGKILL recovery) ---
    # Runs independently of WebSocket connection. Replay and gaps from a previous
    # process remain visible even when _on_close was never called.
    startup_recovery_results: list = []
    startup_reconcile_error: str | None = None
    startup_replay_inserted: int = 0
    startup_replay_errors: int = 0
    startup_bars_replayed: int = 0
    def reconcile_background(stop):
        nonlocal startup_bars_replayed, startup_replay_inserted
        nonlocal startup_replay_errors, startup_reconcile_error
        if stop.is_set():
            return
        try:
            (startup_bars_replayed,
             startup_replay_inserted,
             startup_replay_errors,
             startup_gaps) = journal.startup_reconcile(
                store=store,
                symbol=symbol,
                interval=interval,
                startup_max_entry_id=startup_max_entry_id,
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
                def recover(stop, start=gap_start, end=gap_end):
                    if not stop.is_set():
                        gr = _run_gap_recovery(journal, store, symbol, interval, start, end, stop)
                        startup_recovery_results.append(gr)
                recovery_lane.submit(recover)
        except Exception as exc:
            startup_reconcile_error = str(exc)
            logger.error("Startup reconciliation FAILED: %s", startup_reconcile_error)
        finally:
            startup_ready.set()

    recovery_lane.submit(reconcile_background)

    # --- WebSocket collection ---
    collector = BinanceCollector(
        symbol=symbol,
        interval=interval,
        journal=journal,
        store=store,
    )

    collector.background_persistence = True
    consumer.start()
    t_start = time.time()
    try:
        metrics = collector.run(timeout_s=duration_s)
    except BaseException:
        consumer.stop_event.set()
        recovery_lane.stop_event.set()
        raise
    elapsed = time.time() - t_start

    # --- Post-collection gap recovery (handles WS disconnects during run) ---
    ws_recovery_result = None
    if collector.gap_start_ms is not None and collector.gap_end_ms is not None:
        def recover_ws(stop):
            nonlocal ws_recovery_result
            if not stop.is_set():
                ws_recovery_result = _run_gap_recovery(
                    journal, store, symbol, interval,
                    collector.gap_start_ms, collector.gap_end_ms, stop)
        recovery_lane.submit(recover_ws)

    recovery_lane_status = recovery_lane.finish()
    consumer_status = consumer.finish()
    if (recovery_lane_status['pending'] or recovery_lane_status['rejected']
            or recovery_lane_status['errors'] or consumer_status['worker_alive']
            or any(r['recovery_errors'] for r in startup_recovery_results)
            or (ws_recovery_result and ws_recovery_result['recovery_errors'])):
        startup_reconcile_error = startup_reconcile_error or "Background work pending/failed; retry from durable journal on restart"

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
    if getattr(collector, "clock_uncertain", False) or getattr(collector, "health_state", "") == "CLOCK_UNCERTAIN":
        startup_reconcile_error = startup_reconcile_error or "Source/local clock divergence; temporal eligibility denied"
    if metrics.error_count:
        startup_reconcile_error = startup_reconcile_error or "Collector reported acquisition errors; no unqualified healthy claim"
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
        "collector_health": getattr(collector, "health_state", "SYNTHETIC"),
        "source_clock_skew_ms": metrics.source_clock_skew_ms,
        "avg_latency_ws_to_commit_ms": metrics.avg_latency_ws_to_commit_ms(),  # legacy, not completion proof
        "commit_return_timing_version": 1,
        "last_commit_return_observed_at_ms": metrics.last_commit_return_observed_at,
        "avg_latency_ws_to_commit_return_ms": (
            sum(metrics.latency_ws_to_commit_return_samples)/len(metrics.latency_ws_to_commit_return_samples)
            if metrics.latency_ws_to_commit_return_samples else None),
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
        "background_recovery": recovery_lane_status,
        "background_persistence": consumer_status,
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
