"""Concurrency and recovery checks against the real Factory SQLite ledger."""
import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
from research_wp_r0.frozen_research_plan import commit_research_plan


def frozen_plan():
    return commit_research_plan(
        "ConcurrentFamily", [("CandidateA", "a" * 64)],
        protocol_digest="b" * 64, dataset_digest="c" * 64,
        split_digest="d" * 64, baseline_digest="e" * 64,
        metrics=["net_return"], selection_rule={"objective": "net_return"},
        cost_model={"fee_bps": 10})


EVENT = {"state": "PENDING", "family_id": "ConcurrentFamily",
         "candidate_id": "CandidateA", "input_digest": "f" * 64,
         "strategy_digest": "a" * 64}


class ConcurrencyRecoveryTests(unittest.TestCase):
    def test_concurrent_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "attempts.sqlite"
            raw, commitment = frozen_plan()
            AttemptLedger(path, require_admission=True)

            def submit(_):
                writer = FrozenAttemptWriter(AttemptLedger(path), raw, commitment)
                return writer.record_attempt(dict(EVENT))

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(submit, range(4)))
            self.assertEqual(len(results), 4)
            events, checkpoint = AttemptLedger(path).snapshot()
            self.assertEqual(len(events), 1)
            self.assertEqual(checkpoint[0], 1)

    def test_reopen_rejects_unguarded_write_and_retains_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "attempts.sqlite"
            raw, commitment = frozen_plan()
            first = AttemptLedger(path, require_admission=True)
            receipt = FrozenAttemptWriter(first, raw, commitment).record_attempt(dict(EVENT))
            restarted = AttemptLedger(path, expected_checkpoint=receipt)
            with self.assertRaisesRegex(ValueError, "admission"):
                restarted.record_attempt(dict(EVENT))
            self.assertEqual(restarted.snapshot()[1], receipt)
            self.assertEqual(len(restarted.snapshot()[0]), 1)


if __name__ == "__main__":
    unittest.main()
