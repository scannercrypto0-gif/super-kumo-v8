"""WP-R14: offline group-commit *experiment*; NOT used by DurableTrialJournal.

A batch is NOT durable, published, or acknowledged before fsync succeeds.
Deliberately isolates a possible alternative durability contract from existing
strict per-event commit. It benchmarks canonical append frames to a new temporary
file and deliberately simulates recovery by retaining only the last synced prefix.
Synthetic payloads only; no actual power-loss or tamper-resistance guarantee.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile
import time


def _encode(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


@dataclass(frozen=True)
class BatchMetrics:
    attempts: int
    batch_size: int
    elapsed_ms: float
    fsync_calls: int
    committed: int
    max_pending_events: int
    journal_bytes: int


class ExperimentalBatchFile:
    """Single-writer temporary file; NEVER use as research evidence journal."""

    def __init__(self, path: Path, batch_size: int):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("Positive batch size required")
        self.batch_size = batch_size
        self.path = path
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        self.fd = os.open(path, flags, 0o600)
        self.next_seq = 1
        self.head = "0" * 64
        self.committed = 0
        self.committed_offset = 0
        self.pending = 0
        self.max_pending_events = 0
        self.fsync_calls = 0
        self.closed = False
        self.poisoned = False

    def append(self, event_id: str) -> None:
        if self.closed or self.poisoned:
            raise RuntimeError("Writer closed/poisoned")
        if not event_id:
            raise ValueError("Event id required")
        body = {"sequence": self.next_seq, "prev_hash": self.head, "event_id": event_id}
        digest = hashlib.sha256(_encode(body)).hexdigest()
        row = _encode({**body, "hash": digest})
        try:
            done = 0
            while done < len(row):
                count = os.write(self.fd, row[done:])
                if count <= 0:
                    raise OSError("Write made no progress")
                done += count
        except BaseException:
            self.poisoned = True
            raise
        self.head = digest
        self.next_seq += 1
        self.pending += 1
        self.max_pending_events = max(self.max_pending_events, self.pending)
        if self.pending >= self.batch_size:
            self.commit()

    def commit(self) -> None:
        if self.closed or self.poisoned:
            raise RuntimeError("Writer closed/poisoned")
        if not self.pending:
            return
        try:
            os.fsync(self.fd)
        except BaseException:
            self.poisoned = True
            raise
        self.fsync_calls += 1
        self.committed += self.pending
        self.pending = 0
        self.committed_offset = os.lseek(self.fd, 0, os.SEEK_CUR)

    def close(self, *, flush: bool = True) -> None:
        if self.closed:
            return
        try:
            if flush and not self.poisoned:
                self.commit()
        finally:
            os.close(self.fd)
            self.closed = True


def verified_prefix(raw: bytes) -> int:
    """Return verified records; fail closed on incomplete/corrupt tails."""
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("Truncated/uncommitted frame")
    prev = "0" * 64
    count = 0
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if type(row) is not dict or set(row) != {"sequence", "prev_hash", "event_id", "hash"}:
            raise ValueError("Unexpected frame schema")
        if _encode(row) != line or row["sequence"] != count + 1 or row["prev_hash"] != prev:
            raise ValueError("Noncanonical, reordered, or broken chain")
        expected = hashlib.sha256(_encode({
            "sequence": row["sequence"], "prev_hash": prev, "event_id": row["event_id"]
        })).hexdigest()
        if row["hash"] != expected:
            raise ValueError("Frame has invalid hash")
        prev = expected
        count += 1
    return count


def benchmark_once(path: Path, *, attempts: int, batch_size: int) -> BatchMetrics:
    if type(attempts) is not int or not 1 <= attempts <= 4096:
        raise ValueError("Invalid workload size")
    started = time.perf_counter()
    writer = ExperimentalBatchFile(path, batch_size)
    try:
        for i in range(attempts):
            writer.append(f"synthetic-{i:04d}")
        writer.close(flush=True)
    finally:
        if not writer.closed:
            writer.close(flush=False)
    elapsed_ms = (time.perf_counter() - started) * 1000
    data = path.read_bytes()
    if verified_prefix(data) != writer.committed or writer.committed != attempts:
        raise AssertionError("Lost/corrupt committed events")
    return BatchMetrics(attempts, batch_size, round(elapsed_ms, 3),
                        writer.fsync_calls, writer.committed,
                        writer.max_pending_events, len(data))


def benchmark_matrix(*, sizes=(16, 32, 64, 128), batches=(1, 4, 16), repeats=3):
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("Invalid repetitions")
    results = []
    for n in sizes:
        for batch in batches:
            samples = []
            for _ in range(repeats):
                with tempfile.TemporaryDirectory(prefix="aql-group-commit-") as d:
                    samples.append(benchmark_once(
                        Path(d) / "frames.jsonl", attempts=n, batch_size=batch
                    ))
            results.append({
                "attempts": n,
                "batch_size": batch,
                "repeats": repeats,
                "median_ms": round(statistics.median(s.elapsed_ms for s in samples), 3),
                "fsync_calls": samples[0].fsync_calls,
                "max_pending_events": samples[0].max_pending_events,
                "committed_events": samples[0].committed,
                "journal_bytes": samples[0].journal_bytes,
            })
    return results


def main() -> None:
    print(json.dumps({
        "scope": "synthetic_experimental_frames_NOT_ResearchJournal",
        "warning": "Before fsync, events may be lost; no crash-proof durability is claimed",
        "results": benchmark_matrix(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
