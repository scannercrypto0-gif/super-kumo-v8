"""Exact Core #216 -> Factory #209 focused integration, synthetic only."""
import copy
import unittest

from research_wp_r0.aql_f1_decision_capture_v1 import digest, hash_f1, validate_f1
from research_wp_r0.aql_w1_f1_prospective_consumer import project_core_verified_f1_slots
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError
from tests.test_aql_f1_decision_capture_v1 import fixture

def setup():
    record, registry = fixture()
    identity = record["c2_identity"]
    plan = {
        "pair_id": record["pair_id"], "c2_identity": identity,
        "experiment_plan_sha256": record["experiment_plan_sha256"],
        "decision_cutoff_ms": record["decision_cutoff_ms"],
        "source_version": record["source_version"],
        "source_bytes_sha256": record["source_bytes_sha256"],
        "correction_generation": record["correction_generation"],
    }
    return plan, record, registry

class CoreFactoryIntegration(unittest.TestCase):
    def project(self, records=None, proof=None, windows=()):
        plan, original, registry = setup()
        if records is None:
            records = [original]
        return project_core_verified_f1_slots(
            [plan], records, windows, indicator_registry=registry,
            proof_verifier=proof,
        )

    def test_unanchored_is_unverified_and_missing_arm_retained(self):
        report = self.project()
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertEqual(report["capture_status_counts"],
                         {"UNVERIFIED": 1, "MISSING_CAPTURE": 1})
        self.assertTrue(all(row["max_favorable"] is None for row in report["outcomes"]))

    def test_trusted_synthetic_verifier_does_not_infer_market_proof(self):
        report = self.project(proof=lambda _: True)
        self.assertEqual(report["capture_status_counts"],
                         {"RECORDED": 1, "MISSING_CAPTURE": 1})
        self.assertTrue(all(row["max_adverse"] is None for row in report["outcomes"]))

    def test_bad_digest_is_quarantined(self):
        _, record, _ = setup()
        record = copy.deepcopy(record)
        record["f1_record_sha256"] = "f" * 64
        report = self.project([record], proof=lambda _: True)
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)

    def test_conflicting_candidates_are_quarantined(self):
        _, record, _ = setup()
        changed = copy.deepcopy(record)
        changed["producer_sequence"] += 1
        report = self.project([record, changed], proof=lambda _: True)
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)

    def test_identical_replay_idempotent(self):
        _, record, _ = setup()
        report = self.project([record, copy.deepcopy(record)], proof=lambda _: True)
        self.assertEqual(report["capture_status_counts"]["RECORDED"], 1)

    def test_forged_pair_is_rejected(self):
        plan, record, registry = setup()
        plan["pair_id"] = "f" * 64
        with self.assertRaises(EvidenceError):
            project_core_verified_f1_slots([plan], [record], indicator_registry=registry)

    def test_late_indicator_quarantined(self):
        _, record, _ = setup()
        record = copy.deepcopy(record)
        record["indicators"][0]["available_at_ms"] = record["decision_cutoff_ms"] + 1
        report = self.project([record], proof=lambda _: True)
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)

    def test_rehashed_valid_source_mismatch_stays_quarantined(self):
        # Core-valid JCS/hash is insufficient if Factory preregistered a
        # different source vintage; even a synthetic lambda-True verifier
        # must not promote the candidate to RECORDED.
        plan, record, registry = setup()
        changed = copy.deepcopy(record)
        changed["source_version"] = "another-valid-vintage"
        changed["f1_record_sha256"] = hash_f1(changed)
        validate_f1(changed, registry)
        report = project_core_verified_f1_slots(
            [plan], [changed], indicator_registry=registry,
            proof_verifier=lambda _: True)
        self.assertEqual(report["capture_status_counts"],
                         {"QUARANTINED": 1, "MISSING_CAPTURE": 1})
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(r["max_favorable"] is None and r["max_adverse"] is None
                            for r in report["outcomes"]))

    def test_rehashed_valid_cutoff_mismatch_stays_quarantined(self):
        plan, record, registry = setup()
        changed = copy.deepcopy(record)
        changed["decision_cutoff_ms"] += 900000
        changed["f1_record_sha256"] = hash_f1(changed)
        validate_f1(changed, registry)
        report = project_core_verified_f1_slots(
            [plan], [changed], indicator_registry=registry,
            proof_verifier=lambda _: True)
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)

    def test_same_source_positive_synthetic_control(self):
        report = self.project(proof=lambda _: True)
        self.assertEqual(report["capture_status_counts"],
                         {"RECORDED": 1, "MISSING_CAPTURE": 1})
        self.assertTrue(report["proof_verifier_supplied"])
        self.assertNotIn("independent_pit_proof", report)

    def test_orphan_rejected(self):
        _, record, _ = setup()
        record = copy.deepcopy(record)
        record["arm"] = "UNSCHEDULED"
        with self.assertRaises(EvidenceError):
            self.project([record])

if __name__ == "__main__":
    unittest.main()
