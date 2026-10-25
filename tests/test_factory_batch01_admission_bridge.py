"""Bounded, offline, adversarial checks for synthetic Batch 01 provenance."""
import copy
import unittest

from research_wp_r0.batch01_admission_bridge import check_synthetic_batch_manifest
from research_wp_r0.frozen_research_plan import commit_research_plan
from research_wp_r0.strategy_definition import digest


class Batch01AdmissionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [("candidateA", "a" * 64), ("candidateB", "b" * 64)]
        self.fields = dict(protocol_digest="1" * 64, dataset_digest="2" * 64,
                           split_digest="3" * 64, baseline_digest="4" * 64)
        self.raw, self.plan_digest = commit_research_plan(
            "batch01", self.candidates, metrics=["return_net"],
            selection_rule={"rule": "predeclared"}, cost_model={"fee_bps": 10},
            **self.fields)
        self.manifest = dict(data_class="SYNTHETIC_TEST", family_id="batch01",
                             candidates=[dict(candidate_id=i, strategy_digest=h)
                                         for i, h in self.candidates],
                             evidence_status="INSUFFICIENT_EVIDENCE", **self.fields)

    def check(self, manifest=None, raw=None, plan_digest=None):
        return check_synthetic_batch_manifest(
            self.raw if raw is None else raw,
            self.plan_digest if plan_digest is None else plan_digest,
            self.manifest if manifest is None else manifest)

    def test_explicitly_unverified_and_never_admitted(self):
        result = self.check()
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["evaluated"])
        self.assertFalse(result["external_custody_verified"])
        self.assertFalse(result["holdout_opened"])

    def test_each_frozen_identity_rejected_if_modified(self):
        for field in ("family_id", "protocol_digest", "dataset_digest",
                      "split_digest", "baseline_digest"):
            with self.subTest(field=field):
                m = copy.deepcopy(self.manifest)
                m[field] = "other" if field == "family_id" else "f" * 64
                with self.assertRaises(ValueError):
                    self.check(m)

    def test_candidate_tampering_and_duplicate_rejected(self):
        for bad in (
            [dict(candidate_id="candidateA", strategy_digest="f" * 64),
             self.manifest["candidates"][1]],
            [self.manifest["candidates"][0], self.manifest["candidates"][0]],
            [self.manifest["candidates"][0]],
        ):
            m = copy.deepcopy(self.manifest)
            m["candidates"] = bad
            with self.assertRaises(ValueError):
                self.check(m)

    def test_non_synthetic_promotion_and_unknown_fields_rejected(self):
        for field, value in (("data_class", "HISTORICAL_RECORDED"),
                             ("evidence_status", "ACCEPTED"),
                             ("new_field", True)):
            m = copy.deepcopy(self.manifest)
            m[field] = value
            with self.assertRaises(ValueError):
                self.check(m)

    def test_plan_digest_mismatch_and_changed_plan_rejected(self):
        with self.assertRaises(ValueError):
            self.check(plan_digest="0" * 64)
        with self.assertRaises(ValueError):
            self.check(raw=self.raw + b" ")

    def test_mutating_input_does_not_change_returned_receipt(self):
        result = self.check()
        self.manifest["candidates"][0]["strategy_digest"] = "f" * 64
        self.assertEqual(result["candidate_count"], 2)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
