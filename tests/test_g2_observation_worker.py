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
                self.assertEqual(status["unconfirmed_event_ids"], [("p", "open"), ("p", "quote-1")])
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
            self.assertEqual(status["failed_event_ids"], [("p", "open")])
            self.assertEqual(status["committed_or_duplicate"], 0)
            self.assertEqual(status["accepted_but_unconfirmed"], 1)
            self.assertEqual(status["unconfirmed_event_ids"], [("p", "quote")])
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

    def test_shared_event_ids_are_disambiguated_by_position(self):
        from threading import Event
        with tempfile.TemporaryDirectory() as d:
            worker = ObservationWorker(Path(d) / "positions.jsonl", capacity=2)
            entered, release = Event(), Event()

            def fail_first(event):
                entered.set()
                release.wait(timeout=5)
                raise OSError("synthetic failure")

            worker.journal.append = fail_first
            try:
                self.assertTrue(worker.submit(PositionEvent(
                    "first", "open", "opened", 0, 0, "offline")))
                self.assertTrue(entered.wait(timeout=3))
                self.assertTrue(worker.submit(PositionEvent(
                    "second", "open", "opened", 0, 0, "offline")))
                report = worker.snapshot()
                self.assertEqual(report["unconfirmed_event_ids"],
                                 [("first", "open"), ("second", "open")])
                self.assertEqual(report["unattributed_unconfirmed_count"], 0)
            finally:
                release.set()
                final = worker.finish(timeout=5)
            self.assertEqual(final["failed_event_ids"], [("first", "open")])
            self.assertEqual(final["unconfirmed_event_ids"], [("second", "open")])

    def test_handoff_race_reports_unattributed_instead_of_missing_identity(self):
        from threading import Event
        with tempfile.TemporaryDirectory() as d:
            import queue
            from unittest.mock import patch
            entered, release = Event(), Event()
            real_get = queue.Queue.get

            def held_get(q, *args, **kwargs):
                event = real_get(q, *args, **kwargs)
                entered.set()
                release.wait(timeout=5)
                return event

            # Patch before the worker thread starts; the worker can then
            # be deterministically held between dequeue and inflight assignment.
            with patch.object(queue.Queue, "get", held_get):
                worker = ObservationWorker(Path(d) / "positions.jsonl")
                self.assertTrue(worker.submit(PositionEvent(
                    "p", "open", "opened", 0, 0, "offline")))
                try:
                    self.assertTrue(entered.wait(timeout=3))
                    report = worker.snapshot()
                    self.assertEqual(report["accepted_but_unconfirmed"], 1)
                    self.assertEqual(report["unconfirmed_event_ids"], [])
                    self.assertEqual(report["unattributed_unconfirmed_count"], 1)
                    self.assertFalse(report["identities_exhaustive"])
                finally:
                    release.set()
                    worker.finish(timeout=5)

    def test_concurrent_submit_and_snapshot_keep_bounded_identity_inventory(self):
        import threading
        import time
        events = [PositionEvent(str(i), "open", "opened", 0, 0, "offline")
                  for i in range(24)]
        expected = {(event.position_id, event.event_id) for event in events}
        failures = []
        with tempfile.TemporaryDirectory() as d:
            worker = ObservationWorker(Path(d) / "positions.jsonl", capacity=4)
            deadline = time.monotonic() + 10

            def produce():
                try:
                    for event in events:
                        while not worker.submit(event):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("test producer could not progress")
                            time.sleep(0.001)
                except Exception as error:
                    failures.append(error)

            producer = threading.Thread(target=produce)
            snapshots = 0
            producer.start()
            try:
                while True:
                    report = worker.snapshot()
                    snapshots += 1
                    identities = report["unconfirmed_event_ids"]
                    self.assertLessEqual(len(identities), 5)
                    self.assertEqual(len(identities), len(set(identities)))
                    self.assertTrue(set(identities) <= expected)
                    self.assertEqual(report["accepted_but_unconfirmed"],
                                     len(identities) + report["unattributed_unconfirmed_count"])
                    self.assertLessEqual(report["unattributed_unconfirmed_count"], 1)
                    self.assertFalse(report["errors"])
                    if not producer.is_alive() and not report["accepted_but_unconfirmed"]:
                        break
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.001)
            finally:
                producer.join(timeout=10)
                final = worker.finish(timeout=10)
            self.assertFalse(producer.is_alive())
            self.assertFalse(failures)
            self.assertGreater(snapshots, 0)
            self.assertEqual(final["committed_or_duplicate"], len(events))
            self.assertFalse(final["errors"])
            replayed = DurablePositionJournal(Path(d) / "positions.jsonl")
            self.assertEqual(len(replayed.ledger.events), len(events))

    def test_snapshot_cannot_mask_new_handoff_with_previous_inflight(self):
        """A's stale identity must never stand in for accepted, dequeued B."""
        import queue
        import threading
        from unittest.mock import patch
        first_entered, first_release = threading.Event(), threading.Event()
        captured, snapshot_release = threading.Event(), threading.Event()
        second_dequeued, second_release = threading.Event(), threading.Event()
        reports, errors = [], []
        real_get = queue.Queue.get
        def held_second(q, *args, **kwargs):
            event = real_get(q, *args, **kwargs)
            if event.position_id == "second":
                second_dequeued.set()
                if not second_release.wait(5): raise TimeoutError("test second handoff")
            return event
        class SnapshotGate:
            def __init__(self, lock): self.lock = lock
            def __enter__(self): self.lock.acquire(); return self
            def __exit__(self, *args):
                self.lock.release()
                if threading.current_thread().name == "G2-diagnostic-snapshot":
                    captured.set()
                    if not snapshot_release.wait(5): raise TimeoutError("test snapshot gate")
        with tempfile.TemporaryDirectory() as d, patch.object(queue.Queue, "get", held_second):
            worker = ObservationWorker(Path(d) / "positions.jsonl", capacity=2)
            original = worker.journal.append
            def held_first(event):
                if event.position_id == "first":
                    first_entered.set()
                    if not first_release.wait(5): raise TimeoutError("test first append")
                return original(event)
            worker.journal.append = held_first
            observer = None
            try:
                self.assertTrue(worker.submit(PositionEvent("first", "open", "opened", 0, 0, "offline")))
                self.assertTrue(first_entered.wait(3))
                self.assertTrue(worker.submit(PositionEvent("second", "open", "opened", 0, 0, "offline")))
                worker._lock = SnapshotGate(worker._lock)
                def observe():
                    try: reports.append(worker.snapshot())
                    except Exception as error: errors.append(error)
                observer = threading.Thread(target=observe, name="G2-diagnostic-snapshot")
                observer.start(); self.assertTrue(captured.wait(3))
                first_release.set(); self.assertTrue(second_dequeued.wait(3))
                snapshot_release.set(); observer.join(3)
                self.assertFalse(observer.is_alive()); self.assertFalse(errors)
                report = reports[0]
                # B was accepted before snapshot and stays uncommitted throughout.
                # A coherent earlier snapshot may show A+B; a later handoff may
                # report an attribution hole, but exhaustive A-only is impossible.
                self.assertTrue(("second", "open") in report["unconfirmed_event_ids"]
                                or not report["identities_exhaustive"], report)
            finally:
                first_release.set(); snapshot_release.set(); second_release.set()
                if observer is not None: observer.join(3)
                worker.finish(timeout=5)

