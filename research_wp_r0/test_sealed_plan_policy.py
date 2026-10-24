"""Sealed ledger policy cannot be bypassed with a caller-supplied callback."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
from research_wp_r0.test_frozen_concurrency_recovery import EVENT, frozen_plan


class SealedPlanPolicyTests(unittest.TestCase):
    def test_forged_callback_cannot_admit_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite"
            raw, digest = frozen_plan()
            ledger = AttemptLedger(path)
            ledger.bind_frozen_plan(raw, digest)
            forged = dict(EVENT, candidate_id="Unplanned")
            with self.assertRaisesRegex(ValueError, "sealed frozen plan"):
                ledger.record_attempt(forged, admission=lambda *args: None)
            self.assertEqual(ledger.snapshot()[1][0], 0)

    def test_valid_direct_write_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite"
            raw, digest = frozen_plan()
            ledger = AttemptLedger(path)
            ledger.bind_frozen_plan(raw, digest)
            receipt = ledger.record_attempt(dict(EVENT), admission=lambda *args: None)
            reopened = AttemptLedger(path, expected_checkpoint=receipt)
            with self.assertRaisesRegex(ValueError, "sealed frozen plan"):
                reopened.record_attempt(dict(EVENT, strategy_digest="b" * 64),
                                        admission=lambda *args: None)
            self.assertEqual(reopened.snapshot()[1], receipt)

    def test_cannot_replace_sealed_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite")
            raw, digest = frozen_plan()
            ledger.bind_frozen_plan(raw, digest)
            ledger.bind_frozen_plan(raw, digest)
            with self.assertRaises(ValueError):
                ledger.bind_frozen_plan(raw, "0" * 64)

    def test_writer_uses_sealed_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite")
            raw, digest = frozen_plan()
            ledger.bind_frozen_plan(raw, digest)
            self.assertEqual(FrozenAttemptWriter(ledger, raw, digest).record_attempt(
                dict(EVENT))[0], 1)


if __name__ == "__main__":
    unittest.main()
