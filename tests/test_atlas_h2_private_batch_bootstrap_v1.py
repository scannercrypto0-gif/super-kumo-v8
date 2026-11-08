"""H2 private batch bootstrap: focused no-original-data security tests."""
from __future__ import annotations
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_h2_private_batch_bootstrap_v1 import (
    INTAKE_SCHEMA, Blocked, REQUIRED, build_scope, digest,
    inspect_private_intake, run_batch, sha_file, write_report,
)


class PrivateBatch(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.intake = root / "intake"
        self.intake.mkdir()
        self.output = root / "output"
        self.output.mkdir()
        self.verifier = root / "separate-custodian.key"
        self.owner = root / "separate-owner.key"
        self.verifier.write_bytes(b"c" * 32)
        self.owner.write_bytes(b"o" * 32)
        self.repo = root / "pinned-repo"
        self.repo.mkdir()
        self.root = root

    def test_no_custody_bundle_emits_single_blocked_summary(self):
        with patch("tools.atlas_h2_private_batch_bootstrap_v1.execute",
                   side_effect=AssertionError("original source accessed")):
            report = run_batch(
                self.intake, self.verifier, self.owner, self.output,
                self.repo, confirm_one_run=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("MISSING_PRIVATE_EVIDENCE:", report["reasons"][0])
        self.assertEqual(report["sha256"],
                         digest({k: v for k, v in report.items()
                                 if k != "sha256"}))
        name = write_report(self.output, report)
        self.assertTrue(name.is_file())
        with self.assertRaises(Blocked):
            write_report(self.output, report)

    def _genuine_intake(self):
        (self.intake / "rights-evidence.bin").write_bytes(b"synthetic private rights")
        (self.intake / "core245-native-receipt.json").write_text("{}")
        (self.intake / "manual-third-ast.json").write_text("{}")
        start = 1709251200000
        data = {
            "schema": INTAKE_SCHEMA,
            "owner_authorization_ref": "#205/6718325330",
            "one_time_scope_authorized": True,
            "custodian_rights_asserted": True,
            "rights_evidence_file_sha256": sha_file(
                self.intake / "rights-evidence.bin"),
            "warehouse_root": str(self.root / "offline-original-warehouse"),
            "vault_root": str(self.root / "offline-original-vault"),
            "dataset_id": "BINANCE-SPOT-BTCUSDT-15M-2024-03-F-v1",
            "version": 1, "month": "2024-03",
            "start_ms": start,
            "end_exclusive_ms": start + 4*900000,
            "decision_cutoff_ms": start + 4*900000,
            "source_bytes_sha256": "a"*64,
            "manifest_integrity_sha256": "b"*64,
            "native_receipt_file_sha256": sha_file(
                self.intake / "core245-native-receipt.json"),
            "strategy_file_sha256": sha_file(
                self.intake / "manual-third-ast.json"),
            "strategy_definition_sha256": "c"*64,
            "strategy_id": "h_manual_distinct_test",
            "factory_code_sha256": "d"*64,
            "experiment_id": "RESEARCH-H-GENERIC-OWNER-SYNTHETIC",
        }
        raw = json.dumps(data,sort_keys=True).encode("utf-8")
        (self.intake / "custody-intake.json").write_bytes(raw)
        (self.intake / "custody-intake.mac").write_text(
            hmac.new(b"c"*32,raw,hashlib.sha256).hexdigest())
        return data

    def test_tampered_intake_is_denied_before_source(self):
        self._genuine_intake()
        (self.intake / "custody-intake.json").write_text("{}")
        with self.assertRaisesRegex(Blocked, "CUSTODIAN_SIGNATURE_UNVERIFIED"):
            inspect_private_intake(self.intake, self.verifier)

    def test_custodian_rights_assertion_not_independent_proof(self):
        self._genuine_intake()
        claim, _, _ = inspect_private_intake(self.intake, self.verifier)
        self.assertEqual(claim["custodian_rights_asserted"], True)
        s = build_scope(claim,self.intake,self.output)
        self.assertEqual(s["source_rights_attested"], True)
        self.assertNotIn("publisher_pit_claim",str(s))

    def test_never_reserve_one_shot_inside_original_source(self):
        self._genuine_intake()
        claim, _, _ = inspect_private_intake(self.intake, self.verifier)
        claim["warehouse_root"] = str(self.intake)
        with self.assertRaisesRegex(
                Blocked, "PRIVATE_INTAKE_OVERLAPS_ORIGINAL_SOURCE"):
            build_scope(claim, self.intake, self.output)
        self.assertFalse((self.intake/"h2-single-use-claim.json").exists())

    def test_different_owner_key_required(self):
        self._genuine_intake()
        result = run_batch(self.intake, self.verifier, self.verifier,
                           self.output, self.repo, confirm_one_run=True)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("OWNER_SIGNING_KEY_MUST_BE_DISTINCT_FROM_CUSTODIAN_KEY",
                      result["reasons"])

    def test_owner_confirmation_is_mandatory_no_source(self):
        self._genuine_intake()
        with patch("tools.atlas_h2_private_batch_bootstrap_v1.execute",
                   side_effect=AssertionError("source IO")):
            report=run_batch(self.intake,self.verifier,self.owner,
                             self.output,self.repo,confirm_one_run=False)
        self.assertEqual(report["status"],"BLOCKED")
        self.assertIn("EXPLICIT_ONE_TIME_LOCAL_CONFIRMATION_REQUIRED",
                      report["reasons"])

    def test_authenticated_only_one_claim_and_sanitized_operator_block(self):
        self._genuine_intake()
        for name in ("offline-original-warehouse","offline-original-vault"):
            (self.root/name).mkdir()
        with patch("tools.atlas_h2_private_batch_bootstrap_v1.execute",
                   return_value={"status":"BLOCKED",
                                 "reason":"SOURCE_NONEMPTY_WAL_REQUIRES_OFFLINE_STABLE_SNAPSHOT",
                                 "sha256":"f"*64}) as fake:
            first=run_batch(self.intake,self.verifier,self.owner,
                            self.output,self.repo,confirm_one_run=True)
        self.assertEqual(fake.call_count,1)
        self.assertEqual(first["status"],"BLOCKED")
        self.assertIsNone(first["source_read"])
        self.assertEqual(first["source_read_status"],"POSSIBLE_AFTER_GATES")
        self.assertIn("OPERATOR_SOURCE_NONEMPTY_WAL_REQUIRES_OFFLINE_STABLE_SNAPSHOT",
                      first["reasons"])
        self.assertTrue((self.intake/"h2-single-use-claim.json").is_file())
        alternate = self.root / "alternative-output"
        alternate.mkdir()
        with patch("tools.atlas_h2_private_batch_bootstrap_v1.execute",
                   side_effect=AssertionError("must not rerun")):
            repeat=run_batch(self.intake,self.verifier,self.owner,
                             alternate,self.repo,confirm_one_run=True)
        self.assertIn("SINGLE_USE_ALREADY_CLAIMED",repeat["reasons"])

    def test_signed_stage_sha_mutation_refused(self):
        self._genuine_intake()
        (self.intake / "manual-third-ast.json").write_text('{"changed":1}')
        with self.assertRaisesRegex(Blocked,"SIGNED_EVIDENCE_FILE_SHA_DRIFT"):
            inspect_private_intake(self.intake,self.verifier)

    def test_negative_no_fake_positive(self):
        r=run_batch(self.intake,None,None,self.output,self.repo,True)
        self.assertFalse(r["source_read"])
        self.assertEqual(r["trading_authority"],"NONE")
        self.assertEqual(r["historical_pit"],"NOT_ATTESTED")


if __name__=="__main__":
    unittest.main()
