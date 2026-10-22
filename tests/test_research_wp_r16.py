"""WP-R16 acceptance: live-thread bounded backlog, fault and evidence isolation."""
import tempfile
from pathlib import Path
import unittest

from research_wp_r0.telemetry_pressure import pressure_trial


class TelemetryPressureAcceptance(unittest.TestCase):
    def run_case(self, mode, *, queue_capacity=8, emitted=512,
                 evidence_attempts=32):
        with tempfile.TemporaryDirectory(prefix="aql-r16-test-") as root:
            return pressure_trial(
                Path(root), mode=mode, queue_capacity=queue_capacity,
                emitted=emitted, evidence_attempts=evidence_attempts,
            )

    def test_stalled_consumer_never_blocks_critical_evidence(self):
        r = self.run_case("stalled-then-drain")
        self.assertEqual((r.emitted, r.accepted, r.dropped_overflow),
                         (512, 8, 504))
        self.assertEqual((r.telemetry_committed, r.telemetry_lost_after_failure),
                         (8, 0))
        self.assertEqual(r.evidence_events, 35)
        self.assertGreater(r.evidence_ms, 0)
        self.assertTrue(r.evidence_restored)
        self.assertTrue(r.evidence_head_unchanged)
        self.assertTrue(r.confirmation_denied)

    def test_worker_failure_fails_telemetry_only(self):
        r = self.run_case("worker-failure")
        self.assertTrue(r.telemetry_failed)
        self.assertEqual(r.telemetry_committed, 0)
        self.assertEqual(r.telemetry_lost_after_failure, 8)
        self.assertTrue(r.evidence_restored)
        self.assertTrue(r.evidence_head_unchanged)
        self.assertTrue(r.confirmation_denied)

    def test_small_queue_and_evidence_accounting(self):
        r = self.run_case("stalled-then-drain", queue_capacity=2,
                          emitted=40, evidence_attempts=8)
        self.assertEqual((r.accepted, r.dropped_overflow), (2, 38))
        self.assertEqual(r.evidence_events, 11)
        self.assertTrue(r.worker_finished)

    def test_bad_workloads_rejected_without_existing_file_edits(self):
        for bad in ((0, 8, 32), (8, 8, 32), (20, True, 32), (20, 4, 1)):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as root:
                path = Path(root)
                with self.assertRaises(ValueError):
                    pressure_trial(path, mode="stalled-then-drain",
                                   emitted=bad[0], queue_capacity=bad[1],
                                   evidence_attempts=bad[2])

    def test_nonempty_directory_left_unmodified(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / "keep").write_text("unchanged")
            with self.assertRaises(ValueError):
                pressure_trial(path, mode="worker-failure")
            self.assertEqual((path / "keep").read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
