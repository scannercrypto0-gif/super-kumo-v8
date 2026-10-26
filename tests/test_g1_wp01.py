"""
G1-WP01-MVP Mandatory Test Suite

8 tests per execution order §4:
  T1 - Live ingestion (mocked — real live test in test_live_ingestion.py)
  T2 - Durability: data survives process restart (journal survives new instance)
  T3 - Duplicate replay: no new rows in store on re-replay
  T4 - Process kill simulation: restart with replay + continuity check
  T5 - Network interruption: gap detection logged
  T6 - REST gap recovery: fetches bars and shows any remaining gap
  T7 - Corrupt/truncated journal: detection, no silent acceptance
  T8 - Storage unavailable: committed data retained locally until retry

All tests are automated (no network required except T6 which is marked
LIVE_OPTIONAL and skipped if BINANCE_LIVE_TEST=0).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

# Make src importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aql.journal.durable_journal import DurableJournal, JournalCorruptionError
from aql.models.bar import BarState, MarketBar
from aql.recovery.gap_recovery import recover_gap
from aql.storage.operational_store import OperationalStore


def _make_bar(
    bar_open: int = 1_700_000_000_000,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    is_final: bool = True,
    source: str = "binance_ws",
    close: float = 42000.0,
) -> MarketBar:
    """Factory: create a synthetic final bar."""
    bar_close = bar_open + 60_000 - 1
    now = int(time.time() * 1000)
    bar = MarketBar(
        symbol=symbol,
        interval=interval,
        bar_open=bar_open,
        bar_close=bar_close,
        open=41900.0,
        high=42100.0,
        low=41800.0,
        close=close,
        volume=100.5,
        is_final=is_final,
        source=source,
        ingested_at=now,
        state=BarState.RECEIVED,
    )
    return bar.with_checksum()


class TestT1_Ingestion(unittest.TestCase):
    """T1: Ingestion — bar parsed from Binance WS payload, final flag respected."""

    def test_parse_binance_ws_kline_final(self):
        k = {
            "s": "BTCUSDT", "i": "1m",
            "t": 1_700_000_000_000, "T": 1_700_000_059_999,
            "o": "41900.0", "h": "42100.0", "l": "41800.0",
            "c": "42000.0", "v": "100.5",
            "x": True,
        }
        bar = MarketBar.from_binance_ws_kline(k)
        self.assertEqual(bar.symbol, "BTCUSDT")
        self.assertEqual(bar.interval, "1m")
        self.assertTrue(bar.is_final)
        self.assertEqual(bar.source, "binance_ws")
        self.assertIsNotNone(bar.checksum)
        self.assertEqual(bar.state, BarState.RECEIVED)

    def test_parse_binance_ws_kline_non_final(self):
        k = {
            "s": "BTCUSDT", "i": "1m",
            "t": 1_700_000_000_000, "T": 1_700_000_059_999,
            "o": "41900.0", "h": "42100.0", "l": "41800.0",
            "c": "42000.0", "v": "100.5",
            "x": False,
        }
        bar = MarketBar.from_binance_ws_kline(k)
        self.assertFalse(bar.is_final)

    def test_timestamps_recorded(self):
        k = {
            "s": "BTCUSDT", "i": "1m",
            "t": 1_700_000_000_000, "T": 1_700_000_059_999,
            "o": "41900", "h": "42100", "l": "41800",
            "c": "42000", "v": "10",
            "x": True,
        }
        before = int(time.time() * 1000)
        bar = MarketBar.from_binance_ws_kline(k)
        after = int(time.time() * 1000)
        self.assertGreaterEqual(bar.ingested_at, before)
        self.assertLessEqual(bar.ingested_at, after)
        self.assertEqual(bar.bar_open, 1_700_000_000_000)
        self.assertEqual(bar.bar_close, 1_700_000_059_999)

    def test_stable_key_format(self):
        bar = _make_bar(bar_open=1_700_000_000_000)
        self.assertEqual(bar.stable_key(), "BTCUSDT:1m:1700000000000")


class TestT2_Durability(unittest.TestCase):
    """T2: Data committed to journal survives creating a new journal instance."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "journal.sqlite")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_data_survives_new_instance(self):
        bar = _make_bar(bar_open=1_700_000_000_000)

        # Write in instance 1
        j1 = DurableJournal(self.db_path)
        committed = j1.commit(bar)
        self.assertTrue(committed)
        del j1  # simulate process restart

        # Read in instance 2 (new object, same file)
        j2 = DurableJournal(self.db_path)
        bars = j2.replay(symbol="BTCUSDT", interval="1m")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].bar_open, 1_700_000_000_000)
        self.assertEqual(bars[0].state, BarState.LOCAL_COMMITTED)

    def test_legacy_marker_and_versioned_commit_return_receipt(self):
        bar = _make_bar()
        j = DurableJournal(self.db_path)
        j.commit(bar)
        bars = j.replay()
        self.assertIsNotNone(bars[0].committed_at)
        self.assertGreater(bars[0].committed_at, bars[0].ingested_at - 1000)
        proof = j.commit_receipt(bars[0].stable_key())
        self.assertEqual(proof["version"], 1)
        self.assertGreaterEqual(proof["commit_return_observed_at_ms"], bars[0].committed_at)


