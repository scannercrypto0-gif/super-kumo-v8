"""Offline crash windows, verified receipts and bounded cooperative isolation."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aql.observation.retained_source import (
    RetainedObservationSource, SourceFullError, SourceIntegrityError, _digest)
from aql.observation.position_journal import DurablePositionJournal, JournalIntegrityError
from aql.observation.positions import PositionEvent
from aql.observation.worker import ObservationWorker
from aql.lanes import BackgroundLane

GENERATION = "5ead245e-78f1-4bd2-a960-6a73d824ec5f"


def event(position="p", price=None):
    return PositionEvent(position, "open", "opened", 0, 0, "offline", price=price)


def source(root, **kwargs):
    return RetainedObservationSource(root / "source.jsonl", root / "target.jsonl",
                                     GENERATION, **kwargs)


def drain(retained, worker):
    deadline = time.monotonic() + 5
    while retained.step(worker) != "drained":
        if time.monotonic() >= deadline:
            raise AssertionError("offline drain did not progress")
        time.sleep(0.001)


class TestRetainedSource(unittest.TestCase):
    def test_retain_is_synced_before_offer_and_sequence_is_stable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            with patch("aql.observation.retained_source.os.fsync", wraps=os.fsync) as sync:
                self.assertEqual(retained.retain(event()), 1)
                self.assertGreaterEqual(sync.call_count, 1)
            self.assertEqual(retained.retain(event("second")), 2)
            restarted = source(root)
            self.assertEqual(restarted.retain(event()), 1)
            self.assertEqual(restarted.status()["pending"], 2)
            worker = ObservationWorker(root / "target.jsonl")
            try:
                drain(restarted, worker)
                self.assertEqual(restarted.status()["acked"], 2)
            finally:
                worker.finish(5)
            self.assertEqual(len(DurablePositionJournal(root / "target.jsonl").ledger.events), 2)

    def test_conflicting_source_duplicate_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            retained = source(Path(d))
            retained.retain(event(price="1"))
            before = retained.path.read_bytes()
            with self.assertRaises(SourceIntegrityError):
                retained.retain(event(price="2"))
            self.assertEqual(retained.path.read_bytes(), before)

    def test_retention_cap_includes_acked_no_eviction(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root, max_events=1)
            retained.retain(event())
            worker = ObservationWorker(root / "target.jsonl")
            try:
                drain(retained, worker)
                before = retained.path.read_bytes()
                with self.assertRaises(SourceFullError):
                    retained.retain(event("second"))
                self.assertEqual(retained.path.read_bytes(), before)
            finally:
                worker.finish(5)

    def test_readable_but_unsynced_source_is_resynced_before_duplicate_success(self):
        with tempfile.TemporaryDirectory() as d:
            retained = source(Path(d))
            original_sync = os.fsync
            def fail_data_sync(fd):
                # Source lease uses its own fsync first; fail the data sync.
                if os.fstat(fd).st_size > 100:
                    raise OSError("synthetic source sync failure")
                original_sync(fd)
            with patch("aql.observation.retained_source.os.fsync", side_effect=fail_data_sync):
                with self.assertRaises(OSError):
                    retained.retain(event())
            with patch("aql.observation.retained_source.os.fsync", wraps=original_sync) as sync:
                self.assertEqual(retained.retain(event()), 1)
                self.assertGreaterEqual(sync.call_count, 2)

    def test_volatile_admission_is_not_ack_and_full_queue_retains_input(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root, max_events=4)
            retained.retain(event())
            worker = ObservationWorker(root / "target.jsonl", capacity=1)
            entered, release = threading.Event(), threading.Event()
            original = worker.journal.append
            def blocked(e):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test blocked append")
                return original(e)
            worker.journal.append = blocked
            try:
                self.assertTrue(worker.submit(event("other1")))
                self.assertTrue(entered.wait(3))
                self.assertTrue(worker.submit(event("other2")))
                self.assertEqual(retained.step(worker), "backpressure")
                self.assertEqual(retained.status()["acked"], 0)
                release.set()
                worker.finish(5)
                self.assertEqual(retained.status()["pending"], 1)
            finally:
                release.set()
                worker.finish(5)
            restarted = ObservationWorker(root / "target.jsonl")
            try:
                drain(retained, restarted)
                self.assertEqual(retained.status()["acked"], 1)
            finally:
                restarted.finish(5)

    def test_failed_worker_leaves_event_retained_and_unacked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            worker = ObservationWorker(root / "target.jsonl")
            worker.journal.append = lambda e: (_ for _ in ()).throw(OSError("disk failed"))
            try:
                self.assertEqual(retained.step(worker), "offered")
                worker.finish(5)
                self.assertEqual(retained.step(worker), "blocked")
                self.assertEqual(retained.status()["acked"], 0)
            finally:
                worker.finish(5)

    def test_accepted_volatile_event_and_aggregate_counter_cannot_ack(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            worker = ObservationWorker(root / "target.jsonl")
            entered, release = threading.Event(), threading.Event()
            original = worker.journal.append
            def blocked(e):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test blocked volatile event")
                return original(e)
            worker.journal.append = blocked
            try:
                self.assertEqual(retained.step(worker), "offered")
                self.assertTrue(entered.wait(3))
                worker.committed = 999  # Not a per-event receipt.
                self.assertEqual(retained.step(worker), "pending")
                self.assertEqual(retained.status()["acked"], 0)
                release.set()
                drain(retained, worker)
                self.assertEqual(retained.status()["acked"], 1)
            finally:
                release.set()
                worker.finish(5)

    def test_target_conflict_is_not_ack(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event(price="1"))
            worker = ObservationWorker(root / "target.jsonl")
            DurablePositionJournal(root / "target.jsonl").append(event(price="2"))
            try:
                with self.assertRaises(SourceIntegrityError):
                    retained.step(worker)
                self.assertEqual(retained.status()["acked"], 0)
            finally:
                worker.finish(5)

    def test_sync_failure_cannot_append_ack(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            worker = ObservationWorker(root / "target.jsonl")
            worker.journal.append(event())
            before = retained.path.read_bytes()
            target_stat = retained.journal_path.stat()
            original_sync = os.fsync
            def fail_target_sync(fd):
                observed = os.fstat(fd)
                if (observed.st_dev, observed.st_ino) == (target_stat.st_dev, target_stat.st_ino):
                    raise OSError("target receipt sync failed")
                original_sync(fd)
            with patch("aql.observation.retained_source.os.fsync", side_effect=fail_target_sync):
                with self.assertRaises(OSError):
                    retained.step(worker)
            self.assertEqual(retained.path.read_bytes(), before)
            try:
                self.assertEqual(retained.step(worker), "acked")
            finally:
                worker.finish(5)

    def test_corrupt_or_truncated_source_is_never_repaired(self):
        for suffix in (b'{"torn":', b'not json\n'):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                retained = source(root)
                retained.retain(event())
                with retained.path.open("ab") as f:
                    f.write(suffix)
                before = retained.path.read_bytes()
                with self.assertRaises(SourceIntegrityError):
                    source(root)
                self.assertEqual(retained.path.read_bytes(), before)

    def test_changed_generation_and_corrupt_target_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            with self.assertRaises(SourceIntegrityError):
                RetainedObservationSource(retained.path, retained.journal_path,
                                          "7ead245e-78f1-4bd2-a960-6a73d824ec5f")
            retained.journal_path.write_bytes(b'bad journal\n')
            with self.assertRaises(JournalIntegrityError):
                retained.status()

    def test_changed_payload_and_truncated_target_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event(price="1"))
            data = retained.path.read_bytes().replace(b'"price":"1"', b'"price":"2"')
            retained.path.write_bytes(data)
            with self.assertRaises(SourceIntegrityError):
                source(root)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            DurablePositionJournal(root / "target.jsonl").append(event())
            raw = retained.journal_path.read_bytes()
            retained.journal_path.write_bytes(raw[:-1])
            with self.assertRaises(JournalIntegrityError):
                retained.status()

    def test_forged_ack_and_missing_source_with_populated_target_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            last = json.loads(retained.path.read_bytes().splitlines()[-1])
            retained._write(dict(kind="ack", seq=1, payload_hash=_digest(asdict(event()))), last["digest"])
            with self.assertRaises(SourceIntegrityError):
                source(root)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            DurablePositionJournal(root / "target.jsonl").append(event())
            with self.assertRaises(SourceIntegrityError):
                source(root)

    def test_dedicated_target_and_source_byte_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root, max_events=1)
            retained.retain(event())
            worker = ObservationWorker(root / "different.jsonl")
            try:
                with self.assertRaises(SourceIntegrityError):
                    retained.step(worker)
            finally:
                worker.finish(5)
            retained.journal_path.write_bytes(b"x" * 8193)
            with self.assertRaises(SourceIntegrityError):
                retained.status()

    def test_g1_commit_continues_while_adapter_lane_is_blocked(self):
        from aql.journal.durable_journal import DurableJournal
        from aql.models.bar import MarketBar
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            retained = source(root)
            retained.retain(event())
            worker = ObservationWorker(root / "target.jsonl")
            lane = BackgroundLane(capacity=1)
            entered, release, committed = threading.Event(), threading.Event(), threading.Event()
            errors = []
            journal = retained._journal
            def blocked():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test blocked adapter IO")
                return journal()
            retained._journal = blocked
            core = DurableJournal(str(root / "core.sqlite"))
            def ingest():
                try:
                    bar = MarketBar("BTCUSDT", "1m", 0, 59999, 100., 101., 99.,
                                    100., 1., True, "offline", 60000)
                    if core.commit(bar):
                        committed.set()
                except Exception as error:
                    errors.append(error)
            foreground = threading.Thread(target=ingest)
            try:
                self.assertTrue(retained.schedule(lane, worker))
                self.assertTrue(entered.wait(3))
                self.assertTrue(retained.schedule(lane, worker))
                self.assertFalse(retained.schedule(lane, worker))
                foreground.start()
                self.assertTrue(committed.wait(3))
                self.assertFalse(release.is_set())
                self.assertFalse(errors)
                self.assertEqual(len(core.replay()), 1)
            finally:
                release.set()
                if foreground.ident is not None:
                    foreground.join(5)
                lane.finish(5)
                worker.finish(5)

    def test_real_process_crash_windows_replay_without_false_ack(self):
        script = '''
import os, sys, time
from pathlib import Path
from aql.observation.retained_source import RetainedObservationSource
from aql.observation.positions import PositionEvent
from aql.observation.worker import ObservationWorker
root, window = Path(sys.argv[1]), sys.argv[2]
source = RetainedObservationSource(root/'source.jsonl', root/'target.jsonl', sys.argv[3])
source.retain(PositionEvent('p','open','opened',0,0,'offline'))
if window == 'before_enqueue': os._exit(73)
worker = ObservationWorker(root/'target.jsonl')
original = worker.journal.append
def crash(event):
    if window == 'after_fsync': original(event)
    os._exit(73)
worker.journal.append = crash
source.step(worker)
time.sleep(5)
os._exit(99)
'''
        for window in ("before_enqueue", "after_dequeue", "after_fsync"):
            with self.subTest(window=window), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                child = subprocess.run([sys.executable, "-B", "-c", script, d, window, GENERATION],
                                       capture_output=True, text=True, timeout=15)
                self.assertEqual(child.returncode, 73, child.stdout + child.stderr)
                # A crash may interrupt step while it owns the source lease.
                # Fail closed first. Only this test's exited subprocess is fenced;
                # remove its disposable orphan lease explicitly, never in runtime.
                lease = root / "source.jsonl.writer.lock"
                if lease.exists():
                    before = (root / "source.jsonl").read_bytes()
                    with self.assertRaises(JournalIntegrityError):
                        source(root)
                    self.assertEqual((root / "source.jsonl").read_bytes(), before)
                    self.assertTrue(lease.read_text().isdigit())
                    lease.unlink()
                retained = source(root)
                self.assertEqual(retained.status()["acked"], 0)
                worker = ObservationWorker(root / "target.jsonl")
                try:
                    drain(retained, worker)
                    self.assertEqual(retained.status()["acked"], 1)
                finally:
                    worker.finish(5)
                self.assertEqual(len((root / "target.jsonl").read_bytes().splitlines()), 1)
                self.assertEqual(source(root).status()["pending"], 0)
