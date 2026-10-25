"""Focused offline worker contract: no network, trading, or live scheduler."""
from pathlib import Path
import tempfile
import time
import unittest

from aql.observation.position_journal import DurablePositionJournal, JournalIntegrityError
from aql.observation.positions import PositionEvent
from aql.observation.worker import ObservationWorker


class TestObservationWorker(unittest.TestCase):
    def test_async_append_restart_explicit_close(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "positions.jsonl"
            worker = ObservationWorker(path, capacity=4)
            opened = PositionEvent("p", "open", "opened", 0, 0, "offline")
            self.assertTrue(worker.submit(opened))
            report = worker.finish(timeout=5)
            self.assertEqual(report["committed_or_duplicate"], 1)
            self.assertEqual(report["accepted_but_unconfirmed"], 0)
            self.assertFalse(report["healthy"])  # stopped is not healthy
            self.assertEqual(DurablePositionJournal(path).ledger.status("p", 366 * 86400000), "open")
            next_worker = ObservationWorker(path)
            closed = PositionEvent("p", "close", "closed", 367 * 86400000,
                                   367 * 86400000, "offline", reason="explicit")
            self.assertTrue(next_worker.submit(closed))
            self.assertEqual(next_worker.finish(timeout=5)["committed_or_duplicate"], 1)
            self.assertEqual(DurablePositionJournal(path).ledger.status("p", 368 * 86400000), "closed")

    def test_corrupt_journal_refuses_start(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "positions.jsonl"
            path.write_bytes(b'{"torn":true}')
            with self.assertRaises(JournalIntegrityError):
                ObservationWorker(path)

    def test_rejected_after_stop_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            worker = ObservationWorker(Path(d) / "positions.jsonl")
            worker.finish()
            event = PositionEvent("p", "open", "opened", 0, 0, "offline")
            self.assertFalse(worker.submit(event))
            self.assertEqual(worker.snapshot()["rejected"], 1)
            self.assertTrue(worker.snapshot()["uncommitted_inputs_are_volatile"])

    def test_unconfirmed_event_ids_are_visible_when_writer_is_blocked(self):
        from threading import Event
        with tempfile.TemporaryDirectory() as d:
            worker = ObservationWorker(Path(d) / "positions.jsonl", capacity=2)
            entered, release = Event(), Event()
            real_append = worker.journal.append

            def blocked_append(event):
                entered.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("synthetic blocked writer")
                return real_append(event)

            worker.journal.append = blocked_append
            first = PositionEvent("p", "open", "opened", 0, 0, "offline")
            second = PositionEvent("p", "quote-1", "quote", 1, 1, "offline", price="1")
            try:
                self.assertTrue(worker.submit(first))
                self.assertTrue(entered.wait(timeout=3))
                self.assertTrue(worker.submit(second))
                status = worker.snapshot()
                self.assertEqual(status["accepted_but_unconfirmed"], 2)
                self.assertEqual(status["unconfirmed_event_ids"], ["open", "quote-1"])
            finally:
                release.set()
                worker.finish(timeout=5)

    def test_failed_g2_writer_fails_closed_without_blocking_g1_journal(self):
        from threading import Event
        from aql.journal.durable_journal import DurableJournal
        from aql.models.bar import MarketBar

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            core = DurableJournal(str(root / "core.sqlite"))
            worker = ObservationWorker(root / "positions.jsonl", capacity=2)
            entered, release = Event(), Event()

            def broken_append(event):
                entered.set()
                release.wait(timeout=5)
                raise OSError("synthetic G2 disk failure")

            worker.journal.append = broken_append
            self.assertTrue(worker.submit(PositionEvent(
                "p", "open", "opened", 0, 0, "offline")))
            self.assertTrue(entered.wait(timeout=3))
            self.assertTrue(worker.submit(PositionEvent(
                "p", "quote", "quote", 1, 1, "offline", price="1")))

            # G1 commit is independent of the blocked G2 writer.
            bar = MarketBar("BTCUSDT", "1m", 0, 59999, 100., 101., 99.,
                            100., 1., True, "synthetic-offline", 60000)
            self.assertTrue(core.commit(bar))
            self.assertEqual(len(core.replay()), 1)
            release.set()
            status = worker.finish(timeout=5)
            self.assertIn("OSError", status["errors"])
            self.assertEqual(status["committed_or_duplicate"], 0)
            self.assertEqual(status["accepted_but_unconfirmed"], 1)
            self.assertEqual(status["unconfirmed_event_ids"], ["quote"])
            self.assertFalse(worker.submit(PositionEvent(
                "p", "close", "closed", 2, 2, "offline", reason="explicit")))
            self.assertEqual(DurablePositionJournal(root / "positions.jsonl").ledger.status(
                "p", 100), "unknown")

    def test_durable_upstream_resubmission_after_restart_is_idempotent(self):
        """Only a retained upstream source can recover volatile admission loss."""
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "positions.jsonl"
            upstream = root / "upstream.jsonl"
            events = [
                PositionEvent("p", "open", "opened", 0, 0, "retained-source"),
                PositionEvent("p", "quote", "quote", 1, 1, "retained-source", price="1"),
            ]
            from dataclasses import asdict
            upstream.write_text("".join(json.dumps(asdict(e)) + "\n" for e in events))
            # Simulate the first process having committed only the opening event.
            first = ObservationWorker(path)
            self.assertTrue(first.submit(events[0]))
            self.assertEqual(first.finish(timeout=5)["committed_or_duplicate"], 1)

            # The retained upstream independently re-sends *all* source events.
            restarted = ObservationWorker(path)
            for line in upstream.read_text().splitlines():
                self.assertTrue(restarted.submit(PositionEvent(**json.loads(line))))
            status = restarted.finish(timeout=5)
            self.assertEqual(status["committed_or_duplicate"], 2)
            journal = DurablePositionJournal(path)
            self.assertEqual(len(journal.ledger.events), 2)
            self.assertEqual(journal.ledger.status("p", 10), "open")
            self.assertEqual(len(path.read_text().splitlines()), 2)