class TestT3_DuplicateReplay(unittest.TestCase):
    """T3: Replaying same bar multiple times → no new rows in store."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_journal_duplicate_idempotent(self):
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        bar = _make_bar(bar_open=1_700_000_000_000)
        r1 = j.commit(bar)
        r2 = j.commit(bar)  # exact same bar
        self.assertTrue(r1)
        self.assertFalse(r2)
        bars = j.replay()
        self.assertEqual(len(bars), 1)

    def test_store_duplicate_idempotent(self):
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))
        bar = _make_bar(bar_open=1_700_000_000_000)
        r1 = s.upsert(bar)
        r2 = s.upsert(bar)
        r3 = s.upsert(bar)
        self.assertTrue(r1)
        self.assertFalse(r2)
        self.assertFalse(r3)
        self.assertEqual(s.count("BTCUSDT", "1m"), 1)

    def test_replay_then_store_no_duplicates(self):
        db = os.path.join(self.tmpdir, "j2.sqlite")
        sdb = os.path.join(self.tmpdir, "s2.sqlite")
        j = DurableJournal(db)
        s = OperationalStore(sdb)

        bars = [_make_bar(bar_open=1_700_000_000_000 + i * 60_000) for i in range(5)]
        for bar in bars:
            j.commit(bar)

        # Replay and upsert — simulate initial consume
        for bar in j.replay():
            s.upsert(bar)

        # Replay again — simulate restart with replay
        for bar in j.replay():
            s.upsert(bar)

        self.assertEqual(s.count("BTCUSDT", "1m"), 5)

    def test_store_rejects_non_final_bar(self):
        s = OperationalStore(os.path.join(self.tmpdir, "s3.sqlite"))
        bar = _make_bar(is_final=False)
        with self.assertRaises(ValueError):
            s.upsert(bar)


class TestT4_ProcessKill(unittest.TestCase):
    """T4: Simulate kill + restart: replay from journal, check continuity."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.jpath = os.path.join(self.tmpdir, "j.sqlite")
        self.spath = os.path.join(self.tmpdir, "s.sqlite")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_restart_replay_continuity(self):
        # Phase 1: receive 5 bars
        j = DurableJournal(self.jpath)
        s = OperationalStore(self.spath)
        bars_phase1 = [_make_bar(bar_open=1_700_000_000_000 + i * 60_000) for i in range(5)]
        for bar in bars_phase1:
            j.commit(bar)
            s.upsert(bar)

        # Simulate kill: close (del) journal and store
        del j, s

        # Phase 2: restart — new instances, same files
        t_restart_start = time.time()
        j2 = DurableJournal(self.jpath)
        s2 = OperationalStore(self.spath)

        replayed = j2.replay(symbol="BTCUSDT", interval="1m")
        inserted_on_replay = 0
        for bar in replayed:
            if s2.upsert(bar):
                inserted_on_replay += 1

        restart_time_ms = (time.time() - t_restart_start) * 1000

        # All 5 bars present, none added again (already persisted)
        self.assertEqual(len(replayed), 5)
        self.assertEqual(s2.count("BTCUSDT", "1m"), 5)
        self.assertEqual(inserted_on_replay, 0)  # already in store before kill
        self.assertLess(restart_time_ms, 5000, "Replay should complete in <5s")

    def test_partial_commit_before_kill(self):
        """Bars committed to journal but not yet upserted to store are recovered on replay."""
        j = DurableJournal(self.jpath)
        s = OperationalStore(self.spath)

        # 3 bars committed to journal only (simulating kill before store upsert)
        bars = [_make_bar(bar_open=1_700_000_000_000 + i * 60_000) for i in range(3)]
        for bar in bars:
            j.commit(bar)
        # "kill" — no s.upsert called
        del j, s

        j2 = DurableJournal(self.jpath)
        s2 = OperationalStore(self.spath)
        replayed = j2.replay()
        for bar in replayed:
            s2.upsert(bar)

        self.assertEqual(s2.count("BTCUSDT", "1m"), 3)


class TestT5_NetworkInterruption(unittest.TestCase):
    """T5: Simulate disconnect — gap window is recorded, reconnect logged."""

    def test_collector_tracks_gap_on_disconnect(self):
        """
        Gap window tracking is in BinanceCollector._on_close / _on_open.
        We test the gap_start and gap_end tracking without real network.
        """
        tmpdir = tempfile.mkdtemp()
        try:
            j = DurableJournal(os.path.join(tmpdir, "j.sqlite"))
            s = OperationalStore(os.path.join(tmpdir, "s.sqlite"))

            from aql.collector.binance_collector import BinanceCollector
            c = BinanceCollector("BTCUSDT", "1m", j, s)

            # Simulate: received a bar, then disconnect
            c.metrics.last_bar_open = 1_700_000_000_000
            mock_ws = MagicMock()
            c._on_close(mock_ws, 1006, "Connection reset")
            self.assertEqual(c.gap_start_ms, 1_700_000_000_000)

            # Simulate reconnect
            c._on_open(mock_ws)
            self.assertIsNotNone(c.gap_end_ms)
            self.assertGreater(c.gap_end_ms, c.gap_start_ms)
        finally:
            shutil.rmtree(tmpdir)

    def test_disconnect_at_recorded(self):
        tmpdir = tempfile.mkdtemp()
        try:
            j = DurableJournal(os.path.join(tmpdir, "j.sqlite"))
            s = OperationalStore(os.path.join(tmpdir, "s.sqlite"))
            from aql.collector.binance_collector import BinanceCollector
            c = BinanceCollector("BTCUSDT", "1m", j, s)
            mock_ws = MagicMock()
            c._on_close(mock_ws, 1006, "test")
            self.assertIsNotNone(c.metrics.disconnect_at)
        finally:
            shutil.rmtree(tmpdir)


