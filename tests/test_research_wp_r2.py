"""WP-R2 acceptance: paired comparison never invents missing trades."""
import unittest

from research_wp_r0.evaluation import (
    EvaluationReport, OpportunityOutcome, OpportunityPair, Resolution, evaluate_paired,
)


def outcome(i, resolution=Resolution.KNOWN, gross=0.01, cost=0.002, group=None):
    common = {"opportunity_id": str(i), "group_id": group or f"day-{i // 5}"}
    if resolution == Resolution.KNOWN:
        return OpportunityOutcome(**common, resolution=resolution, gross_return=gross, execution_cost=cost)
    if resolution == Resolution.AMBIGUOUS:
        return OpportunityOutcome(**common, resolution=resolution, bound_low=-0.05, bound_high=0.08)
    return OpportunityOutcome(**common, resolution=resolution)


def pair(i, b=Resolution.KNOWN, c=Resolution.KNOWN, gain=0.003):
    return OpportunityPair(outcome(i, b), outcome(i, c, gross=0.01 + gain))


class EvaluationAcceptance(unittest.TestCase):
    def test_known_costs_and_frozen_paired_lift(self):
        pairs = [pair(i) for i in range(50)]
        r = evaluate_paired(pairs, block_length=5, replicates=300, seed=29, minimum_paired=20)
        self.assertEqual(r.opportunities, 50)
        self.assertEqual(r.fully_known_pairs, 50)
        self.assertEqual(r.observed_group_count, 10)
        self.assertAlmostEqual(r.paired_net_lift, 0.003)
        self.assertAlmostEqual(r.lift_interval.lower, 0.003)
        self.assertEqual(r.decision, "HISTORICAL_CANDIDATE_ONLY")
        self.assertEqual(r.evidence_status, "EXPLORATORY")

    def test_no_fill_and_missing_not_zero_pnl(self):
        pairs = [pair(i) for i in range(30)]
        pairs[0] = pair(0, c=Resolution.NO_FILL)
        pairs[1] = pair(1, b=Resolution.MISSING)
        pairs[2] = pair(2, c=Resolution.AMBIGUOUS)
        r = evaluate_paired(pairs, block_length=3, replicates=150, seed=2, minimum_paired=10)
        self.assertEqual(r.opportunities, 30)
        self.assertEqual(r.candidate_no_fill, 1)
        self.assertEqual(r.missing_pairs, 1)
        self.assertEqual(r.ambiguous_pairs, 1)
        self.assertEqual(r.fully_known_pairs, 27)
        self.assertEqual(r.evidence_status, "INCOMPLETE_COVERAGE")
        self.assertNotEqual(r.decision, "HISTORICAL_CANDIDATE_ONLY")

    def test_too_few_resolved_returns_insufficient(self):
        pairs = [pair(0), pair(1, c=Resolution.NO_FILL), pair(2, b=Resolution.MISSING)]
        r = evaluate_paired(pairs, block_length=1, replicates=100, seed=3, minimum_paired=2)
        self.assertEqual(r.decision, "NO_PROMOTION")
        self.assertEqual(r.evidence_status, "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(r.lift_interval)

    def test_negative_lift_must_not_be_nominated(self):
        pairs = [pair(i, gain=-0.004) for i in range(40)]
        r = evaluate_paired(pairs, block_length=4, replicates=200, seed=99, minimum_paired=20)
        self.assertEqual(r.decision, "DO_NOT_NOMINATE")

    def test_report_is_deterministic(self):
        pairs = [pair(i, gain=(0.01 if i % 3 == 0 else -0.004)) for i in range(40)]
        args = {"block_length": 4, "replicates": 250, "seed": 6, "minimum_paired": 10}
        self.assertEqual(evaluate_paired(pairs, **args), evaluate_paired(pairs, **args))

    def test_duplicate_identity_and_mismatched_pair_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_paired([pair(1), pair(1)], block_length=1, replicates=100,
                            seed=1, minimum_paired=2)
        with self.assertRaises(ValueError):
            OpportunityPair(outcome(1), outcome(2))
        with self.assertRaises(ValueError):
            OpportunityPair(outcome(1, group="BTC-event"), outcome(1, group="sector-event"))

    def test_no_fill_never_accepts_gross_or_cost(self):
        with self.assertRaises(ValueError):
            OpportunityOutcome("1", "g", Resolution.NO_FILL, gross_return=0.)
        with self.assertRaises(ValueError):
            OpportunityOutcome("1", "g", Resolution.MISSING, execution_cost=0.001)
        with self.assertRaises(ValueError):
            OpportunityOutcome("1", "g", Resolution.AMBIGUOUS, bound_low=0.02, bound_high=-0.01)
        with self.assertRaises(ValueError):
            OpportunityOutcome("1", "g", Resolution.KNOWN, gross_return=0.03, execution_cost=-0.01)

    def test_fees_are_subtracted_and_fill_cost_required(self):
        a = outcome(1, gross=0.02, cost=0.004)
        self.assertAlmostEqual(a.known_net, 0.016)
        with self.assertRaises(ValueError):
            OpportunityOutcome("1", "g", Resolution.KNOWN, gross_return=0.02)

    def test_cannot_claim_minimum_independent_sample_from_one_trade(self):
        r = evaluate_paired([pair(1)], block_length=1, replicates=100,
                            seed=1, minimum_paired=5)
        self.assertEqual(r.decision, "NO_PROMOTION")


if __name__ == "__main__":
    unittest.main()
