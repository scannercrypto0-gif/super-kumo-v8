"""Synthetic-only acceptance and negative tests for quantitative WP-R1."""
import unittest
from datetime import datetime, timedelta, timezone

from research_wp_r0.statistics import (
    LabelWindow, bonferroni, holm, paired_moving_block_interval,
    purged_forward_folds, synthetic_correlated_null_audit,
)


class MultiplicityTests(unittest.TestCase):
    def test_holm_and_bonferroni_reference_values(self):
        p = [0.01, 0.04, 0.03]
        self.assertEqual(bonferroni(p), (0.03, 0.12, 0.09))
        adjusted = holm(p)
        self.assertAlmostEqual(adjusted[0], 0.03)
        self.assertAlmostEqual(adjusted[1], 0.06)
        self.assertAlmostEqual(adjusted[2], 0.06)
        self.assertTrue(all(a >= original for a, original in zip(adjusted, p)))

    def test_invalid_or_empty_search_family_rejected(self):
        for values in ([], [-0.1], [1.01], [float("nan")], [float("inf")]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    holm(values)

    def test_more_trials_are_not_free(self):
        self.assertGreater(holm([0.012, 0.4, 0.5])[0], holm([0.012])[0])


class UncertaintyTests(unittest.TestCase):
    def test_paired_determinism_and_known_effect(self):
        left = [0.01, 0.04, -0.02, 0.02, -0.01, 0.04] * 8
        right = [v + 0.003 for v in left]
        one = paired_moving_block_interval(left, right, block_length=4, replicates=250, seed=11)
        two = paired_moving_block_interval(left, right, block_length=4, replicates=250, seed=11)
        self.assertEqual(one, two)
        self.assertAlmostEqual(one.effect, 0.003)
        self.assertAlmostEqual(one.lower, 0.003)
        self.assertAlmostEqual(one.upper, 0.003)
        self.assertEqual(one.observations, len(left))

    def test_preserves_aligned_opportunity_and_rejects_missing(self):
        with self.assertRaises(ValueError):
            paired_moving_block_interval([1., 2., 3.], [1., 2.],
                                         block_length=2, replicates=100, seed=3)
        with self.assertRaises(ValueError):
            paired_moving_block_interval([1., float("nan")], [1., 2.],
                                         block_length=2, replicates=100, seed=3)
        with self.assertRaises(ValueError):
            paired_moving_block_interval([0., 1.], [0., 1.],
                                         block_length=3, replicates=100, seed=3)

    def test_block_size_records_dependence_assumption(self):
        baseline = [0., 0.01, 0.02, 0., -0.01] * 10
        candidate = [x + (0.01 if i % 5 < 3 else -0.005)
                     for i, x in enumerate(baseline)]
        result = paired_moving_block_interval(baseline, candidate,
                                              block_length=5, replicates=200, seed=3)
        self.assertEqual(result.block_length, 5)
        self.assertLessEqual(result.lower, result.effect)
        self.assertLessEqual(result.effect, result.upper)


class TimeSplitTests(unittest.TestCase):
    @staticmethod
    def windows(n=12):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [LabelWindow(base + timedelta(days=i),
                            base + timedelta(days=i+2)) for i in range(n)]

    def test_purges_overlapping_outcomes_before_test(self):
        windows = self.windows()
        folds = purged_forward_folds(windows, minimum_training=3, test_size=3)
        self.assertTrue(folds)
        for fold in folds:
            first_test = windows[fold.test_indices[0]].observation_at
            self.assertTrue(all(windows[i].label_end_at <= first_test
                                for i in fold.train_indices))
            self.assertTrue(all(i < fold.test_indices[0] for i in fold.train_indices))
        self.assertNotIn(folds[0].test_indices[0] - 1, folds[0].train_indices)

    def test_embargo_is_respected(self):
        windows = self.windows()
        folds = purged_forward_folds(windows, minimum_training=3,
                                     test_size=3, embargo=timedelta(days=1))
        for fold in folds:
            cutoff = windows[fold.test_indices[0]].observation_at - timedelta(days=1)
            self.assertTrue(all(windows[i].label_end_at <= cutoff
                                for i in fold.train_indices))

    def test_nonchronological_input_rejected(self):
        windows = self.windows()
        windows[2], windows[3] = windows[3], windows[2]
        with self.assertRaises(ValueError):
            purged_forward_folds(windows, minimum_training=2, test_size=2)


class NullAuditTests(unittest.TestCase):
    def test_correlated_null_selection_is_bounded_under_ideal_assumptions(self):
        report = synthetic_correlated_null_audit(
            seed=20261022, replicates=1000, candidates=20, factor_loading=0.75,
        )
        self.assertEqual(report.replicates, 1000)
        self.assertEqual(report.candidates, 20)
        # Demonstration sanity guard only, not a certified financial FWER bound.
        self.assertLess(report.selected_family_rate, 0.09)
        self.assertGreaterEqual(report.monte_carlo_standard_error, 0.)

    def test_invalid_null_parameters(self):
        with self.assertRaises(ValueError):
            synthetic_correlated_null_audit(seed=1, replicates=50,
                                            candidates=10, factor_loading=0.2)
        with self.assertRaises(ValueError):
            synthetic_correlated_null_audit(seed=1, replicates=100,
                                            candidates=10, factor_loading=1.2)


if __name__ == "__main__":
    unittest.main()
