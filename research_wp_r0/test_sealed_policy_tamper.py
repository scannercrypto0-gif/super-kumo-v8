"""Security regression: sealed plan remains authoritative after policy downgrade."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.test_frozen_concurrency_recovery import EVENT, frozen_plan


class SealedPolicyTamperTests(unittest.TestCase):
    def test_sealed_plan_still_rejects_unplanned_event_if_callback_policy_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite"
            raw, digest = frozen_plan()
            ledger = AttemptLedger(path)
            ledger.bind_frozen_plan(raw, digest)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE ledger_policy SET require_admission=0 WHERE id=1")
            with self.assertRaisesRegex(ValueError, "sealed frozen plan"):
                AttemptLedger(path).record_attempt(dict(EVENT, candidate_id="Unplanned"),
                                                   admission=lambda *_: None)
            self.assertEqual(AttemptLedger(path).snapshot()[1][0], 0)

    def test_cannot_enroll_after_unprotected_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite"
            raw, digest = frozen_plan()
            ledger = AttemptLedger(path)
            ledger.record_attempt(dict(EVENT))
            with self.assertRaisesRegex(ValueError, "empty ledger"):
                ledger.bind_frozen_plan(raw, digest)
            self.assertEqual(ledger.snapshot()[1][0], 1)


if __name__ == "__main__":
    unittest.main()
