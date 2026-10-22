"""WP-R12: execute measurable offline pipeline, not just component contracts."""
import tempfile
from pathlib import Path
import unittest

from research_wp_r0.measured_pipeline import run_measurement, Measurement


class MeasuredPipelineAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Run once; the CI workflow also runs executable CLI separately.
        cls.measurement = run_measurement()

    def test_workload_and_accounting(self):
        r = self.measurement
        self.assertEqual(r.opportunities, 120)
        self.assertEqual(r.attempted_candidates, 32)
        self.assertEqual(r.failed_trials, 5)
        self.assertEqual(r.journal_events, 35)
        self.assertGreater(r.journal_bytes, 0)

    def test_real_durations_are_recorded(self):
        r = self.measurement
        for name in ("total_ms", "evaluate_ms", "journal_ms",
                     "restore_ms", "checkpoint_ms"):
            with self.subTest(name=name):
                self.assertGreater(getattr(r, name), 0)
        self.assertGreaterEqual(r.total_ms, r.journal_ms)

    def test_research_protection_stays_fail_closed(self):
        r = self.measurement
        self.assertTrue(r.tamper_detected)
        self.assertTrue(r.rollback_detected)
        self.assertTrue(r.positive_nomination_blocked)
        self.assertTrue(r.positive_screen_blocked)
        self.assertTrue(r.custody_is_simulated)

    def test_metric_output_is_machine_readable(self):
        import json
        payload = json.loads(self.measurement.as_json())
        self.assertEqual(payload["opportunities"], 120)
        self.assertEqual(payload["attempted_candidates"], 32)

    def test_refuses_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "existing-evidence").write_text("do-not-overwrite")
            with self.assertRaises(ValueError):
                run_measurement(directory=path)
            self.assertEqual((path / "existing-evidence").read_text(), "do-not-overwrite")


if __name__ == "__main__":
    unittest.main()
