"""WP-R3 synthetic opportunity accounting and clustered-dependence tests."""
import unittest

from research_wp_r0.evaluation import OpportunityOutcome, OpportunityPair, Resolution
from research_wp_r0.opportunity_clusters import (
    ClusteredPair, FrozenAccountingPolicy, evaluate_opportunity_clusters,
)

STRICT = FrozenAccountingPolicy("zero-exposure-no-fee-v1", True, True, minimum_clusters=5)
UNKNOWN_COSTS = FrozenAccountingPolicy("cost-unknown-v1", True, False, minimum_clusters=5)


def outcome(n, market, resolution, *, gross=0.01, cost=0.002):
    if resolution == Resolution.KNOWN:
        return OpportunityOutcome(str(n), market, resolution, gross_return=gross,
                                  execution_cost=cost)
    if resolution == Resolution.AMBIGUOUS:
        return OpportunityOutcome(str(n), market, resolution, bound_low=-0.05,
                                  bound_high=0.04)
    return OpportunityOutcome(str(n), market, resolution)


def row(n, baseline=Resolution.KNOWN, candidate=Resolution.KNOWN,
        *, gain=0.003, market=None, sector=None):
    market = market or f"market-{n // 4}"
    sector = sector or f"sector-{n % 6}"
    b = outcome(n, market, baseline)
    c = outcome(n, market, candidate, gross=0.01 + gain)
    return ClusteredPair(OpportunityPair(b, c), market, sector)


def evaluate(rows, *, policy=STRICT):
    return evaluate_opportunity_clusters(rows, policy=policy,
                                         replicates=300, seed=53)


class NoFillAccountingTests(unittest.TestCase):
    def test_confirmed_no_fill_zero_exposure_only_under_frozen_policy(self):
        rows = [row(i) for i in range(60)]
        rows[0] = row(0, candidate=Resolution.NO_FILL)
        rows[1] = row(1, baseline=Resolution.NO_FILL)
        result = evaluate(rows)
        self.assertEqual(result.denominator, 60)
        self.assertEqual(result.complete_pairs, 60)
        self.assertEqual(result.candidate_no_fills, 1)
        self.assertEqual(result.baseline_no_fills, 1)
        self.assertEqual(result.baseline_executed, 59)
        self.assertEqual(result.candidate_executed, 59)
        self.assertEqual(result.status, "EXPLORATORY_CLUSTER_SCREEN")
        self.assertIsNotNone(result.realized_policy_net_lift)

    def test_unknown_no_fill_fees_prevents_zero_assumption(self):
        rows = [row(i) for i in range(60)]
        rows[0] = row(0, candidate=Resolution.NO_FILL)
        result = evaluate(rows, policy=UNKNOWN_COSTS)
        self.assertEqual(result.complete_pairs, 59)
        self.assertEqual(result.status, "INCOMPLETE_COVERAGE")
        self.assertFalse(result.nomination_eligible)

    def test_missing_and_ambiguous_are_never_imputed(self):
        rows = [row(i) for i in range(60)]
        rows[0] = row(0, candidate=Resolution.MISSING)
        rows[1] = row(1, baseline=Resolution.AMBIGUOUS)
        result = evaluate(rows)
        self.assertEqual(result.unknown_pairs, 1)
        self.assertEqual(result.ambiguous_pairs, 1)
        self.assertEqual(result.complete_pairs, 58)
        self.assertFalse(result.nomination_eligible)
        self.assertEqual(result.status, "INCOMPLETE_COVERAGE")

    def test_all_missing_is_insufficient_not_zero(self):
        rows = [row(i, candidate=Resolution.MISSING) for i in range(20)]
        result = evaluate(rows)
        self.assertIsNone(result.realized_policy_net_lift)
        self.assertEqual(result.status, "INSUFFICIENT_EVIDENCE")


class GroupSensitivityTests(unittest.TestCase):
    def test_dual_axis_interval_and_determinism(self):
        rows = [row(i, gain=(0.009 if i % 4 else -0.002))
                for i in range(120)]
        a, b = evaluate(rows), evaluate(rows)
        self.assertEqual(a, b)
        self.assertEqual(a.market_interval.independent_groups, 30)
        self.assertEqual(a.sector_interval.independent_groups, 6)
        self.assertLessEqual(a.sensitivity_lower, a.sensitivity_upper)
        self.assertEqual(a.denominator, 120)

    def test_one_shared_market_event_blocks_claim(self):
        rows = [row(i, market="btc-crash") for i in range(60)]
        result = evaluate(rows)
        self.assertEqual(result.status, "INSUFFICIENT_CLUSTER_DIVERSITY")
        self.assertFalse(result.nomination_eligible)
        self.assertIsNone(result.market_interval)

    def test_one_sector_blocks_claim_even_with_multiple_market_shocks(self):
        rows = [row(i, sector="memecoins") for i in range(60)]
        result = evaluate(rows)
        self.assertEqual(result.status, "INSUFFICIENT_CLUSTER_DIVERSITY")
        self.assertIsNone(result.sector_interval)

    def test_no_duplicates_or_forged_market_cluster(self):
        rows = [row(i) for i in range(30)]
        with self.assertRaises(ValueError):
            evaluate(rows + [rows[0]])
        with self.assertRaises(ValueError):
            ClusteredPair(rows[0].pair, "wrong-shock", "sector-A")

    def test_negative_gain_screen_does_not_pass(self):
        rows = [row(i, gain=-0.008) for i in range(72)]
        result = evaluate(rows)
        self.assertFalse(result.nomination_eligible)
        self.assertLess(result.realized_policy_net_lift, 0)

    def test_invalid_policy_and_bootstrap_rejected(self):
        with self.assertRaises(ValueError):
            FrozenAccountingPolicy("", True, True)
        with self.assertRaises(ValueError):
            evaluate_opportunity_clusters([row(0)], policy=STRICT,
                                          replicates=1, seed=2)


if __name__ == "__main__":
    unittest.main()