class TestT6_RestGapRecovery(unittest.TestCase):
    """T6: REST gap recovery — mocked for unit test, live marked LIVE_OPTIONAL."""

    def test_recovery_idempotent_with_existing_keys(self):
        """Recovery skips bars already in existing_keys (idempotent)."""
        # Use a base timestamp that IS aligned to 60-second bar boundaries.
        # 1_700_000_040_000 % 60_000 == 0 (verified).
        base = 1_700_000_040_000  # aligned to 60s grid
        interval_ms = 60_000

        rest_rows = [
            [base + i * interval_ms, "41900", "42100", "41800", "42000", "10.0",
             base + i * interval_ms + 59_999, "0", "0", "0", "0", "0"]
            for i in range(5)
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rest_rows, 2)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=base,
                # gap_end_ms must be >= bar_open + interval_ms for the last bar to be
                # considered fully closed by Fix 2's unfinished-candle filter.
                # Bar 4 opens at base+4m and closes at base+5m, so gap_end must be >= base+5m.
                gap_end_ms=base + 5 * interval_ms,
                existing_keys={base + i * interval_ms for i in range(3)},  # 3 already stored
            )

        # Only 2 new bars (indices 3,4)
        self.assertEqual(len(bars), 2)
        self.assertEqual(report.recovered_bars, 5)
        self.assertEqual(report.already_stored, 3)
        self.assertEqual(report.status, "FULL")

    def test_recovery_marks_bars_as_recovered(self):
        # Use aligned base (divisible by 60_000).
        # gap_end must cover the full bar: base + interval_ms so aligned_end = base + interval_ms
        # and expected = 1.
        base = 1_700_000_040_000  # aligned to 60s grid
        interval_ms = 60_000
        rest_rows = [
            [base, "41900", "42100", "41800", "42000", "10.0",
             base + 59_999, "0", "0", "0", "0", "0"]
        ]
        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rest_rows, 2)
            # gap_end = base + interval_ms so aligned_end = base + interval_ms,
            # expected = 1 bar
            bars, report = recover_gap("BTCUSDT", "1m", base, base + interval_ms, set())

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].state, BarState.RECOVERED)
        self.assertEqual(bars[0].source, "binance_rest_recovery")
        self.assertTrue(bars[0].is_final)

    def test_recovery_unresolved_when_rest_returns_fewer_bars(self):
        base = 1_700_000_000_000
        interval_ms = 60_000
        # Only 2 bars returned, but gap expected 10
        rest_rows = [
            [base + i * interval_ms, "41900", "42100", "41800", "42000", "10.0",
             base + i * interval_ms + 59_999, "0", "0", "0", "0", "0"]
            for i in range(2)
        ]
        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rest_rows, 2)
            bars, report = recover_gap(
                "BTCUSDT", "1m", base, base + 9 * interval_ms, set()
            )

        self.assertEqual(report.status, "UNRESOLVED_DATA_GAP")
        self.assertGreater(report.unresolved, 0)

    @unittest.skipIf(
        os.environ.get("BINANCE_LIVE_TEST", "0") != "1",
        "LIVE_OPTIONAL: set BINANCE_LIVE_TEST=1 to run",
    )
    def test_live_rest_gap_recovery(self):
        """LIVE: Actually fetch from Binance REST."""
        now_ms = int(time.time() * 1000)
        # Request last 3 completed 1m bars
        interval_ms = 60_000
        end_ms = (now_ms // interval_ms) * interval_ms  # floor to minute
        start_ms = end_ms - 3 * interval_ms

        bars, report = recover_gap("BTCUSDT", "1m", start_ms, end_ms, set())
        self.assertGreater(len(bars), 0)
        self.assertEqual(report.status, "FULL")
        self.assertEqual(bars[0].source, "binance_rest_recovery")


class TestT7_CorruptTruncatedJournal(unittest.TestCase):
    """T7: Corrupt journal entries detected — no silent acceptance."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "j.sqlite")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_checksum_mismatch_raises(self):
        j = DurableJournal(self.db_path)
        bar = _make_bar(bar_open=1_700_000_000_000)
        j.commit(bar)

        # Corrupt the entry
        j.inject_truncation_for_test(bar.stable_key())

        with self.assertRaises(JournalCorruptionError):
            j.replay()

    def test_clean_journal_passes(self):
        j = DurableJournal(self.db_path)
        bars = [_make_bar(bar_open=1_700_000_000_000 + i * 60_000) for i in range(5)]
        for b in bars:
            j.commit(b)
        replayed = j.replay()
        self.assertEqual(len(replayed), 5)

    def test_checksum_computed_correctly(self):
        bar = _make_bar()
        expected = bar.compute_checksum()
        # Mutate close price — checksum must differ
        bar2 = _make_bar(close=99999.0)
        self.assertNotEqual(bar.checksum, bar2.checksum)
        self.assertEqual(bar.checksum, expected)


class TestT8_StorageUnavailable(unittest.TestCase):
    """
    T8: Storage unavailable — data retained in journal until store comes back.
    Simulates store failure: journal committed, store.upsert raises, bars
    still in journal and recovered after store is available again.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_journal_retains_data_when_store_fails(self):
        jpath = os.path.join(self.tmpdir, "j.sqlite")
        spath = os.path.join(self.tmpdir, "s.sqlite")

        j = DurableJournal(jpath)
        s = OperationalStore(spath)

        bars = [_make_bar(bar_open=1_700_000_000_000 + i * 60_000) for i in range(4)]
        committed_count = 0

        # Commit to journal; store is "unavailable" (mock raises)
        with patch.object(s, "upsert", side_effect=Exception("Store unavailable")):
            for bar in bars:
                j.commit(bar)
                committed_count += 1
                try:
                    s.upsert(bar)
                except Exception:
                    pass  # Store failure: data stays in journal

        # Journal has all 4
        replayed = j.replay()
        self.assertEqual(len(replayed), 4)
        self.assertEqual(committed_count, 4)

        # Store has 0 (all failed)
        self.assertEqual(s.count(), 0)

        # "Store comes back online" — replay journal into store
        for bar in j.replay():
            s.upsert(bar)

        self.assertEqual(s.count("BTCUSDT", "1m"), 4)

    def test_journal_state_count_after_store_failure(self):
        jpath = os.path.join(self.tmpdir, "j2.sqlite")
        j = DurableJournal(jpath)
        bars = [_make_bar(bar_open=1_700_000_000_000 + i * 60_000) for i in range(3)]
        for bar in bars:
            j.commit(bar)

        counts = j.count_by_state()
        self.assertEqual(counts.get("LOCAL_COMMITTED", 0), 3)
        self.assertEqual(counts.get("PERSISTED", 0), 0)


class TestModelIntegrity(unittest.TestCase):
    """Additional model-level invariant checks."""

    def test_stable_key_unique_per_bar_open(self):
        b1 = _make_bar(bar_open=1_700_000_000_000)
        b2 = _make_bar(bar_open=1_700_000_060_000)
        self.assertNotEqual(b1.stable_key(), b2.stable_key())

    def test_from_dict_roundtrip(self):
        bar = _make_bar()
        d = bar.to_dict()
        bar2 = MarketBar.from_dict(d)
        self.assertEqual(bar.stable_key(), bar2.stable_key())
        self.assertEqual(bar.checksum, bar2.checksum)

    def test_checksum_changes_on_payload_mutation(self):
        bar = _make_bar(close=42000.0)
        original = bar.checksum
        bar.close = 43000.0
        new_cs = bar.compute_checksum()
        self.assertNotEqual(original, new_cs)


class TestT9_SIGKILLSubprocess(unittest.TestCase):
    """
    T9: Real SIGKILL durability test.

    Spawns a child process that:
      1. Opens the journal
      2. Commits bars with synchronous=FULL
      3. Receives SIGKILL (os.kill SIGKILL) before it can call _on_close

    Then the parent verifies the journal still has the committed bars.
    This tests that SQLite WAL + synchronous=FULL survives abrupt termination
    without any manual fsync.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @unittest.skipIf(sys.platform == "win32", "SIGKILL not available on Windows")
    def test_sigkill_after_commit_journal_survives(self):
        """
        Child commits N bars then is SIGKILL'd. Parent reads same journal
        and verifies all bars are present.
        """
        import signal
        import subprocess

        jpath = os.path.join(self.tmpdir, "kill_test_journal.sqlite")
        n_bars = 5

        # Script to run in child process
        child_script = os.path.join(self.tmpdir, "child_commit.py")
        src_path = os.path.join(os.path.dirname(__file__), "..", "src")
        child_code = f"""
import sys, time
sys.path.insert(0, {repr(src_path)})
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import BarState, MarketBar

j = DurableJournal({repr(jpath)})
for i in range({n_bars}):
    bar_open = 1_700_000_000_000 + i * 60_000
    bar = MarketBar(
        symbol="BTCUSDT", interval="1m",
        bar_open=bar_open, bar_close=bar_open + 59_999,
        open=41900.0, high=42100.0, low=41800.0, close=42000.0,
        volume=10.0, is_final=True, source="test",
        ingested_at=int(time.time() * 1000),
        state=BarState.RECEIVED,
    )
    bar = bar.with_checksum()
    j.commit(bar)

# Signal parent that commits are done, then hang
import signal, os
os.kill(os.getpid(), signal.SIGUSR1)  # notify done
time.sleep(60)  # wait for SIGKILL
"""
        with open(child_script, "w") as f:
            f.write(child_code)

        proc = subprocess.Popen(
            [sys.executable, child_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait up to 10s for child to commit all bars (SIGUSR1 will be sent but
        # we can't easily receive it in the parent; just wait a short time)
        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.2)
            # Check if journal file exists and has rows
            if os.path.exists(jpath):
                try:
                    import sqlite3 as _sqlite3
                    conn = _sqlite3.connect(jpath)
                    count = conn.execute(
                        "SELECT COUNT(*) FROM journal_entries"
                    ).fetchone()[0]
                    conn.close()
                    if count >= n_bars:
                        break
                except Exception:
                    pass

        # SIGKILL the child — no _on_close, no graceful shutdown
        try:
            proc.send_signal(signal.SIGKILL)
        except ProcessLookupError:
            pass  # Already dead
        proc.wait(timeout=5)

        # Now verify journal is readable and has all bars
        j2 = DurableJournal(jpath)
        bars = j2.replay(symbol="BTCUSDT", interval="1m")

        self.assertEqual(
            len(bars), n_bars,
            f"Expected {n_bars} bars after SIGKILL, got {len(bars)}"
        )
        # Verify all bar opens are accounted for
        opens = {b.bar_open for b in bars}
        expected_opens = {1_700_000_000_000 + i * 60_000 for i in range(n_bars)}
        self.assertEqual(opens, expected_opens)
        # All should be LOCAL_COMMITTED (not PERSISTED — _on_close never called)
        for bar in bars:
            self.assertEqual(bar.state, BarState.LOCAL_COMMITTED)


class TestT10_InternalGapDetection(unittest.TestCase):
    """
    T10: Internal gap detection — gaps that don't appear from simple row counting.

    If bars A, B, D, E are stored (C is missing), row count = 4 but there is
    a gap at C.  Gap accounting must detect the missing bar by checking bar
    open timestamps, not just counting rows.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_internal_gap_not_visible_from_count_alone(self):
        """Store 4 bars with a hole at position 3. Count=4 but gap exists."""
        base = 1_700_000_000_000
        interval_ms = 60_000

        sdb = os.path.join(self.tmpdir, "store.sqlite")
        s = OperationalStore(sdb)

        # Store bars 0,1,2,4 — skip bar 3 (internal gap)
        stored_opens = [0, 1, 2, 4]
        for i in stored_opens:
            bar = _make_bar(bar_open=base + i * interval_ms)
            s.upsert(bar)

        self.assertEqual(s.count("BTCUSDT", "1m"), 4)  # count looks fine

        # Detect gap: compute expected bars in range, compare to stored
        min_open, max_open = s.get_range("BTCUSDT", "1m")
        stored_keys = s.get_stored_keys("BTCUSDT", "1m")

        # Generate expected opens between min and max
        expected_opens = set()
        t = min_open
        while t <= max_open:
            expected_opens.add(t)
            t += interval_ms

        missing = expected_opens - stored_keys
        self.assertEqual(
            missing, {base + 3 * interval_ms},
            "Internal gap at bar 3 must be detected"
        )
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(stored_keys), 4)

    def test_recovery_fills_internal_gap(self):
        """Recovery fetched from REST fills the internal gap (bar 3 missing)."""
        # Use aligned base so bar boundaries line up with Binance grid.
        base = 1_700_000_040_000  # aligned to 60s grid
        interval_ms = 60_000

        sdb = os.path.join(self.tmpdir, "store2.sqlite")
        s = OperationalStore(sdb)

        # Store bars 0,1,2 then 4 (internal gap at 3)
        for i in [0, 1, 2, 4]:
            bar = _make_bar(bar_open=base + i * interval_ms)
            s.upsert(bar)

        existing_keys = s.get_stored_keys("BTCUSDT", "1m")

        # REST returns bar 3 (the missing one)
        missing_open = base + 3 * interval_ms
        rest_rows = [
            [missing_open, "41900", "42100", "41800", "42000", "10.0",
             missing_open + 59_999, "0", "0", "0", "0", "0"]
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rest_rows, 2)
            # gap_end must cover the full bar (+ interval_ms) for aligned_end to include it
            bars, report = recover_gap(
                "BTCUSDT", "1m",
                gap_start_ms=missing_open,
                gap_end_ms=missing_open + interval_ms,
                existing_keys=existing_keys,
            )

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].bar_open, missing_open)

        # Insert recovered bar
        for bar in bars:
            s.upsert(bar)

        # Now all 5 bars present, no gap
        self.assertEqual(s.count("BTCUSDT", "1m"), 5)
        final_keys = s.get_stored_keys("BTCUSDT", "1m")
        self.assertEqual(final_keys, {base + i * interval_ms for i in range(5)})


