"""Adversarial bounded tests for Factory #250 (TEST_ONLY, no private source)."""
import copy
import unittest

from research_wp_r0.aql_factory_opportunity_comparison_gate import (
    OpportunityGateError, assess_opportunity_comparison,
)


def packet():
    h = "a" * 64
    return {
        "schema": "aql.factory.opportunity-comparison-plan.v1",
        "holdout": "SEALED_UNOPENED",
        "execution_authority": "NONE",
        "candidate_origin": "INDEPENDENT_TEST_ONLY_RESEARCH_SEED",
        "historical_pit": "NOT_ATTESTED",
        "historical_preregistration": False,
        "comparison_plan_frozen_before_evaluation": True,
        "comparison_scope": "DEVELOPMENT_ONLY",
        "development_end_ms": 1733011200000,
        "holdout_start_ms": 1733270400000,
        "embargo_ms": 259200000,
        "source_pins": {
            "archive_sha256": h, "member_sha256": "b" * 64,
            "checksum_sha256": "c" * 64, "core_price_query_sha256": "d" * 64,
        },
        "candidate_generation_sha256": "e" * 64,
        "precalculation_plan_sha256": "f" * 64,
        "trials": [
            {"attempt_id": "a%02d" % i, "family_id": "F%03d" % (i % 7 + 1),
             "state": "PROPOSED"} for i in range(53)
        ],
        "selection_multiplicity": {
            "attempts_examined": 53, "families_examined": 7,
            "selection_policy": "FROZEN_NO_OUTCOME_RETUNING",
            "adjustment_status": "NOT_ESTIMATED",
        },
        "modeled_costs_bps": {
            "fee_entry": "10", "fee_exit": "10",
            "spread_entry": "0", "spread_exit": "0",
            "slippage_entry": "5", "slippage_exit": "5", "funding": "0",
        },
        "cost_scenarios_bps": [
            {"name": "BASE_ASSUMPTION", "total_round_trip_bps": "30"},
            {"name": "HIGHER_COST", "total_round_trip_bps": "50"},
        ],
        "universe_inventory": None,
    }


class OpportunityComparisonGateTests(unittest.TestCase):
    def test_missing_universe_remains_null(self):
        x = assess_opportunity_comparison(packet())
        self.assertIsNone(x["universe_denominator"])
        self.assertIsNone(x["paired_arm_slots"])
        self.assertIsNone(x["base_shadow_comparison"])
        self.assertEqual(x["scientific_result"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(x["trial_attempts"], 53)

    def test_explicit_census_and_two_arms(self):
        x = packet()
        x["universe_inventory"] = {
            "scope": "EXPLICIT_SINGLE_SYMBOL_DEVELOPMENT",
            "coverage": "SUPPLIED_NOT_INDEPENDENTLY_ATTESTED",
            "source_manifest_sha256": "a" * 64,
            "opportunities": [
                {"opportunity_id": "o%d" % i, "bar_open_ms": 1700000000000 + i * 900000,
                 "status": s, "reason": "fixture", "base_status": "UNKNOWN",
                 "shadow_status": "NOT_EVALUATED"}
                for i, s in enumerate(("ELIGIBLE", "INELIGIBLE", "UNSCANNED",
                                        "REJECTED", "UNKNOWN", "MISSING"))
            ],
        }
        y = assess_opportunity_comparison(x)
        self.assertEqual(y["universe_denominator"], 6)
        self.assertEqual(y["paired_arm_slots"], 12)
        self.assertEqual(sum(y["universe_status_counts"].values()), 6)
        self.assertIsNone(y["independent_market_opportunity_denominator"])

    def test_deterministic(self):
        x = packet()
        self.assertEqual(assess_opportunity_comparison(x), assess_opportunity_comparison(copy.deepcopy(x)))

    def test_negative_mutations(self):
        cases = [
            ("holdout", "OPENED"),
            ("execution_authority", "PAPER"),
            ("historical_pit", "ATTESTED"),
            ("historical_preregistration", True),
            ("comparison_plan_frozen_before_evaluation", False),
            ("embargo_ms", 0),
            ("candidate_origin", "HISTORICALLY_REGISTERED"),
        ]
        for key, value in cases:
            with self.subTest(key=key):
                x = packet()
                x[key] = value
                with self.assertRaises(OpportunityGateError):
                    assess_opportunity_comparison(x)

    def test_duplicate_trial_and_missing_attempt(self):
        x = packet()
        x["trials"][1]["attempt_id"] = x["trials"][0]["attempt_id"]
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)
        x = packet()
        x["trials"].pop()
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)

    def test_false_multiplicity(self):
        x = packet()
        x["selection_multiplicity"]["adjustment_status"] = "CORRECTED"
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)

    def test_cost_assumptions_and_sensitivity(self):
        x = packet()
        x["cost_scenarios_bps"][1]["total_round_trip_bps"] = "29"
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)
        x = packet()
        x["modeled_costs_bps"]["slippage_entry"] = "NaN"
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)

    def test_invented_or_duplicate_opportunity(self):
        x = packet()
        o = {"opportunity_id": "o1", "bar_open_ms": 1700000000000,
             "status": "UNKNOWN", "reason": "missing provenance",
             "base_status": "UNKNOWN", "shadow_status": "UNKNOWN"}
        x["universe_inventory"] = {
            "scope": "EXPLICIT_SINGLE_SYMBOL_DEVELOPMENT",
            "coverage": "SUPPLIED_NOT_INDEPENDENTLY_ATTESTED",
            "source_manifest_sha256": "a" * 64,
            "opportunities": [o, copy.deepcopy(o)],
        }
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)
        x["universe_inventory"]["opportunities"] = [o]
        o["shadow_status"] = "WINNER"
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)

    def test_future_opportunity(self):
        x = packet()
        x["universe_inventory"] = {
            "scope": "EXPLICIT_SINGLE_SYMBOL_DEVELOPMENT",
            "coverage": "SUPPLIED_NOT_INDEPENDENTLY_ATTESTED",
            "source_manifest_sha256": "a" * 64,
            "opportunities": [{
                "opportunity_id": "future", "bar_open_ms": x["holdout_start_ms"],
                "status": "UNKNOWN", "reason": "future",
                "base_status": "UNKNOWN", "shadow_status": "UNKNOWN",
            }],
        }
        with self.assertRaises(OpportunityGateError):
            assess_opportunity_comparison(x)


if __name__ == "__main__":
    unittest.main()
