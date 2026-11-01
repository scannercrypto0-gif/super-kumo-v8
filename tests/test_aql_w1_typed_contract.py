"""Focused contract seam regressions; does not rerun the prior 14 Core tests."""
import unittest
from dataclasses import replace
from research_wp_r0.aql_w1_typed_contract import F1SelectionV1, F3EffectV1, EvidenceError, reconcile_typed


def fixture():
    t = 1704067200000
    envelope = dict(trial_id="trial", opportunity_id="opp", producer_event_id="producer",
                    envelope_sha256="envelope", run_manifest_sha256="manifest",
                    decision_cutoff_ms=t, decision_ms=t+2000,
                    prefix_start_ms=t-18000000, prefix_end_exclusive_ms=t,
                    prefix_bar_checksums_sha256="prefix", input_disposition="EVALUABLE_RETROSPECTIVE",
                    strategy_id="strategy", dataset_version=1, feature_policy_version="v1",
                    gap_inventory_sha256="gap", correction_lineage_sha256="lineage")
    selection = F1SelectionV1(
        **envelope, f1_signal_state="ARMED", f1_reason_code=None, direction=None,
        predecision_eligibility="NOT_ESTABLISHED", eligibility_evidence_ref=None,
        source_version="archive-v1", source_bytes_sha256="sourcehash",
        selection_policy_version="policy-v1", correction_generation="original",
        evidence_class="RECONSTRUCTED_RETROSPECTIVE_NON_PIT", receipt_sha256=None)
    return envelope, selection


class TypedContractTests(unittest.TestCase):
    def test_f1_armed_is_not_f3_rejected(self):
        envelope, selection = fixture()
        snapshot, = reconcile_typed([envelope], [selection])
        self.assertEqual(snapshot.signal_state, "ARMED")
        self.assertEqual(snapshot.eligibility, "NOT_ESTABLISHED")
        with self.assertRaises(EvidenceError):
            replace(selection, f1_signal_state="REJECTED")
        final_effect = F3EffectV1("trial", "opp", "producer", "envelope", "REJECTED",
                                  "POSITION_ALREADY_OPEN_AT_DECISION", None, "receipt",
                                  "archive-v1", "MODELED_NON_EXECUTABLE")
        with self.assertRaises(EvidenceError):
            reconcile_typed([envelope], [final_effect])

    def test_original_f1_absence_is_not_backfilled(self):
        envelope, _ = fixture()
        with self.assertRaisesRegex(EvidenceError, "NOT_RECORDED_IN_P0"):
            reconcile_typed([envelope], [])

    def test_reconstructed_eligibility_cannot_be_upgraded(self):
        _, selection = fixture()
        with self.assertRaises(EvidenceError):
            replace(selection, predecision_eligibility="YES", eligibility_evidence_ref="inferred")

    def test_exact_identity_and_provenance_mismatch(self):
        envelope, selection = fixture()
        for field in ("envelope_sha256", "run_manifest_sha256",
                      "decision_cutoff_ms", "prefix_bar_checksums_sha256", "decision_ms"):
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                reconcile_typed([{**envelope, field: "tampered"}], [selection])

    def test_duplicate_selection_is_rejected(self):
        envelope, selection = fixture()
        with self.assertRaises(EvidenceError):
            reconcile_typed([envelope, envelope], [selection, selection])

    def test_recorded_f1_requires_receipt(self):
        envelope, selection = fixture()
        with self.assertRaises(EvidenceError):
            replace(selection, evidence_class="RECORDED_F1_PREDECISION")
        recorded = replace(selection, evidence_class="RECORDED_F1_PREDECISION",
                           receipt_sha256="original-receipt", predecision_eligibility="YES",
                           eligibility_evidence_ref="original-evidence")
        self.assertEqual(reconcile_typed([envelope], [recorded])[0].eligibility, "YES")


if __name__ == "__main__":
    unittest.main()
