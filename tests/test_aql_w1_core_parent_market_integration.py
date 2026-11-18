"""Focused Factory parent source bridge ↔ Core RAW parent witness contract.

All trust callbacks here are synthetic; no live independent issuer or clock.
"""
import hashlib
import unittest

from research_wp_r0.aql_f1_decision_capture_v1 import digest
from research_wp_r0.aql_f1_parent_witness_v1 import (
    make_parent_bound_provenance_verifier, validate_parent_binding,
)
from research_wp_r0.aql_w1_f1_prospective_consumer import project_parent_authenticated_f1_slots
from tests.test_aql_f1_provenance_v1 import evidence_for
from tests.test_aql_w1_raw_parent_bridge import fixture


def core_evidence(record, parent, manifest):
    original = evidence_for(record)
    manifest_bytes = __import__("json").dumps(
        manifest, sort_keys=True, separators=(",", ":")).encode()
    binding = {
        "schema_version": "aql.f1-raw-parent-binding.v1",
        "parent_source_id": manifest["vendor"],
        "parent_source_version": manifest["format_version"],
        "parent_source_bytes_sha256": hashlib.sha256(parent).hexdigest(),
        "parent_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        **{key: record[key] for key in (
            "source_id", "source_version", "source_bytes_sha256",
            "correction_generation", "correction_lineage_sha256")},
        "source_published_at_ms": record["decision_cutoff_ms"],
        "correction_published_at_ms": record["decision_cutoff_ms"],
        "source_finalized_at_ms": record["decision_cutoff_ms"] - 1,
        "parent_receipt_ref": "synthetic-independent-parent-receipt",
    }
    binding["parent_binding_sha256"] = digest(binding)
    original.update(raw_parent_binding=binding, raw_parent_bytes=parent,
                    raw_parent_manifest_bytes=manifest_bytes)
    return original


class CoreFactoryOriginalParent(unittest.TestCase):
    def projection(self, *, parent_witness=True, source_witness=True,
                   market_parent=True, anchor=True):
        plan, record, registry, parent, manifest, derived, lineage = fixture()
        evidence = core_evidence(record, parent, manifest)
        verifier = make_parent_bound_provenance_verifier(
            registry, lambda _: evidence,
            source_attestor=(lambda _: True) if source_witness else None,
            freeze_attestor=lambda _: True,
            durable_anchor_verifier=(lambda _: True) if anchor else None,
            parent_witness=(lambda _: True) if parent_witness else None)
        result = project_parent_authenticated_f1_slots(
            [plan], [record], parent_bytes_by_pair={plan["pair_id"]: parent},
            manifest_by_pair={plan["pair_id"]: manifest},
            derived_bars_by_pair={plan["pair_id"]: derived},
            derived_evidence_by_pair={plan["pair_id"]: lineage},
            indicator_registry=registry,
            verify_parent_manifest=(lambda meta, data: True) if market_parent else None,
            verify_derivation=lambda lineage, parent, view: True,
            verify_external_receipt=lambda lineage, meta: True,
            proof_verifier=verifier,
        )
        return result, record, registry, parent, manifest, evidence

    def test_different_f1_source_and_raw_parent_hash_valid_synthetic(self):
        report, record, _, parent, _, _ = self.projection()
        self.assertNotEqual(record["source_bytes_sha256"],
                            hashlib.sha256(parent).hexdigest())
        self.assertEqual(report["capture_status_counts"],
                         {"MISSING_CAPTURE": 1, "RECORDED": 1})
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertFalse(report["operational_pit_and_custody_proven"])

    def test_missing_external_parent_issuer_unverified(self):
        report, *_ = self.projection(parent_witness=False)
        self.assertEqual(report["capture_status_counts"]["UNVERIFIED"], 1)
        self.assertTrue(all(row["max_favorable"] is None for row in report["outcomes"]))

    def test_missing_core_anchor_unverified(self):
        report, *_ = self.projection(anchor=False)
        self.assertEqual(report["capture_status_counts"]["UNVERIFIED"], 1)

    def test_market_receipt_does_not_replace_core_parent_witness(self):
        report, *_ = self.projection(market_parent=True, parent_witness=False)
        self.assertEqual(report["capture_status_counts"]["UNVERIFIED"], 1)

    def test_core_parent_witness_does_not_replace_market_receipt(self):
        report, *_ = self.projection(market_parent=False)
        self.assertTrue(all(row["max_favorable"] is None for row in report["outcomes"]))
        self.assertEqual(report["outcome_rows"], 6)

    def test_core_binding_rejects_tampered_parent(self):
        _, record, registry, parent, manifest, evidence = self.projection()
        self.assertFalse(validate_parent_binding(
            record, evidence["raw_parent_binding"],
            parent_bytes=parent+b"x",
            parent_manifest_bytes=evidence["raw_parent_manifest_bytes"],
            parent_witness=lambda _: True))

    def test_core_binding_rejects_late_parent_source(self):
        _, record, registry, parent, manifest, evidence = self.projection()
        modified = dict(evidence["raw_parent_binding"])
        modified["source_published_at_ms"] = record["decision_cutoff_ms"] + 1
        modified["parent_binding_sha256"] = digest({
            k: v for k, v in modified.items() if k != "parent_binding_sha256"})
        self.assertFalse(validate_parent_binding(
            record, modified, parent_bytes=parent,
            parent_manifest_bytes=evidence["raw_parent_manifest_bytes"],
            parent_witness=lambda _: True))


if __name__ == "__main__":
    unittest.main()
