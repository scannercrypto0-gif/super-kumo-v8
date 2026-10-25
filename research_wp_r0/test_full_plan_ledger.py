"""End-to-end frozen full research plan to actual durable attempt ledger."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_research_plan import commit_research_plan
from research_wp_r0.frozen_plan_reconciliation import reconcile_full_research_plan


def plan():
    return commit_research_plan(
        "Family1", [("Candidate1", "a" * 64)],
        protocol_digest="b" * 64, dataset_digest="c" * 64,
        split_digest="d" * 64, baseline_digest="e" * 64,
        metrics=["net_return"], selection_rule={"objective": "net_return"},
        cost_model={"fee_bps": 10, "slippage_bps": 5})


class FullPlanLedgerTests(unittest.TestCase):
    def test_real_ledger_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = plan()
            self.assertEqual(reconcile_full_research_plan(
                raw, commitment, ledger)["missing"], ["Candidate1"])
            ledger.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Candidate1", "input_digest": "f" * 64,
                                   "strategy_digest": "a" * 64})
            result = reconcile_full_research_plan(raw, commitment, ledger)
            self.assertEqual(result["pending"], ["Candidate1"])
            self.assertEqual(result["evaluation_status"], "NOT_EVALUATED")

    def test_unknown_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = plan()
            ledger.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Unplanned", "input_digest": "f" * 64,
                                   "strategy_digest": "a" * 64})
            with self.assertRaises(ValueError):
                reconcile_full_research_plan(raw, commitment, ledger)

    def test_wrong_strategy_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = plan()
            ledger.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Candidate1", "input_digest": "f" * 64,
                                   "strategy_digest": "0" * 64})
            with self.assertRaises(ValueError):
                reconcile_full_research_plan(raw, commitment, ledger)


if __name__ == "__main__":
    unittest.main()
