"""Synthetic result quarantine must not create COMPLETE receipts."""
import copy
from pathlib import Path
import tempfile
import unittest

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.batch01_attempt_adapter import register_synthetic_batch_attempt
from research_wp_r0.batch01_result_quarantine import quarantine_synthetic_result
from research_wp_r0.frozen_research_plan import commit_research_plan


class ResultQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.plan_digest = commit_research_plan(
            "Batch01", [("CandidateA", "a" * 64)],
            protocol_digest="1" * 64, dataset_digest="2" * 64,
            split_digest="3" * 64, baseline_digest="4" * 64,
            metrics=["net_return"], selection_rule={"objective": "net_return"},
            cost_model={"fee_bps": 10})
        self.manifest = {
            "data_class": "SYNTHETIC_TEST", "family_id": "Batch01",
            "protocol_digest": "1" * 64, "dataset_digest": "2" * 64,
            "split_digest": "3" * 64, "baseline_digest": "4" * 64,
            "evidence_status": "INSUFFICIENT_EVIDENCE",
            "candidates": [{"candidate_id": "CandidateA", "strategy_digest": "a" * 64}]}
        self.inputs = {
            "data_class": "SYNTHETIC_TEST", "dataset_digest": "2" * 64,
            "split_digest": "3" * 64, "protocol_digest": "1" * 64,
            "candidate_id": "CandidateA", "input_version": "V1"}

    def test_quarantine_never_completes_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            admitted = register_synthetic_batch_attempt(
                ledger, self.raw, self.plan_digest, self.manifest,
                candidate_id="CandidateA", input_commitment=self.inputs)
            claim = {
                "data_class": "SYNTHETIC_TEST", "candidate_id": "CandidateA",
                "input_digest": admitted["input_digest"],
                "strategy_digest": "a" * 64, "plan_digest": self.plan_digest,
                "manifest_digest": admitted_manifest_digest(self.manifest),
                "result_digest": "f" * 64, "claim_version": "V1"}
            original, checkpoint = ledger.snapshot()
            result = quarantine_synthetic_result(
                ledger, self.raw, self.plan_digest, self.manifest, claim)
            self.assertEqual(result["disposition"], "QUARANTINED_NOT_EVALUATED")
            self.assertFalse(result["result_verified"])
            self.assertFalse(result["ledger_complete_written"])
            self.assertEqual(ledger.snapshot(), (original, checkpoint))
            for field, bad in (("candidate_id", "Unknown"),
                               ("input_digest", "0" * 64),
                               ("strategy_digest", "0" * 64),
                               ("plan_digest", "0" * 64),
                               ("manifest_digest", "0" * 64),
                               ("data_class", "HISTORICAL_RECORDED")):
                with self.subTest(field=field):
                    changed = copy.deepcopy(claim)
                    changed[field] = bad
                    with self.assertRaises(ValueError):
                        quarantine_synthetic_result(
                            ledger, self.raw, self.plan_digest,
                            self.manifest, changed)
            self.assertEqual(ledger.snapshot(), (original, checkpoint))

    def test_missing_pending_attempt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite")
            claim = {
                "data_class": "SYNTHETIC_TEST", "candidate_id": "CandidateA",
                "input_digest": "0" * 64, "strategy_digest": "a" * 64,
                "plan_digest": self.plan_digest,
                "manifest_digest": admitted_manifest_digest(self.manifest),
                "result_digest": "f" * 64, "claim_version": "V1"}
            with self.assertRaises(ValueError):
                quarantine_synthetic_result(
                    ledger, self.raw, self.plan_digest, self.manifest, claim)


def admitted_manifest_digest(manifest):
    from research_wp_r0.strategy_definition import digest
    return digest(manifest)


if __name__ == "__main__":
    unittest.main()
