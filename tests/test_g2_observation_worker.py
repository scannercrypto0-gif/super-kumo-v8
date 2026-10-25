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
