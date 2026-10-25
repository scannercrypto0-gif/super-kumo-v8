"""Focused full-plan integrity tests; no evaluator or paper-trading side effects."""
import unittest

from research_wp_r0.frozen_research_plan import (
    commit_research_plan, verify_research_plan,
)


def fixture():
    return commit_research_plan(
        "Family1", [("Candidate1", "a" * 64)],
        protocol_digest="b" * 64, dataset_digest="c" * 64,
        split_digest="d" * 64, baseline_digest="e" * 64,
        metrics=["net_return", "max_drawdown"],
        selection_rule={"kind": "predeclared", "objective": "net_return"},
        cost_model={"fee_bps": 10, "slippage_bps": 5},
    )


class FrozenResearchPlanTests(unittest.TestCase):
    def test_round_trip(self):
        raw, commitment = fixture()
        plan = verify_research_plan(raw, commitment)
        self.assertEqual(plan["metrics"], ["net_return", "max_drawdown"])

    def test_modified_digest_fails(self):
        raw, _ = fixture()
        with self.assertRaises(ValueError):
            verify_research_plan(raw, "0" * 64)

    def test_modified_bytes_fails(self):
        raw, commitment = fixture()
        with self.assertRaises(ValueError):
            verify_research_plan(raw.replace(b"net_return", b"gross_gain"), commitment)

    def test_duplicate_candidate_fails(self):
        with self.assertRaises(ValueError):
            commit_research_plan(
                "Family1", [("Candidate1", "a" * 64), ("Candidate1", "a" * 64)],
                protocol_digest="b" * 64, dataset_digest="c" * 64,
                split_digest="d" * 64, baseline_digest="e" * 64,
                metrics=["net_return"], selection_rule={"kind": "fixed"},
                cost_model={"fee_bps": 10},
            )

    def test_missing_metrics_fails(self):
        with self.assertRaises(ValueError):
            commit_research_plan(
                "Family1", [("Candidate1", "a" * 64)],
                protocol_digest="b" * 64, dataset_digest="c" * 64,
                split_digest="d" * 64, baseline_digest="e" * 64,
                metrics=[], selection_rule={"kind": "fixed"},
                cost_model={"fee_bps": 10},
            )


if __name__ == "__main__":
    unittest.main()
