"""Legacy bridge must not be used on protected Factory ledgers."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger, prepare_durable_candidate
from research_wp_r0.test_frozen_concurrency_recovery import frozen_plan


class LegacyBridgeIsolationTests(unittest.TestCase):
    def test_sealed_ledger_rejects_legacy_bridge_before_any_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite")
            raw, digest = frozen_plan()
            ledger.bind_frozen_plan(raw, digest)
            with self.assertRaisesRegex(ValueError, "Legacy preparation prohibited"):
                prepare_durable_candidate(ledger)
            self.assertEqual(ledger.snapshot()[1][0], 0)

    def test_callback_protected_ledger_rejects_legacy_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite", require_admission=True)
            with self.assertRaisesRegex(ValueError, "Legacy preparation prohibited"):
                prepare_durable_candidate(ledger)
            self.assertEqual(ledger.snapshot()[1][0], 0)

    def test_wrong_sink_rejected(self):
        with self.assertRaisesRegex(ValueError, "Real Factory"):
            prepare_durable_candidate(object())


if __name__ == "__main__":
    unittest.main()
