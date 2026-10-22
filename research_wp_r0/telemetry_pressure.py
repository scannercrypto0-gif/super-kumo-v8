"""WP-R16: bounded, lossy telemetry under deterministic pressure and failure.

Entirely synthetic/offline. This is an executable containment test, not a
production telemetry service, an OS power-loss experiment, or performance SLA.
Authoritative evidence never depends on a telemetry queue or its worker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from queue import Empty, Full, Queue
import tempfile
import threading
import time

from research_wp_r0.durable_journal import DurableTrialJournal
from research_wp_r0.group_commit_experiment import ExperimentalBatchFile, verified_prefix
from research_wp_r0.trial_holdout import (
    FrozenSearchFamily, Attempt, AttemptState, HoldoutEvent,
)

T0 = datetime(2026, 10, 22, tzinfo=timezone.utc)


@dataclass(frozen=True)
class PressureResult:
    mode: str
    emitted: int
    accepted: int
    dropped_overflow: int
    telemetry_committed: int
    telemetry_lost_after_failure: int
    telemetry_failed: bool
    telemetry_queue_capacity: int
    evidence_attempts: int
    evidence_events: int
    evidence_ms: float
    evidence_restored: bool
    evidence_head_unchanged: bool
    confirmation_denied: bool
    worker_finished: bool


def _family(count: int) -> FrozenSearchFamily:
    return FrozenSearchFamily(
        "r16-pressure", "synthetic-protocol", "synthetic-temporal",
        "synthetic-dataset", "net", "MAXIMIZE",
        tuple(f"trial-{i:03d}" for i in range(count)),
        0.05, T0,
    )


def pressure_trial(directory: Path, *, mode: str,
                   emitted: int = 512, queue_capacity: int = 8,
                   evidence_attempts: int = 32) -> PressureResult:
    if mode not in ("stalled-then-drain", "worker-failure"):
        raise ValueError("Invalid pressure mode")
    if any(type(v) is not int for v in (emitted, queue_capacity, evidence_attempts)):
        raise ValueError("Workload parameters must be integers")
    if not (1 <= queue_capacity <= 64 and queue_capacity < emitted <= 4096 and
            2 <= evidence_attempts <= 128):
        raise ValueError("Invalid pressure workload")
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("Need an empty, isolated experiment directory")

    queue: Queue[str] = Queue(maxsize=queue_capacity)
    started = threading.Event()
    release = threading.Event()
    worker_done = threading.Event()
    counters = {"committed": 0, "failed": False}
    telemetry = directory / "telemetry.jsonl"

    def worker() -> None:
        writer = None
        try:
            writer = ExperimentalBatchFile(telemetry, batch_size=4)
            started.set()
            if not release.wait(timeout=30):
                raise RuntimeError("Experiment telemetry worker release timed out")
            consumed = 0
            while True:
                try:
                    item = queue.get_nowait()
                except Empty:
                    break
                if mode == "worker-failure" and consumed == 3:
                    raise OSError("Synthetic telemetry-only writer failure")
                writer.append(item)
                consumed += 1
            writer.close(flush=True)
            counters["committed"] = writer.committed
        except BaseException:
            counters["failed"] = True
            if writer is not None:
                counters["committed"] = writer.committed
                if not writer.closed:
                    writer.close(flush=False)
        finally:
            started.set()
            worker_done.set()

    background = threading.Thread(target=worker, name="synthetic-lossy-telemetry")
    background.start()
    evidence_elapsed = 0.0
    anchor_head = ""
    anchor_sequence = 0
    accepted = 0
    overflow = 0
    try:
        if not started.wait(timeout=10):
            raise AssertionError("Telemetry worker failed to start")
        # Deterministically saturate a stopped consumer: put_nowait MUST never
        # block, and cannot influence authoritative trial recording.
        for i in range(emitted):
            try:
                queue.put_nowait(f"metric-{i:04d}")
                accepted += 1
            except Full:
                overflow += 1
        if accepted != queue_capacity or overflow != emitted - queue_capacity:
            raise AssertionError("Backpressure test was not deterministic")

        family = _family(evidence_attempts)
        begun = time.perf_counter()
        with DurableTrialJournal(directory / "evidence.jsonl", family) as journal:
            for i in range(evidence_attempts):
                state = AttemptState.FAILED if i % 7 == 0 else AttemptState.COMPLETE
                journal.record_attempt(Attempt(
                    f"trial-{i:03d}", state, f"result-{i:03d}",
                    T0 + timedelta(minutes=1, seconds=i),
                    None if state == AttemptState.FAILED else 0.5,
                ), event_id=f"attempt-{i:03d}")
            journal.select("trial-001", at=T0 + timedelta(hours=1),
                           event_id="frozen-selection")
            journal.holdout_event(HoldoutEvent(
                "OPEN", T0 + timedelta(hours=2), "synthetic-access",
            ), event_id="holdout-open")
            anchor_head, anchor_sequence = journal.head, journal.sequence
            if journal.report().confirmatory_eligible:
                raise AssertionError("Positive research gate incorrectly allowed")
        evidence_elapsed = (time.perf_counter() - begun) * 1000
    finally:
        # Always release and join, even on evidence validation errors.
        release.set()
        background.join(timeout=15)
    if background.is_alive() or not worker_done.is_set():
        raise RuntimeError("Telemetry worker did not exit cleanly")
    recovered = False
    unchanged = False
    denied = False
    with DurableTrialJournal(directory / "evidence.jsonl", _family(evidence_attempts),
                             expected_head=anchor_head,
                             expected_sequence=anchor_sequence) as journal:
        report = journal.report()
        recovered = report.total_declared == evidence_attempts and report.missing == 0
        unchanged = journal.head == anchor_head and journal.sequence == anchor_sequence
        denied = not report.confirmatory_eligible
    saved = counters["committed"]
    if saved:
        lines = telemetry.read_bytes().splitlines(keepends=True)
        # The worker-failure mode can leave a readable unsynced tail. Count
        # only the committed first records: never call readable == durable.
        durable_prefix = b"".join(lines[:saved])
        if verified_prefix(durable_prefix) != saved:
            raise AssertionError("Telemetry synced prefix invalid")
    result = PressureResult(
        mode, emitted, accepted, overflow, saved,
        accepted - saved, counters["failed"], queue_capacity,
        evidence_attempts, anchor_sequence, round(evidence_elapsed, 3),
        recovered, unchanged, denied, not background.is_alive(),
    )
    if not (result.evidence_restored and result.evidence_head_unchanged and
            result.confirmation_denied and result.worker_finished):
        raise AssertionError("Telemetry failure crossed research evidence boundary")
    if mode == "stalled-then-drain" and (saved != accepted or counters["failed"]):
        raise AssertionError("Telemetry drain unexpectedly lost queued records")
    if mode == "worker-failure" and (saved != 0 or not counters["failed"]):
        raise AssertionError("Fault injection did not fail before telemetry durability")
    return result


def main() -> None:
    results = []
    for mode in ("stalled-then-drain", "worker-failure"):
        with tempfile.TemporaryDirectory(prefix="aql-r16-") as directory:
            results.append(asdict(pressure_trial(Path(directory), mode=mode)))
    print(json.dumps({
        "scope": "offline_discardable_telemetry_pressure_not_production",
        "results": results,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
