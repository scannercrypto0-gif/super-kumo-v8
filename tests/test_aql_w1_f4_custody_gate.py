"""Synthetic-only negative tests. Never assert these bytes are original P0 evidence."""
import unittest
from dataclasses import replace
from hashlib import sha256

from research_wp_r0.aql_w1_f4_custody_gate import F4Custody, verify_f3_custody
from research_wp_r0.aql_w1_factory_research_consumer import (describe_original_p0_f3, describe_original_p0_f3_effects)
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError
from research_wp_r0.aql_w1_typed_contract import F3EffectV1


def h(data):
    return sha256(data).hexdigest()


class CustodyGateTest(unittest.TestCase):
    def setUp(self):
        self.receipt = b"synthetic-f4-receipt"
        self.ack = b"synthetic-c2-ack"
        self.effect = F3EffectV1("trial", "opp", "producer", "envelope",
                                 "REJECTED", "reason", None,
                                 h(self.receipt), "source-v1",
                                 "MODELED_NON_EXECUTABLE")
        self.key = ("trial", "opp", "producer", "envelope")
        self.custody = F4Custody(
            self.receipt, self.ack, h(self.receipt), h(self.ack),
            *self.key, "source-v1", h(b"source"),
            "policy-v1", "original", h(b"manifest"))
        self.source = {name: getattr(self.custody, name) for name in (
            "source_version", "source_bytes_sha256", "policy_version",
            "correction_generation", "run_manifest_sha256",
            "expected_receipt_sha256", "expected_ack_sha256")}

    def verify(self, effect=None, custody=None, source=None):
        return verify_f3_custody(
            [effect if effect is not None else self.effect],
            {self.key: custody if custody is not None else self.custody},
            {self.key: source if source is not None else self.source})

    def test_synthetic_positive_structural_gate(self):
        self.assertTrue(self.verify())

    def test_tampered_original_receipt_bytes(self):
        with self.assertRaises(EvidenceError):
            self.verify(custody=replace(self.custody, receipt_bytes=b"changed"))

    def test_tampered_ack_bytes(self):
        with self.assertRaises(EvidenceError):
            self.verify(custody=replace(self.custody, ack_bytes=b"changed"))

    def test_wrong_receipt_link(self):
        with self.assertRaises(EvidenceError):
            self.verify(effect=replace(self.effect, consumer_receipt_sha256=h(b"wrong")))

    def test_wrong_source_and_correction(self):
        for field, value in (("source_version", "other"),
                             ("correction_generation", "correction-2"),
                             ("expected_ack_sha256", h(b"other"))):
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                self.verify(source={**self.source, field: value})

    def test_forged_f1_selection(self):
        with self.assertRaises(EvidenceError):
            self.verify(effect=replace(self.effect, f1_selection_sha256=h(b"forged")))

    def test_missing_custody_fails_closed(self):
        with self.assertRaises(EvidenceError):
            verify_f3_custody([self.effect], {}, {self.key: self.source})

    def test_original_f3_only_no_f1_inference(self):
        report = describe_original_p0_f3_effects([self.effect], expected_total=1)
        self.assertEqual(report["original_f1_status"], "NOT_RECORDED_IN_P0")
        self.assertEqual(report["entry_eligibility"], "NOT_ESTABLISHED")
        self.assertEqual(report["f3_final_effects"], {"REJECTED": 1})
        with self.assertRaises(EvidenceError):
            describe_original_p0_f3_effects([self.effect], expected_total=653)

    def test_duplicate_effect_fails_closed(self):
        with self.assertRaises(EvidenceError):
            verify_f3_custody([self.effect, self.effect],
                              {self.key: self.custody}, {self.key: self.source})


class OriginalP0DescriptiveTest(unittest.TestCase):
    def test_original_f3_descriptive_without_f1(self):
        values = ["NO_SIGNAL"] * 616 + ["REJECTED"] * 27 + ["TRIGGERED"] * 10
        report = describe_original_p0_f3(values)
        self.assertEqual(report["f3_final_effects"],
                         {"NO_SIGNAL": 616, "REJECTED": 27, "TRIGGERED": 10})
        self.assertEqual(report["original_f1_status"], "NOT_RECORDED_IN_P0")
        self.assertEqual(report["entry_eligibility"], "NOT_ESTABLISHED")
        self.assertFalse(report["original_f4_ack_authenticated"])

    def test_descriptive_denominator_fail_closed(self):
        with self.assertRaises(EvidenceError):
            describe_original_p0_f3(["NO_SIGNAL"] * 652)


if __name__ == "__main__":
    unittest.main()
