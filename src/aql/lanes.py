"""Bounded non-production background lane; no network in the core callback."""
from __future__ import annotations
import queue
import threading
import time
from .g1_integrity import ContentConflictError, propagate_conflict


class BackgroundLane:
    """One daemon worker, bounded admission, observable errors and bounded join.

    Jobs must respect stop_event between bounded units of work. An uncooperative
    external call cannot be killed safely in a thread: timeout is exposed rather
    than delaying the core. Pending work is rediscovered from the journal.
    """
    def __init__(self, capacity=16):
        self.jobs = queue.Queue(maxsize=capacity)
        self.stop_event = threading.Event()
        self.errors = []
        self.rejected = 0
        self.completed = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, job):
        try:
            self.jobs.put_nowait(job)
            return True
        except queue.Full:
            self.rejected += 1
            return False

    def _run(self):
        while not self.stop_event.is_set():
            try:
                job = self.jobs.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                job(self.stop_event)
            except Exception as exc:
                self.errors.append(type(exc).__name__)
                self.errors[:] = self.errors[-16:]
            finally:
                self.completed += 1
                self.jobs.task_done()

    def finish(self, timeout=1.0):
        deadline = time.monotonic() + timeout
        while self.jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.005)
        pending = self.jobs.unfinished_tasks
        self.stop_event.set()
        self.thread.join(timeout=max(0, deadline-time.monotonic()))
        return {'pending': pending, 'rejected': self.rejected,
                'errors': list(self.errors), 'worker_alive': self.thread.is_alive()}


class JournalConsumer:
    """Retry only durable, unacknowledged bars in bounded batches.

    Store success (including an existing key) precedes ACK. A failed store never
    prevents another core commit; retry uses the journal, not a lossy RAM queue.
    """
    def __init__(self, journal, store, symbol, interval, batch_size=64, ready=None):
        from .delivery.authority import register_legacy_writer
        register_legacy_writer(journal, 'journal-consumer')
        self.journal, self.store = journal, store
        self.symbol, self.interval = symbol, interval
        self.batch_size = batch_size
        self.ready = ready
        self.stop_event = threading.Event()
        self.errors = 0
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def drain_once(self):
        bars = self.journal.replay(self.symbol, self.interval,
                                   pending_only=True, limit=self.batch_size)
        for bar in bars:
            if self.stop_event.is_set():
                break
            try:
                self.journal.require_eligible(bar.stable_key())
                self.store.upsert(bar)
                self.journal.mark_persisted(bar.stable_key())
            except ContentConflictError as exc:
                propagate_conflict(exc,self.journal,self.store)
                self.errors += 1  # leave this key unacknowledged; continue others
        return len(bars)

    def _run(self):
        while not self.stop_event.is_set():
            if self.ready is not None and not self.ready.is_set():
                self.stop_event.wait(0.01)
                continue
            try:
                n = self.drain_once()
            except Exception:
                self.errors += 1
                n = 0
            if not n:
                self.stop_event.wait(0.05)

    def finish(self, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            counts = self.journal.count_by_state()
            if not counts.get('LOCAL_COMMITTED', 0):
                break
            self.stop_event.wait(0.01)
        self.stop_event.set()
        self.thread.join(timeout=max(0, deadline-time.monotonic()))
        return {'errors': self.errors, 'worker_alive': self.thread.is_alive()}

class WritePriority:
    """Prefer waiting ingestion commits over the next background SQLite write.

    Cooperative priority within one pipeline, not a real-time or host-wide CPU
    guarantee. A current fsync cannot be preempted safely.
    """
    def __init__(self):
        self.condition = threading.Condition()
        self.busy = False
        self.core_waiters = 0

    def hold(self, background=False):
        from contextlib import contextmanager
        @contextmanager
        def guard():
            with self.condition:
                if not background:
                    self.core_waiters += 1
                try:
                    while self.busy or (background and self.core_waiters):
                        self.condition.wait()
                    self.busy = True
                finally:
                    if not background:
                        self.core_waiters -= 1
            try:
                yield
            finally:
                with self.condition:
                    self.busy = False
                    self.condition.notify_all()
        return guard()
