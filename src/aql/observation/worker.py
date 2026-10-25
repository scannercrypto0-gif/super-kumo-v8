"""Optional offline G2 observation worker; never called synchronously by G1.

Admission is volatile until append/fsync completes. A rejected or uncommitted
event MUST be retried by its upstream source; this is not a durable input queue.
"""
from __future__ import annotations

import queue
import threading
from pathlib import Path

from .position_journal import DurablePositionJournal, JournalIntegrityError
from .positions import PositionEvent


class ObservationWorker:
    """Bounded, single-writer G2 lane with separate health and journal ownership."""

    def __init__(self, journal_path: str | Path, capacity: int = 16):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.journal_path = Path(journal_path)
        self.jobs: queue.Queue[PositionEvent] = queue.Queue(maxsize=capacity)
        self.stop_event = threading.Event()
        self.errors: list[str] = []
        self.rejected = 0
        self.committed = 0
        self._inflight: PositionEvent | None = None
        self._failed_event_ids: list[str] = []
        self._lock = threading.Lock()
        # Fail closed on corrupt historical journal BEFORE admitting any work.
        self.journal = DurablePositionJournal(self.journal_path)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, event: PositionEvent) -> bool:
        if not isinstance(event, PositionEvent):
            raise TypeError("expected PositionEvent")
        with self._lock:
            if self.stop_event.is_set() or self.errors:
                self.rejected += 1
                return False
            try:
                self.jobs.put_nowait(event)
                return True
            except queue.Full:
                self.rejected += 1
                return False

    def _run(self):
        while not self.stop_event.is_set():
            try:
                event = self.jobs.get(timeout=0.05)
            except queue.Empty:
                continue
            with self._lock:
                self._inflight = event
            try:
                result = self.journal.append(event)
                if result in ("inserted", "duplicate"):
                    with self._lock:
                        self.committed += 1
            except Exception as exc:
                with self._lock:
                    self.errors.append(type(exc).__name__)
                    self._failed_event_ids.append(event.event_id)
                    self.errors[:] = self.errors[-16:]
                # Fail closed: no more writes after an uncommitted event.
                self.stop_event.set()
            finally:
                with self._lock:
                    self._inflight = None
                self.jobs.task_done()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "accepted_but_unconfirmed": self.jobs.unfinished_tasks,
                "failed_event_ids": list(self._failed_event_ids),
                "unconfirmed_event_ids": ([self._inflight.event_id] if self._inflight else [])
                    + [event.event_id for event in list(self.jobs.queue)],
                "committed_or_duplicate": self.committed,
                "rejected": self.rejected,
                "errors": list(self.errors),
                "worker_alive": self.thread.is_alive(),
                "healthy": not self.errors and not self.stop_event.is_set()
                           and self.thread.is_alive(),
                "uncommitted_inputs_are_volatile": True,
            }

    def finish(self, timeout: float = 1.0) -> dict:
        if timeout < 0:
            raise ValueError("timeout must be nonnegative")
        import time
        deadline = time.monotonic() + timeout
        while self.jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.005)
        self.stop_event.set()
        self.thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return self.snapshot()
