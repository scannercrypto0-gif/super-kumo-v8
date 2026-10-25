"""
AQL G1-WP04-FIX01/FIX02 — Pipeline Integration and Subprocess SIGKILL Evidence
================================================================================

Required by Issue #49 (G1-WP04-FIX01) and Issue #51 (G1-WP04-FIX02):

1. T_WP04_FIX01_01_PipelineOrchestration
   Integration tests that drive actual src/aql/pipeline.py orchestration
   (BinanceCollector patched with SyntheticCollector; recover_gap patched
   with a synthetic no-op).  Exercises the complete code path:
     startup_reconcile → collect → health snapshot
   using real SQLite journal + store — not component-level stubs.

   FIX02 update: now_ms_fn injected via run_pipeline() so health status is
   deterministic; AG-F01 and AG-F02 assert exactly HEALTHY, not a loose set.

2. T_WP04_FIX01_02_SubprocessSigkill
   Real OS-level subprocess SIGKILL tests using subprocess.Popen +
   os.kill(pid, signal.SIGKILL).  A child process commits N bars to the
   durable journal (not to the operational store), signals the parent
   via a flag file, and is then hard-killed.  The parent opens fresh
   journal + store objects and calls startup_reconcile to verify:
     - full committed-bar recovery
     - zero replay errors
     - no duplicate store rows
     - correct post-recovery health transitions (HEALTHY)

   Skipped on Windows (SIGKILL not available on that platform); marked
   SKIP with explicit reason — never PASS-without-kill.

   This is a journal-level component test (proves journal durability).

3. T_WP04_FIX02_04_FullPipelineSIGKILL  (new — Issue #51)
   Full-pipeline OS-level subprocess SIGKILL.  The child process runs the
   actual run_pipeline() with deterministic synthetic WS/REST adapters and
   real SQLite.  A _CrashCollector commits N bars to the journal then writes
   a flag and sleeps (never calls store.upsert).  The parent SIGKILLs the
   running pipeline, then restarts it via run_pipeline() with an empty
   collector.  Verifies replay, idempotency, exact key coverage and HEALTHY.

Distinction from WP04 T_WP04_02_SigkillRestart (existing approximation)
-------------------------------------------------------------------------
WP04 T_WP04_02 approximated SIGKILL by ``del journal; del store; reopen``.
FIX01 T_WP04_FIX01_02 uses actual OS-level subprocess termination with an
explicit journal-commit synchronisation point (journal-level writer only).
FIX02 T_WP04_FIX02_04 kills a child running the full orchestrated pipeline.

New acceptance gates
--------------------
AG-F01  Pipeline orchestration: run_pipeline() with synthetic adapters,
        deterministic now_ms_fn → store_total==N_PIPELINE_BARS, errors==0,
        health==HEALTHY (exact)
AG-F02  Pipeline restart: startup_reconcile replays journal bars into store,
        deterministic now_ms_fn → health==HEALTHY (exact)
AG-F03  Subprocess SIGKILL (journal-level child): child commits N bars to
        journal only, SIGKILL, startup_reconcile recovers all bars, no dups
AG-F04  Double startup_reconcile is idempotent → replay_inserted_2==0
AG-F05  Health after journal-level SIGKILL recovery == HEALTHY (now_ms_fn)
AG-FP01 Full-pipeline SIGKILL: child runs run_pipeline() with _CrashCollector,
        SIGKILL after flag, restart via run_pipeline() → bars_replayed==N
AG-FP02 Exact key coverage + idempotent double-restart + health==HEALTHY
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aql.collector.binance_collector import CollectorMetrics
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import BarState, MarketBar
from aql.recovery.gap_recovery import RecoveryReport
from aql.storage.operational_store import OperationalStore
from aql.health.snapshot import (
    take_snapshot,
    DEFAULT_LAG_WARN_S,
    DEFAULT_LAG_CRIT_S,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
SYMBOL = "BTCUSDT"
INTERVAL = "1m"
INTERVAL_MS = 60_000

# Source path for child scripts — absolute, used as sys.path insertion.
_SRC_PATH = str(Path(__file__).parent.parent / "src")

# ---------------------------------------------------------------------------
# "Live" bars: timestamps near wall-clock so health snapshot lag is small.
# Last bar closes ≈ 30 s before the test snapshot → lag well under
# DEFAULT_LAG_WARN_S=90 s → HEALTHY.
# ---------------------------------------------------------------------------
N_PIPELINE_BARS = 5

_NOW_AT_IMPORT = int(time.time() * 1000)
# Last bar closes 30 s before module load; all subsequent lag measurements
# are < 90 s as long as test setup completes within 60 s.
_LAST_CLOSE_TARGET = _NOW_AT_IMPORT - 30_000
BASE_OPEN_LIVE = _LAST_CLOSE_TARGET - N_PIPELINE_BARS * INTERVAL_MS


def _make_live_bar(i: int) -> MarketBar:
    """Bar with near-current timestamps so pipeline health check gives HEALTHY."""
    bar_open = BASE_OPEN_LIVE + i * INTERVAL_MS
    bar_close = bar_open + INTERVAL_MS - 1
    bar = MarketBar(
        symbol=SYMBOL,
        interval=INTERVAL,
        bar_open=bar_open,
        bar_close=bar_close,
        open=100.0 + i,
        high=101.0 + i,
        low=99.0 + i,
        close=100.5 + i,
        volume=10.0 + i,
        is_final=True,
        source="synthetic_ws",
        ingested_at=bar_open + 500,
        committed_at=bar_open + 550,
        state=BarState.LOCAL_COMMITTED,
        checksum=None,
    )
    bar.checksum = bar.compute_checksum()
    return bar


# ---------------------------------------------------------------------------
# "Static" bars at a fixed epoch — used in SIGKILL tests where timing does
# not matter (we inject now_ms_fn for the health snapshot).
# ---------------------------------------------------------------------------
BASE_OPEN_STATIC = 1_700_000_000_000  # 2023-11-15 (deterministic)


def _make_static_bar(i: int) -> MarketBar:
    """Bar at a fixed historical epoch for SIGKILL tests."""
    bar_open = BASE_OPEN_STATIC + i * INTERVAL_MS
    bar_close = bar_open + INTERVAL_MS - 1
    bar = MarketBar(
        symbol=SYMBOL,
        interval=INTERVAL,
        bar_open=bar_open,
        bar_close=bar_close,
        open=200.0 + i,
        high=201.0 + i,
        low=199.0 + i,
        close=200.5 + i,
        volume=20.0 + i,
        is_final=True,
        source="synthetic_ws",
        ingested_at=bar_open + 500,
        committed_at=bar_open + 550,
        state=BarState.LOCAL_COMMITTED,
        checksum=None,
    )
    bar.checksum = bar.compute_checksum()
    return bar


# ---------------------------------------------------------------------------
# Synthetic BinanceCollector — drop-in for pipeline patching
# ---------------------------------------------------------------------------

def _make_synthetic_collector_class(bars: List[MarketBar], *, startup_replayed=None):
    """
    Return a class whose constructor signature matches BinanceCollector
    and whose run() method injects ``bars`` directly into the pipeline's
    real SQLite journal + store, then returns a CollectorMetrics object.

    gap_start_ms / gap_end_ms are left None (clean synthetic run).
    """
    _bars = bars

    class _SyntheticCollector:
        def __init__(
            self,
            symbol: str,
            interval: str,
            journal: DurableJournal,
            store: OperationalStore,
            **kwargs,
        ):
            self._symbol = symbol
            self._interval = interval
            self._journal = journal
            self._store = store
            self.gap_start_ms: Optional[int] = None
            self.gap_end_ms: Optional[int] = None

        def run(self, timeout_s: Optional[float] = None) -> CollectorMetrics:
            if startup_replayed is not None:
                # Instant collection must not race durable startup replay into
                # shutdown. Test barrier only; production budgets are unchanged.
                assert startup_replayed.wait(5), "Startup replay did not complete within test barrier"
            metrics = CollectorMetrics()
            for bar in _bars:
                committed = self._journal.commit(bar)
                if committed:
                    metrics.journal_commit_count += 1
                    metrics.final_bar_count += 1
                else:
                    metrics.duplicate_count += 1
                metrics.ws_message_count += 1

                upserted = self._store.upsert(bar)
                if upserted:
                    metrics.store_insert_count += 1
                    self._journal.mark_persisted(bar.stable_key())
                else:
                    # Duplicate in store — mark persisted anyway (bar IS there)
                    self._journal.mark_persisted(bar.stable_key())

            metrics.error_count = 0
            metrics.reconnect_count = 0
            return metrics

    return _SyntheticCollector


def _synthetic_recover_gap(
    symbol: str,
    interval: str,
    gap_start_ms: int,
    gap_end_ms: int,
    existing_keys,
):
    """
    Synthetic REST gap recovery: no bars fetched, FULL report (unresolved=0).
    Prevents real HTTP calls in integration tests.
    """
    return [], RecoveryReport(
        symbol=symbol,
        interval=interval,
        gap_start_ms=gap_start_ms,
        gap_end_ms=gap_end_ms,
        expected_bars=0,
        recovered_bars=0,
        already_stored=0,
        unresolved=0,
        missing_opens=[],
        status="FULL",
        weight_cost=0,
        last_seen_window_weight=0,
        http_error=None,
    )


# ---------------------------------------------------------------------------
# T_WP04_FIX01_01 — Pipeline Orchestration with Synthetic Adapters
# ---------------------------------------------------------------------------

class TestT_WP04_FIX01_01_PipelineOrchestration:
    """
    AG-F01, AG-F02: Drive actual pipeline.run_pipeline() with synthetic
    BinanceCollector + recover_gap.  All assertions target the real result
    dict produced by run_pipeline().

    Distinction from existing WP04 tests
    -------------------------------------
    WP04 tests call journal/store/take_snapshot directly.  These tests
    call run_pipeline() which exercises the full orchestration sequence:
      Data dir init → DurableJournal init → OperationalStore init →
      startup_reconcile (+ gap recovery loop) → BinanceCollector.run() →
      post-WS gap recovery → take_snapshot → result dict assembly.
    """

    def test_ag_f01_pipeline_fresh_start_healthy(self, tmp_path):
        """
        AG-F01: run_pipeline() with N_PIPELINE_BARS synthetic bars on a
        fresh SQLite database.  Injects deterministic now_ms_fn so the
        health snapshot clock is pinned at module-import time
        (lag ≈ 30 s < DEFAULT_LAG_WARN_S=90 s → exactly HEALTHY).

        FIX02 change: assert hs["status"] == "HEALTHY" (strict, not loose set).
        """
        from aql.pipeline import run_pipeline

        bars = [_make_live_bar(i) for i in range(N_PIPELINE_BARS)]
        CollectorCls = _make_synthetic_collector_class(bars)

        # Deterministic clock: pinned at module import (lag ≈ 30 s → HEALTHY).
        # _LAST_CLOSE_TARGET = _NOW_AT_IMPORT - 30_000; last bar close is at
        # _LAST_CLOSE_TARGET - 1.  lag = _NOW_AT_IMPORT - (_LAST_CLOSE_TARGET-1)
        # ≈ 30 001 ms ≈ 30 s < DEFAULT_LAG_WARN_S=90 s.
        _fixed_now_ms = _NOW_AT_IMPORT

        with (
            patch("aql.pipeline.BinanceCollector", CollectorCls),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
        ):
            result = run_pipeline(
                symbol=SYMBOL,
                interval=INTERVAL,
                duration_s=1.0,
                data_dir=str(tmp_path / "pipeline_fresh"),
                now_ms_fn=lambda: _fixed_now_ms,
            )

        assert result["symbol"] == SYMBOL
        assert result["interval"] == INTERVAL
        assert result["errors"] == 0, f"Pipeline errors: {result['errors']}"
        assert result["store_total"] == N_PIPELINE_BARS, (
            f"Expected {N_PIPELINE_BARS} in store, got {result['store_total']}"
        )
        assert result["journal_committed"] == N_PIPELINE_BARS, (
            f"Expected {N_PIPELINE_BARS} journal commits, got {result['journal_committed']}"
        )
        sr = result["startup_reconcile"]
        assert sr["bars_replayed"] == 0, (
            f"Fresh start: expected 0 bars replayed, got {sr['bars_replayed']}"
        )
        assert sr["replay_errors"] == 0
        assert sr["error"] is None

        hs = result["health_snapshot"]
        # FIX02: exact assertion — deterministic clock guarantees HEALTHY.
        assert hs["status"] == "HEALTHY", (
            f"AG-F01 FAIL: expected exactly HEALTHY with deterministic clock "
            f"(lag≈30s). Got: {hs['status']}. Full snapshot: {hs}"
        )
        # store and journal counts must be present in health snapshot
        assert hs["store_final_count"] == N_PIPELINE_BARS, hs
        assert hs["journal_final_count"] == N_PIPELINE_BARS, hs

        print(
            f"\n  AG-F01 PASS: fresh run  store={result['store_total']}  "
            f"journal={result['journal_committed']}  "
            f"health={hs['status']}  (now_ms pinned, lag≈30s)"
        )

    def test_ag_f02_pipeline_restart_replays_journal(self, tmp_path):
        """
        AG-F02: Pre-seed journal with N bars without writing to the store
        (simulates a crash between journal.commit and store.upsert).
        run_pipeline() should detect the gap in startup_reconcile, replay
        all bars into the store, and report exactly HEALTHY.

        FIX02 change: now_ms_fn injected so health status is deterministic.
        The "live" bars have their last close ≈ 30 s before module import;
        pinning the clock at _NOW_AT_IMPORT keeps lag ≈ 30 s < 90 s → HEALTHY.
        Asserts hs["status"] == "HEALTHY" (strict, not loose set).
        """
        from aql.pipeline import run_pipeline

        data_dir = str(tmp_path / "pipeline_restart")
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        # Pre-seed: commit bars to journal only (no store writes)
        N = N_PIPELINE_BARS
        bars = [_make_live_bar(i) for i in range(N)]
        pre_jrn = DurableJournal(str(Path(data_dir) / "journal.sqlite"))
        pre_sto = OperationalStore(str(Path(data_dir) / "operational.sqlite"))
        for bar in bars:
            pre_jrn.commit(bar)
            # Deliberately skip store.upsert — simulates mid-write crash
        del pre_jrn
        del pre_sto

        # Restart: empty synthetic collector; startup_reconcile must replay
        startup_replayed = threading.Event()
        original_reconcile = DurableJournal.startup_reconcile
        def reconcile_then_signal(journal, *args, **kwargs):
            try:
                return original_reconcile(journal, *args, **kwargs)
            finally:
                # Completion, not success: failures still reach strict assertions.
                startup_replayed.set()
        CollectorCls = _make_synthetic_collector_class([], startup_replayed=startup_replayed)

        # Deterministic clock: pinned at module import (lag ≈ 30 s → HEALTHY).
        _fixed_now_ms = _NOW_AT_IMPORT

        with (
            patch("aql.pipeline.BinanceCollector", CollectorCls),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
            patch.object(DurableJournal, "startup_reconcile", reconcile_then_signal),
        ):
            result = run_pipeline(
                symbol=SYMBOL,
                interval=INTERVAL,
                duration_s=1.0,
                data_dir=data_dir,
                now_ms_fn=lambda: _fixed_now_ms,
            )

        sr = result["startup_reconcile"]
        assert sr["bars_replayed"] == N, (
            f"Expected {N} bars replayed, got {sr['bars_replayed']}"
        )
        assert sr["replay_errors"] == 0
        assert result["store_total"] == N, (
            f"Expected {N} bars in store after restart, got {result['store_total']}"
        )

        hs = result["health_snapshot"]
        # FIX02: exact assertion — deterministic clock guarantees HEALTHY.
        assert hs["status"] == "HEALTHY", (
            f"AG-F02 FAIL: expected exactly HEALTHY with deterministic clock "
            f"(lag≈30s) after journal-replay restart. Got: {hs['status']}. "
            f"Full snapshot: {hs}; "
            f"background_recovery={result.get('background_recovery')}; "
            f"background_persistence={result.get('background_persistence')}; "
            f"startup_reconcile={result.get('startup_reconcile')}"
        )
        assert hs["unresolved_backlog"] is False
        assert hs["integrity_ok"] is True

        print(
            f"\n  AG-F02 PASS: restart  bars_replayed={sr['bars_replayed']}  "
            f"store={result['store_total']}  health={hs['status']}  "
            f"(now_ms pinned, lag≈30s)"
        )

    def test_ag_f02_slow_startup_finishes_before_synthetic_shutdown(self, tmp_path):
        """Five injected .25s writes exceed the unchanged1s shutdown budget."""
        original = OperationalStore.upsert
        def slow_upsert(store, *args, **kwargs):
            time.sleep(.25)
            return original(store, *args, **kwargs)
        with patch.object(OperationalStore, "upsert", slow_upsert):
            self.test_ag_f02_pipeline_restart_replays_journal(tmp_path)

    def test_ag_f02_genuinely_pending_background_stays_unhealthy(self, tmp_path):
        """Completed replay does not excuse an unfinished background job."""
        import aql.pipeline as pipeline
        from aql.lanes import BackgroundLane
        release = threading.Event()
        lanes, results = [], []
        original_run = pipeline.run_pipeline
        class HeldLane(BackgroundLane):
            def __init__(self):
                self.first = True
                super().__init__(); lanes.append(self)
            def submit(self, job):
                if self.first:
                    self.first = False
                    def held(stop):
                        job(stop)
                        assert release.wait(5), "Test must release held startup tail"
                    return super().submit(held)
                return super().submit(job)
        def observed(*args, **kwargs):
            result = original_run(*args, **kwargs); results.append(result); return result
        try:
            with patch.object(pipeline, "BackgroundLane", HeldLane), patch.object(pipeline, "run_pipeline", observed):
                with pytest.raises(AssertionError, match="Got: UNHEALTHY"):
                    self.test_ag_f02_pipeline_restart_replays_journal(tmp_path)
            result = results[0]
            assert result["store_total"] == N_PIPELINE_BARS
            assert result["startup_reconcile"]["replay_errors"] == 0
            assert result["background_recovery"]["pending"] > 0
            assert result["background_recovery"]["worker_alive"] is True
            assert result["background_recovery"]["errors"] == []
            assert result["health_snapshot"]["status"] == "UNHEALTHY"
            assert result["health_snapshot"]["reconcile_error"]
        finally:
            release.set()
            for lane in lanes: lane.thread.join(2)

    def test_pipeline_result_dict_all_keys_present(self, tmp_path):
        """run_pipeline() result dict contains all documented keys."""
        from aql.pipeline import run_pipeline

        bars = [_make_live_bar(i) for i in range(3)]
        CollectorCls = _make_synthetic_collector_class(bars)

        with (
            patch("aql.pipeline.BinanceCollector", CollectorCls),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
        ):
            result = run_pipeline(
                symbol=SYMBOL, interval=INTERVAL,
                duration_s=1.0,
                data_dir=str(tmp_path / "keys_test"),
            )

        required_keys = {
            "symbol", "interval", "elapsed_s", "ws_messages", "final_bars_received",
            "non_final_bars", "journal_committed", "duplicates", "store_inserted",
            "store_total", "errors", "reconnects", "avg_latency_ws_to_commit_ms",
            "journal_state_counts", "bar_range", "startup_gap_recovery",
            "startup_reconcile", "ws_gap_recovery", "supabase_status",
            "health_snapshot",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"Missing keys in pipeline result: {missing}"

    def test_pipeline_duplicate_bars_no_store_duplicates(self, tmp_path):
        """Injecting the same bar twice must not create duplicate store rows."""
        from aql.pipeline import run_pipeline

        bars = [_make_live_bar(i) for i in range(3)]
        bars_doubled = bars + bars  # same bars twice
        CollectorCls = _make_synthetic_collector_class(bars_doubled)

        with (
            patch("aql.pipeline.BinanceCollector", CollectorCls),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
        ):
            result = run_pipeline(
                symbol=SYMBOL, interval=INTERVAL,
                duration_s=1.0,
                data_dir=str(tmp_path / "dup_test"),
            )

        assert result["store_total"] == 3, (
            f"Expected exactly 3 unique rows, got {result['store_total']}"
        )
        # SyntheticCollector tracks journal duplicates in metrics.duplicate_count
        assert result["duplicates"] >= 3, (
            f"Expected ≥3 duplicates tracked, got {result['duplicates']}"
        )

    def test_pipeline_health_snapshot_fully_serialisable(self, tmp_path):
        """health_snapshot from run_pipeline must be JSON-serialisable."""
        import json
        from aql.pipeline import run_pipeline

        bars = [_make_live_bar(i) for i in range(3)]
        CollectorCls = _make_synthetic_collector_class(bars)

        with (
            patch("aql.pipeline.BinanceCollector", CollectorCls),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
        ):
            result = run_pipeline(
                symbol=SYMBOL, interval=INTERVAL,
                duration_s=1.0,
                data_dir=str(tmp_path / "serial_test"),
            )

        # Must not raise
        serialised = json.dumps(result["health_snapshot"])
        assert '"status"' in serialised


# ---------------------------------------------------------------------------
# Child process script template
# ---------------------------------------------------------------------------
# The child:
#   1. Opens DurableJournal at JOURNAL_PATH
#   2. Commits N_BARS bars (not to store — simulates crash before store.upsert)
#   3. Writes a "ready" file (SIGKILL synchronisation point)
#   4. Sleeps until killed
#
# The parent (test) polls for the ready file, then os.kill(SIGKILL), and
# opens fresh journal+store to run startup_reconcile.

_CHILD_SCRIPT = textwrap.dedent(
    """\
    import sys
    import time
    from pathlib import Path

    sys.path.insert(0, "{src_path}")

    from aql.journal.durable_journal import DurableJournal
    from aql.models.bar import BarState, MarketBar

    SYMBOL = "BTCUSDT"
    INTERVAL = "1m"
    INTERVAL_MS = 60_000
    BASE_OPEN = {base_open}
    N_BARS = {n_bars}

    journal = DurableJournal("{journal_path}")
    for i in range(N_BARS):
        bar_open = BASE_OPEN + i * INTERVAL_MS
        bar_close = bar_open + INTERVAL_MS - 1
        bar = MarketBar(
            symbol=SYMBOL,
            interval=INTERVAL,
            bar_open=bar_open,
            bar_close=bar_close,
            open=200.0 + i,
            high=201.0 + i,
            low=199.0 + i,
            close=200.5 + i,
            volume=20.0 + i,
            is_final=True,
            source="synthetic_ws",
            ingested_at=bar_open + 500,
            committed_at=bar_open + 550,
            state=BarState.LOCAL_COMMITTED,
            checksum=None,
        )
        bar.checksum = bar.compute_checksum()
        # Commit to journal — SIGKILL durability boundary
        journal.commit(bar)
        # Deliberately do NOT call store.upsert or mark_persisted:
        # startup_reconcile must replay these bars after the kill.

    # Signal parent: all journal.commit() calls have returned (WAL fsynced).
    Path("{flag_path}").write_text("ready")

    # Wait for SIGKILL — no graceful shutdown
    time.sleep(3600)
    """
)

_SYNC_TIMEOUT_S = 20  # max seconds to wait for child's flag file


# ---------------------------------------------------------------------------
# T_WP04_FIX01_02 — Real Subprocess SIGKILL Evidence
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "signal.SIGKILL is not available on Windows — subprocess termination "
        "semantics differ.  Run this test on a POSIX runner (Linux/macOS) to "
        "generate real SIGKILL evidence.  Not PASS-without-kill."
    ),
)
class TestT_WP04_FIX01_02_SubprocessSigkill:
    """
    AG-F03, AG-F04, AG-F05: Real OS-level subprocess SIGKILL with an
    explicit synchronisation point confirming durable journal commits
    before the kill.

    Not PARTIAL — uses subprocess.Popen + os.kill(pid, signal.SIGKILL).
    Skipped on Windows with an explicit reason (never PASS-without-kill).
    """

    N_SIGKILL_BARS = 10

    def _spawn_child_and_sync(
        self,
        tmp_path: Path,
        n_bars: Optional[int] = None,
        suffix: str = "",
    ):
        """
        Write child script to disk, start it, wait for journal-ready flag.

        Returns (proc, journal_path, store_path, expected_opens).
        Raises pytest.fail if the child exits early or times out.
        """
        if n_bars is None:
            n_bars = self.N_SIGKILL_BARS

        journal_path = str(tmp_path / f"j_sigkill{suffix}.sqlite")
        store_path = str(tmp_path / f"s_sigkill{suffix}.sqlite")
        flag_path = str(tmp_path / f"journal_ready{suffix}.flag")
        script_path = str(tmp_path / f"child_writer{suffix}.py")

        script = _CHILD_SCRIPT.format(
            src_path=_SRC_PATH,
            base_open=BASE_OPEN_STATIC,
            n_bars=n_bars,
            journal_path=journal_path,
            flag_path=flag_path,
        )
        Path(script_path).write_text(script)

        # -I: isolated mode — ignores PYTHONPATH but respects sys.path.insert in script
        proc = subprocess.Popen(
            [sys.executable, "-I", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        deadline = time.monotonic() + _SYNC_TIMEOUT_S
        while time.monotonic() < deadline:
            if Path(flag_path).exists():
                break
            if proc.poll() is not None:
                _, stderr = proc.communicate(timeout=3)
                pytest.fail(
                    f"Child process exited prematurely (code={proc.returncode}). "
                    f"stderr: {stderr.decode(errors='replace')[:800]}"
                )
            time.sleep(0.05)
        else:
            proc.kill()
            proc.wait(timeout=5)
            pytest.fail(
                f"Child did not write journal-ready flag within {_SYNC_TIMEOUT_S}s"
            )

        expected_opens = {
            BASE_OPEN_STATIC + i * INTERVAL_MS for i in range(n_bars)
        }
        return proc, journal_path, store_path, expected_opens

    # ------------------------------------------------------------------
    # AG-F03
    # ------------------------------------------------------------------

    def test_ag_f03_sigkill_journal_to_store_recovery(self, tmp_path):
        """
        AG-F03: Child commits N_SIGKILL_BARS to journal only (no store),
        is hard-killed with SIGKILL.  Parent's startup_reconcile must
        replay ALL N bars into the store with zero errors and exact key
        coverage.

        Evidence produced:
          - subprocess.Popen returncode == -SIGKILL (< 0 on Linux)
          - bars_replayed == N_SIGKILL_BARS
          - store_count == N_SIGKILL_BARS
          - store_keys == expected_opens (no missing, no extras)
          - replay_errors == 0
        """
        proc, journal_path, store_path, expected_opens = (
            self._spawn_child_and_sync(tmp_path)
        )

        # Hard kill — no graceful shutdown, no journal flush, no mark_persisted
        os.kill(proc.pid, signal.SIGKILL)
        rc = proc.wait(timeout=5)

        # On Linux: returncode == -(signal_number) for SIGKILL
        assert rc < 0, (
            f"Process not killed by signal (returncode={rc}); expected < 0"
        )

        # ---- Open fresh journal + store ("new process" after restart) ----
        journal2 = DurableJournal(journal_path)
        store2 = OperationalStore(store_path)

        bars_replayed, replay_inserted, replay_errors, gaps = (
            journal2.startup_reconcile(
                store=store2,
                symbol=SYMBOL,
                interval=INTERVAL,
            )
        )

        store_count = store2.count(SYMBOL, INTERVAL)
        store_keys = store2.get_stored_keys(SYMBOL, INTERVAL)

        assert store_count == self.N_SIGKILL_BARS, (
            f"Expected {self.N_SIGKILL_BARS} bars after SIGKILL recovery, "
            f"got {store_count}"
        )
        assert replay_errors == 0, f"replay_errors={replay_errors}"
        assert bars_replayed == self.N_SIGKILL_BARS, (
            f"Expected {self.N_SIGKILL_BARS} bars replayed from journal, "
            f"got {bars_replayed}"
        )
        assert store_keys == expected_opens, (
            f"Key coverage mismatch after SIGKILL recovery:\n"
            f"  missing={expected_opens - store_keys}\n"
            f"  extra={store_keys - expected_opens}"
        )

        print(
            f"\n  AG-F03 PASS  SIGKILL rc={rc}  "
            f"bars_replayed={bars_replayed}  "
            f"store={store_count}  "
            f"replay_errors={replay_errors}"
        )

    # ------------------------------------------------------------------
    # AG-F04
    # ------------------------------------------------------------------

    def test_ag_f04_double_reconcile_idempotent_no_duplicates(self, tmp_path):
        """
        AG-F04: After SIGKILL + first startup_reconcile, a second call to
        startup_reconcile must insert 0 new rows (idempotent replay).
        Store row count remains N after both calls — no duplicates.
        """
        proc, journal_path, store_path, _ = (
            self._spawn_child_and_sync(tmp_path, suffix="_f04")
        )
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)

        # First reconcile — fills the store
        j1 = DurableJournal(journal_path)
        s1 = OperationalStore(store_path)
        j1.startup_reconcile(store=s1, symbol=SYMBOL, interval=INTERVAL)
        count_after_first = s1.count(SYMBOL, INTERVAL)

        # Second reconcile — must not insert any new rows
        j2 = DurableJournal(journal_path)
        s2 = OperationalStore(store_path)
        _, replay_inserted2, replay_errors2, _ = j2.startup_reconcile(
            store=s2, symbol=SYMBOL, interval=INTERVAL
        )
        count_after_second = s2.count(SYMBOL, INTERVAL)

        assert count_after_first == self.N_SIGKILL_BARS, (
            f"After first reconcile: expected {self.N_SIGKILL_BARS}, "
            f"got {count_after_first}"
        )
        assert count_after_second == self.N_SIGKILL_BARS, (
            f"After second reconcile: expected {self.N_SIGKILL_BARS}, "
            f"got {count_after_second}"
        )
        assert replay_inserted2 == 0, (
            f"Second reconcile inserted {replay_inserted2} rows — not idempotent"
        )
        assert replay_errors2 == 0

        print(
            f"\n  AG-F04 PASS  "
            f"count_1={count_after_first}  count_2={count_after_second}  "
            f"inserted_2nd={replay_inserted2} (idempotent)"
        )

    # ------------------------------------------------------------------
    # AG-F05
    # ------------------------------------------------------------------

    def test_ag_f05_health_healthy_after_sigkill_recovery(self, tmp_path):
        """
        AG-F05: After SIGKILL + startup_reconcile, take_snapshot must
        return HEALTHY.  Injected now_ms_fn sets lag = 30 s
        (< DEFAULT_LAG_WARN_S=90 s).  All bars recovered → no backlog.
        integrity_ok must be True.
        """
        proc, journal_path, store_path, _ = (
            self._spawn_child_and_sync(tmp_path, suffix="_f05")
        )
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)

        j2 = DurableJournal(journal_path)
        s2 = OperationalStore(store_path)
        _, _, replay_errors, _ = j2.startup_reconcile(
            store=s2, symbol=SYMBOL, interval=INTERVAL
        )
        assert replay_errors == 0

        # Inject a synthetic now_ms: 30 s after the last bar's close.
        # BASE_OPEN_STATIC bars are at 2023-11-15; wall-clock lag would be
        # enormous if we used real time, so we must inject now_ms_fn.
        last_close = BASE_OPEN_STATIC + self.N_SIGKILL_BARS * INTERVAL_MS - 1
        now_ms = last_close + 30_000  # 30 s lag — inside HEALTHY window

        snap = take_snapshot(
            j2, s2, SYMBOL, INTERVAL,
            replay_errors=replay_errors,
            now_ms_fn=lambda: now_ms,
        )

        assert snap.status == "HEALTHY", (
            f"Expected HEALTHY after SIGKILL recovery. Snapshot: {snap.to_dict()}"
        )
        assert snap.unresolved_backlog is False, (
            f"Unexpected unresolved_backlog after full replay: {snap.to_dict()}"
        )
        assert snap.integrity_ok is True, (
            f"integrity_ok=False after recovery: {snap.to_dict()}"
        )
        assert snap.store_final_count == self.N_SIGKILL_BARS, (
            f"Expected {self.N_SIGKILL_BARS} in store, got {snap.store_final_count}"
        )

        print(
            f"\n  AG-F05 PASS  health={snap.status}  "
            f"store={snap.store_final_count}  "
            f"backlog={snap.unresolved_backlog}  "
            f"integrity={snap.integrity_ok}"
        )


# ---------------------------------------------------------------------------
# T_WP04_FIX01_03 — Combined FIX01 Acceptance Gate Report
# ---------------------------------------------------------------------------

class TestT_WP04_FIX01_03_AcceptanceGateReport:
    """
    Prints a consolidated gate summary and validates gate map completeness.
    Runs after all individual tests.
    """

    def test_fix01_gate_map_complete(self):
        """
        Document the FIX01 acceptance gate → test mapping and assert that
        all non-Windows gates are present (non-empty references).
        """
        gate_map = {
            "AG-F01": (
                "Pipeline orchestration: run_pipeline() with synthetic adapters, "
                "deterministic now_ms_fn → store_total==N_PIPELINE_BARS, errors==0, "
                "health==HEALTHY (exact, not loose set)",
                "TestT_WP04_FIX01_01::test_ag_f01_pipeline_fresh_start_healthy",
                "PASS (all platforms)",
            ),
            "AG-F02": (
                "Pipeline restart: startup_reconcile replays journal bars, "
                "deterministic now_ms_fn → health==HEALTHY (exact, not loose set)",
                "TestT_WP04_FIX01_01::test_ag_f02_pipeline_restart_replays_journal",
                "PASS (all platforms)",
            ),
            "AG-F03": (
                "Subprocess SIGKILL: child commits N bars to journal only, "
                "SIGKILL, startup_reconcile recovers all bars, no duplicates",
                "TestT_WP04_FIX01_02::test_ag_f03_sigkill_journal_to_store_recovery",
                "PASS (POSIX) / SKIP (Windows)",
            ),
            "AG-F04": (
                "Double startup_reconcile is idempotent "
                "→ replay_inserted_2==0, store_count unchanged",
                "TestT_WP04_FIX01_02::test_ag_f04_double_reconcile_idempotent_no_duplicates",
                "PASS (POSIX) / SKIP (Windows)",
            ),
            "AG-F05": (
                "Health after SIGKILL recovery == HEALTHY, "
                "unresolved_backlog==False, integrity_ok==True",
                "TestT_WP04_FIX01_02::test_ag_f05_health_healthy_after_sigkill_recovery",
                "PASS (POSIX) / SKIP (Windows)",
            ),
            "AG-FP01": (
                "Full-pipeline SIGKILL: child runs run_pipeline() with _CrashCollector "
                "(journal-only, no store.upsert), SIGKILL after flag, "
                "restart via run_pipeline() → bars_replayed==N_FP_BARS",
                "TestT_WP04_FIX02_04_FullPipelineSIGKILL::"
                "test_ag_fp01_full_pipeline_sigkill_and_restart",
                "PASS (POSIX) / SKIP (Windows)",
            ),
            "AG-FP02": (
                "Exact key coverage + health==HEALTHY after full-pipeline restart; "
                "idempotent double-restart (replay_inserted_2==0)",
                "TestT_WP04_FIX02_04_FullPipelineSIGKILL::"
                "test_ag_fp01_full_pipeline_sigkill_and_restart",
                "PASS (POSIX) / SKIP (Windows)",
            ),
        }

        print("\n=== WP04-FIX01 Acceptance Gate Summary ===")
        for gate_id, (description, test_ref, expected) in sorted(gate_map.items()):
            print(f"  {gate_id}: {expected}")
            print(f"    {description}")
            print(f"    → {test_ref}")
        print("==========================================\n")

        always_present_gates = ["AG-F01", "AG-F02", "AG-FP01", "AG-FP02"]
        for gate_id in always_present_gates:
            desc, ref, _ = gate_map[gate_id]
            assert desc, f"{gate_id} has empty description"
            assert ref, f"{gate_id} has no test reference"


# ---------------------------------------------------------------------------
# Full-pipeline SIGKILL child script template  (Issue #51 — FIX02)
# ---------------------------------------------------------------------------
#
# The child process runs actual run_pipeline() with:
#   - _CrashCollector: commits N bars to journal, writes flag, sleeps
#     (never calls store.upsert — simulates crash before store write)
#   - _noop_recover_gap: no real HTTP calls
#
# The parent polls for the flag file, then os.kill(SIGKILL) on the
# child's PID (which is the pipeline process itself, not a separate
# journal-writer).  This proves full pipeline orchestration: startup_reconcile
# runs (0 bars, clean DB), then _CrashCollector.run() commits N bars and
# signals the parent, then the child is killed — all through the real
# run_pipeline() call stack.

_PIPELINE_CHILD_SCRIPT = textwrap.dedent(
    """\
    import sys
    import time
    from pathlib import Path
    from unittest.mock import patch

    sys.path.insert(0, "{src_path}")

    from aql.pipeline import run_pipeline
    from aql.collector.binance_collector import CollectorMetrics
    from aql.journal.durable_journal import DurableJournal
    from aql.models.bar import BarState, MarketBar
    from aql.recovery.gap_recovery import RecoveryReport

    SYMBOL = "BTCUSDT"
    INTERVAL = "1m"
    INTERVAL_MS = 60_000
    BASE_OPEN = {base_open}
    N_BARS = {n_bars}
    FLAG_PATH = "{flag_path}"
    DATA_DIR = "{data_dir}"

    def _noop_recover_gap(symbol, interval, gap_start_ms, gap_end_ms, existing_keys):
        \"\"\"Synthetic REST gap recovery — no HTTP calls.\"\"\"
        return [], RecoveryReport(
            symbol=symbol,
            interval=interval,
            gap_start_ms=gap_start_ms,
            gap_end_ms=gap_end_ms,
            expected_bars=0,
            recovered_bars=0,
            already_stored=0,
            unresolved=0,
            missing_opens=[],
            status="FULL",
            weight_cost=0,
            last_seen_window_weight=0,
            http_error=None,
        )

    class _CrashCollector:
        \"\"\"
        Commits N bars to journal only (no store.upsert), writes a flag file
        to signal the parent that journal commits are durable, then sleeps
        until the parent SIGKILLs this process.

        gap_start_ms / gap_end_ms left None (no WS gap).
        \"\"\"
        def __init__(self, symbol, interval, journal, store, **kwargs):
            self._journal = journal
            self.gap_start_ms = None
            self.gap_end_ms = None

        def run(self, timeout_s=None):
            metrics = CollectorMetrics()
            for i in range(N_BARS):
                bar_open = BASE_OPEN + i * INTERVAL_MS
                bar_close = bar_open + INTERVAL_MS - 1
                bar = MarketBar(
                    symbol=SYMBOL,
                    interval=INTERVAL,
                    bar_open=bar_open,
                    bar_close=bar_close,
                    open=300.0 + i,
                    high=301.0 + i,
                    low=299.0 + i,
                    close=300.5 + i,
                    volume=30.0 + i,
                    is_final=True,
                    source="synthetic_pipeline_crash",
                    ingested_at=bar_open + 500,
                    committed_at=bar_open + 550,
                    state=BarState.LOCAL_COMMITTED,
                    checksum=None,
                )
                bar.checksum = bar.compute_checksum()
                # Commit to journal — durable before flag write (WAL + FULL sync)
                self._journal.commit(bar)
                metrics.journal_commit_count += 1
                metrics.final_bar_count += 1
                metrics.ws_message_count += 1

            # Signal parent: all journal.commit() calls have returned.
            # IMPORTANT: do NOT call store.upsert() — simulate crash before store.
            Path(FLAG_PATH).write_text("ready")

            # Sleep until SIGKILL — never reaches store.upsert or mark_persisted.
            time.sleep(3600)
            return metrics  # unreachable

    with (
        patch("aql.pipeline.BinanceCollector", _CrashCollector),
        patch("aql.pipeline.recover_gap", _noop_recover_gap),
        # Independent persistence now runs beside collection. Explicitly inject
        # a store outage so the SIGKILL boundary still has N orphaned commits.
        # All original exact key/replay/health assertions remain unchanged.
        patch("aql.pipeline.OperationalStore.upsert",
              side_effect=ConnectionError("synthetic store outage before SIGKILL")),
    ):
        run_pipeline(
            symbol=SYMBOL,
            interval=INTERVAL,
            duration_s=3600.0,
            data_dir=DATA_DIR,
        )
    """
)


# ---------------------------------------------------------------------------
# T_WP04_FIX02_04 — Full-Pipeline Subprocess SIGKILL (Issue #51)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "signal.SIGKILL is not available on Windows — subprocess termination "
        "semantics differ.  Run this test on a POSIX runner (Linux/macOS) to "
        "generate real full-pipeline SIGKILL evidence.  Not PASS-without-kill."
    ),
)
class TestT_WP04_FIX02_04_FullPipelineSIGKILL:
    """
    AG-FP01, AG-FP02: Full-pipeline OS-level subprocess SIGKILL.

    The child process runs actual run_pipeline() with:
      - _CrashCollector injected for BinanceCollector (commits to journal
        only, writes flag, sleeps — no store.upsert)
      - _noop_recover_gap injected for recover_gap (no HTTP)

    Distinction from T_WP04_FIX01_02 (journal-level component test)
    -----------------------------------------------------------------
    FIX01 child is a standalone journal writer (never calls run_pipeline).
    FIX02 child executes ``run_pipeline()`` through its real entry point,
    exercising startup_reconcile → _CrashCollector.run() → flag → sleep.
    The kill target is the pipeline orchestration process itself.

    Not PARTIAL — uses subprocess.Popen + os.kill(pid, signal.SIGKILL).
    Skipped on Windows with explicit reason (never PASS-without-kill).
    """

    N_FP_BARS = 8  # bars committed to journal before SIGKILL

    def _spawn_pipeline_child_and_sync(
        self,
        tmp_path: Path,
        n_bars: int,
        suffix: str = "",
    ):
        """
        Write pipeline child script to disk, start it, wait for flag.

        The child runs run_pipeline() via _CrashCollector; the flag file
        is written after all N_BARS journal.commit() calls return,
        confirming durable writes before the parent sends SIGKILL.

        Returns (proc, data_dir_str, expected_opens).
        Raises pytest.fail if child exits early or times out.
        """
        data_dir = str(tmp_path / f"fp_data{suffix}")
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        flag_path = str(tmp_path / f"fp_ready{suffix}.flag")
        script_path = str(tmp_path / f"fp_child{suffix}.py")

        script = _PIPELINE_CHILD_SCRIPT.format(
            src_path=_SRC_PATH,
            base_open=BASE_OPEN_STATIC,
            n_bars=n_bars,
            flag_path=flag_path,
            data_dir=data_dir,
        )
        Path(script_path).write_text(script)

        # -I: isolated mode so child uses sys.path.insert(0, src_path) from script
        proc = subprocess.Popen(
            [sys.executable, "-I", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        deadline = time.monotonic() + _SYNC_TIMEOUT_S
        while time.monotonic() < deadline:
            if Path(flag_path).exists():
                break
            if proc.poll() is not None:
                _, stderr = proc.communicate(timeout=3)
                pytest.fail(
                    f"Pipeline child process exited prematurely "
                    f"(code={proc.returncode}). "
                    f"stderr: {stderr.decode(errors='replace')[:1200]}"
                )
            time.sleep(0.05)
        else:
            proc.kill()
            proc.wait(timeout=5)
            pytest.fail(
                f"Pipeline child did not write ready flag within {_SYNC_TIMEOUT_S}s"
            )

        expected_opens = {
            BASE_OPEN_STATIC + i * INTERVAL_MS for i in range(n_bars)
        }
        return proc, data_dir, expected_opens

    def test_ag_fp01_full_pipeline_sigkill_and_restart(self, tmp_path):
        """
        AG-FP01, AG-FP02: Full-pipeline SIGKILL and restart verification.

        Phase 1 — Spawn pipeline child
          - Child runs run_pipeline() with _CrashCollector + _noop_recover_gap
          - startup_reconcile: 0 bars on clean DB (no-op)
          - _CrashCollector.run(): commits N_FP_BARS to journal, writes flag
          - Parent waits for flag (durable journal commit confirmed)

        Phase 2 — SIGKILL pipeline process
          - os.kill(child.pid, signal.SIGKILL) — kills the run_pipeline() process
          - Assert returncode < 0 (signal kill, not graceful exit)

        Phase 3 — Restart via actual pipeline entry point (AG-FP01)
          - run_pipeline() called with empty _SyntheticCollector
          - startup_reconcile detects N_FP_BARS orphaned journal entries
            (journal.commit done, store never written)
          - Replays all N_FP_BARS into store
          - Assert bars_replayed == N_FP_BARS, store_total == N_FP_BARS

        Phase 4 — Exact key coverage + health (AG-FP02)
          - store.get_stored_keys() == expected_opens (no missing, no extras)
          - deterministic now_ms_fn → health == "HEALTHY" (exact)
          - unresolved_backlog == False, integrity_ok == True

        Phase 5 — Idempotent double-restart (AG-FP02)
          - Second run_pipeline() with empty collector
          - startup_reconcile finds all bars already in store → replay_inserted==0
          - store_total unchanged at N_FP_BARS
        """
        from aql.pipeline import run_pipeline

        # Phase 1: spawn pipeline child and wait for durable journal commits
        proc, data_dir, expected_opens = self._spawn_pipeline_child_and_sync(
            tmp_path, n_bars=self.N_FP_BARS
        )

        # Phase 2: SIGKILL the pipeline process
        os.kill(proc.pid, signal.SIGKILL)
        rc = proc.wait(timeout=5)
        # On Linux: returncode == -(signal_number) for SIGKILL
        assert rc < 0, (
            f"AG-FP01: pipeline process not killed by signal "
            f"(returncode={rc}); expected < 0"
        )

        # Phase 3: Restart via actual pipeline entry point
        # Empty collector — startup_reconcile handles all bars
        EmptyCollector = _make_synthetic_collector_class([])

        # Deterministic clock: 30 s after last bar's close (BASE_OPEN_STATIC epoch)
        last_close_fp = BASE_OPEN_STATIC + self.N_FP_BARS * INTERVAL_MS - 1
        restart_now_ms = last_close_fp + 30_000  # 30 s lag → HEALTHY

        with (
            patch("aql.pipeline.BinanceCollector", EmptyCollector),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
        ):
            result = run_pipeline(
                symbol=SYMBOL,
                interval=INTERVAL,
                duration_s=1.0,
                data_dir=data_dir,
                now_ms_fn=lambda: restart_now_ms,
            )

        # AG-FP01: bars_replayed and store_total
        sr = result["startup_reconcile"]
        assert sr["bars_replayed"] == self.N_FP_BARS, (
            f"AG-FP01 FAIL: expected {self.N_FP_BARS} bars replayed by "
            f"startup_reconcile after SIGKILL, got {sr['bars_replayed']}"
        )
        assert sr["replay_errors"] == 0, (
            f"AG-FP01 FAIL: replay_errors={sr['replay_errors']} (expected 0)"
        )
        assert result["store_total"] == self.N_FP_BARS, (
            f"AG-FP01 FAIL: expected {self.N_FP_BARS} bars in store after restart, "
            f"got {result['store_total']}"
        )

        # Phase 4: exact key coverage and health (AG-FP02)
        store_verify = OperationalStore(
            str(Path(data_dir) / "operational.sqlite")
        )
        actual_keys = store_verify.get_stored_keys(SYMBOL, INTERVAL)
        assert actual_keys == expected_opens, (
            f"AG-FP02 FAIL: key coverage mismatch after full-pipeline SIGKILL restart:\n"
            f"  missing={expected_opens - actual_keys}\n"
            f"  extra={actual_keys - expected_opens}"
        )

        hs = result["health_snapshot"]
        assert hs["status"] == "HEALTHY", (
            f"AG-FP02 FAIL: expected exactly HEALTHY after full-pipeline restart "
            f"(deterministic clock, lag=30s). Got: {hs['status']}. "
            f"Full snapshot: {hs}"
        )
        assert hs["unresolved_backlog"] is False, (
            f"AG-FP02 FAIL: unresolved_backlog=True after full replay: {hs}"
        )
        assert hs["integrity_ok"] is True, (
            f"AG-FP02 FAIL: integrity_ok=False after recovery: {hs}"
        )

        # Phase 5: idempotent double-restart (AG-FP02)
        with (
            patch("aql.pipeline.BinanceCollector", EmptyCollector),
            patch("aql.pipeline.recover_gap", _synthetic_recover_gap),
        ):
            result2 = run_pipeline(
                symbol=SYMBOL,
                interval=INTERVAL,
                duration_s=1.0,
                data_dir=data_dir,
                now_ms_fn=lambda: restart_now_ms,
            )

        sr2 = result2["startup_reconcile"]
        assert sr2["replay_inserted"] == 0, (
            f"AG-FP02 FAIL: second restart inserted {sr2['replay_inserted']} "
            f"rows — not idempotent"
        )
        assert result2["store_total"] == self.N_FP_BARS, (
            f"AG-FP02 FAIL: after second restart: expected {self.N_FP_BARS}, "
            f"got {result2['store_total']}"
        )

        print(
            f"\n  AG-FP01 PASS  SIGKILL rc={rc}  "
            f"bars_replayed={sr['bars_replayed']}  "
            f"store={result['store_total']}  "
            f"health={hs['status']}\n"
            f"  AG-FP02 PASS  "
            f"exact_key_coverage=True  "
            f"idempotent=(replay_inserted_2=={sr2['replay_inserted']})"
        )
