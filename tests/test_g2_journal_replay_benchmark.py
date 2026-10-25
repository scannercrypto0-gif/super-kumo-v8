"""Opt-in, offline G2 journal replay benchmark; not a CI regression test.

Run explicitly with AQL_G2_BENCHMARK=1 and unittest discovery pattern
test_g2_journal_replay_benchmark.py. Report the machine and filesystem.
No performance threshold is inferred from this diagnostic.
"""
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aql.observation.position_journal import DurablePositionJournal
from aql.observation.positions import PositionEvent


@unittest.skipUnless(os.environ.get("AQL_G2_BENCHMARK") == "1",
                     "opt-in only; do not run on normal CI")
class JournalReplayBenchmark(unittest.TestCase):
    def test_replay_cost_by_journal_size(self):
        results = []
        for count in (10, 50, 100):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "journal.jsonl"
                writer = DurablePositionJournal(path)
                append_seconds = []
                for i in range(count):
                    event = PositionEvent("p1", f"event-{i}",
                                          "opened" if i == 0 else "quote",
                                          i, i, "offline")
                    start = time.perf_counter()
                    self.assertEqual(writer.append(event), "inserted")
                    append_seconds.append(time.perf_counter() - start)
                reopen_seconds = []
                for _ in range(3):
                    start = time.perf_counter()
                    reopened = DurablePositionJournal(path)
                    reopen_seconds.append(time.perf_counter() - start)
                    self.assertEqual(len(reopened.ledger.events), count)
                    self.assertEqual(reopened._tail, writer._tail)
                ordered = sorted(append_seconds)
                results.append({
                    "events": count,
                    "bytes": path.stat().st_size,
                    "append_p50_ms": round(statistics.median(ordered) * 1000, 3),
                    "append_p95_ms": round(ordered[max(0, int(.95 * len(ordered)) - 1)] * 1000, 3),
                    "append_p99_ms": round(ordered[max(0, int(.99 * len(ordered)) - 1)] * 1000, 3),
                    "reopen_samples_ms": [round(v * 1000, 3) for v in reopen_seconds],
                })
        print("G2_REPLAY_BENCHMARK " + json.dumps({
            "os": platform.platform(),
            "python": platform.python_version(),
            "filesystem": "operator must record actual filesystem/storage",
            "results": results,
            "status": "diagnostic only; not an acceptance threshold",
        }, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
