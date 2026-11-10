import json
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from aql.collector.binance_collector import BinanceCollector
from aql.g1_integrity import ContentConflictError, propagate_conflict
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.observation.contracts import HORIZONS_MS
from aql.observation.prospective import ProspectiveObserver, STEP
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
from tools.atlas_april_archive import NAME, START, admit_partition, pressure, sha
from tools.atlas_prospective_observe import FIXTURE, read_only_g1


class ProspectiveResearchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.journal = DurableJournal(str(self.root / "journal.sqlite"))
        self.store = OperationalStore(str(self.root / "store.sqlite"))
        self.fixture = json.loads(FIXTURE.read_text())[0]
        self.observer = self.restart()

    def restart(self):
        return ProspectiveObserver(self.root / "g2.sqlite", self.journal, self.store,
                                   self.fixture, synthetic=True)

    def put(self, open_ms, *, delay=1, source="binance_ws", persist=True, price=101.0):
        close = open_ms + STEP - 1
        received = close + delay
        bar = MarketBar("BTCUSDT", "15m", open_ms, close, price, price + 1,
                        price - 1, price, 4., True, source, received).with_checksum()
        with patch("time.time", return_value=(received + 2) / 1000):
            self.journal.commit(bar)
            if persist:
                self.store.upsert(bar)
                self.journal.mark_persisted(bar.stable_key())
        return received + 3

    def tick(self, now):
        with patch("aql.observation.prospective.time_ns", return_value=now * 1_000_000):
            self.observer.tick()

    def test_real_scanner_receipts_and_all_horizons_after_restart(self):
        for i in range(4):
            now = self.put(START + i * STEP)
            self.tick(now)
        first = self.observer.verified_read(as_of_ms=now)
        self.assertEqual(len(first["rows"]), 4)
        self.assertEqual(first["rows"][-1]["decision"]["state"], "ENTRY_SIGNAL")
        self.assertEqual(first["rows"][0]["decision"]["state"], "UNKNOWN")
        self.assertIsNone(first["rows"][0]["decision"]["opportunity_id"])
        self.observer = self.restart()
        self.tick(now)
        self.assertEqual(self.observer.verified_read(as_of_ms=now), first)

        for h in HORIZONS_MS:
            due = now + h
            opening = due // STEP * STEP
            self.assertEqual(self.observer.verified_read(as_of_ms=due)["rows"][3]["horizons"][
                HORIZONS_MS.index(h)]["state"], "UNKNOWN")
            end = self.put(opening)
            self.tick(end)
            after = self.observer.verified_read(as_of_ms=end)
            self.assertEqual(after["rows"][3]["horizons"][HORIZONS_MS.index(h)]["state"], "mature")
        self.assertEqual(self.observer.verified_read(as_of_ms=now), first)
        result = read_prospective_research(self.observer, as_of_ms=end)
        self.assertEqual(result["trading_authority"], "NONE")
        self.assertFalse(result["secretary_enqueued"])
        self.assertEqual(result["evidence_mode"], "SYNTHETIC_TESTED")

        from aql.observation.forward_evidence import read_forward_evidence
        reader = ProspectiveObserver(self.root / "g2.sqlite", self.journal, self.store,
                                     self.fixture, synthetic=True, read_only=True)
        report = read_forward_evidence(reader, as_of_ms=end)
        self.assertEqual(report["g2_sha256"], result["g2_sha256"])
        self.assertEqual(report["factory_sha256"], result["sha256"])
        self.assertEqual(report["rows"][0]["regimes"]["ALT"]["label"], "UNKNOWN")
        self.assertEqual(report["rows"][0]["windows"][0]["state"], "missing")
        self.assertEqual(report, read_forward_evidence(reader, as_of_ms=end))
        self.assertEqual(reader.verified_read(as_of_ms=now), first)


    def test_full_forward_contract_replays_from_durable_historical_fixture(self):
        from aql.observation.forward_evidence import read_forward_evidence

        for i in range(4):
            origin = self.put(START + i * STEP)
            self.tick(origin)
        first = START + 4 * STEP
        for i in range(72 * 4):
            self.put(first + i * STEP, price=100.0 if i != 3 else 103.0)
        end = origin + HORIZONS_MS[-1]

        def read():
            reader = ProspectiveObserver(self.root / "g2.sqlite", self.journal, self.store,
                                         self.fixture, synthetic=True, read_only=True)
            return read_forward_evidence(reader, as_of_ms=end)

        report = read()
        self.assertEqual(report, read())
        self.assertEqual(report["historical_pit"], "NOT_ATTESTED")
        self.assertEqual(report["evidence_mode"], "SYNTHETIC_TESTED")
        self.assertEqual([w["state"] for w in report["rows"][0]["windows"]], ["mature"] * 3)
        self.assertEqual([w["expected_bars"] for w in report["rows"][0]["windows"]], [15, 95, 287])
        self.assertEqual(report["rows"][0]["windows"][-1]["extrema"]["high"]["value"], 104.0)
        self.assertEqual(len(report["source_receipts"]), 292)

    def test_missing_receipt_future_and_no_signal_do_not_create_opportunities(self):
        self.put(START, persist=False)
        now = self.put(START + STEP, source="binance_rest_recovery")
        self.put(START + 10 * STEP)
        self.tick(now)
        self.assertEqual(self.observer.verified_read(as_of_ms=now)["rows"], [])
        for i in range(4):
            now = self.put(START + (i + 2) * STEP, price=99.5)
            self.tick(now)
        rows = self.observer.verified_read(as_of_ms=now)["rows"]
        self.assertEqual(rows[-1]["decision"]["state"], "NO_SIGNAL")
        self.assertIsNone(rows[-1]["decision"]["opportunity_id"])

    def test_collector_rejects_clock_and_nonfinal_then_calls_real_observer(self):
        opening = START
        close = opening + STEP - 1
        now = close + 2
        collector = BinanceCollector("BTCUSDT", "15m", self.journal, self.store,
                                     on_persisted=lambda: self.tick(now + 2),
                                     public_market_only=True)
        kline = dict(s="BTCUSDT", i="15m", t=opening, T=close,
                     o="101", h="102", l="100", c="101", v="4", x=True)
        with patch("time.time", return_value=now / 1000):
            with self.assertLogs("aql.collector.binance_collector", level="ERROR"):
                collector._on_message(None, json.dumps({"E": now - 10_000, "k": kline}))
            collector._on_message(None, json.dumps({"E": close - 60_000, "k": {**kline, "x": False}}))
            self.assertEqual(collector.metrics.non_final_bar_count, 1)
            self.assertEqual(collector.metrics.error_count, 1)
            self.assertEqual(self.store.count(), 0)
            collector._on_message(None, json.dumps({"E": now, "k": kline}))
            collector._on_close(None, 1006, "fixture reconnect")
            collector._on_open(None)
            collector._on_message(None, json.dumps({"E": now, "k": kline}))
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(len(self.observer.verified_read(as_of_ms=now + 2)["rows"]), 1)

    def test_public_final_waits_for_local_close_and_preserves_arrival_skew(self):
        close = START + STEP - 1
        now = close - 14
        collector = BinanceCollector("BTCUSDT", "15m", self.journal, self.store,
                                     public_market_only=True)
        kline = dict(s="BTCUSDT", i="15m", t=START, T=close,
                     o="101", h="102", l="100", c="101", v="4", x=True)

        def advance(seconds):
            nonlocal now
            now += round(seconds * 1000)

        message = json.dumps({"E": close + 59, "k": kline})
        with patch("time.time", side_effect=lambda: now / 1000):
            with patch("time.sleep") as stalled:
                with self.assertLogs("aql.collector.binance_collector", level="ERROR"):
                    collector._on_message(None, message)
                stalled.assert_called_once()
                self.assertEqual(self.store.count(), 0)
            with patch("time.sleep", side_effect=advance) as wait:
                collector._on_message(None, message)
                wait.assert_called_once_with(0.016)
        self.assertEqual(collector.metrics.source_clock_skew_ms, 73)
        bar = self.journal.replay("BTCUSDT", "15m")[0]
        self.assertGreater(bar.ingested_at, close)
        self.assertEqual(self.journal.commit_receipt(bar.stable_key())["status"],
                         "SQLITE_COMMIT_RETURN_OBSERVED")

    def test_late_missing_and_revised_source_remain_explicit(self):
        for i in range(4):
            now = self.put(START + i * STEP)
            self.tick(now)
        due = now + HORIZONS_MS[0]
        late = self.put(due // STEP * STEP, delay=10_000)
        self.tick(late)
        read = self.observer.verified_read(as_of_ms=late)
        self.assertEqual(read["rows"][3]["horizons"][0]["state"], "late")
        due2 = now + HORIZONS_MS[1]
        absent = self.put(due2 // STEP * STEP + STEP)
        self.tick(absent)
        read = self.observer.verified_read(as_of_ms=absent)
        self.assertEqual(read["rows"][3]["horizons"][1]["state"], "missing")
        try:
            self.put(START + 3 * STEP, price=102)
        except ContentConflictError as exc:
            propagate_conflict(exc, self.journal, self.store)
        else:
            self.fail("Revised bar was not quarantined")
        updated = self.observer.verified_read(as_of_ms=absent)
        self.assertFalse(updated["rows"][3]["source_valid"])
        self.assertEqual(updated["rows"][3]["horizons"][0]["state"], "UNKNOWN")

    def test_interruption_between_store_and_observer_recovers_without_backdating(self):
        now = self.put(START)
        self.observer = self.restart()
        self.tick(now + 60_000)
        row = self.observer.verified_read(as_of_ms=now + 60_000)["rows"][0]["decision"]
        self.assertEqual(row["state"], "UNKNOWN")
        self.assertEqual(row["cutoff_ms"], now + 60_000)
        self.assertEqual(row["reason"], "STALE_OR_RESTARTED_BEFORE_DECISION")


    def test_process_interruption_after_g1_receipt_then_factory_read_only(self):
        script = """
import os, sys
from pathlib import Path
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from unittest.mock import patch
root, opened = Path(sys.argv[1]), int(sys.argv[2])
close = opened + 899999
bar = MarketBar('BTCUSDT', '15m', opened, close, 101., 102., 100., 101.,
                4., True, 'binance_ws', close + 1).with_checksum()
with patch('time.time', return_value=(close + 3) / 1000):
    assert DurableJournal(str(root / 'journal.sqlite')).commit(bar)
os._exit(17)
"""
        child = subprocess.run([sys.executable, "-B", "-c", script, str(self.root), str(START)],
                               capture_output=True, text=True, check=False)
        self.assertEqual(child.returncode, 17, child.stderr)
        self.assertEqual(self.store.count(), 0)
        self.journal.startup_reconcile(self.store, "BTCUSDT", "15m")
        self.observer = self.restart()
        as_of = START + STEP + 10_000
        self.tick(as_of)
        reader = ProspectiveObserver(
            self.root / "g2.sqlite",
            read_only_g1(DurableJournal, self.root / "journal.sqlite"),
            read_only_g1(OperationalStore, self.root / "store.sqlite"),
            self.fixture, synthetic=True, read_only=True,
        )
        report = read_prospective_research(reader, as_of_ms=as_of)
        self.assertEqual(report["decision_counts"], {"UNKNOWN": 1})
        self.assertFalse(report["orders_enabled"])
        with self.assertRaisesRegex(ValueError, "PROSPECTIVE_READ_ONLY"):
            reader.tick()


class ArchiveTests(unittest.TestCase):
    def test_immutable_dedup_bad_checksum_and_revision(self):
        end = START + 4 * STEP

        def capture(price):
            buffer = BytesIO()
            with ZipFile(buffer, "w") as z:
                rows = []
                for open_ms in range(START, end, STEP):
                    rows.append(f"{open_ms},{price},{price+1},{price-1},{price},5,{open_ms+STEP-1},500,5,2,200,0")
                z.writestr(NAME[:-4] + ".csv", "\n".join(rows) + "\n")
            raw = buffer.getvalue()
            return raw, f"{sha(raw)}  {NAME}\n".encode()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, check = capture(100)
            calls = 0

            def pause_after_checkpoint():
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise RuntimeError("P1_PAUSED_FOR_P0_OBSERVER")

            with self.assertRaisesRegex(RuntimeError, "P1_PAUSED"):
                admit_partition(root, raw, check, end=end, test_only=True,
                                check_progress=pause_after_checkpoint)
            first = admit_partition(root, raw, check, end=end, test_only=True)
            self.assertEqual(first, admit_partition(root, raw, check, end=end, test_only=True))
            self.assertNotEqual(first["core245_sha256"], first["core253_sha256"])
            self.assertEqual(first["bars"], 4)
            revised, revised_check = capture(101)
            with self.assertRaisesRegex(ValueError, "CHECKSUM_MISMATCH"):
                admit_partition(root, revised, check, end=end, test_only=True)
            next_version = admit_partition(root, revised, revised_check, end=end, test_only=True,
                                           version=2, parent_sha=first["source_sha256"])
            self.assertNotEqual(next_version["manifest_sha256"], first["manifest_sha256"])

    def test_priority_pauses_for_p0_lock(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = sqlite3.connect(root / "runner-lock.sqlite")
            try:
                lock.execute("BEGIN EXCLUSIVE")
                with self.assertRaisesRegex(RuntimeError, "P1_PAUSED"):
                    pressure(root)
                lock.rollback()
                pressure(root)
            finally:
                lock.close()


class ForwardEvidenceTests(unittest.TestCase):
    def test_full_historical_fixture_window_replay_and_temporal_boundaries(self):
        from types import SimpleNamespace
        from aql.observation.forward_evidence import _window

        # Frozen, generated fixture with simulated receipt times. Historical PIT
        # and actual market provenance are deliberately not asserted.
        origin = START + 7
        for horizon in HORIZONS_MS:
            bars = {}
            for i in range(1, horizon // STEP):
                opening = START + i * STEP
                close = opening + STEP - 1
                bars[opening] = (
                    SimpleNamespace(open=100, close=100, high=105 if i == 2 else 102,
                                    low=90 if i == 3 else 98),
                    dict(open_ms=opening, close_ms=close, commit_ms=close + 3,
                         g1_receipt_sha256=f"{i:064x}"),
                )
            due = origin + horizon
            self.assertEqual(_window(origin, horizon, due - 1, bars, True)["state"], "pending")
            report = _window(origin, horizon, due, bars, True)
            self.assertEqual(report, _window(origin, horizon, due, dict(reversed(list(bars.items()))), True))
            self.assertEqual(report["expected_bars"], horizon // STEP - 1)
            self.assertEqual(report["extrema"]["high"]["value"], 105)
            self.assertEqual(report["extrema"]["low"]["value"], 90)
            self.assertEqual(report["extrema"]["order"], "HIGH_BEFORE_LOW")
            self.assertEqual(report["extrema"]["high"]["relative_intervals_ms"][0][0], 2 * STEP - 7)
            removed = bars.pop(START + STEP)
            self.assertEqual(_window(origin, horizon, due, bars, True)["state"], "missing")
            bars[START + STEP] = removed
            removed[1]["commit_ms"] += 5001
            self.assertEqual(_window(origin, horizon, due, bars, True)["state"], "late")
            removed[1]["commit_ms"] -= 5001
            bars[START + 2 * STEP][0].low = 90
            self.assertEqual(_window(origin, horizon, due, bars, True)["extrema"]["order"], "AMBIGUOUS")
            self.assertEqual(_window(origin, horizon, due, bars, False)["state"], "UNKNOWN")

    def test_regime_receipt_available_at_cutoff_and_conflicts(self):
        from aql.observation.contracts import digest
        from aql.observation.forward_evidence import _regime

        sample = dict(market="BTC", label="UP", as_of_ms=10, available_ms=20,
                      valid_until_ms=30, source_sha256="a"*64)
        sealed = {**sample, "sha256": digest(sample)}
        self.assertEqual(_regime([sealed], "BTC", 19)["label"], "UNKNOWN")
        self.assertEqual(_regime([sealed], "BTC", 20)["label"], "UP")
        self.assertEqual(_regime([sealed], "BTC", 30)["label"], "UNKNOWN")
        self.assertEqual(_regime([sealed], "ALT", 20)["label"], "UNKNOWN")
        self.assertEqual(_regime([{**sealed, "label": "DOWN"}], "BTC", 20)["label"], "UNKNOWN")
        other = {**sample, "label": "DOWN"}
        self.assertEqual(_regime([sealed, {**other, "sha256": digest(other)}], "BTC", 20)["reason"],
                         "CONFLICT")


if __name__ == "__main__":
    unittest.main()
