"""Offline tests for Batch 01 admission into the real frozen AttemptLedger."""
import copy
from pathlib import Path
import tempfile
import unittest

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.batch01_attempt_adapter import register_synthetic_batch_attempt
from research_wp_r0.frozen_research_plan import commit_research_plan


class Batch01AttemptAdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.plan_digest = commit_research_plan(
            "batch01", [("CandidateA", "a" * 64), ("CandidateB", "b" * 64)],
            protocol_digest="1" * 64, dataset_digest="2" * 64,
            split_digest="3" * 64, baseline_digest="4" * 64,
            metrics=["net_return"], selection_rule={"objective": "net_return"},
            cost_model={"fee_bps": 10})
        self.manifest = {
            "data_class": "SYNTHETIC_TEST", "family_id": "batch01",
            "protocol_digest": "1" * 64, "dataset_digest": "2" * 64,
            "split_digest": "3" * 64, "baseline_digest": "4" * 64,
            "evidence_status": "INSUFFICIENT_EVIDENCE",
            "candidates": [
                {"candidate_id": "CandidateA", "strategy_digest": "a" * 64},
                {"candidate_id": "CandidateB", "strategy_digest": "b" * 64}]}
        self.inputs = {
            "data_class": "SYNTHETIC_TEST", "dataset_digest": "2" * 64,
            "split_digest": "3" * 64, "protocol_digest": "1" * 64,
            "candidate_id": "CandidateA", "input_version": "V1"}

    def record(self, ledger, manifest=None, inputs=None, candidate="CandidateA"):
        return register_synthetic_batch_attempt(
            ledger, self.raw, self.plan_digest,
            self.manifest if manifest is None else manifest,
            candidate_id=candidate,
            input_commitment=self.inputs if inputs is None else inputs)

    def test_pending_is_durable_and_replay_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite"
            ledger = AttemptLedger(path)
            result = self.record(ledger)
            self.assertEqual(result["state"], "PENDING")
            self.assertFalse(result["evaluated"])
            self.assertFalse(result["external_custody_verified"])
            self.assertEqual(len(ledger.snapshot()[0]), 1)
            self.record(ledger)
            self.assertEqual(len(ledger.snapshot()[0]), 1)
            reopened = AttemptLedger(path)
            self.assertEqual(len(reopened.snapshot()[0]), 1)
            with self.assertRaises(ValueError):
                reopened.record_attempt({
                    "state": "PENDING", "family_id": "batch01",
                    "candidate_id": "CandidateB", "strategy_digest": "b" * 64,
                    "input_digest": "f" * 64})

    def test_unfrozen_candidate_and_modified_strategy_never_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite")
            for candidate, mutation in (
                ("Unknown", None),
                ("CandidateA", ("candidates", "strategy_digest"))):
                m = copy.deepcopy(self.manifest)
                if mutation:
                    m["candidates"][0]["strategy_digest"] = "f" * 64
                with self.assertRaises(ValueError):
                    self.record(ledger, m, candidate=candidate)
            self.assertEqual(ledger.snapshot()[0], [])

    def test_wrong_dataset_protocol_split_or_candidate_never_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite")
            for field in ("dataset_digest", "protocol_digest",
                          "split_digest", "candidate_id", "data_class"):
                with self.subTest(field=field):
                    inp = copy.deepcopy(self.inputs)
                    inp[field] = "other" if field in ("candidate_id", "data_class") else "f" * 64
                    with self.assertRaises(ValueError):
                        self.record(ledger, inputs=inp)
            self.assertEqual(ledger.snapshot()[0], [])

    def test_different_input_version_cannot_reuse_candidate_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "ledger.sqlite")
            self.record(ledger)
            inp = copy.deepcopy(self.inputs)
            inp["input_version"] = "V2"
            with self.assertRaises(ValueError):
                self.record(ledger, inputs=inp)
            self.assertEqual(len(ledger.snapshot()[0]), 1)


if __name__ == "__main__":
    unittest.main()
