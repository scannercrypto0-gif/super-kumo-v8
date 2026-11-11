"""B3 changed-seam tests: exact Core parent handoff -> real Vault -> Factory.

Reuses independently published Core B2/B3 artifact bytes. No B1/B2 suite rerun.
"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_b3_core_parent_factory_overlay import (
    CORE_B2_DIGEST, CORE_B3_DIGEST, run_pinned_core_parent_factory, sha,
)
from research_wp_r0.aql_f1_b3_vault_parent_adapter import (
    parent_input_for_pair, exercised_vault_parent, bound_parent_evidence,
)
from research_wp_r0.aql_f1_parent_witness_v1 import validate_parent_binding
from research_wp_r0.aql_w1_f1_prospective_consumer import project_parent_authenticated_f1_slots
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline import schema as vault_schema


class FactoryB3PinnedCoreParentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        b2 = Path(os.environ.get("AQL_B3_CORE_B2", "/tmp/aql-b3-core-b2.json"))
        b3 = Path(os.environ.get("AQL_B3_CORE_B3", "/tmp/aql-b3-core-b3.json"))
        if not b2.is_file() or not b3.is_file():
            raise unittest.SkipTest("Pinned actual Core artifacts missing")
        cls.raw_b2, cls.raw_b3 = b2.read_bytes(), b3.read_bytes()
        assert sha(cls.raw_b2) == CORE_B2_DIGEST
        assert sha(cls.raw_b3) == CORE_B3_DIGEST
        cls.core = json.loads(cls.raw_b2)

    def first_parent(self, root: Path):
        plan = self.core["schedule"][0]
        rows = [r for r in self.core["original_candidates_test_only"]
                if r["pair_id"] == plan["pair_id"]]
        p = parent_input_for_pair(plan, rows)
        retained = exercised_vault_parent(p, RawVault(root), vault_schema)
        return plan, rows, retained

    def test_exact_core_b3_actual_vault_factory_n_2n_6n_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            a = run_pinned_core_parent_factory(self.raw_b2, self.raw_b3, Path(temp))
            b = run_pinned_core_parent_factory(self.raw_b2, self.raw_b3, Path(temp))
        self.assertEqual(a, b)
        self.assertEqual((a["N"], a["observed_2N"], a["observed_6N"]), (2,4,12))
        self.assertEqual(len(a["real_vault_parent_objects"]), 2)
        self.assertEqual(len(a["core_parent_original_F1_arm_bindings"]), 4)
        self.assertEqual(a["per_seam"]["readback_Core_parent_to_real_Factory_parent_consumer"],
                         "PASS_FAIL_CLOSED")

    def test_changed_exact_pinned_core_handoff_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "PINNED_CORE_B3_HANDOFF_DRIFT"):
                run_pinned_core_parent_factory(self.raw_b2, self.raw_b3+b"x", Path(temp))

    def test_changed_f1_source_vintage_refused_by_core_parent_seam(self):
        plan = copy.deepcopy(self.core["schedule"][0])
        originals = copy.deepcopy([r for r in self.core["original_candidates_test_only"]
                                   if r["pair_id"] == plan["pair_id"]])
        plan["source_version"] = "FORGED_SOURCE_VERSION"
        with self.assertRaises(Exception):
            parent_input_for_pair(plan, originals)

    def test_missing_shadow_refused_by_core_parent_seam(self):
        plan = self.core["schedule"][0]
        one = [r for r in self.core["original_candidates_test_only"]
               if r["pair_id"] == plan["pair_id"] and r["arm"] == "BASE"]
        with self.assertRaises(Exception):
            parent_input_for_pair(plan, one)

    def test_late_published_source_cannot_pass_even_controlled_structure(self):
        with tempfile.TemporaryDirectory() as temp:
            plan, rows, retained = self.first_parent(Path(temp))
            b = bound_parent_evidence(
                rows[0], retained,
                source_published_at_ms=plan["decision_cutoff_ms"]+1,
                source_finalized_at_ms=plan["decision_cutoff_ms"],
                correction_published_at_ms=plan["decision_cutoff_ms"]+1,
            )
        self.assertFalse(b["structural_parent_binding_test_only"])
        self.assertFalse(b["independent_parent_proof"])

    def test_forged_parent_manifest_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            plan, rows, retained = self.first_parent(Path(temp))
            record = rows[0]
            evidence = bound_parent_evidence(
                record, retained,
                source_published_at_ms=record["source_available_at_ms"],
                source_finalized_at_ms=record["source_asof_ms"],
                correction_published_at_ms=record["source_available_at_ms"],
            )
            allowed = validate_parent_binding(
                record, evidence["raw_parent_binding"],
                parent_manifest_bytes=retained["manifest_bytes"]+b"forged",
                parent_bytes=retained["parent_bytes"], parent_witness=lambda _: True,
            )
        self.assertFalse(allowed)

    def test_no_real_witness_never_authorizes_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            _, rows, retained = self.first_parent(Path(temp))
            record = rows[0]
            evidence = bound_parent_evidence(
                record, retained,
                source_published_at_ms=record["source_available_at_ms"],
                source_finalized_at_ms=record["source_asof_ms"],
                correction_published_at_ms=record["source_available_at_ms"],
            )
            self.assertTrue(evidence["structural_parent_binding_test_only"])
            self.assertFalse(validate_parent_binding(
                record, evidence["raw_parent_binding"],
                parent_manifest_bytes=retained["manifest_bytes"],
                parent_bytes=retained["parent_bytes"], parent_witness=None,
            ))

    def test_missing_vault_parent_not_silently_a_market_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            plan, _, retained = self.first_parent(Path(temp))
            p = plan["pair_id"]
            result = project_parent_authenticated_f1_slots(
                self.core["schedule"], self.core["original_candidates_test_only"],
                parent_bytes_by_pair={p: retained["parent_bytes"]},
                manifest_by_pair={p: retained["vault_manifest_record"]},
                derived_bars_by_pair={}, derived_evidence_by_pair={},
                indicator_registry=self.core["indicator_registry"],
            )
        self.assertEqual(result["arm_slots"], 4)
        self.assertEqual(result["outcome_rows"], 12)
        self.assertTrue(all(x["capture_status"] == "UNVERIFIED" and
                            x["coverage_status"] == "UNKNOWN"
                            for x in result["outcomes"]))


if __name__ == "__main__":
    unittest.main()
