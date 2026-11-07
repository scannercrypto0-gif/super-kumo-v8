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
            self.assertEqual(set(outcome["missing_fields"]),
                             {"warehouse_root","vault_root","recovery_file"})
            self.assertEqual(list(workspace.iterdir()),[])

    def test_unapproved_manifest_is_denied_without_touching_sources(self):
        self.assertEqual(runner.run({})["missing_fields"],
                         ["operator.manifest_or_authorization"])

    def test_factory_ledger_cost_policy_inventory_not_fabricated(self):
        self.assertEqual(policy_missing(None,None,None),[
            "inventory.2024-02.source_receipt_sha256",
            "inventory.2024-08.source_receipt_sha256",
            "inventory.schema",
            "policy.costs","policy.direction","policy.focus_month",
            "policy.focus_strategy_id","policy.research_window",
            "policy.schema","trial_ledger.plan_digest",
            "trial_ledger.schema","trial_ledger.selected_attempt_id",
            "trial_ledger.trials",
        ])

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
