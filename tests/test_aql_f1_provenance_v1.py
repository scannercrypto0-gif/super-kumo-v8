"""Focused F1 provenance seams: synthetic evidence, NOT operational PIT proof."""
import copy
import unittest

from research_wp_r0.aql_f1_decision_capture_v1 import digest, hash_f1, status_slots, validate_f1
from research_wp_r0.aql_f1_provenance_v1 import make_provenance_verifier, verify_original_provenance
from tests.test_aql_f1_decision_capture_v1 import fixture


def evidence_for(record):
    source = {
        "schema_version": "aql.f1-source-publication-proof.v1",
        **{k: record[k] for k in ("pair_id", "arm", "f1_record_sha256",
           "source_id", "source_version", "source_bytes_sha256",
           "correction_generation", "correction_lineage_sha256",
           "source_asof_ms", "source_available_at_ms", "decision_cutoff_ms")},
        "source_published_at_ms": record["decision_cutoff_ms"],
        "correction_published_at_ms": record["decision_cutoff_ms"],
    }
    source["source_receipt_sha256"] = digest(source)
    freeze = {
        "schema_version": "aql.f1-pre-f3-freeze-proof.v1",
        **{k: record[k] for k in ("pair_id", "arm", "f1_record_sha256",
                                  "arm_event_sha256")},
        "frozen_at_ms": record["capture_ms"],
        "f3_started_at_ms": record["capture_ms"] + 20,
        "freeze_ref": "external-frozen-event",
    }
    freeze["freeze_receipt_sha256"] = digest(freeze)
    receipt = {
        "schema_version": "aql.f1-commit-receipt.v1",
        "receipt_id": "external-durable-commit",
        "f1_record_sha256": record["f1_record_sha256"],
        "producer_sequence": record["producer_sequence"],
        "previous_event_sha256": record["previous_event_sha256"],
        "frozen_arm_event_sha256": record["arm_event_sha256"],
        "committed_at_ms": record["capture_ms"] + 1,
        "durable_store_ref": "external-durable-store",
        "independent_anchor_ref": "external-anchor",
    }
    receipt["commit_receipt_sha256"] = digest(receipt)
    return {"source_proof": source, "freeze_proof": freeze, "commit_receipt": receipt}


def rehash(proof, field):
    proof[field] = digest({k:v for k,v in proof.items() if k != field})


class ProvenanceTests(unittest.TestCase):
    def check(self, record, registry, evidence=None, *, callbacks=True):
        if evidence is None:
            evidence = evidence_for(record)
        verifier = make_provenance_verifier(
            registry, lambda _: evidence,
            source_attestor=(lambda _: True) if callbacks else None,
            freeze_attestor=(lambda _: True) if callbacks else None,
            durable_anchor_verifier=(lambda _: True) if callbacks else None)
        slots = status_slots([record["c2_identity"]], record["experiment_plan_sha256"],
                             {(record["pair_id"], record["arm"]): [record]},
                             registry, verifier)
        return slots[0]["capture_status"]

    def test_synthetic_positive_but_no_self_attestation(self):
        r, registry = fixture()
        e = evidence_for(r)
        self.assertEqual(self.check(r, registry, e), "RECORDED")
        self.assertEqual(self.check(r, registry, e, callbacks=False), "UNVERIFIED")
        self.assertFalse(verify_original_provenance(
            r, registry, source_proof=e["source_proof"],
            freeze_proof=e["freeze_proof"], commit_receipt=e["commit_receipt"]))

    def test_late_original_source_publication(self):
        r, registry = fixture()
        e = evidence_for(r)
        e["source_proof"]["source_published_at_ms"] += 1
        rehash(e["source_proof"], "source_receipt_sha256")
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")

    def test_late_correction_publication(self):
        r, registry = fixture()
        e = evidence_for(r)
        e["source_proof"]["correction_published_at_ms"] += 1
        rehash(e["source_proof"], "source_receipt_sha256")
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")

    def test_missing_external_anchor_or_receipt(self):
        r, registry = fixture()
        e = evidence_for(r)
        self.assertEqual(self.check(r, registry, {**e, "commit_receipt": None}), "UNVERIFIED")
        e["commit_receipt"]["independent_anchor_ref"] = ""
        rehash(e["commit_receipt"], "commit_receipt_sha256")
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")

    def test_changed_source_version_valid_f1_rehashed(self):
        r, registry = fixture()
        e = evidence_for(r)
        r["source_version"] = "v2"
        r["f1_record_sha256"] = hash_f1(r)
        validate_f1(r, registry)
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")

    def test_conflicting_freeze_and_event_hash(self):
        r, registry = fixture()
        e = evidence_for(r)
        e["freeze_proof"]["arm_event_sha256"] = "b" * 64
        rehash(e["freeze_proof"], "freeze_receipt_sha256")
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")

    def test_freeze_or_commit_after_f3(self):
        r, registry = fixture()
        e = evidence_for(r)
        e["freeze_proof"]["frozen_at_ms"] = e["freeze_proof"]["f3_started_at_ms"] + 1
        rehash(e["freeze_proof"], "freeze_receipt_sha256")
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")
        e = evidence_for(r)
        e["commit_receipt"]["committed_at_ms"] = e["freeze_proof"]["f3_started_at_ms"] + 1
        rehash(e["commit_receipt"], "commit_receipt_sha256")
        self.assertEqual(self.check(r, registry, e), "UNVERIFIED")

    def test_replay_idempotent_and_conflicting_replay_quarantine(self):
        r, registry = fixture()
        e = evidence_for(r)
        verifier = make_provenance_verifier(registry, lambda _: e,
            source_attestor=lambda _: True, freeze_attestor=lambda _: True,
            durable_anchor_verifier=lambda _: True)
        c2, plan, key = [r["c2_identity"]], r["experiment_plan_sha256"], (r["pair_id"], r["arm"])
        slots = status_slots(c2, plan, {key: [r, copy.deepcopy(r)]}, registry, verifier)
        self.assertEqual(slots[0]["capture_status"], "RECORDED")
        changed = copy.deepcopy(r)
        changed["f1_signal_state"] = "WATCH"
        changed["f1_record_sha256"] = hash_f1(changed)
        slots = status_slots(c2, plan, {key: [r, changed]}, registry, verifier)
        self.assertEqual(slots[0]["capture_status"], "QUARANTINED")

    def test_external_callback_denial_and_exception(self):
        r, registry = fixture()
        e = evidence_for(r)
        for deny in ("source", "freeze", "anchor"):
            callbacks = dict(source_attestor=lambda _: True, freeze_attestor=lambda _: True,
                             durable_anchor_verifier=lambda _: True)
            callbacks[{"source":"source_attestor","freeze":"freeze_attestor","anchor":"durable_anchor_verifier"}[deny]] = lambda _: False
            self.assertFalse(verify_original_provenance(
                r, registry, source_proof=e["source_proof"],
                freeze_proof=e["freeze_proof"], commit_receipt=e["commit_receipt"],
                **callbacks))
        self.assertFalse(make_provenance_verifier(registry, lambda _: 1 / 0)(
            r))


if __name__ == "__main__":
    unittest.main()
