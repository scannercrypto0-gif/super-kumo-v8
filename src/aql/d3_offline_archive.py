"""Offline opt-in D3 local archive: nonblocking admission and verified restore.

Not a realtime pipeline integration, independent custody or physical durability claim.
"""
from __future__ import annotations

from concurrent.futures import Future
import json
import os
from pathlib import Path
import queue
import threading
from typing import Mapping

from .d3_synthetic_archive import D3IntegrityError, _canonical, verify_catalog


def publish_generation(directory: Path, catalog: Mapping[str, object]) -> Path:
    """Publish one immutable synthetic manifest without overwriting a generation."""
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise D3IntegrityError("archive directory must exist and be non-symlink")
    name = catalog.get("generation")
    if not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise D3IntegrityError("unsafe generation")
    destination = root / (name + ".json")
    pending = root / (name + ".pending")
    data = _canonical(dict(catalog)) + b"\n"
    # O_EXCL prevents overwrite, including stale pending generations.
    fd = None
    try:
        fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link promotion refuses overwrite atomically; same filesystem required.
        os.link(pending, destination, follow_symlinks=False)
        if hasattr(os, "O_DIRECTORY"):
            dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        return destination
    except (OSError, TypeError, ValueError) as exc:
        raise D3IntegrityError("archive publication failed closed") from exc
    finally:
        if fd is not None:
            os.close(fd)
        # A crash can leave .pending; operator must inspect before manual cleanup.
        if destination.exists():
            pending.unlink(missing_ok=True)


def verify_restore(directory: Path, *, generation: str, pinned_digest: str,
                   expected_consumer: str, minimum_epoch: int,
                   source_digests: Mapping[int, str],
                   target_receipts: Mapping[int, str]) -> tuple:
    """Read-only restore rehearsal; never writes into a live source/target store."""
    if not generation or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in generation):
        raise D3IntegrityError("unsafe generation")
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise D3IntegrityError("invalid archive root")
    path = root / (generation + ".json")
    if path.is_symlink() or not path.is_file():
        raise D3IntegrityError("missing or replaced manifest")
    try:
        with path.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise D3IntegrityError("manifest exceeds bounded size")
        catalog = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise D3IntegrityError("unreadable archive") from exc
    return verify_catalog(catalog, pinned_digest=pinned_digest,
                          expected_generation=generation,
                          expected_consumer=expected_consumer,
                          minimum_epoch=minimum_epoch,
                          source_digests=source_digests,
                          target_receipts=target_receipts)


class OfflineArchiveLane:
    """Explicitly isolated opt-in queue; submit never runs archive I/O.

    Queue full rejects immediately. Accepted jobs return a Future; callers must
    inspect it, and must retain upstream evidence until publication is confirmed.
    """

    def __init__(self, directory: Path, *, capacity: int = 8):
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError("invalid queue capacity")
        self.directory = Path(directory)
        self._jobs: queue.Queue = queue.Queue(maxsize=capacity)
        self._closed = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True, name="d3-offline-archive")
        self._thread.start()

    def submit(self, catalog: Mapping[str, object]) -> Future | None:
        with self._lock:
            if self._closed:
                return None
            future: Future = Future()
            try:
                self._jobs.put_nowait((dict(catalog), future))
            except queue.Full:
                return None
            return future

    def _run(self) -> None:
        while True:
            item = self._jobs.get()
            try:
                if item is None:
                    return
                catalog, future = item
                try:
                    future.set_result(publish_generation(self.directory, catalog))
                except Exception as exc:
                    future.set_exception(exc)
            finally:
                self._jobs.task_done()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # Closing is an offline control-plane operation and may wait for I/O.
        self._jobs.put(None)
        self._thread.join()
