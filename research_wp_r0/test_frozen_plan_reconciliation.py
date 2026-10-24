"""Focused tests using the real Factory AttemptLedger, no mocks."""
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_plan_reconciliation import frozen_commitment, reconcile_plan


class Definition:
    digest = "a" * 64


class FrozenPlanTests(unittest.TestCase):
    def test_pending_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = frozen_commitment("Family1", [("Candidate1", Definition())])
            self.assertEqual(reconcile_plan(raw, commitment, ledger)["missing"], ["Candidate1"])
            ledger.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Candidate1",
                                   "input_digest": "b" * 64, "strategy_digest": "a" * 64})
            report = reconcile_plan(raw, commitment, ledger)
            self.assertEqual(report["pending"], ["Candidate1"])
            self.assertEqual(report["evaluation_status"], "NOT_EVALUATED")
            self.assertEqual(report["checkpoint"], ledger.snapshot()[1])

    def test_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = frozen_commitment("Family1", [("Candidate1", Definition())])
            with self.assertRaises(ValueError):
                reconcile_plan(raw, "0" * 64, ledger)
            ledger.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Unexpected",
                                   "input_digest": "b" * 64, "strategy_digest": "a" * 64})
            with self.assertRaises(ValueError):
                reconcile_plan(raw, commitment, ledger)

    def test_duplicate_candidates_rejected(self):
        with self.assertRaises(ValueError):
            frozen_commitment("Family1", [("Candidate1", Definition()),
                                           ("Candidate1", Definition())])


if __name__ == "__main__":
    unittest.main()
