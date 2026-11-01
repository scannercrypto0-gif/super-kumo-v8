"""Core B2 test-only input: minimal changed-seam adversarial contract checks."""
from __future__ import annotations

import copy
import unittest

from research_wp_r0.aql_f1_b2_integrity_input import (
    make_b2_test_records, make_b2_evidence_contract, factory_schedules,
)
from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError, hash_f1, digest, validate_f1
from examples.aql_f1_b2_emit_integrity_input import build_b2_input


class TestB2IntegrityInput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = build_b2_input()

    def test_complete_schema_and_deterministic_replay(self):
        again = build_b2_input()
        self.assertEqual(again, self.baseline)
        self.assertEqual(self.baseline["n"], 2)
        self.assertEqual(self.baseline["expected_2n"], 4)
        self.assertEqual(self.baseline["expected_6n"], 12)
        self.assertEqual(self.baseline["contract_sha256"],
                         digest({k: v for k, v in self.baseline.items() if k != "contract_sha256"}))
        pairs = {p["pair_id"] for p in self.baseline["schedule"]}
        self.assertEqual(len(pairs), 2)
        self.assertEqual({(r["pair_id"], r["arm"]) for r in self.baseline["core_projection"]["signal_rows"]},
                         {(p, arm) for p in pairs for arm in ("BASE", "SHADOW")})
        self.assertEqual({r["capture_status"] for r in self.baseline["core_projection"]["signal_rows"]},
                         {"UNVERIFIED"})
        self.assertFalse(self.baseline["original_pit_verified"])
        self.assertFalse(self.baseline["live_f3_connected"])

    def test_test_only_direction_tp_sl_and_observe_only_indicators(self):
        rows = self.baseline["original_candidates_test_only"]
        base = next(r for r in rows if r["arm"] == "BASE" and
                    r["opportunity_id"] == "B2-TEST-OPPORTUNITY-01")
        self.assertEqual(base["direction"], "LONG")
        self.assertEqual(base["reference"]["price"], "100")
        self.assertEqual(base["sl"]["level"], "90")
        self.assertEqual(base["tp"]["level"], "110")
        self.assertEqual(base["arm_strategy_version"], "TEST_ONLY_1")
        self.assertEqual(base["decision_cutoff_ms"], 900000)
        self.assertEqual({x["role"] for x in base["indicators"]},
                         {"DECISION", "OBSERVE_ONLY"})
        self.assertTrue(all(r["research_direction"] is None and
                            not r["directional_outcomes_allowed"]
                            for r in self.baseline["core_projection"]["signal_rows"]))

    def test_duplicate_opportunity_cannot_enter_schedule(self):
        changed = copy.deepcopy(self.baseline)
        changed["schedule"][1] = changed["schedule"][0]
        with self.assertRaisesRegex(CaptureError, "B2_DUPLICATE_OPPORTUNITY"):
            make_b2_evidence_contract(
                changed["schedule"], changed["original_candidates_test_only"],
                changed["host_handoffs"], changed["indicator_registry"])

    def test_changed_host_evidence_fails_hash_check(self):
        changed = copy.deepcopy(self.baseline)
        changed["host_handoffs"][0]["slots"][0]["capture_status"] = "RECORDED"
        with self.assertRaisesRegex(CaptureError, "HOST_HANDOFF_DIGEST"):
            make_b2_evidence_contract(changed["schedule"],
                                      changed["original_candidates_test_only"],
                                      changed["host_handoffs"], changed["indicator_registry"])

    def test_missing_shadow_keeps_denominator_not_silently_dropped(self):
        changed = copy.deepcopy(self.baseline)
        changed["original_candidates_test_only"] = [
            r for r in changed["original_candidates_test_only"]
            if not (r["arm"] == "SHADOW" and
                    r["opportunity_id"] == "B2-TEST-OPPORTUNITY-01")]
        with self.assertRaisesRegex(CaptureError, "MISSING_CAPTURE_SLOT_MISMATCH"):
            make_b2_evidence_contract(changed["schedule"],
                                      changed["original_candidates_test_only"],
                                      changed["host_handoffs"], changed["indicator_registry"])

    def test_source_drift_quarantines_not_promotes(self):
        changed = copy.deepcopy(self.baseline)
        candidate = changed["original_candidates_test_only"][0]
        candidate["source_version"] = "drifted-after-capture"
        candidate["f1_record_sha256"] = hash_f1(candidate)
        result = make_b2_evidence_contract(
            changed["schedule"], changed["original_candidates_test_only"],
            changed["host_handoffs"], changed["indicator_registry"])
        original = next(row for row in result["core_projection"]["signal_rows"]
                        if row["pair_id"] == candidate["pair_id"] and row["arm"] == candidate["arm"])
        self.assertEqual(original["capture_status"], "QUARANTINED")
        self.assertFalse(original["directional_outcomes_allowed"])

    def test_late_source_is_invalid_even_with_recomputed_digest(self):
        changed = copy.deepcopy(self.baseline)
        candidate = changed["original_candidates_test_only"][0]
        candidate["source_available_at_ms"] = candidate["decision_cutoff_ms"] + 1
        candidate["f1_record_sha256"] = hash_f1(candidate)
        with self.assertRaisesRegex(CaptureError, "SOURCE_LATE"):
            validate_f1(candidate, changed["indicator_registry"])
        result = make_b2_evidence_contract(
            changed["schedule"], changed["original_candidates_test_only"],
            changed["host_handoffs"], changed["indicator_registry"])
        base = next(row for row in result["core_projection"]["signal_rows"]
                    if row["pair_id"] == candidate["pair_id"] and row["arm"] == candidate["arm"])
        self.assertEqual(base["capture_status"], "QUARANTINED")

    def test_factory_input_pin_and_independent_absence(self):
        plans = factory_schedules(self.baseline["schedule"])
        self.assertEqual(len(plans), 2)
        self.assertEqual(set(plans[0]), {
            "pair_id", "c2_identity", "experiment_plan_sha256",
            "decision_cutoff_ms", "source_version", "source_bytes_sha256",
            "correction_generation"})
        self.assertEqual(self.baseline["interface_map"]["real_producer_f3"], "NOT_CONNECTED")
        self.assertIn("not called", self.baseline["interface_map"]["original_parent_to_vault"])


if __name__ == "__main__":
    unittest.main()
