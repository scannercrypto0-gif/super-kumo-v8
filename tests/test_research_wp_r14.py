"""Safety and measurements for the independent WP-R14 batch-commit experiment."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

from research_wp_r0.group_commit_experiment import (
    ExperimentalBatchFile, benchmark_matrix, benchmark_once, verified_prefix,
)


class GroupCommitExperimentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "frames.jsonl"

    def test_per_event_strict_mode(self):
        r = benchmark_once(self.path, attempts=16, batch_size=1)
        self.assertEqual((r.fsync_calls, r.committed, r.max_pending_events), (16, 16, 1))

    def test_batch_sizes_and_full_flush(self):
        r = benchmark_once(self.path, attempts=17, batch_size=4)
        self.assertEqual((r.fsync_calls, r.committed, r.max_pending_events), (5, 17, 4))

    def test_pending_data_must_not_be_acked(self):
        w = ExperimentalBatchFile(self.path, batch_size=4)
        try:
            w.append("one")
            w.append("two")
            self.assertEqual(w.committed, 0)
            self.assertEqual(w.pending, 2)
            self.assertEqual(w.fsync_calls, 0)
            self.assertEqual(w.committed_offset, 0)
            self.assertEqual(verified_prefix(self.path.read_bytes()), 2)
            # Readability is NOT a durability guarantee: no fsync occurred.
        finally:
            w.close(flush=False)

    def test_crash_simulation_only_earlier_committed_prefix_survives(self):
        w = ExperimentalBatchFile(self.path, batch_size=4)
        try:
            for i in range(6):
                w.append(str(i))
            self.assertEqual((w.committed, w.pending), (4, 2))
            committed_offset = w.committed_offset
            self.assertGreater(committed_offset, 0)
        finally:
            w.close(flush=False)
        # Simulates a power-loss outcome where the unsynced tail vanishes.
        # This is NOT a real power failure or proof of filesystem durability.
        with self.path.open("r+b") as file:
            file.truncate(committed_offset)
        self.assertEqual(verified_prefix(self.path.read_bytes()), 4)

    def test_uncommitted_torn_tail_fails_closed(self):
        w = ExperimentalBatchFile(self.path, batch_size=16)
        w.append("one")
        w.close(flush=False)
        with self.path.open("ab") as file:
            file.write(b"broken")
        with self.assertRaises(ValueError):
            verified_prefix(self.path.read_bytes())

    def test_fsync_failure_does_not_advance_commit(self):
        w = ExperimentalBatchFile(self.path, batch_size=4)
        try:
            for i in range(3):
                w.append(str(i))
            with patch("research_wp_r0.group_commit_experiment.os.fsync",
                       side_effect=OSError("synthetic flush failure")):
                with self.assertRaises(OSError):
                    w.commit()
            self.assertEqual((w.committed, w.pending), (0, 3))
            self.assertTrue(w.poisoned)
            with self.assertRaises(RuntimeError):
                w.append("never")
        finally:
            w.close(flush=False)

    def test_hash_and_order_tampering_rejected(self):
        benchmark_once(self.path, attempts=8, batch_size=4)
        data = self.path.read_bytes()
        self.path.write_bytes(data.replace(b"synthetic-0001", b"synthetic-9999"))
        with self.assertRaises(ValueError):
            verified_prefix(self.path.read_bytes())

    def test_benchmark_matrix_counts_and_positive_timings(self):
        results = benchmark_matrix(sizes=(16,), batches=(1, 4, 16), repeats=2)
        self.assertEqual(len(results), 3)
        self.assertEqual([row["fsync_calls"] for row in results], [16, 4, 1])
        self.assertEqual([row["max_pending_events"] for row in results], [1, 4, 16])
        self.assertTrue(all(row["median_ms"] > 0 for row in results))


if __name__ == "__main__":
    unittest.main()
