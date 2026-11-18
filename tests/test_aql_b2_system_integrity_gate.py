"""Changed-path B2 gate tests; no original 2024 ZIP re-download."""
import copy
import unittest
from research_wp_r0.aql_b2_system_integrity_gate import assess


def sample():
    pairs = ["p1", "p2"]
    schedule = [{"pair_id": p, "c2_identity": {"opportunity_id": p},
                 "decision_cutoff_ms": 1704067200000} for p in pairs]
    rows = [{"pair_id": p, "arm": a, "capture_status": "UNVERIFIED",
             "research_direction": None, "directional_outcomes_allowed": False}
            for p in pairs for a in ("BASE", "SHADOW")]
    core = {"schema_version": "aql.b2-core-factory-integrity-input.v1",
            "evidence_class": "TEST_ONLY_CONTROLLED_SYSTEM_INPUT",
            "original_2024_strategy_decisions_supplied": False,
            "original_pit_verified": False, "live_f3_connected": False,
            "n": 2, "expected_2n": 4, "expected_6n": 12,
            "horizons_ms": [14400000, 86400000, 259200000],
            "schedule": schedule,
            "core_projection": {"scheduled_pairs": 2, "arm_denominator": 4,
                                "signal_rows": rows},
            "interface_map": {"market_2024_factory_sha":
                              "54316200aa6887cf8f4e7e752c469361fc250aea"}}
    market = {"schema": "aql.b1.market-only-report.v1",
              "scope": "RETROSPECTIVE_MARKET_ONLY", "observed_bars": 35136,
              "missing_bars": 0, "duplicate_bars": 0,
              "operational_pit_proven": False,
              "horizons": [{"horizon_hours": h, "complete": 35136-c,
                            "censored": c} for h,c in [(4,16),(24,96),(72,288)]]}
    return core, market


class B2IntegrityGateTests(unittest.TestCase):
    def check(self, core, market):
        return assess(core, market, core_sha="a"*64, market_sha="b"*64)

    def test_bounded_contract_does_not_claim_e2e(self):
        result = self.check(*sample())
        self.assertEqual((result["n"], result["observed_2n"]), (2,4))
        self.assertIsNone(result["observed_6n"])
        self.assertEqual(result["result"], "BLOCKED_NOT_END_TO_END")

    def test_duplicate_arm_fails(self):
        c,m = sample()
        c["core_projection"]["signal_rows"][1] = copy.deepcopy(c["core_projection"]["signal_rows"][0])
        with self.assertRaisesRegex(ValueError, "ARM_LOSS"):
            self.check(c,m)

    def test_synthetic_direction_promoted_fails(self):
        c,m = sample()
        c["core_projection"]["signal_rows"][0]["research_direction"] = "LONG"
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_PIT_PROMOTION"):
            self.check(c,m)

    def test_incomplete_market_horizon_fails(self):
        c,m = sample()
        m["horizons"][0]["complete"] -= 1
        with self.assertRaisesRegex(ValueError, "MARKET_HORIZON_DENOMINATOR"):
            self.check(c,m)

    def test_duplicate_opportunity_fails(self):
        c,m = sample()
        c["schedule"][1]["c2_identity"] = c["schedule"][0]["c2_identity"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OPPORTUNITY"):
            self.check(c,m)

    def test_no_future_grid_misalignment(self):
        c,m = sample()
        c["schedule"][0]["decision_cutoff_ms"] += 1
        with self.assertRaisesRegex(ValueError, "CUTOFF_NOT_15M_ALIGNED"):
            self.check(c,m)


if __name__ == "__main__":
    unittest.main()
