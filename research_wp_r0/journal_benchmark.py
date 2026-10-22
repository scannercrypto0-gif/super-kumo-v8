"""Reproducible synthetic journal throughput bench, no real research evidence.

Usage: python journal_benchmark.py --module-root BASE_OR_HEAD --sizes 16,32,64
Uses one temporary directory per iteration. Reports actual median durations;
single CI runs should never be treated as stable performance guarantees.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import time


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle-1] + ordered[middle]) / 2


def run(*, module_root: Path, sizes: tuple[int, ...], repeats: int) -> dict:
    module_root = module_root.resolve()
    if not (module_root / "research_wp_r0" / "durable_journal.py").is_file():
        raise ValueError("Need repository module root")
    # Running a script inside research_wp_r0 puts that directory on sys.path;
    # its statistics.py would shadow Python's standard-library statistics.
    script_dir = str(Path(__file__).resolve().parent)
    sys.path[:] = [p for p in sys.path if str(Path(p).resolve()) != script_dir]
    sys.path.insert(0, str(module_root))
    from research_wp_r0.durable_journal import DurableTrialJournal
    from research_wp_r0.trial_holdout import Attempt, AttemptState, FrozenSearchFamily

    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    data = []
    for n in sizes:
        if n < 2 or n > 1024:
            raise ValueError("Require 2..1024 synthetic attempts")
        observed = []
        for _ in range(repeats):
            with tempfile.TemporaryDirectory(prefix="aql-bench-") as d:
                path = Path(d) / "journal.jsonl"
                family = FrozenSearchFamily(
                    "bench", "protocol-fixture", "temporal-fixture", "data-fixture",
                    "net", "MAXIMIZE", tuple(f"c{i:04d}" for i in range(n)),
                    0.05, now,
                )
                fsync_total_seconds = 0.0
                fsync_calls = 0
                real_fsync = os.fsync

                def measured_fsync(fd):
                    nonlocal fsync_total_seconds, fsync_calls
                    before_fsync = time.perf_counter()
                    try:
                        return real_fsync(fd)  # DO NOT weaken write durability
                    finally:
                        fsync_total_seconds += time.perf_counter() - before_fsync
                        fsync_calls += 1

                started = time.perf_counter()
                with patch("os.fsync", side_effect=measured_fsync):
                    with DurableTrialJournal(path, family) as journal:
                        for i in range(n):
                            journal.record_attempt(
                                Attempt(f"c{i:04d}", AttemptState.COMPLETE,
                                        f"digest-{i:04d}",
                                        now + timedelta(seconds=i + 1), 0.5),
                                event_id=f"event-{i:04d}",
                            )
                        if journal.sequence != n + 1 or journal.report().complete != n:
                            raise AssertionError("Journal failed attempt accounting")
                        head = journal.head
                write_ms = (time.perf_counter() - started) * 1000
                if fsync_calls != n + 1:
                    raise AssertionError("Expected every append, including genesis, to fsync")
                replay_started = time.perf_counter()
                with DurableTrialJournal(path, family) as restored:
                    if restored.head != head or restored.report().complete != n:
                        raise AssertionError("Restored chain mismatch")
                replay_ms = (time.perf_counter() - replay_started) * 1000
                observed.append((write_ms, replay_ms, path.stat().st_size,
                                 fsync_total_seconds * 1000, fsync_calls))
        data.append({
            "attempts": n,
            "repeat_count": repeats,
            "append_total_median_ms": round(_median(x[0] for x in observed), 3),
            "restore_median_ms": round(_median(x[1] for x in observed), 3),
            "journal_bytes": observed[0][2],
            "append_ms_per_attempt": round(_median(x[0] for x in observed) / n, 3),
            "fsync_total_median_ms": round(_median(x[3] for x in observed), 3),
            "fsync_calls": observed[0][4],
            "fsync_share_of_append_pct": round(100 * _median(x[3] for x in observed) / _median(x[0] for x in observed), 1),
        })
    return {
        "module_root": module_root.name,
        "performance_scope": "synthetic_tempfile_fs_synced_single_writer",
        "results": data,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-root", type=Path, required=True)
    parser.add_argument("--sizes", default="16,32,64")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 10:
        raise ValueError("repeats must be between 1 and 10")
    sizes = tuple(int(x) for x in args.sizes.split(","))
    print(json.dumps(run(module_root=args.module_root, sizes=sizes,
                         repeats=args.repeats), sort_keys=True))


if __name__ == "__main__":
    main()