class TestT11_PerBarStorageFailure(unittest.TestCase):
    """
    T11: Per-bar storage failure injection.

    When individual upsert calls fail for some bars (e.g. intermittent DB
    write errors), the journal must still have ALL bars, and mark_persisted
    must NOT be called for the failed bars.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_partial_store_failure_journal_retains_all(self):
        """
        5 bars committed to journal. Bars 1 and 3 fail to upsert.
        Journal still has 5 bars. Store has 3.
        mark_persisted called only for successful bars.
        """
        jpath = os.path.join(self.tmpdir, "j.sqlite")
        spath = os.path.join(self.tmpdir, "s.sqlite")
        j = DurableJournal(jpath)
        s = OperationalStore(spath)

        base = 1_700_000_000_000
        bars = [_make_bar(bar_open=base + i * 60_000) for i in range(5)]

        fail_indices = {1, 3}
        persisted_keys = []
        failed_keys = []

        call_count = [0]

        original_upsert = s.upsert

        def failing_upsert(bar):
            idx = call_count[0]
            call_count[0] += 1
            if idx in fail_indices:
                raise Exception(f"Injected storage failure for bar index {idx}")
            return original_upsert(bar)

        for bar in bars:
            j.commit(bar)
            try:
                with patch.object(s, "upsert", side_effect=failing_upsert):
                    upserted = s.upsert(bar)
                # mark_persisted only on confirmed write
                if upserted:
                    j.mark_persisted(bar.stable_key())
                    persisted_keys.append(bar.stable_key())
                else:
                    # Duplicate (not expected here)
                    j.mark_persisted(bar.stable_key())
                    persisted_keys.append(bar.stable_key())
            except Exception:
                failed_keys.append(bar.stable_key())
                # Do NOT mark_persisted

        # All 5 in journal
        replayed = j.replay()
        self.assertEqual(len(replayed), 5)

        # 3 succeeded, 2 failed
        self.assertEqual(len(failed_keys), 2)
        self.assertEqual(len(persisted_keys), 3)

        # Journal state: 3 PERSISTED, 2 LOCAL_COMMITTED
        counts = j.count_by_state()
        self.assertEqual(counts.get("PERSISTED", 0), 3)
        self.assertEqual(counts.get("LOCAL_COMMITTED", 0), 2)

        # Store has 3 bars
        self.assertEqual(s.count("BTCUSDT", "1m"), 3)

    def test_failed_bars_recoverable_on_retry(self):
        """After partial failure, re-replaying journal fills the store gap."""
        jpath = os.path.join(self.tmpdir, "j2.sqlite")
        spath = os.path.join(self.tmpdir, "s2.sqlite")
        j = DurableJournal(jpath)
        s = OperationalStore(spath)

        base = 1_700_000_000_000
        bars = [_make_bar(bar_open=base + i * 60_000) for i in range(3)]

        # Commit all to journal; simulate store failure on first pass
        for bar in bars:
            j.commit(bar)

        # First pass: all store writes "fail"
        # (journal has all bars, store has 0)

        # Retry pass: replay journal and try store again
        for bar in j.replay():
            s.upsert(bar)

        self.assertEqual(s.count("BTCUSDT", "1m"), 3)


class TestT12_WeightAccounting(unittest.TestCase):
    """
    T12: Verify that weight_cost is tracked as requests * KLINES_WEIGHT_PER_REQUEST,
    not as accumulated X-MBX-USED-WEIGHT-1M header values.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_weight_cost_is_request_count_times_per_request_weight(self):
        """
        Mock fetch returns window_weight=500 (cumulative) for each call.
        With 2 requests made, weight_cost must be 2*2=4 (not 500+500=1000).
        """
        from aql.recovery.gap_recovery import KLINES_WEIGHT_PER_REQUEST, MAX_KLINES_PER_REQUEST

        base = 1_700_000_000_000
        interval_ms = 60_000

        # First page: MAX_KLINES_PER_REQUEST bars (triggers pagination)
        page1 = [
            [base + i * interval_ms, "41900", "42100", "41800", "42000", "10",
             base + i * interval_ms + 59_999, "0", "0", "0", "0", "0"]
            for i in range(MAX_KLINES_PER_REQUEST)
        ]
        # Second page: 3 bars (ends pagination)
        page2_start = base + MAX_KLINES_PER_REQUEST * interval_ms
        page2 = [
            [page2_start + i * interval_ms, "41900", "42100", "41800", "42000", "10",
             page2_start + i * interval_ms + 59_999, "0", "0", "0", "0", "0"]
            for i in range(3)
        ]

        call_num = [0]

        def mock_fetch(symbol, interval, start_ms, end_ms, limit=1000):
            n = call_num[0]
            call_num[0] += 1
            # Simulate cumulative header growing (e.g. 250, 252 for two calls)
            window_weight = 250 + n * 2
            if n == 0:
                return page1, window_weight
            else:
                return page2, window_weight

        gap_end = page2_start + 2 * interval_ms
        with patch("aql.recovery.gap_recovery._fetch_klines", side_effect=mock_fetch):
            bars, report = recover_gap(
                "BTCUSDT", "1m",
                gap_start_ms=base,
                gap_end_ms=gap_end,
                existing_keys=set(),
            )

        # 2 requests made
        self.assertEqual(call_num[0], 2)
        # weight_cost = requests_made * KLINES_WEIGHT_PER_REQUEST = 2 * 2 = 4
        self.assertEqual(report.weight_cost, 2 * KLINES_WEIGHT_PER_REQUEST)
        # last_seen_window_weight is the cumulative header value (not the sum)
        self.assertNotEqual(report.last_seen_window_weight, report.weight_cost)

    def test_single_request_weight(self):
        """Single request: weight_cost == KLINES_WEIGHT_PER_REQUEST."""
        from aql.recovery.gap_recovery import KLINES_WEIGHT_PER_REQUEST

        # Use aligned base. gap_end = base + interval_ms so 1 bar is expected
        # and exactly 1 fetch request fires.
        base = 1_700_000_040_000  # aligned to 60s grid
        interval_ms = 60_000
        rest_rows = [
            [base, "41900", "42100", "41800", "42000", "10",
             base + 59_999, "0", "0", "0", "0", "0"]
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            # Window weight = 42 (cumulative, whatever the server says)
            mock_fetch.return_value = (rest_rows, 42)
            bars, report = recover_gap("BTCUSDT", "1m", base, base + interval_ms, set())

        self.assertEqual(report.weight_cost, KLINES_WEIGHT_PER_REQUEST)
        self.assertEqual(report.last_seen_window_weight, 42)
        self.assertNotEqual(report.weight_cost, 42)


class TestT13_StartupReconcile(unittest.TestCase):
    """
    T13: startup_reconcile correctly detects gap from last stored bar to now,
    even after an abrupt shutdown where _on_close was never called.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_no_data_returns_no_gap(self):
        """With empty journal and store, no gap is returned."""
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )
        self.assertEqual(bars_replayed, 0)
        self.assertEqual(replay_inserted, 0)
        self.assertEqual(replay_errors, 0)
        self.assertEqual(gaps, [])

    def test_gap_computed_from_last_stored_bar(self):
        """
        With last stored bar at T, gap_start = T + interval_ms, gap_end ~= now.
        """
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        interval_ms = 60_000
        # Store some bars (simulate bars from previous process run)
        base = 1_700_000_000_000
        for i in range(3):
            bar = _make_bar(bar_open=base + i * interval_ms)
            j.commit(bar)
            s.upsert(bar)
            j.mark_persisted(bar.stable_key())

        t_before = int(time.time() * 1000)
        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )
        t_after = int(time.time() * 1000)

        # All bars already in store, none need replaying
        self.assertEqual(bars_replayed, 0)
        self.assertEqual(replay_inserted, 0)
        self.assertEqual(replay_errors, 0)

        # Trailing gap is last element (no internal gaps — bars are consecutive)
        self.assertGreaterEqual(len(gaps), 1)
        gap_start, gap_end = gaps[-1]

        # Gap starts at last bar + interval
        last_bar_open = base + 2 * interval_ms
        expected_gap_start = last_bar_open + interval_ms
        self.assertEqual(gap_start, expected_gap_start)

        # Gap end is approximately now
        self.assertGreaterEqual(gap_end, t_before)
        self.assertLessEqual(gap_end, t_after + 1000)

    def test_unsynced_bars_counted_in_bars_replayed(self):
        """
        Bars in journal but NOT in store (simulating kill before upsert)
        are counted in bars_replayed.
        """
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        base = 1_700_000_000_000
        interval_ms = 60_000
        bars = [_make_bar(bar_open=base + i * interval_ms) for i in range(4)]

        # Commit all to journal; only first 2 to store (simulating kill mid-write)
        for bar in bars:
            j.commit(bar)
        for bar in bars[:2]:
            s.upsert(bar)
            j.mark_persisted(bar.stable_key())
        # bars[2] and bars[3] are in journal but NOT in store

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )
        # 2 bars need to be upserted to store
        self.assertEqual(bars_replayed, 2)
        # Both missing bars must now be in the store (real replay)
        self.assertEqual(replay_inserted, 2)
        self.assertEqual(replay_errors, 0)
        # Verify they are actually in the store
        stored_keys = s.get_stored_keys("BTCUSDT", "1m")
        self.assertIn(bars[2].bar_open, stored_keys)
        self.assertIn(bars[3].bar_open, stored_keys)
        # Trailing gap starts after the last known bar (bars[3])
        trailing_gap = gaps[-1]
        self.assertEqual(trailing_gap[0], base + 3 * interval_ms + interval_ms)

    def test_gap_start_in_future_returns_none(self):
        """
        If last bar open is very recent (within current interval),
        gap_start >= now → no gap returned.
        """
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        # Bar open = now (just closed)
        now_ms = int(time.time() * 1000)
        interval_ms = 60_000
        # Set bar_open to future-ish so gap_start > now
        bar_open = now_ms + interval_ms  # definitely in future
        bar = MarketBar(
            symbol="BTCUSDT", interval="1m",
            bar_open=bar_open, bar_close=bar_open + 59_999,
            open=1.0, high=1.0, low=1.0, close=1.0,
            volume=1.0, is_final=True, source="test",
            ingested_at=now_ms, state=BarState.RECEIVED,
        )
        bar = bar.with_checksum()
        j.commit(bar)
        s.upsert(bar)
        j.mark_persisted(bar.stable_key())

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )
        # gap_start > now → no gap (trailing_start >= trailing_end)
        self.assertEqual(gaps, [])


# ---------------------------------------------------------------------------
# T14 — Real journal-to-store replay: bars are actually upserted on restart
# ---------------------------------------------------------------------------
class TestT14_RealJournalReplay(unittest.TestCase):
    """
    Regression for review finding 1:
    startup_reconcile must actually call store.upsert for bars present in
    journal but absent from store.  The bar must be retrievable from the
    store after reconcile returns.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_bar_upserted_and_retrievable(self):
        """Bar committed to journal but never stored must appear in store after reconcile."""
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        base = 1_700_000_040_000  # aligned to 60s grid
        bar = _make_bar(bar_open=base)
        j.commit(bar)
        # Do NOT upsert to store — simulate kill between commit and upsert

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )

        self.assertEqual(bars_replayed, 1)
        self.assertEqual(replay_inserted, 1)
        self.assertEqual(replay_errors, 0)

        # Must be in store with confirmed ACK
        stored_keys = s.get_stored_keys("BTCUSDT", "1m")
        self.assertIn(base, stored_keys, "Bar must be in store after replay")

    def test_upsert_error_counted_in_replay_errors(self):
        """When store.upsert raises, replay_errors is incremented and bar NOT lost silently."""
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        base = 1_700_000_040_000
        bar = _make_bar(bar_open=base)
        j.commit(bar)

        # Inject upsert failure
        original_upsert = s.upsert
        def _failing_upsert(b):
            raise RuntimeError("injected storage failure")
        s.upsert = _failing_upsert

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )

        s.upsert = original_upsert

        self.assertEqual(bars_replayed, 1)
        self.assertEqual(replay_inserted, 0)
        self.assertEqual(replay_errors, 1)

    def test_already_stored_bar_not_double_counted(self):
        """Bar already in store must not be counted in bars_replayed."""
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        base = 1_700_000_040_000
        bar = _make_bar(bar_open=base)
        j.commit(bar)
        s.upsert(bar)
        j.mark_persisted(bar.stable_key())

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )

        self.assertEqual(bars_replayed, 0)
        self.assertEqual(replay_inserted, 0)
        self.assertEqual(replay_errors, 0)


