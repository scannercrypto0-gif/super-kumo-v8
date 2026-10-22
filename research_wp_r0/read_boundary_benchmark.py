"""Offline WP-R19 before/after read-validation cost and regression probes.

Synthetic temporary journals only; real per-event fsync remains enabled.
Timing samples are local observations, not a durability or service guarantee.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time
from unittest.mock import patch
import os

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import export_checkpoint, verify_owner_checkpoint
from research_wp_r0.temporal_contract import FrozenTemporalManifest, TemporalOpportunity
from research_wp_r0.trial_holdout import Attempt, AttemptState, FrozenSearchFamily, HoldoutEvent

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family(count=2, **kwargs):
    data = dict(family_id="read-audit", protocol_digest="protocol", temporal_manifest_digest="manifest",
                dataset_version="synthetic-v1", metric_name="net", metric_direction="MAXIMIZE",
                candidate_ids=tuple(f"c{i}" for i in range(count)), alpha=0.05, declared_at=T)
    data.update(kwargs)
    return FrozenSearchFamily(**data)


def rejected(operation):
    try:
        operation()
    except (ValueError, OSError):
        return True
    return False


def fault_probes():
    probes = {}
    for name, change in (
        ("malformed_report", lambda path: path.write_bytes(b"BROKEN\n")),
        ("torn_report", lambda path: path.write_bytes(path.read_bytes()[:-1])),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "j.jsonl"
            with DurableTrialJournal(path, family()) as j:
                change(path)
                probes[name] = rejected(j.report)
    with tempfile.TemporaryDirectory() as tmp:
        with DurableTrialJournal(Path(tmp) / "j.jsonl", family()) as j:
            c = export_checkpoint(j)
            probes["string_false_trust"] = rejected(
                lambda: verify_owner_checkpoint(j, c, independently_trusted="false"))
    probes["mutable_frozen_family_reference"] = rejected(lambda: family(protocol_digest=["mutable"]))
    event = TemporalOpportunity("o", T, T, T, T + timedelta(hours=1), T + timedelta(hours=1),
                                T + timedelta(hours=1), T + timedelta(hours=1), "g")
    probes["mutable_frozen_manifest_reference"] = rejected(
        lambda: FrozenTemporalManifest(["mutable"], "source", "60m", (event,)))
    return probes


def sample(count, reports):
    with tempfile.TemporaryDirectory(prefix="aql-read-boundary-") as tmp:
        path = Path(tmp) / "evidence.jsonl"
        real_sync = os.fsync
        with patch("research_wp_r0.durable_journal.os.fsync", wraps=real_sync) as sync:
            with DurableTrialJournal(path, family(count)) as j:
                started = time.perf_counter()
                for i in range(count):
                    j.record_attempt(Attempt(f"c{i}", AttemptState.COMPLETE, f"result-{i}",
                                             T + timedelta(minutes=1), 0.1), event_id=f"trial-{i}")
                append_ms = (time.perf_counter() - started) * 1000
                j.select("c0", at=T + timedelta(minutes=2), event_id="select")
                j.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=3), "synthetic-open"), event_id="open")
                checkpoint = export_checkpoint(j)
                verify_owner_checkpoint(j, checkpoint, independently_trusted=True)
                before_bytes, before_head = path.read_bytes(), j.head
                with patch.object(j, "_restore", wraps=j._restore) as restore:
                    started = time.perf_counter()
                    for _ in range(reports):
                        report = j.report()
                        if report.complete != count or report.confirmatory_eligible:
                            raise AssertionError("Research safety gate/count changed")
                    report_ms = (time.perf_counter() - started) * 1000
                    restore_calls = restore.call_count
                if path.read_bytes() != before_bytes or j.head != before_head:
                    raise AssertionError("Report mutated committed evidence")
                events = j.sequence
            with DurableTrialJournal(path, family(count), expected_head=checkpoint.head,
                                      expected_sequence=checkpoint.sequence) as reopened:
                if reopened.report().complete != count:
                    raise AssertionError("Restart lost trial accounting")
            if sync.call_count != count + 3:
                raise AssertionError("Strict per-event fsync contract changed")
        return dict(attempts=count, events=events, reports=reports, append_ms=append_ms,
                    report_ms=report_ms, report_replays=restore_calls,
                    fsync_calls=sync.call_count, bytes=len(before_bytes),
                    head=before_head, report_mutated_evidence=False, restart_verified=True,
                    confirmatory_eligible=False)


def run(label, *, sizes=(8, 32, 128), reports=12, repeats=3):
    results = []
    for size in sizes:
        samples = [sample(size, reports) for _ in range(repeats)]
        results.append(dict(attempts=size, median_append_ms=statistics.median(x["append_ms"] for x in samples),
                            median_report_ms=statistics.median(x["report_ms"] for x in samples),
                            samples=samples))
    here = Path(__file__).parent
    files = ("durable_journal.py", "owner_checkpoints.py", "trial_holdout.py", "temporal_contract.py")
    return dict(label=label, synthetic_only=True, python=platform.python_version(), platform=platform.platform(),
                source_sha256={name: hashlib.sha256((here/name).read_bytes()).hexdigest() for name in files},
                repeats=repeats, reports_per_sample=reports, results=results,
                negative_probes=fault_probes(),
                limitation="Local Linux samples only; not Windows, real holdout custody or hardware power-loss proof.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="working-tree")
    args = parser.parse_args()
    print(json.dumps(run(args.label), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
