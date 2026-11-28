"""WP-R6 adversarial synthetic trial-family and holdout custody acceptance."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, HoldoutEvent, TrialFamilyLedger,
)

T = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)


def family(ids=("a", "b", "c")):
    return FrozenSearchFamily(
        family_id="family-1", protocol_digest="protocol-sha",
        temporal_manifest_digest="manifest-sha", dataset_version="source-v1",
        metric_name="mean-net-return", metric_direction="MAXIMIZE",
        candidate_ids=tuple(ids), alpha=0.05, declared_at=T,
    )


def attempt(candidate, state=AttemptState.COMPLETE, p=0.01):
    return Attempt(candidate_id=candidate, state=state,
                   result_digest="evidence:" + candidate,
                   recorded_at=T + timedelta(minutes=1),
                   marginal_p_value=p if state == AttemptState.COMPLETE else None)


def complete_ledger():
    ledger = TrialFamilyLedger(family())
    ledger.record_attempt(attempt("a", p=0.01))
    ledger.record_attempt(attempt("b", state=AttemptState.FAILED))
    ledger.record_attempt(attempt("c", p=0.2))
    return ledger


class FamilyTests(unittest.TestCase):
    def test_all_trials_count_and_failures_not_discarded(self):
        ledger = complete_ledger()
        report = ledger.report()
        self.assertEqual((report.total_declared, report.complete,
                          report.failed, report.missing), (3, 2, 1, 0))
        self.assertAlmostEqual(dict(report.adjusted_p_values)["a"], 0.03)
        self.assertFalse(report.confirmatory_eligible)

    def test_unlogged_trials_block_selection(self):
        ledger = TrialFamilyLedger(family())
        ledger.record_attempt(attempt("a"))
        self.assertEqual(ledger.report().status, "INCOMPLETE_TRIAL_FAMILY")
        with self.assertRaises(ValueError):
            ledger.select("a", at=T + timedelta(minutes=2))

    def test_unknown_duplicate_and_revised_attempts_rejected(self):
        ledger = TrialFamilyLedger(family())
        with self.assertRaises(ValueError):
            ledger.record_attempt(attempt("unregistered"))
        ledger.record_attempt(attempt("a"))
        with self.assertRaises(ValueError):
            ledger.record_attempt(attempt("a", p=0.000001))

    def test_family_digest_changes_with_population_or_data_revision(self):
        a = family()
        self.assertNotEqual(a.digest, replace(a, candidate_ids=("a", "b")).digest)
        self.assertNotEqual(a.digest, replace(a, dataset_version="corrected").digest)
        self.assertNotEqual(a.digest, replace(a, temporal_manifest_digest="new").digest)

    def test_nonfinite_probability_and_undeclared_scope_rejected(self):
        with self.assertRaises(ValueError):
            attempt("a", p=float("nan"))
        with self.assertRaises(ValueError):
            family(("a", "a"))
        with self.assertRaises(ValueError):
            replace(family(), alpha=float("inf"))
        with self.assertRaises(ValueError):
            replace(family(), metric_direction="UNKNOWN")

    def test_missing_experiment_outcome_evidence_rejected(self):
        with self.assertRaises(ValueError):
            Attempt("a", AttemptState.COMPLETE, "", T, 0.01)
        with self.assertRaises(ValueError):
            Attempt("a", AttemptState.FAILED, "failed", T, 0.1)


class HoldoutTests(unittest.TestCase):
    def test_selection_then_open_does_not_imply_confirmation(self):
        ledger = complete_ledger()
        ledger.select("a", at=T + timedelta(minutes=2))
        self.assertEqual(ledger.report().status, "FROZEN_HOLDOUT_UNOPENED")
        ledger.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=3), "access-audit"))
        self.assertEqual(ledger.report().status, "EXPLORATORY_HOLDOUT_OPENED")
        self.assertFalse(ledger.report().confirmatory_eligible)
        with self.assertRaises(ValueError):
            ledger.record_attempt(attempt("b"))

    def test_tuning_after_open_contaminates(self):
        ledger = complete_ledger()
        ledger.select("a", at=T + timedelta(minutes=2))
        ledger.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=3), "access-audit"))
        ledger.holdout_event(HoldoutEvent("TUNE", T + timedelta(minutes=4), "tuning-log"))
        self.assertTrue(ledger.report().holdout_tainted)
        self.assertEqual(ledger.report().status, "HOLDOUT_CONTAMINATED")

    def test_reopen_explicitly_contaminates(self):
        ledger = complete_ledger()
        ledger.select("a", at=T + timedelta(minutes=2))
        ledger.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=3), "audit"))
        with self.assertRaises(ValueError):
            ledger.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=4), "audit"))
        ledger.holdout_event(HoldoutEvent("REOPEN", T + timedelta(minutes=4), "audit-again"))
        self.assertEqual(ledger.report().status, "HOLDOUT_CONTAMINATED")

    def test_open_before_selection_or_chronology_rejected(self):
        ledger = complete_ledger()
        with self.assertRaises(ValueError):
            ledger.holdout_event(HoldoutEvent("OPEN", T, "audit"))
        with self.assertRaises(ValueError):
            ledger.select("a", at=T)
        ledger.select("a", at=T + timedelta(minutes=2))
        with self.assertRaises(ValueError):
            ledger.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=1), "audit"))
        with self.assertRaises(ValueError):
            ledger.holdout_event(HoldoutEvent("TUNE", T + timedelta(minutes=3), "audit"))

    def test_cannot_select_failed_candidate(self):
        ledger = complete_ledger()
        with self.assertRaises(ValueError):
            ledger.select("b", at=T + timedelta(minutes=2))

    def test_no_hidden_causality_in_selected_pvalue(self):
        ledger = complete_ledger()
        ledger.select("a", at=T + timedelta(minutes=2))
        report = ledger.report()
        self.assertLess(dict(report.adjusted_p_values)["a"], 0.05)
        self.assertFalse(report.confirmatory_eligible)
        self.assertTrue(any("Holm needs" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
