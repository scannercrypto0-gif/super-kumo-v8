"""Focused seam tests. Existing Factory schedule validation is mocked ONLY here;
the consolidated integration gate must use the real Core schedule fixture.
"""
import copy
import unittest
from unittest.mock import patch
from research_wp_r0.aql_factory_research_consumer_seam import build_research_handoff, LabContractError, digest

H = "a" * 64

def sample():
    schedule = {"test_only": True, "artifact_sha256": H, "source": {"source_package_sha256": "b"*64}}
    pairs = {"c"*64: {"opportunity": {"opportunity_id": "opp1", "decision_cutoff_ms": 100}}}
    rows = []
    for arm in ("BASE", "SHADOW"):
        rows.append(dict(pair_id="c"*64, arm=arm, opportunity_id="opp1",
            attempt_id="attempt-"+arm, cohort_id="cohort", strategy_version="v1",
            source_manifest_sha256="d"*64, source_package_sha256="b"*64,
            decision_cutoff_ms=100, feature_available_ms=99,
            feature_snapshot_sha256="e"*64, status="NULL",
            descriptive_outcomes_4_24_72h=None, modeled_trade=None,
            execution_status="NOT_OBSERVED", **{"return":None}))
    envelope = dict(schema="aql.factory.research-consumer-seam.v1", test_only=True,
        execution_status="NOT_OBSERVED", source_schedule_sha256=H,
        source_package_sha256="b"*64, source_manifest_sha256="d"*64,
        cohort_id="cohort", strategy_version="v1", rows=rows)
    return schedule, pairs, envelope

class SeamTests(unittest.TestCase):
    def run_seam(self, mutation=None):
        schedule, pairs, envelope = sample()
        if mutation:
            mutation(envelope)
        with patch("research_wp_r0.aql_factory_research_consumer_seam.validate_schedule", return_value=pairs):
            return build_research_handoff(schedule, envelope)

    def test_conserved_census_and_replay(self):
        a, b = self.run_seam(), self.run_seam()
        self.assertEqual(a, b)
        self.assertEqual(a["arm_slots"], 2)
        self.assertEqual(a["status_counts"]["NULL"], 2)
        self.assertEqual(a["trading_authority"], "NONE")
        self.assertEqual(a["artifact_sha256"], digest({k:v for k,v in a.items() if k!="artifact_sha256"}))

    def test_reject_adversarial_inputs(self):
        cases = [
            lambda x: x.update(source_package_sha256=H),
            lambda x: x["rows"].pop(),
            lambda x: x["rows"][1].update(cohort_id="other"),
            lambda x: x["rows"][0].update(feature_available_ms=101),
            lambda x: x["rows"][0].update(decision_cutoff_ms=101),
            lambda x: x["rows"][0].update(source_manifest_sha256=H),
            lambda x: x["rows"][0].update(status="INVALID"),
            lambda x: x["rows"][0].update(**{"return":0}),
            lambda x: x["rows"][0].update(modeled_trade={"pnl":0}),
            lambda x: x["rows"][0].update(descriptive_outcomes_4_24_72h={"4":0}),
            lambda x: x["rows"][1].update(attempt_id="attempt-BASE"),
            lambda x: x["rows"].append(copy.deepcopy(x["rows"][0])),
            lambda x: x.update(execution_status="OBSERVED"),
        ]
        for mutate in cases:
            with self.subTest(mutate=repr(mutate)):
                with self.assertRaises(LabContractError):
                    self.run_seam(mutate)

if __name__ == "__main__":
    unittest.main()
