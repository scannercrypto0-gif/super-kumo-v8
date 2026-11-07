"""Fail-closed contract checks for the private F diagnostic orchestrator.

Never claims a synthetic F2, signer or Factory Lab positive result.
"""
import tempfile
import unittest
from pathlib import Path

from tools.atlas_f_research_diagnostic_operator import (
    SCHEMA, demand, digest, require_scope, verify_pinned_modules,
)


class DiagnosticOperatorFailClosed(unittest.TestCase):
    def test_owner_private_explicit_authorization_is_required(self):
        with self.assertRaisesRegex(ValueError, "AUTHORIZATION"):
            require_scope({})
        with self.assertRaisesRegex(ValueError, "AUTHORIZATION"):
            require_scope({"schema":SCHEMA,"owner_operator_authorized":False})

    def test_cannot_write_under_original_vault_or_warehouse(self):
        with tempfile.TemporaryDirectory(prefix="aql-diag-negative-") as d:
            p=Path(d)
            vault=p/"original_raw"
            wh=p/"original_warehouse"
            vault.mkdir()
            wh.mkdir()
            manifest={
                "schema":SCHEMA,"owner_operator_authorized":True,
                "warehouse_root":str(wh),"vault_root":str(vault),
                "core_f2_report_path":str(p/"absent-report.json"),
                "scanner_policy_draft_path":str(p/"absent-policy.json"),
                "scanner_proposal_path":str(p/"absent-proposal.json"),
                "scanner_approval_request_path":str(p/"absent-approval.json"),
                "frozen_work_specs_path":str(p/"absent-work.json"),
                "factory_diagnostic_input_path":str(p/"absent-factory.json"),
                "diagnostic_store_path":str(vault/"tamper.sqlite"),
                "sanitized_output_path":str(p/"receipt.json"),
            }
            with self.assertRaisesRegex(ValueError, "NO_WRITES_UNDER_ORIGINAL_SOURCE"):
                require_scope(manifest)
            self.assertFalse((vault/"tamper.sqlite").exists())
            manifest["diagnostic_store_path"]=str(p/"diagnostic.sqlite")
            # Disposable negative-only fixture files satisfy path preflight;
            # they are never interpreted as authentic source or read by F2.
            for key in ("core_f2_report_path","scanner_policy_draft_path",
                        "scanner_proposal_path","scanner_approval_request_path",
                        "frozen_work_specs_path","factory_diagnostic_input_path"):
                Path(manifest[key]).write_text("{}",encoding="utf-8")
            assert require_scope(manifest)[2] == p/"diagnostic.sqlite"
            (p/"diagnostic.sqlite").write_bytes(b"preexisting")
            with self.assertRaisesRegex(ValueError, "FRESH_RUN_OUTPUT_REQUIRED"):
                require_scope(manifest)

    def test_receipts_are_hash_sealed_but_cannot_issue_authority(self):
        a={"kind":"RESEARCH_E2E_DIAGNOSTIC","trading_authority":"NONE",
           "source_ack_sha256":None}
        self.assertEqual(digest(a),digest(dict(reversed(list(a.items())))))
        self.assertNotEqual(digest(a),digest({**a,"source_ack_sha256":"f"*64}))

    def test_current_assembled_owner_source_identity(self):
        modules=verify_pinned_modules()
        self.assertEqual(len(modules),3)
        self.assertTrue(all(len(v["git_blob"])==40 and
                            len(v["working_bytes_sha256"])==64
                            for v in modules.values()))


if __name__=="__main__":
    unittest.main()
