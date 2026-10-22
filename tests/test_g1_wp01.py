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

    def test_committed_at_set_after_fsync(self):
        bar = _make_bar()
        j = DurableJournal(self.db_path)
        j.commit(bar)
        bars = j.replay()
        self.assertIsNotNone(bars[0].committed_at)
        self.assertGreater(bars[0].committed_at, bars[0].ingested_at - 1000)


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
        # 5 bars at 1m spacing
        base = 1_700_000_000_000
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
                gap_end_ms=base + 4 * interval_ms,
                existing_keys={base + i * interval_ms for i in range(3)},  # 3 already stored
            )

        # Only 2 new bars (indices 3,4)
        self.assertEqual(len(bars), 2)
        self.assertEqual(report.recovered_bars, 5)
        self.assertEqual(report.already_stored, 3)
        self.assertEqual(report.status, "FULL")

    def test_recovery_marks_bars_as_recovered(self):
        base = 1_700_000_000_000
        rest_rows = [
            [base, "41900", "42100", "41800", "42000", "10.0",
             base + 59_999, "0", "0", "0", "0", "0"]
        ]
        with patch("aql.recovery.gap_recovery._fetch_klines") as mock_fetch:
            mock_fetch.return_value = (rest_rows, 2)
            bars, report = recover_gap("BTCUSDT", "1m", base, base + 59_999, set())

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
