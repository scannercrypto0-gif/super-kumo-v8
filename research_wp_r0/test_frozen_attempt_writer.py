"""Tests for frozen-plan pre-write admission against the actual ledger."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
from research_wp_r0.frozen_research_plan import commit_research_plan


def plan():
    return commit_research_plan(
        "Family1", [("Candidate1", "a" * 64)],
        protocol_digest="b" * 64, dataset_digest="c" * 64,
        split_digest="d" * 64, baseline_digest="e" * 64,
        metrics=["net_return"], selection_rule={"objective": "net_return"},
        cost_model={"fee_bps": 10})


class AdmissionTests(unittest.TestCase):
    def test_valid_pending_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = plan()
            writer = FrozenAttemptWriter(ledger, raw, commitment)
            writer.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Candidate1",
                                   "input_digest": "f" * 64, "strategy_digest": "a" * 64})
            self.assertEqual(len(ledger.snapshot()[0]), 1)

    def test_unknown_candidate_never_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = plan()
            writer = FrozenAttemptWriter(ledger, raw, commitment)
            with self.assertRaises(ValueError):
                writer.record_attempt({"state": "PENDING", "family_id": "Family1",
                                       "candidate_id": "Unplanned",
                                       "input_digest": "f" * 64, "strategy_digest": "a" * 64})
            self.assertEqual(ledger.snapshot()[0], [])

    def test_wrong_strategy_never_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            raw, commitment = plan()
            writer = FrozenAttemptWriter(ledger, raw, commitment)
            with self.assertRaises(ValueError):
                writer.record_attempt({"state": "PENDING", "family_id": "Family1",
                                       "candidate_id": "Candidate1",
                                       "input_digest": "f" * 64, "strategy_digest": "0" * 64})
            self.assertEqual(ledger.snapshot()[0], [])

    def test_existing_unplanned_attempt_blocks_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            ledger.record_attempt({"state": "PENDING", "family_id": "Family1",
                                   "candidate_id": "Unplanned",
                                   "input_digest": "f" * 64, "strategy_digest": "a" * 64})
            raw, commitment = plan()
            with self.assertRaises(ValueError):
                FrozenAttemptWriter(ledger, raw, commitment)


if __name__ == "__main__":
    unittest.main()
