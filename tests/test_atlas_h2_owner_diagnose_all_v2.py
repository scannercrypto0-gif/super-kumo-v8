"""True one-pass MULTI-FINDING, no signed artifact mutation, no H2 claim."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_atlas_h2_owner_evidence_recovery_v2 import OwnerRecoverySafeSynthetic
from tools.atlas_h2_owner_diagnose_all_v2 import (
    inspect_four, Findings, _is_link, diagnose, write_private_report,
    LIMITS, FILES,
)


class MultiFindingOwnerPreflight(unittest.TestCase):
    def setUp(self):
        self.fx=OwnerRecoverySafeSynthetic(
            methodName="test_genuine_shaped_synthetic_mock_proofs_generate_four_not_h2")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx._do()
        self.key=self.fx.identity_dir/"owner-signing.key"
        self.repo=self.fx.root/"repo"
        self.repo.mkdir()
        self.previous=self.fx.output/"h2-readiness-summary.json"
        self.previous.write_bytes(b'{"status":"BLOCKED","reason":"BLOCKED_PERSONAL_EVIDENCE_FILE_UNSAFE"}')
    def entries(self,**kwargs):
        params=dict(include_original_read=False,
                    overlay_check=lambda *a: {
                        "sha256":"a"*64,
                        "scanner_f3_import_seam_sha256":["b"*64,"c"*64]})
        params.update(kwargs)
        with patch("tools.atlas_h2_owner_diagnose_all_v2._scanner_effective",
                   return_value=True),patch(
             "tools.atlas_h2_owner_diagnose_all_v2._factory_sha",
             return_value=True):
            result=diagnose(
                self.fx.evidence,self.fx.output,self.key,self.repo,**params)
        return result,{r["id"]:r for r in result["findings"]}
    def test_four_genuine_synthetic_files_and_original_report_remain(self):
        original=self.previous.read_bytes()
        report,findings=self.entries()
        self.assertEqual(findings["OWNER_MAC_TIME_CUSTODY"]["status"],"PASS")
        self.assertEqual(findings["SIGNED_EXACT_ROOT"]["status"],"PASS")
        self.assertEqual(findings["NATIVE_FILE_SHA"]["status"],"PASS")
        self.assertEqual(findings["PRIOR_READINESS_REPORT_PRESERVED"]["status"],"PASS")
        self.assertEqual(findings["EXECUTION_FIVE_ROLE_OVERLAY"]["status"],"PASS")
        self.assertEqual(findings["PUBLISHER_BYTE_IDENTITY"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
        self.assertEqual(findings["ORIGINAL_H2_EXECUTION"]["status"],
                         "NOT_RUN_REQUIRES_ORIGINAL_EXECUTION")
        self.assertEqual(self.previous.read_bytes(),original)
        self.assertFalse((self.fx.evidence/"h2-personal-one-use-claim.json").exists())
        self.assertFalse((self.fx.output/"h2-personal-scope-claim.json").exists())
        self.assertFalse(report["original_h2_executed"])
    def test_native_realistic_large_receipt_is_bounded_to_4mib(self):
        path=self.fx.evidence/"core245-native-receipt.json"
        with path.open("ab") as f:
            f.write(b" "*(700_000-path.stat().st_size))
        f=Findings()
        inspect_four(self.fx.evidence,f)
        native=[x for x in f.entries if
                x["id"]=="FILE_CORE245_NATIVE_RECEIPT_JSON"][0]
        self.assertEqual(native["status"],"PASS")
        self.assertEqual(native["evidence"]["byte_count"],700_000)
        self.assertEqual(native["evidence"]["limit_bytes"],4*1024*1024)
        # A second independent SHA check MUST still catch any byte drift.
        _,results=self.entries()
        self.assertEqual(results["NATIVE_FILE_SHA"]["status"],"FAIL")
    def test_above_4mib_native_rejected_without_unbounded_json_read(self):
        path=self.fx.evidence/"core245-native-receipt.json"
        with path.open("ab") as f:
            f.truncate(4*1024*1024+1)
        _,results=self.entries()
        self.assertEqual(results["FILE_CORE245_NATIVE_RECEIPT_JSON"]["status"],"FAIL")
        self.assertEqual(results["FILE_CORE245_NATIVE_RECEIPT_JSON"]["reason"],"OVERSIZE")
        self.assertEqual(results["CORE245_SCHEMA_SEAL"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
    def test_symlink_or_reparse_flag_is_denied_without_following_it(self):
        class FakeStat:
            st_mode=0o100644
            st_size=50
            st_file_attributes=0x400
        self.assertTrue(_is_link("no-real-path",FakeStat()))
    def test_four_independent_failures_and_existing_report_preserved(self):
        (self.fx.evidence/"manual-third-ast.json").unlink()
        (self.fx.evidence/"owner-personal-assertion.json").write_text("{bad")
        reg=self.fx.identity_dir/"owner-revocations.json"
        reg.write_text(json.dumps({"schema":"aql.integration.h2.owner-revocations.v2",
                  "revoked_key_ids":[self.fx.identity["key_id"]]}))
        (self.fx.output/"h2-personal-scope-claim.json").write_text("already")
        old=self.previous.read_bytes()
        summary,results=self.entries()
        self.assertEqual(results["FILE_MANUAL_THIRD_AST_JSON"]["status"],"FAIL")
        self.assertEqual(results["JSON_OWNER_PERSONAL_ASSERTION_JSON"]["status"],"FAIL")
        self.assertEqual(results["NO_SIGNED_OUTPUT_ONE_USE"]["status"],"FAIL")
        self.assertEqual(results["OWNER_REVOCATIONS"]["status"],"PASS")
        self.assertEqual(results["OWNER_MAC_TIME_CUSTODY"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
        self.assertEqual(results["EXECUTION_FIVE_ROLE_OVERLAY"]["status"],"PASS")
        self.assertEqual(self.previous.read_bytes(),old)
        self.assertGreaterEqual(summary["counts"]["FAIL"],3)
    def test_independent_bad_cost_and_nonce_are_reported_by_owner_mac(self):
        p=self.fx.evidence/"owner-personal-assertion.json"
        env=json.loads(p.read_text())
        env["assertion"]["scope"]["one_use_nonce"]="0"*32
        env["assertion"]["cost_policy"]["costs"]["fee_exit_bps"]="9999"
        p.write_text(json.dumps(env))
        _,results=self.entries()
        self.assertEqual(results["OWNER_MAC_TIME_CUSTODY"]["status"],"FAIL")
        self.assertEqual(results["SIGNED_EXACT_ROOT"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
        self.assertEqual(results["EXECUTION_FIVE_ROLE_OVERLAY"]["status"],"PASS")
    def test_publisher_offline_then_core_blocked_by_explicit_dependency(self):
        report,results=self.entries(
            include_original_read=True,
            publisher=lambda *a,**kw: (_ for _ in ()).throw(
                OSError("private endpoint not available")))
        self.assertEqual(results["PUBLISHER_BYTE_IDENTITY"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
        self.assertEqual(results["ORIGINAL_ZIP_IDENTITY"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
        self.assertEqual(results["CORE253_DUAL_COMPLETE"]["status"],
                         "BLOCKED_BY_DEPENDENCY")
        self.assertEqual(results["EXECUTION_FIVE_ROLE_OVERLAY"]["status"],"PASS")
    def test_missing_import_overlay_fails_but_evidence_checks_continue(self):
        _,results=self.entries(overlay_check=lambda *a:
            (_ for _ in ()).throw(ModuleNotFoundError("scanner_b")))
        self.assertEqual(results["EXECUTION_FIVE_ROLE_OVERLAY"]["status"],"FAIL")
        self.assertEqual(results["NATIVE_FILE_SHA"]["status"],"PASS")
    def test_bad_signed_output_root_independent_checks_continue(self):
        other=self.fx.root/"not-signed"
        other.mkdir()
        report=diagnose(self.fx.evidence,other,self.key,self.repo,
            include_original_read=False,
            overlay_check=lambda *a:{"scanner_f3_import_seam_sha256":["a"]})
        results={x["id"]:x for x in report["findings"]}
        self.assertEqual(results["SIGNED_EXACT_ROOT"]["status"],"FAIL")
        self.assertEqual(results["AST_FILE_SHA"]["status"],"PASS")
    def test_no_overwrite_existing_diagnostic_or_signed_readiness(self):
        root=self.fx.root/"new-diagnostics"
        existing=self.previous.read_bytes()
        report,_=self.entries()
        path=write_private_report(report,root)
        self.assertTrue(path.exists())
        self.assertEqual(self.previous.read_bytes(),existing)
        with self.assertRaises(FileExistsError):
            write_private_report(report,root)
    def test_no_actual_source_write_from_multi_finding(self):
        original=self.fx.source.read_bytes()
        self.entries(include_original_read=False)
        self.assertEqual(self.fx.source.read_bytes(),original)
        self.assertFalse((self.fx.output/"results.sqlite").exists())


if __name__=="__main__":
    unittest.main()