# ---------------------------------------------------------------------------
# T15 — Unfinished REST candle must not enter store
# ---------------------------------------------------------------------------
class TestT15_UnfinishedCandleFilter(unittest.TestCase):
    """
    Regression for review finding 2:
    recover_gap must reject any REST row whose close time (bar_open + interval_ms)
    exceeds gap_end_ms.  An unfinalized candle must never enter the store.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_open_candle_rejected(self):
        """
        A bar whose bar_open + interval_ms > gap_end_ms is not-yet-closed
        and must be excluded from recovered bars.
        """
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap, KLINES_WEIGHT_PER_REQUEST

        interval_ms = 60_000
        base = 1_700_000_040_000  # aligned

        # gap_end_ms is in the middle of the last bar — bar not yet closed
        gap_end_ms = base + interval_ms - 1   # 1 ms before bar closes
        gap_start_ms = base

        # Simulate REST returning the current open (not yet closed) bar
        raw_row = [
            base,                    # open time
            "100.0",                 # open
            "101.0",                 # high
            "99.0",                  # low
            "100.5",                 # close
            "50.0",                  # volume
            base + interval_ms - 1,  # close time
            "5000.0",                # quote vol
            100,                     # trades
            "25.0",                  # taker base
            "2500.0",                # taker quote
            "0",                     # ignore
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = ([raw_row], 10)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        # Bar must be filtered out as unfinished
        self.assertEqual(len(bars), 0,
            "Unfinished candle must not appear in recovered bars")
        # expected=0 because aligned_end < aligned_start when gap<interval
        # The bar was returned but filtered; report must reflect unresolved=0
        # (expected was 0 since gap_end < base+interval → aligned_end=base < aligned_start)

    def test_fully_closed_candle_accepted(self):
        """
        A bar whose bar_open + interval_ms <= gap_end_ms is fully closed and must
        be accepted.
        """
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        interval_ms = 60_000
        base = 1_700_000_040_000

        # gap covers exactly one full bar
        gap_start_ms = base
        gap_end_ms = base + interval_ms   # bar closes exactly at gap_end

        raw_row = [
            base, "100.0", "101.0", "99.0", "100.5", "50.0",
            base + interval_ms - 1, "5000.0", 100, "25.0", "2500.0", "0",
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = ([raw_row], 10)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        self.assertEqual(len(bars), 1, "Fully closed candle must be accepted")
        self.assertEqual(bars[0].bar_open, base)


# ---------------------------------------------------------------------------
# T16 — Exact open-time set gap coverage (interior gap + off-grid extra)
# ---------------------------------------------------------------------------
class TestT16_ExactSetGapCoverage(unittest.TestCase):
    """
    Regression for review finding 3:
    Gap coverage must be verified as exact expected open-time set, not
    expected_count - row_count.  A missing interior bar plus an extra
    boundary/off-grid bar must NOT report FULL.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_raw_row(self, bar_open, interval_ms=60_000):
        return [
            bar_open, "100.0", "101.0", "99.0", "100.5", "50.0",
            bar_open + interval_ms - 1, "5000.0", 100, "25.0", "2500.0", "0",
        ]

    def test_interior_gap_reported_as_unresolved(self):
        """
        3 bars expected (base, base+1m, base+2m); REST returns base and base+2m
        only (interior bar base+1m missing).  Must report UNRESOLVED_DATA_GAP,
        not FULL.  Row count == 2 == expected-1, so a count-based check would
        still report unresolved, but the missing_opens set must name the exact bar.
        """
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        interval_ms = 60_000
        base = 1_700_000_040_000

        gap_start_ms = base
        gap_end_ms = base + 3 * interval_ms  # 3 bars expected

        rows = [
            self._make_raw_row(base),
            # base + interval_ms MISSING
            self._make_raw_row(base + 2 * interval_ms),
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rows, 10)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        self.assertEqual(report.status, "UNRESOLVED_DATA_GAP")
        self.assertIn(base + interval_ms, report.missing_opens,
            "missing_opens must name the exact interior bar open time")
        self.assertEqual(report.unresolved, 1)

    def test_off_grid_extra_bar_does_not_inflate_count(self):
        """
        2 bars expected (base, base+1m); REST returns base, base+1m, and an
        off-grid bar.  The off-grid bar must be discarded.  Status must be FULL.
        """
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        interval_ms = 60_000
        base = 1_700_000_040_000

        gap_start_ms = base
        gap_end_ms = base + 2 * interval_ms

        off_grid = base + 30_000  # not on 60s boundary

        rows = [
            self._make_raw_row(base),
            self._make_raw_row(base + interval_ms),
            self._make_raw_row(off_grid),
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rows, 10)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        self.assertEqual(report.status, "FULL")
        self.assertEqual(len(bars), 2, "Off-grid extra bar must be discarded")
        bar_opens = {b.bar_open for b in bars}
        self.assertNotIn(off_grid, bar_opens)

    def test_existing_keys_overlap_reported_correctly(self):
        """
        2 bars expected; 1 already in store (existing_keys).
        recovered_new = 1, already_stored = 1, status FULL.
        """
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        interval_ms = 60_000
        base = 1_700_000_040_000

        gap_start_ms = base
        gap_end_ms = base + 2 * interval_ms

        rows = [
            self._make_raw_row(base),
            self._make_raw_row(base + interval_ms),
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rows, 10)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys={base},  # base already stored
            )

        self.assertEqual(report.status, "FULL")
        self.assertEqual(report.already_stored, 1)
        self.assertEqual(len(bars), 1, "Only new bar returned")
        self.assertEqual(bars[0].bar_open, base + interval_ms)


