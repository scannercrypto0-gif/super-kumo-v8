"""Original RAW parent -> derived measurement chain; synthetic only."""
import copy
import hashlib
import json
import unittest

from research_wp_r0.aql_w1_raw_parent_bridge import authenticated_parent_market_windows
from research_wp_r0.aql_w1_f1_prospective_consumer import project_parent_authenticated_f1_slots
from tests.test_aql_w1_market_window_adapter import sample


def fixture():
    plan, original, registry, derived, derived_receipt = sample()
    parent = b"open_time,high,low\n900000,110,95\n"
    parent_sha = hashlib.sha256(parent).hexdigest()
    # F1 bounded-source hash stays distinct from parent RAW object digest.
    from research_wp_r0.aql_f1_decision_capture_v1 import hash_f1
    original["f1_record_sha256"] = hash_f1(original)
    manifest = dict(
        schema_version="raw_object.v1", content_sha256=parent_sha,
        byte_length=len(parent), source_format="RAW_CSV", format_version="v1",
        interval="15m", correction_generation=1,
        parent_content_sha256="a"*64,
        coverage_start_utc="1970-01-01T00:00:00Z",
        coverage_end_utc="1970-01-06T00:00:00Z",
        admitted_at_utc="1970-01-06T01:00:00Z",
        trust_status="UNKNOWN", evidence_class="FIXTURE_SYNTHETIC",
        vendor="source",
    )
    lineage = dict(
        parent_content_sha256=parent_sha,
        f1_source_bytes_sha256=plan["source_bytes_sha256"],
        source_id=original["source_id"],
        derived_bytes_sha256=hashlib.sha256(derived).hexdigest(),
        source_version=plan["source_version"],
        correction_generation=1,
        normalization_policy="canonical_15m-v1",
        published_at_ms=derived_receipt["published_at_ms"],
        finalized_at_ms=derived_receipt["finalized_at_ms"],
    )
    plan["correction_generation"] = "1"
    original["correction_generation"] = "1"
    original["f1_record_sha256"] = hash_f1(original)
    return plan, original, registry, parent, manifest, derived, lineage


def windows_fixture(**changes):
    plan, original, registry, parent, manifest, derived, lineage = fixture()
    if "parent" in changes: parent = changes["parent"]
    if "manifest" in changes: manifest = changes["manifest"]
    if "lineage" in changes: lineage = changes["lineage"]
    pm = None if changes.get("no_parent_verifier") else lambda meta, data: True
    deriv = None if changes.get("no_derivation_verifier") else lambda info, data, view: True
    receipt = None if changes.get("no_external_receipt") else lambda info, meta: True
    market, check = authenticated_parent_market_windows(
        [plan], {plan["pair_id"]: parent},
        {plan["pair_id"]: manifest} if manifest is not None else {},
        {plan["pair_id"]: derived}, {plan["pair_id"]: lineage},
        verify_parent_manifest=pm, verify_derivation=deriv,
        verify_external_receipt=receipt)
    return market, check, plan, original, registry, parent, manifest, derived, lineage


class ParentProvenanceTests(unittest.TestCase):
    def test_bound_parent_and_derived_complete_synthetic(self):
        windows, checker, plan, f1, registry, parent, manifest, derived, lineage = windows_fixture()
        self.assertEqual(len(windows), 3)
        self.assertEqual([w["coverage_status"] for w in windows], ["COMPLETE"]*3)
        self.assertTrue(all(checker(x) for x in windows))
        self.assertTrue(all(w["source_bytes_sha256"] == plan["source_bytes_sha256"]
                            for w in windows))
        self.assertNotEqual(plan["source_bytes_sha256"], hashlib.sha256(parent).hexdigest())
        self.assertTrue(all(w["raw_bytes_sha256"] == hashlib.sha256(derived).hexdigest()
                            for w in windows))
        report = project_parent_authenticated_f1_slots(
            [plan], [f1], parent_bytes_by_pair={plan["pair_id"]: parent},
            manifest_by_pair={plan["pair_id"]: manifest},
            derived_bars_by_pair={plan["pair_id"]: derived},
            derived_evidence_by_pair={plan["pair_id"]: lineage},
            indicator_registry=registry, verify_parent_manifest=lambda m, b: True,
            verify_derivation=lambda l, p, d: True,
            verify_external_receipt=lambda l, m: True)
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertEqual(report["capture_status_counts"], {"UNVERIFIED": 1, "MISSING_CAPTURE": 1})
        self.assertTrue(all(x["max_favorable"] is None for x in report["outcomes"]))
        self.assertFalse(report["operational_pit_and_custody_proven"])

    def test_tampered_parent_never_authenticated(self):
        windows, check, *_ = windows_fixture(parent=b"tampered bytes")
        self.assertEqual(windows, [])
        self.assertFalse(check({}))

    def test_missing_manifest_never_authenticated(self):
        windows, check, *_ = windows_fixture(manifest=None)
        self.assertEqual(windows, [])
        self.assertFalse(check({}))

    def test_mismatched_correction_never_authenticated(self):
        plan, f1, registry, parent, manifest, derived, lineage = fixture()
        lineage["correction_generation"] = 2
        windows, check = authenticated_parent_market_windows(
            [plan], {plan["pair_id"]: parent}, {plan["pair_id"]: manifest},
            {plan["pair_id"]: derived}, {plan["pair_id"]: lineage},
            verify_parent_manifest=lambda m, b: True,
            verify_derivation=lambda l, p, d: True,
            verify_external_receipt=lambda l, m: True)
        self.assertEqual(windows, [])
        self.assertFalse(check({}))

    def test_late_bar_fails_coverage_not_silent_drop(self):
        plan, f1, registry, parent, manifest, derived, lineage = fixture()
        bars = json.loads(derived)
        bars[0]["published_at_ms"] = lineage["published_at_ms"] + 1
        revised = json.dumps(bars, separators=(",", ":")).encode()
        lineage["derived_bytes_sha256"] = hashlib.sha256(revised).hexdigest()
        windows, check = authenticated_parent_market_windows(
            [plan], {plan["pair_id"]: parent}, {plan["pair_id"]: manifest},
            {plan["pair_id"]: revised}, {plan["pair_id"]: lineage},
            verify_parent_manifest=lambda m, b: True,
            verify_derivation=lambda l, p, d: True,
            verify_external_receipt=lambda l, m: True)
        self.assertEqual(windows, [])
        self.assertFalse(check({}))

    def test_no_external_receipt_no_positive_market(self):
        windows, checker, *_ = windows_fixture(no_external_receipt=True)
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))

    def test_no_parent_or_derivation_witness(self):
        for key in ("no_parent_verifier", "no_derivation_verifier"):
            with self.subTest(key=key):
                windows, checker, *_ = windows_fixture(**{key: True})
                self.assertEqual(windows, [])
                self.assertFalse(checker({}))

    def test_valid_rehashed_derivative_without_parent_attestation_fails(self):
        plan, f1, registry, parent, manifest, derived, lineage = fixture()
        altered = derived + b" "
        lineage["derived_bytes_sha256"] = hashlib.sha256(altered).hexdigest()
        windows, checker = authenticated_parent_market_windows(
            [plan], {plan["pair_id"]: parent}, {plan["pair_id"]: manifest},
            {plan["pair_id"]: altered}, {plan["pair_id"]: lineage},
            verify_parent_manifest=None, verify_derivation=lambda l,p,d: True,
            verify_external_receipt=lambda l,m: True)
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))


if __name__ == "__main__":
    unittest.main()
