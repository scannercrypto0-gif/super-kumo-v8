"""Focused synthetic RAW parent binding tests; not live source evidence."""
import copy
import hashlib
import unittest

from research_wp_r0.aql_f1_decision_capture_v1 import digest, hash_f1, status_slots
from research_wp_r0.aql_f1_parent_witness_v1 import (
    make_parent_bound_provenance_verifier, validate_parent_binding)
from tests.test_aql_f1_decision_capture_v1 import fixture
from tests.test_aql_f1_provenance_v1 import evidence_for


def bundle(record):
    evidence = evidence_for(record)
    parent = b"unchanged-original-raw-parent-bytes"
    manifest = b"unchanged-raw-parent-manifest"
    binding = {
        "schema_version": "aql.f1-raw-parent-binding.v1",
        "parent_source_id": "external-source",
        "parent_source_version": "real-original-v1",
        "parent_source_bytes_sha256": hashlib.sha256(parent).hexdigest(),
        "parent_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        **{key: record[key] for key in (
            "source_id", "source_version", "source_bytes_sha256",
            "correction_generation", "correction_lineage_sha256")},
        "source_published_at_ms": record["decision_cutoff_ms"],
        "correction_published_at_ms": record["decision_cutoff_ms"],
        "source_finalized_at_ms": record["decision_cutoff_ms"] - 1,
        "parent_receipt_ref": "externally-stored-immutable-parent-receipt",
    }
    binding["parent_binding_sha256"] = digest(binding)
    evidence.update(raw_parent_bytes=parent, raw_parent_manifest_bytes=manifest,
                    raw_parent_binding=binding)
    return evidence


def verifier(registry, evidence, *, parent_callback=True):
    return make_parent_bound_provenance_verifier(
        registry, lambda _: evidence,
        source_attestor=lambda _: True,
        freeze_attestor=lambda _: True,
        durable_anchor_verifier=lambda _: True,
        parent_witness=(lambda _: True) if parent_callback else None,
    )


class ParentWitnessTests(unittest.TestCase):
    def status(self, rec, reg, evidence, *, parent_callback=True):
        rows = status_slots(
            [rec["c2_identity"]], rec["experiment_plan_sha256"],
            {(rec["pair_id"], rec["arm"]): [rec]}, reg,
            verifier(reg, evidence, parent_callback=parent_callback),
        )
        return rows[0]["capture_status"]

    def test_synthetic_parent_positive_and_no_external_parent_witness(self):
        rec, reg = fixture()
        e = bundle(rec)
        self.assertEqual(self.status(rec, reg, e), "RECORDED")
        self.assertEqual(self.status(rec, reg, e, parent_callback=False), "UNVERIFIED")

    def test_tampered_parent_bytes_fail_closed(self):
        rec, reg = fixture()
        e = bundle(rec)
        e["raw_parent_bytes"] += b"corrupt"
        self.assertEqual(self.status(rec, reg, e), "UNVERIFIED")

    def test_missing_parent_manifest_fail_closed(self):
        rec, reg = fixture()
        e = bundle(rec)
        e["raw_parent_manifest_bytes"] = None
        self.assertEqual(self.status(rec, reg, e), "UNVERIFIED")

    def test_rehashed_wrong_correction_generation(self):
        rec, reg = fixture()
        e = bundle(rec)
        e["raw_parent_binding"]["correction_generation"] = "other-correction"
        e["raw_parent_binding"]["parent_binding_sha256"] = digest({
            k:v for k,v in e["raw_parent_binding"].items() if k != "parent_binding_sha256"})
        self.assertEqual(self.status(rec, reg, e), "UNVERIFIED")

    def test_late_parent_publication_and_finalization(self):
        rec, reg = fixture()
        e = bundle(rec)
        e["raw_parent_binding"]["source_published_at_ms"] += 1
        e["raw_parent_binding"]["parent_binding_sha256"] = digest({
            k:v for k,v in e["raw_parent_binding"].items() if k != "parent_binding_sha256"})
        self.assertEqual(self.status(rec, reg, e), "UNVERIFIED")
        e = bundle(rec)
        e["raw_parent_binding"]["source_finalized_at_ms"] = rec["decision_cutoff_ms"] + 1
        e["raw_parent_binding"]["parent_binding_sha256"] = digest({
            k:v for k,v in e["raw_parent_binding"].items() if k != "parent_binding_sha256"})
        self.assertEqual(self.status(rec, reg, e), "UNVERIFIED")

    def test_replay_conflict_still_quarantines(self):
        rec, reg = fixture()
        e = bundle(rec)
        changed = copy.deepcopy(rec)
        changed["f1_signal_state"] = "WATCH"
        changed["f1_record_sha256"] = hash_f1(changed)
        pair = (rec["pair_id"], rec["arm"])
        rows = status_slots(
            [rec["c2_identity"]], rec["experiment_plan_sha256"],
            {pair:[rec,changed]}, reg, verifier(reg,e))
        self.assertEqual(rows[0]["capture_status"], "QUARANTINED")


if __name__=="__main__":
    unittest.main()