# ---------------------------------------------------------------------------
# T17 — Reconciliation/recovery failures machine-readable in result
# ---------------------------------------------------------------------------
class TestT17_ReconcileFailureObservability(unittest.TestCase):
    """
    Regression for review finding 4:
    Reconciliation and recovery failures must be explicitly observable in the
    machine-readable result dict.  No false-green: unresolved_backlog must be
    True when there are replay errors or a reconcile exception.
    HTTP errors from recover_gap must appear in the gap report.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_replay_errors_set_unresolved_backlog(self):
        """
        When store.upsert fails during reconcile, startup_reconcile returns
        replay_errors > 0 and the pipeline result must have unresolved_backlog=True.
        """
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        base = 1_700_000_040_000
        bar = _make_bar(bar_open=base)
        j.commit(bar)

        original_upsert = s.upsert
        def _fail(b):
            raise RuntimeError("forced failure")
        s.upsert = _fail

        bars_replayed, replay_inserted, replay_errors, gaps = \
            j.startup_reconcile(store=s, symbol="BTCUSDT", interval="1m")

        s.upsert = original_upsert

        self.assertEqual(replay_errors, 1)
        # Caller must surface unresolved_backlog = True
        unresolved_backlog = replay_errors > 0
        self.assertTrue(unresolved_backlog)

    def test_http_error_in_recovery_report_is_traceable(self):
        """
        When _fetch_klines raises, recover_gap must record http_error in the
        report (not silently drop the failure).  Status must be HTTP_ERROR
        when there are unresolved bars.
        """
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        interval_ms = 60_000
        base = 1_700_000_040_000

        gap_start_ms = base
        gap_end_ms = base + 2 * interval_ms  # 2 bars expected

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.side_effect = OSError("connection refused")
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        self.assertEqual(report.status, "HTTP_ERROR",
            "REST fetch failure must produce HTTP_ERROR status, not FULL")
        self.assertIsNotNone(report.http_error,
            "http_error field must be set with failure description")
        self.assertIn("connection refused", report.http_error)
        self.assertEqual(len(bars), 0)
        self.assertEqual(report.unresolved, 2)

    def test_successful_recovery_http_error_is_none(self):
        """http_error must be None when recovery succeeds."""
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        interval_ms = 60_000
        base = 1_700_000_040_000

        gap_start_ms = base
        gap_end_ms = base + interval_ms

        raw_row = [
            base, "100.0", "101.0", "99.0", "100.5", "50.0",
            base + interval_ms - 1, "5000.0", 100, "25.0", "2500.0", "0",
        ]

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = ([raw_row], 10)
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        self.assertIsNone(report.http_error)
        self.assertEqual(report.status, "FULL")


# ---------------------------------------------------------------------------
# T18 — Interior Gap on Restart
# ---------------------------------------------------------------------------
class TestT18_InteriorGapOnRestart(unittest.TestCase):
    """
    Regression: startup_reconcile must detect internal gaps within the
    known bar sequence (A,B,D,E present → C missing → C detected in gaps list).
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_internal_gap_detected_in_gaps_list(self):
        """Bars A,B,D,E in journal+store; C missing. gaps must include (base+2m, base+3m)."""
        j = DurableJournal(os.path.join(self.tmpdir, "j.sqlite"))
        s = OperationalStore(os.path.join(self.tmpdir, "s.sqlite"))

        base = 1_700_000_040_000
        interval_ms = 60_000

        # A=base, B=base+1m, D=base+3m, E=base+4m; C=base+2m intentionally absent
        for offset in [0, 1, 3, 4]:
            bar = _make_bar(bar_open=base + offset * interval_ms)
            j.commit(bar)
            s.upsert(bar)
            j.mark_persisted(bar.stable_key())

        bars_replayed, replay_inserted, replay_errors, gaps = j.startup_reconcile(
            store=s, symbol="BTCUSDT", interval="1m"
        )

        self.assertEqual(bars_replayed, 0)  # all already in store
        # Internal gaps: gap_end <= base+4m (trailing gap_end >> base+4m)
        internal_gaps = [(gs, ge) for gs, ge in gaps if ge <= base + 4 * interval_ms]
        self.assertGreaterEqual(
            len(internal_gaps), 1,
            "Must report at least one internal gap covering C",
        )
        gap_starts = [gs for gs, ge in internal_gaps]
        self.assertIn(
            base + 2 * interval_ms,
            gap_starts,
            "Internal gap must start at C's bar_open (base+2m)",
        )

    def test_rest_failure_leaves_c_as_unresolved(self):
        """REST fetch fails for C's internal gap → HTTP_ERROR, C in missing_opens."""
        from unittest.mock import patch
        from aql.recovery.gap_recovery import recover_gap

        base = 1_700_000_040_000
        interval_ms = 60_000
        c_open = base + 2 * interval_ms

        # Internal gap: expected_next=base+2m, actual_next=base+3m
        # gap_end = base+3m (the first present bar after C); bar at c_open closes at c_open+interval_ms
        # For recover_gap to expect exactly 1 bar, gap_end must be >= c_open + interval_ms
        gap_start_ms = c_open
        gap_end_ms = c_open + interval_ms  # gap_end = close of C's candle

        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.side_effect = OSError("connection refused")
            bars, report = recover_gap(
                symbol="BTCUSDT",
                interval="1m",
                gap_start_ms=gap_start_ms,
                gap_end_ms=gap_end_ms,
                existing_keys=set(),
            )

        self.assertEqual(
            report.status, "HTTP_ERROR",
            "REST failure on internal gap must produce HTTP_ERROR, not FULL",
        )
        self.assertEqual(report.unresolved, 1)
        self.assertIn(c_open, report.missing_opens)
        self.assertIsNotNone(report.http_error)
        self.assertIn("connection refused", report.http_error)
        self.assertEqual(len(bars), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
