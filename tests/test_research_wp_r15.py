"""WP-R15 acceptance: evidence survives disposable telemetry failure/loss."""
import tempfile
from pathlib import Path
import unittest

from research_wp_r0.isolated_telemetry import isolation_trial, run_measurement
from research_wp_r0.durable_journal import DurableTrialJournal
from research_wp_r0.isolated_telemetry import family


class IsolatedTelemetryTests(unittest.TestCase):
    def test_partial_telemetry_loss_never_changes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = isolation_trial(root, evidence_trials=16, telemetry_batch=5)
            self.assertEqual(result.committed_evidence_events, 19)
            self.assertEqual(result.telemetry_events_written, 16)
            self.assertEqual(result.telemetry_events_durable, 15)
            self.assertEqual(result.telemetry_events_lost_in_simulated_crash, 1)
            self.assertTrue(result.evidence_recovered)
            self.assertTrue(result.evidence_head_unchanged)
            self.assertTrue(result.positive_confirmation_blocked)

    def test_zero_telemetry_commit_still_has_full_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = isolation_trial(root, evidence_trials=8, telemetry_batch=16)
            self.assertEqual(result.telemetry_events_durable, 0)
            self.assertEqual(result.telemetry_events_lost_in_simulated_crash, 8)
            self.assertTrue(result.evidence_recovered)
            with DurableTrialJournal(root / "evidence.jsonl", family(8)) as journal:
                self.assertEqual(journal.report().total_declared, 8)
                self.assertFalse(journal.report().confirmatory_eligible)

    def test_no_loss_when_telemetry_exact_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            result = isolation_trial(Path(directory), evidence_trials=16, telemetry_batch=4)
            self.assertEqual(result.telemetry_events_lost_in_simulated_crash, 0)

    def test_evidence_directory_must_be_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing").write_text("untouched")
            with self.assertRaises(ValueError):
                isolation_trial(root)
            self.assertEqual((root / "existing").read_text(), "untouched")

    def test_invalid_telemetry_batch_refused(self):
        for n in (0, -1, True, 1000):
            with self.subTest(n=n), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    isolation_trial(Path(directory), telemetry_batch=n)

    def test_measurement_runs_and_never_changes_durability_policy(self):
        result = run_measurement(attempts=16, repeats=1)
        self.assertEqual(set(result["telemetry_median_ms_by_batch"]), {"1", "4", "16"})
        self.assertTrue(result["evidence_uses_strict_fsync"])
        self.assertEqual(result["isolation"]["telemetry_events_lost_in_simulated_crash"], 1)
        self.assertTrue(all(v > 0 for v in result["telemetry_median_ms_by_batch"].values()))


if __name__ == "__main__":
    unittest.main()
