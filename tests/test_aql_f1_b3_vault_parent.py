"""B3 new-seam-only Core F1 -> actual pinned Vault tests."""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path

from examples.aql_f1_b2_emit_integrity_input import build_b2_input
from examples.aql_f1_b3_emit_vault_parent import exercise_b3_connection
from research_wp_r0.aql_f1_b3_vault_parent_adapter import (
    parent_input_for_pair, make_vault_meta, exercised_vault_parent,
    bound_parent_evidence,
)
from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError
from tools.raw_vault_offline import schema
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.schema import ChecksumMismatch


class TestB3VaultParentIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b2 = build_b2_input()

    def _pair(self):
        s = self.b2["schedule"][0]
        r = [x for x in self.b2["original_candidates_test_only"] if x["pair_id"] == s["pair_id"]]
        return s, r, parent_input_for_pair(s, r)

    def test_real_vault_admit_readback_manifest_and_two_n(self):
        report = exercise_b3_connection()
        self.assertEqual((report["n"], report["expected_2n"], report["expected_6n"]), (2, 4, 12))
        self.assertEqual(report["vault_admit_readback"], "PASS_LOCAL_VAULT_SOFTWARE_SEAM")
        self.assertEqual(report["vault_recovery_status"], "CLEAN")
        self.assertEqual(len(report["vault_parents"]), 2)
        self.assertEqual(len(report["arm_bindings"]), 4)
        self.assertTrue(all(x["binding"]["structural_parent_binding_test_only"] for x in report["arm_bindings"]))
        self.assertTrue(all(not x["binding"]["independent_parent_proof"] for x in report["arm_bindings"]))
        self.assertEqual(report["independent_source_issuer_custody_clock"], "BLOCKED_EXTERNAL_EVIDENCE")
        self.assertFalse(report["original_pit"])

    def test_idempotent_same_parent_and_readback(self):
        _, _, pair = self._pair()
        with tempfile.TemporaryDirectory() as d:
            vault = RawVault(Path(d))
            a = exercised_vault_parent(pair, vault, schema)
            b = exercised_vault_parent(pair, vault, schema)
            self.assertEqual(a["vault_parent_sha256"], b["vault_parent_sha256"])
            self.assertEqual(len(vault.manifest_entries()), 1)

    def test_forged_parent_bytes_rejected_before_readback(self):
        _, _, pair = self._pair()
        with tempfile.TemporaryDirectory() as d:
            vault = RawVault(Path(d))
            meta = make_vault_meta(pair, schema)
            with self.assertRaises(ChecksumMismatch):
                vault.admit(pair["parent_bytes"] + b"TAMPER", meta)
            self.assertEqual(len(vault.manifest_entries()), 0)

    def test_missing_parent_readback_fails_closed(self):
        _, _, pair = self._pair()
        with tempfile.TemporaryDirectory() as d:
            vault = RawVault(Path(d))
            with self.assertRaises(KeyError):
                vault.read(pair["parent_sha256"])

    def test_source_clock_mismatch_denies_binding(self):
        _, records, pair = self._pair()
        with tempfile.TemporaryDirectory() as d:
            retained = exercised_vault_parent(pair, RawVault(Path(d)), schema)
            record = records[0]
            result = bound_parent_evidence(
                record, retained,
                source_published_at_ms=record["decision_cutoff_ms"] + 1,
                source_finalized_at_ms=record["source_asof_ms"],
                correction_published_at_ms=record["source_available_at_ms"],
            )
            self.assertFalse(result["structural_parent_binding_test_only"])
            self.assertFalse(result["independent_parent_proof"])

    def test_forged_manifest_parent_proof_not_accepted(self):
        _, records, pair = self._pair()
        with tempfile.TemporaryDirectory() as d:
            retained = exercised_vault_parent(pair, RawVault(Path(d)), schema)
            tampered = dict(retained)
            tampered["manifest_bytes"] = b"forged"
            result = bound_parent_evidence(
                records[0], tampered,
                source_published_at_ms=records[0]["source_available_at_ms"],
                source_finalized_at_ms=records[0]["source_asof_ms"],
                correction_published_at_ms=records[0]["source_available_at_ms"],
            )
            self.assertFalse(result["structural_parent_binding_test_only"])
            self.assertFalse(result["independent_parent_proof"])

    def test_original_f1_identity_and_distinct_sha_remain_unchanged(self):
        schedule, records, pair = self._pair()
        self.assertNotEqual(pair["parent_sha256"], schedule["source_bytes_sha256"])
        original_ids = [r["f1_record_sha256"] for r in records]
        with tempfile.TemporaryDirectory() as d:
            retained = exercised_vault_parent(pair, RawVault(Path(d)), schema)
        self.assertEqual(retained["f1_source_bytes_sha256"], schedule["source_bytes_sha256"])
        self.assertEqual([r["f1_record_sha256"] for r in records], original_ids)

    def test_absent_witness_stays_unverified(self):
        _, records, pair = self._pair()
        with tempfile.TemporaryDirectory() as d:
            retained = exercised_vault_parent(pair, RawVault(Path(d)), schema)
            result = bound_parent_evidence(
                records[0], retained,
                source_published_at_ms=records[0]["source_available_at_ms"],
                source_finalized_at_ms=records[0]["source_asof_ms"],
                correction_published_at_ms=records[0]["source_available_at_ms"],
            )
        self.assertFalse(result["independent_parent_proof"])
        self.assertEqual(result["f1_capture_status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
