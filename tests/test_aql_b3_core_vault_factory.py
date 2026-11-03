"""Focused B3 actual local RawVault to Factory readback integration tests.

Only pinned Core/B1 Actions artifact bytes and pinned actual Vault module.
No profitability test, no old B1/B2 suite.
"""
import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from research_wp_r0.aql_b3_core_vault_factory import (
    B1_ARTIFACT_SHA, CORE_SHA, canonical, integrate, meta_for, sha,
    source_from_accepted_b1, verify_binding_fails_closed,
)
from research_wp_r0.aql_w1_raw_parent_bridge import authenticated_parent_market_windows
from tools.raw_vault_offline.schema import (
    ChecksumMismatch, IdentityConflict, RawObjectMeta, EvidenceClass,
    TrustStatus, SourceFormat,
)
from tools.raw_vault_offline.vault import RawVault


class B3ActualSoftwareSeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = Path(os.environ.get("AQL_B3_CORE_JSON", "/tmp/aql-b3-core.json"))
        market = Path(os.environ.get("AQL_B3_B1_ARTIFACT", "/tmp/aql-b3-originals.zip"))
        if not core.is_file() or not market.is_file():
            raise unittest.SkipTest("B3 pinned artifacts absent; no synthetic substitution")
        cls.core_bytes, cls.b1_bytes = core.read_bytes(), market.read_bytes()
        assert sha(cls.core_bytes) == CORE_SHA
        assert sha(cls.b1_bytes) == B1_ARTIFACT_SHA
        cls.core = json.loads(cls.core_bytes)

    def test_actual_vault_to_factory_deterministic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            a = integrate(self.core_bytes, self.b1_bytes, Path(root))
            b = integrate(self.core_bytes, self.b1_bytes, Path(root))
            self.assertEqual(canonical(a), canonical(b))
            self.assertEqual(a["actual_vault_software"]["objects_admitted"], 4)
            self.assertEqual(a["actual_vault_software"]["manifest_entries"], 4)
            self.assertEqual((a["post_vault_factory_consumer"]["N"],
                              a["post_vault_factory_consumer"]["observed_2N"],
                              a["post_vault_factory_consumer"]["observed_6N"]), (2, 4, 12))
            self.assertEqual(a["seams"]["external_issuer_custody_clock_proof"],
                             "BLOCKED_EXTERNAL_EVIDENCE")

    def test_missing_original_arm_fails_closed(self):
        altered = copy.deepcopy(self.core)
        pair = altered["schedule"][0]["pair_id"]
        altered["original_candidates_test_only"] = [
            x for x in altered["original_candidates_test_only"]
            if not (x["pair_id"] == pair and x["arm"] == "SHADOW")
        ]
        # Original SHA must fail first; no silent use of changed Core bytes.
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "CORE_INPUT_DRIFT"):
                integrate(canonical(altered), self.b1_bytes, Path(root))

    def test_forged_original_bytes_rejected_before_vault(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "ORIGINAL_MARKET_B1_ARTIFACT_DRIFT"):
                integrate(self.core_bytes, self.b1_bytes + b"forgery", Path(root))

    def test_vault_local_read_rejects_changed_parent_object(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            vault = RawVault(root)
            raw = b"TEST_ONLY parent fixture evidence"
            meta = meta_for(
                raw, vendor="AQL-B3-NEGATIVE-TEST", source="TEST_ONLY_F1",
                coverage_start="1970-01-01T00:00:00Z",
                coverage_end="1970-01-01T00:15:00Z",
                evidence_class=EvidenceClass.FIXTURE_SYNTHETIC,
                trust_status=TrustStatus.UNVERIFIED, source_format=SourceFormat.JSON_LINES,
                filename="fixture.jsonl",
            )
            vault.admit(raw, meta)
            obj = root / "objects" / meta.content_sha256[:2] / meta.content_sha256[2:]
            obj.write_bytes(b"changed")
            with self.assertRaises(ChecksumMismatch):
                vault.read(meta.content_sha256)

    def test_vault_same_identity_different_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            vault = RawVault(Path(root))
            kw = dict(vendor="AQL-B3-NEGATIVE-TEST", source="TEST_ONLY_F1",
                      coverage_start="1970-01-01T00:00:00Z",
                      coverage_end="1970-01-01T00:15:00Z",
                      evidence_class=EvidenceClass.FIXTURE_SYNTHETIC,
                      trust_status=TrustStatus.UNVERIFIED,
                      source_format=SourceFormat.JSON_LINES, filename="fixture.jsonl")
            a = b"candidate-a"
            b = b"candidate-b"
            vault.admit(a, meta_for(a, **kw))
            with self.assertRaises(IdentityConflict):
                vault.admit(b, meta_for(b, **kw))

    def test_missing_external_witness_must_not_verify_parent(self):
        schedule = self.core["schedule"]
        windows, verifier = authenticated_parent_market_windows(
            schedule, {}, {}, {}, {},
            verify_parent_manifest=None,
            verify_derivation=None,
            verify_external_receipt=None,
        )
        self.assertEqual(windows, [])
        self.assertFalse(verifier({"coverage_status": "COMPLETE"}))

    def test_mismatched_2024_parent_cutoff_and_source_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            report = integrate(self.core_bytes, self.b1_bytes, Path(root))
        parents = report["actual_vault_software"]["original_market_parent_objects"]
        self.assertEqual(len(parents), 2)
        self.assertTrue(all(
            p["original_core_source_binding"]["status"]
            == "BLOCKED_SOURCE_VINTAGE_AND_CUTOFF_MISMATCH" for p in parents))
        self.assertTrue(all(not p["original_core_source_binding"]["source_pin_matches"]
                            for p in parents))

    def test_mismatched_scheduled_opportunity_detected(self):
        altered = copy.deepcopy(self.core)
        altered["schedule"][1]["pair_id"] = altered["schedule"][0]["pair_id"]
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "CORE_INPUT_DRIFT"):
                integrate(canonical(altered), self.b1_bytes, Path(root))


if __name__ == "__main__":
    unittest.main()
