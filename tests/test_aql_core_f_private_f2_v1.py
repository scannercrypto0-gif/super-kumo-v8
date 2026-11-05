"""F2 tests: fail closed before privately authorized original-byte admission."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_wp_r0.aql_core_f_bulk_source_v1 import (
    build_manifest, build_coverage_ledger,
)
from research_wp_r0.aql_core_f_private_f2_v1 import (
    authorize_local_admission, check_local_batch, digest, execute_local_f2,
    verify_f1_container,
)

MANIFEST_SHA = "f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7"
F1_LEDGER_SHA = "303cf791ff01be9d74f824909814e7a015ae6b265ba61e824f374f21648a2ab7"


class CoreF2Safety(unittest.TestCase):
    def setUp(self):
        self.m = build_manifest()
        self.missing = build_coverage_ledger(self.m)
        self.auth = {
            "schema": "aql.core.f.private-custody-authorization.v1",
            "owner_permission": True,
            "rights_evidence_reference": "OUT_OF_BAND_RIGHTS_RECORD_20261105",
            "issuer_provenance_reference": "OUT_OF_BAND_TLS_PUBLISHER_WITNESS_20261105",
            "publisher_checksum_issued_via": "SEPARATE_PUBLISHER_HTTPS",
            "authorized_months": [r["month"] for r in self.m["rows"]
                                  if r["month"] not in ("2024-02", "2024-08")],
            "source_class": "ORIGINAL_PUBLISHER_RETROSPECTIVE_NON_PIT",
            "historical_pit": "NOT_ATTESTED",
            "trading_authority": "NONE",
        }

    def test_owner_manifest_pin_expected_current_contract(self):
        self.assertEqual(self.m["manifest_sha256"], MANIFEST_SHA)
        self.assertNotEqual(self.missing["coverage_ledger_sha256"], F1_LEDGER_SHA)

    def test_owner_f1_json_requires_exact_independent_sha(self):
        pair = {"manifest": self.m, "coverage": self.missing}
        self.assertEqual(verify_f1_container(
            pair, self.m["manifest_sha256"], self.missing["coverage_ledger_sha256"]),
            (self.m, self.missing))
        for manifest_hash, ledger_hash in (
            ("0" * 64, self.missing["coverage_ledger_sha256"]),
            (self.m["manifest_sha256"], F1_LEDGER_SHA),
        ):
            with self.assertRaises(ValueError):
                verify_f1_container(pair, manifest_hash, ledger_hash)

    def test_no_f1_files_are_accepted_as_original(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d).chmod(0o700)
            with patch("research_wp_r0.aql_core_f_private_f2_v1._fetch",
                       side_effect=AssertionError("no network without local files")):
                rows, raw = check_local_batch(
                    self.m, self.missing, d,
                    allow_network=True, publisher_recheck=True)
            self.assertEqual(raw, {})
            self.assertEqual(sum(r["state"] == "RETAINED_INVENTORY_ONLY"
                                 for r in rows), 2)
            self.assertEqual(sum(r["state"] == "MISSING_OR_QUARANTINED"
                                 for r in rows), 10)

    def test_authorization_requires_separate_pin(self):
        correct = digest(self.auth)
        self.assertTrue(authorize_local_admission(self.auth, correct, self.m))
        with self.assertRaisesRegex(ValueError, "PIN_MISMATCH"):
            authorize_local_admission(self.auth, "0" * 64, self.m)
        for key, value in (("owner_permission", False),
                           ("trading_authority", "LIVE"),
                           ("historical_pit", "ATTESTED"),
                           ("publisher_checksum_issued_via", "LOCAL_COPY"),
                           ("authorized_months", ["2024-02"])):
            changed = {**self.auth, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                authorize_local_admission(changed, digest(changed), self.m)

    def test_refuse_raw_when_local_files_not_available(self):
        pair = {"manifest": self.m, "coverage": self.missing}
        with tempfile.TemporaryDirectory() as d:
            Path(d).chmod(0o700)
            with self.assertRaisesRegex(ValueError, "F2_APPROVED_COHORT_MISMATCH"):
                execute_local_f2(
                    pair, d, d, d,
                    expected_manifest_sha=self.m["manifest_sha256"],
                    expected_ledger_sha=self.missing["coverage_ledger_sha256"],
                    authorization=self.auth,
                    expected_authorization_sha=digest(self.auth),
                    allow_network=True, publisher_recheck=True,
                    allow_raw_admission=True)


if __name__ == "__main__":
    unittest.main()
