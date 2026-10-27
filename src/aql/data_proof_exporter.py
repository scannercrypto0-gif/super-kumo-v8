"""Opt-in bounded offline Core evidence exporter; never touches G1 ACK.

A full queue rejects explicitly. The caller must already have committed Core data.
"""
from __future__ import annotations

from concurrent.futures import Future
from queue import Full, Queue
from threading import Thread

from aql.data_proof import ProofError
from aql.data_proof_envelope import export_envelope
from aql.data_proof_registry import RevisionRegistry


class BoundedEvidenceExporter:
    def __init__(self, registry: RevisionRegistry, *, capacity: int = 16):
        if type(capacity) is not int or capacity < 1:
            raise ProofError("capacity must be positive")
        self._registry = registry
        self._queue: Queue = Queue(maxsize=capacity)
        self._closed = False
        self._worker = Thread(target=self._run, daemon=True, name="core-evidence-export")
        self._worker.start()

    def submit(self, *, consumer: str, epoch: int, logical_bar_id: str,
               gap_states: dict[str, str] | None = None) -> Future:
        """Return Future immediately; reject queue saturation without waiting."""
        future: Future = Future()
        if self._closed:
            future.set_exception(ProofError("exporter closed"))
            return future
        job = (consumer, epoch, logical_bar_id, dict(gap_states or {}), future)
        try:
            self._queue.put_nowait(job)
        except Full:
            future.set_exception(ProofError("evidence queue full; replay required"))
        return future

    def _run(self):
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                consumer, epoch, bar_id, gaps, future = job
                if future.set_running_or_notify_cancel():
                    try:
                        versions = self._registry.revisions(bar_id)
                        if not versions:
                            raise ProofError("no committed observation revisions")
                        future.set_result(export_envelope(
                            consumer=consumer, epoch=epoch, versions=versions,
                            gap_states=gaps))
                    except Exception as exc:
                        future.set_exception(exc)
            finally:
                self._queue.task_done()

    def close(self):
        """Drain accepted work, then stop; never call from the realtime hot path."""
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._worker.join()
