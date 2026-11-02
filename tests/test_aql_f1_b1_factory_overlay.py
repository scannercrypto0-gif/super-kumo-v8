"""Core B1 ↔ pinned Factory #209 adapter compatibility (read-only overlay only).

Requires factory aql_w1_f1_prospective_consumer.py copied from exact pinned
Factory SHA in CI. No cross-PR merge and no independent PIT attestation.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import digest, hash_f1
from research_wp_r0.aql_f1_prospective_host_v1 import run_prospective_host
from research_wp_r0.aql_f1_research_signal_handoff_v1 import project_original_signal_handoffs
from research_wp_r0.aql_w1_f1_prospective_consumer import project_core_verified_f1_slots
from tests.test_aql_f1_decision_capture_v1 import fixture
from tests.test_aql_f1_prospective_bridge import envelope
from tests.test_aql_f1_b1_research_signal_handoff import _schedule


class B1FactoryAdapterTests(unittest.TestCase):
    def test_two_pair_core_factory_status_and_six_n_horizons(self):
        base, registry = fixture()
        shadow, _ = fixture("SHADOW")
        records, plans, handoffs = [], [], []
        with tempfile.TemporaryDirectory() as root:
            for index in range(2):
                a, b = copy.deepcopy(base), copy.deepcopy(shadow)
                for rec in (a, b):
                    rec["opportunity_id"] = f"opportunity-{index}"
                    rec["c2_identity"]["opportunity_id"] = rec["opportunity_id"]
                    rec["pair_id"] = digest({
                        "experiment_plan_sha256": rec["experiment_plan_sha256"],
                        "c2_identity": rec["c2_identity"]})
                    rec["f1_record_sha256"] = hash_f1(rec)
                handoffs.append(run_prospective_host(
                    envelope(a), a["experiment_plan_sha256"],
                    {"BASE": a, "SHADOW": b}, registry, Path(root) / str(index),
                    pre_f3_gate=lambda _: True))
                plans.append(_schedule(a))
                records.extend((a, b))
            core = project_original_signal_handoffs(plans, handoffs, records, registry)
            factory = project_core_verified_f1_slots(
                plans, records, indicator_registry=registry)
        self.assertEqual(core["arm_denominator"], 4)
        self.assertEqual(factory["arm_slots"], 4)
        self.assertEqual(factory["outcome_rows"], 12)
        core_by_pair_arm = {(r["pair_id"], r["arm"]): r["capture_status"]
                            for r in core["signal_rows"]}
        for row in factory["outcomes"]:
            self.assertEqual(row["capture_status"], core_by_pair_arm[row["pair_id"], row["arm"]])
            self.assertEqual(row["capture_status"], "UNVERIFIED")
            self.assertEqual(row["coverage_status"], "UNKNOWN")
            self.assertEqual(row["measurement_class"], "MARKET_ONLY")
            self.assertIsNone(row["max_favorable"])
            self.assertIsNone(row["max_adverse"])
            self.assertTrue(row["no_fill_or_pnl_inference"])

    def test_source_vintage_drift_never_becomes_recorded(self):
        original, registry = fixture()
        shadow, _ = fixture("SHADOW")
        changed = copy.deepcopy(original)
        changed["source_version"] = "tampered-but-rehashed"
        changed["f1_record_sha256"] = hash_f1(changed)
        plan = _schedule(original)
        with tempfile.TemporaryDirectory() as root:
            h = run_prospective_host(
                envelope(changed), changed["experiment_plan_sha256"],
                {"BASE": changed, "SHADOW": shadow}, registry, Path(root),
                pre_f3_gate=lambda _: True)
            core = project_original_signal_handoffs([plan], [h], [changed, shadow], registry)
        factory = project_core_verified_f1_slots(
            [plan], [changed, shadow],
            indicator_registry=registry, proof_verifier=lambda _: True)
        self.assertEqual(core["signal_rows"][0]["capture_status"], "QUARANTINED")
        base_rows = [row for row in factory["outcomes"] if row["arm"] == "BASE"]
        self.assertTrue(all(row["capture_status"] == "QUARANTINED" for row in base_rows))
        self.assertTrue(all(row["max_favorable"] is None and row["max_adverse"] is None
                            for row in base_rows))


if __name__ == "__main__":
    unittest.main()
