"""Focused Core provenance to Factory RAW market adapter coordination.

These use deliberately synthetic witnesses; never evidence of an operational
source publication clock, immutable pre-F3 freeze or external durable anchor.
"""
import unittest

from research_wp_r0.aql_f1_provenance_v1 import make_provenance_verifier
from research_wp_r0.aql_w1_f1_prospective_consumer import project_authenticated_market_f1_slots
from tests.test_aql_f1_provenance_v1 import evidence_for
from tests.test_aql_w1_market_window_adapter import sample


class PinnedCoreMarketBoundary(unittest.TestCase):
    def project(self, *, source=True, freeze=True, anchor=True, market=True):
        plan, record, registry, raw, receipt = sample()
        evidence = evidence_for(record)
        original_verifier = make_provenance_verifier(
            registry, lambda _: evidence,
            source_attestor=(lambda _: True) if source else None,
            freeze_attestor=(lambda _: True) if freeze else None,
            durable_anchor_verifier=(lambda _: True) if anchor else None,
        )
        report = project_authenticated_market_f1_slots(
            [plan], [record], raw_by_pair={plan["pair_id"]: raw},
            receipt_by_pair={plan["pair_id"]: receipt},
            indicator_registry=registry,
            proof_verifier=original_verifier,
            verify_raw_receipt=(lambda _: True) if market else None)
        return report

    def test_missing_independent_source_witness_never_recorded(self):
        report = self.project(source=False)
        self.assertEqual(report["capture_status_counts"]["UNVERIFIED"], 1)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(r["max_favorable"] is None and r["max_adverse"] is None
                            for r in report["outcomes"]))

    def test_missing_freeze_witness_never_recorded(self):
        report = self.project(freeze=False)
        self.assertEqual(report["capture_status_counts"]["UNVERIFIED"], 1)

    def test_missing_anchor_witness_never_recorded(self):
        report = self.project(anchor=False)
        self.assertEqual(report["capture_status_counts"]["UNVERIFIED"], 1)

    def test_missing_market_witness_does_not_produce_signed(self):
        report = self.project(market=False)
        self.assertTrue(all(r["max_favorable"] is None and r["max_adverse"] is None
                            for r in report["outcomes"]))
        self.assertEqual(report["outcome_rows"], 6)

    def test_synthetic_positive_still_not_operational_proof(self):
        report = self.project()
        self.assertEqual(report["capture_status_counts"],
                         {"MISSING_CAPTURE": 1, "RECORDED": 1})
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(report["proof_verifier_supplied"])
        self.assertTrue(report["market_receipt_verifier_supplied"])
        self.assertFalse(report["operational_pit_and_custody_proven"])


if __name__ == "__main__":
    unittest.main()
