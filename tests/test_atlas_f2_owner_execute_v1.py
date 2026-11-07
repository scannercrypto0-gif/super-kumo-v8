"""Owner-local F2 single operator: synthetic negative-only regression coverage.

No genuine private E: files, authentic F2, trial history or source rights.
Tests demand that unknown parents/cost ledgers are NEVER silently invented.
"""
from __future__ import annotations
import inspect
import tempfile
import unittest
from pathlib import Path

from tools import atlas_f2_owner_execute as runner
from tools import atlas_f2_owner_provenance_v1 as collector
from research_wp_r0 import aql_core_f_recovery_readonly_v1 as core
from tools.atlas_f2_owner_factory_packet_v1 import (
    policy_missing, _bar_from_original,
)
from research_wp_r0.aql_factory_authentic_research_admission import _digest


class OwnerF2NegativeTests(unittest.TestCase):
    def test_absent_originals_are_sanitized_without_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            workspace=root/"isolated"
            workspace.mkdir()
            m={
                "schema":runner.SCHEMA,
                "owner_operator_authorized":True,
                "warehouse_root":str(root/"missing-warehouse"),
                "vault_root":str(root/"missing-vault"),
                "recovery_file":str(root/"missing-real-report.json"),
                "policy_file":"",
                "trial_ledger_file":"",
                "inventory_receipts_file":"",
                "isolated_workspace":str(workspace),
            }
            outcome=runner.run(m)
            self.assertEqual(outcome["status"],"PRIVATE_WAIT")
            self.assertEqual(outcome["trading_authority"],"NONE")
            self.assertTrue({"warehouse_root","vault_root","recovery_file",
                             "operator_policy.schema",
                             "operator_policy.costs.fee_entry_bps",
                             "operator_policy.research_window.train_end_exclusive_ms"}.issubset(
                                 set(outcome["missing_fields"])))
            self.assertFalse(any("trial_ledger" in x or "inventory." in x
                                 for x in outcome["missing_fields"]))
            self.assertEqual(list(workspace.iterdir()),[])

    def test_unapproved_manifest_is_denied_without_touching_sources(self):
        self.assertEqual(runner.run({})["missing_fields"],
                         ["operator.manifest_or_authorization"])

    def test_factory_v2_authorized_policy_missing_fields_not_fabricated(self):
        missing=policy_missing(None,None,None)
        expected={
            "operator_policy.schema",
            "operator_policy.owner_operator_authorized",
            "operator_policy.costs",
            "operator_policy.research_window",
            "operator_policy.direction",
            "operator_policy.ambiguity_policy",
            "operator_policy.focus_month",
            "operator_policy.focus_strategy_id",
        }
        expected.update("operator_policy.costs."+k for k in (
            "fee_entry_bps","fee_exit_bps","spread_entry_bps",
            "spread_exit_bps","slippage_entry_bps",
            "slippage_exit_bps","funding_bps_per_bar"))
        expected.update("operator_policy.research_window."+k for k in (
            "train_end_exclusive_ms","embargo_ms","holdout_start_ms",
            "holdout_end_exclusive_ms"))
        self.assertEqual(missing,sorted(expected))
        self.assertFalse(any("trial_ledger" in x or "inventory." in x
                             for x in missing))

    def test_owner_private_exception_diagnostic_is_fixed_enum_and_redacted(self):
        runner._set_stage("RECOVERY_SOURCE_MONTH")
        diagnostic=runner._sanitized_exception(
            FileNotFoundError("E:/PRIVATE/SECRET/source.zip"))
        self.assertEqual(diagnostic,{
            "failure_stage":"RECOVERY_SOURCE_MONTH",
            "failure_class":"FileNotFoundError"})
        self.assertNotIn("PRIVATE",repr(diagnostic))
        runner._set_stage("RECOVERY_MAPPING_VALIDATION")
        self.assertEqual(runner._sanitized_exception(
            ValueError("OHLCV SECRET"))["failure_class"],"ValueError")
        self.assertNotIn("SECRET",repr(runner._sanitized_exception(
            ValueError("OHLCV SECRET"))))
        with self.assertRaisesRegex(ValueError,"AQL_DIAG_UNRECOGNIZED_STAGE"):
            runner._set_stage("USER_PRIVATE_PATH")
        self.assertEqual(runner.CURRENT_STAGE,"RECOVERY_MAPPING_VALIDATION")
        runner._set_stage("MANIFEST_INPUTS")

    def test_scanner_boundary_error_is_classified_without_private_message(self):
        from tools.strategy_service_offline.common import BoundaryError
        runner._set_stage("SCANNER_RECOVERY_DIAGNOSTIC")
        safe=runner._sanitized_exception(BoundaryError(
            "F_DIAG_RECOVERY_LOCAL253_RECOMPUTED_SHA_DRIFT"))
        self.assertEqual(safe,{
            "failure_stage":"SCANNER_RECOVERY_DIAGNOSTIC",
            "failure_class":"ValueError",
            "failure_reason_code":"F_DIAG_RECOVERY_LOCAL253_RECOMPUTED_SHA_DRIFT"})
        private=runner._sanitized_exception(BoundaryError(
            "DEPENDENCY_REFUSED:SECRET_PRIVATE_E_DRIVE"))
        self.assertEqual(private,{
            "failure_stage":"SCANNER_RECOVERY_DIAGNOSTIC",
            "failure_class":"ValueError"})
        self.assertNotIn("SECRET",repr(private))
        runner._set_stage("MANIFEST_INPUTS")

    def test_pinned_scanner_subphase_callback_is_wired_and_redacted(self):
        from tools.scanner_strategy_f import recovery_diagnostic_adapter as adapter
        self.assertTrue(adapter.SAFE_SCANNER_PHASES.issubset(runner.SAFE_STAGES))
        for phase in sorted(adapter.SAFE_SCANNER_PHASES):
            with self.subTest(phase=phase):
                runner._set_stage("SCANNER_RECOVERY_DIAGNOSTIC")
                adapter._safe_phase_callback(runner._set_stage,phase)
                self.assertEqual(runner.CURRENT_STAGE,phase)
                safe=runner._sanitized_exception(
                    ValueError("OWNER_PRIVATE_SOURCE:SECRET"))
                self.assertEqual(safe["failure_stage"],phase)
                self.assertEqual(safe["failure_class"],"ValueError")
                self.assertNotIn("SECRET",repr(safe))
        runner._set_stage("MANIFEST_INPUTS")

    def test_phase_callback_cannot_change_source_verifier_code(self):
        stages=[]
        with self.assertRaisesRegex(ValueError,"CORE_F2_RECOVERY_"):
            collector.collect_recovery_source(
                "/missing-warehouse","/missing-vault","/missing-recovery.json",
                stage_callback=stages.append)
        self.assertEqual(stages,["RECOVERY_REPORT_PIN"])

    def test_source_only_receipt_schema_import_is_explicit_and_core_owned(self):
        # Regression: source derivation emitted schema=SCHEMA without importing
        # that Core constant. Only private E: runs reached the code path.
        self.assertEqual(collector.SCHEMA, core.SCHEMA)
        self.assertEqual(collector.SCHEMA,
                         "aql.core.f2-recovery-readonly-source.v1")

    def test_recovery_report_state_projects_only_to_strict_core_mapping(self):
        row = {
            "month": "2024-01", "state": "DUAL_READBACK_VERIFIED",
            "bars": 2976, "source_sha256": "a"*64,
            "core245_native_query_sha256": "b"*64,
            "core253_local_query_sha256": "c"*64,
        }
        projected = collector._project_verified_recovery_entry(row)
        self.assertEqual(row["state"], "DUAL_READBACK_VERIFIED")
        self.assertEqual(projected["state"], "RAW_AND_DUAL_QUERY_READBACK")
        self.assertEqual(set(projected), core.MONTH_FIELDS - {
            "warehouse_receipt_sha256", "dual_query_map_sha256"})
        self.assertEqual(projected["source_sha256"], row["source_sha256"])
        self.assertEqual(projected["core_245_native_price_query_sha256"],
                         row["core245_native_query_sha256"])
        for forged in ("RAW_AND_DUAL_QUERY_READBACK", "SELECTED",
                       "F5_APPROVED", None, False):
            with self.subTest(forged=forged):
                bad = {**row, "state": forged}
                with self.assertRaisesRegex(
                    ValueError, "CORE_F2_RECOVERY_RECOVERY_ENTRY_STATE_DRIFT"):
                    collector._project_verified_recovery_entry(bad)
        self.assertEqual(row["state"], "DUAL_READBACK_VERIFIED")

    def test_private_derived_bar_hash_is_factory_canonical(self):
        synthetic_test_only={
            "bar_open_ms":1704067200000,"bar_close_ms":1704068099999,
            "open":42000.0,"high":42001.0,"low":41999.0,
            "close":42000.5,"volume":2.0,
        }
        output=_bar_from_original(synthetic_test_only)
        self.assertEqual(output["bar_sha256"],_digest({
            k:v for k,v in output.items() if k!="bar_sha256"}))
        self.assertIsNone(output["known_at_ms"])
        self.assertEqual(output["quality"],"FINAL")

    def test_derivation_fork_only_removes_two_missing_parent_comparisons(self):
        actual=inspect.getsource(collector._derive_existing_month).strip()
        expected=inspect.getsource(core._read_existing_month).strip()
        expected=expected.replace(
            "def _read_existing_month(","def _derive_existing_month(")
        expected=expected.replace(
            "set(untrusted) == MONTH_FIELDS and",
            'set(untrusted) == MONTH_FIELDS - {\n'
            '             "warehouse_receipt_sha256", "dual_query_map_sha256"\n'
            '         } and')
        expected=expected.replace(
            'for k in MONTH_FIELDS if k.endswith("sha256"))',
            'for k in MONTH_FIELDS if k.endswith("sha256")\n'
            '         and k not in {"warehouse_receipt_sha256", "dual_query_map_sha256"})')
        expected=expected.replace(
            '    need(warehouse_receipt["receipt_sha256"] ==\n'
            '         untrusted["warehouse_receipt_sha256"],\n'
            '         "RECOMPUTED_WAREHOUSE_RECEIPT_MISMATCH")',
            '    # Derivation has no caller-provided parent to compare with. This digest\n'
            '    # was recomputed from the original immutable SQLite row, sealed committed\n'
            '    # stage, and separately byte-checked RawVault object above.\n'
            '    need(hexsha(warehouse_receipt["receipt_sha256"]), "DERIVED_WAREHOUSE_SHA")')
        expected=expected.replace(
            '    need(dual["identity_map_sha256"] == untrusted["dual_query_map_sha256"],\n'
            '         "RECOMPUTED_DUAL_MAP_DRIFT")',
            '    # The independent #245/#253 queries have just been recomputed and the\n'
            '    # native dual-query bind verifies both parent seals and original grids.\n'
            '    need(hexsha(dual["identity_map_sha256"]), "DERIVED_DUAL_SHA")')
        self.assertEqual(actual,expected)


if __name__=="__main__":
    unittest.main()
