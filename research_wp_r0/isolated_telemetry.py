"""WP-R15: isolated, discardable telemetry versus strict evidence journal.

Synthetic offline demonstration, not a production pipeline. Telemetry never
carries authoritative trial or holdout state; it may be lost without affecting
the independently fsynced and replay-verified evidence journal.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import tempfile
import time

from research_wp_r0.durable_journal import DurableTrialJournal
from research_wp_r0.group_commit_experiment import (
    ExperimentalBatchFile, verified_prefix, benchmark_once,
)
from research_wp_r0.trial_holdout import (
    FrozenSearchFamily, Attempt, AttemptState, HoldoutEvent,
)

ORIGIN = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family(count: int) -> FrozenSearchFamily:
    if type(count) is not int or not 2 <= count <= 128:
        raise ValueError("Synthetic evidence count must be between 2 and 128")
    return FrozenSearchFamily(
        "isolated-telemetry-demo", "synthetic-protocol", "synthetic-temporal",
        "synthetic-dataset", "net", "MAXIMIZE",
        tuple(f"candidate-{i:04d}" for i in range(count)), 0.05, ORIGIN,
    )


@dataclass(frozen=True)
class IsolationResult:
    evidence_trials: int
    committed_evidence_events: int
    evidence_recovered: bool
    evidence_head_unchanged: bool
    telemetry_events_written: int
    telemetry_events_durable: int
    telemetry_events_lost_in_simulated_crash: int
    telemetry_batch: int
    positive_confirmation_blocked: bool


def isolation_trial(directory: Path, *, evidence_trials: int = 16,
                    telemetry_batch: int = 16) -> IsolationResult:
    """Commit evidence then simulate telemetry crash by dropping unsynced tail.

    Never use a pre-existing evidence directory or modify real research data.
    Any telemetry fsync failure is telemetry-only; evidence journal's failure
    policy remains unchanged and is not modified by this experiment.
    """
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("Require a new empty temporary experiment directory")
    if type(telemetry_batch) is not int or not 1 <= telemetry_batch <= 128:
        raise ValueError("Invalid telemetry batch size")
    evidence = directory / "evidence.jsonl"
    telemetry = directory / "telemetry.jsonl"
    frozen = family(evidence_trials)

    with DurableTrialJournal(evidence, frozen) as journal:
        for i in range(evidence_trials):
            state = AttemptState.FAILED if i % 7 == 0 else AttemptState.COMPLETE
            journal.record_attempt(Attempt(
                f"candidate-{i:04d}", state, f"synthetic-result-{i:04d}",
                ORIGIN + timedelta(minutes=1, seconds=i),
                None if state == AttemptState.FAILED else 0.5
            ), event_id=f"trial-{i:04d}")
        journal.select("candidate-0001", at=ORIGIN + timedelta(hours=1),
                       event_id="select")
        journal.holdout_event(HoldoutEvent(
            "OPEN", ORIGIN + timedelta(hours=2), "simulated-open"
        ), event_id="holdout")
        anchor_head, anchor_seq = journal.head, journal.sequence
        if journal.report().confirmatory_eligible:
            raise AssertionError("False strategy confirmation")

    # Different file, data type and state machine. Telemetry is never an
    # input to research trial accounting or to the evidence checkpoint.
    writer = ExperimentalBatchFile(telemetry, telemetry_batch)
    try:
        for i in range(evidence_trials):
            writer.append(f"latency-observation-{i:04d}")
        # The last incomplete batch remains uncommitted.
        committed_offset = writer.committed_offset
        committed_events = writer.committed
        written_events = writer.next_seq - 1
    finally:
        writer.close(flush=False)

    # Model *possible* crash loss: truncate exactly to synced prefix.
    # No claim of real physical power-loss durability.
    with telemetry.open("r+b") as handle:
        handle.truncate(committed_offset)
    if committed_events:
        if verified_prefix(telemetry.read_bytes()) != committed_events:
            raise AssertionError("Telemetry prefix invalid")
    elif telemetry.read_bytes():
        raise AssertionError("Uncommitted telemetry survived truncation simulation")

    with DurableTrialJournal(evidence, frozen,
                             expected_head=anchor_head,
                             expected_sequence=anchor_seq) as restored:
        report = restored.report()
        valid = report.complete + report.failed == evidence_trials
        blocked = not report.confirmatory_eligible
        unchanged = restored.head == anchor_head and restored.sequence == anchor_seq
    if not all((valid, unchanged, blocked)):
        raise AssertionError("Telemetry affected authoritative research evidence")
    return IsolationResult(
        evidence_trials, anchor_seq, valid, unchanged,
        written_events, committed_events, written_events - committed_events,
        telemetry_batch, blocked,
    )


def run_measurement(*, attempts: int = 32, repeats: int = 3) -> dict:
    """Same-runner comparison of temporary telemetry batch sizes.

    This is intentionally not a throughput benchmark for the full Research
    Journal: each group-commit sample writes only disposable telemetry frames.
    """
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("1..10 repeats required")
    timings = {}
    for batch in (1, 4, 16):
        values = []
        for _ in range(repeats):
            with tempfile.TemporaryDirectory(prefix="aql-telemetry-speed-") as d:
                tick = time.perf_counter()
                result = benchmark_once(Path(d) / "frames.jsonl",
                                        attempts=attempts, batch_size=batch)
                values.append((time.perf_counter() - tick) * 1000)
                if result.committed != attempts:
                    raise AssertionError("Telemetry benchmark lost final committed records")
        timings[str(batch)] = round(statistics.median(values), 3)
    with tempfile.TemporaryDirectory(prefix="aql-telemetry-isolation-") as d:
        isolation = isolation_trial(Path(d), evidence_trials=16, telemetry_batch=5)
    if isolation.telemetry_events_lost_in_simulated_crash != 1:
        raise AssertionError("Loss simulation did not exercise unsafe pending tail")
    return {
        "scope": "synthetic_discardable_telemetry_only",
        "telemetry_attempts": attempts,
        "repeat_count": repeats,
        "telemetry_median_ms_by_batch": timings,
        "evidence_uses_strict_fsync": True,
        "isolation": asdict(isolation),
    }


def main() -> None:
    print(json.dumps(run_measurement(), sort_keys=True))


if __name__ == "__main__":
    main()
