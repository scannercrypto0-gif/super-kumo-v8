import unittest

from research_wp_r0.aql_w1_factory_research_consumer import (
    ResearchSelectionV1, project,
)
from research_wp_r0.aql_w1_opportunity_outcomes import (
    BAR_MS, HORIZONS, EvidenceError, RetrospectiveSnapshot, market_outcome,
)


def snapshot(name="a", state="ARMED", eligibility="YES"):
    t = 1704067200000
    return RetrospectiveSnapshot("trial", "manifest", name, name + "-producer",
        name + "-envelope", t, t + 2000, state, "reason", "LONG",
        eligibility, "policy-v1-before-decision" if eligibility == "YES" else None,
        "context")


def outcome(s, *, generation="original"):
    t = s.decision_cutoff_ms
    bars = [dict(open_ms=t + i * BAR_MS, open=100, high=102,
                 low=98, close=100, finalized=True) for i in range(16)]
    return market_outcome(s, HORIZONS[0], bars, source_version="original-ohlc",
                          source_end_exclusive_ms=t + HORIZONS[0],
                          correction_generation=generation)


class FactoryResearchConsumerTest(unittest.TestCase):
    def test_full_denominator_and_no_hindsight(self):
        rows = [snapshot("a"), snapshot("b", "NO_SIGNAL", "NOT_ESTABLISHED"),
                snapshot("c", "ARMED", "YES")]
        r = project(rows, [outcome(s) for s in rows], expected_total=3)
        self.assertEqual(r["scheduled_total"], 3)
        self.assertEqual(r["cohorts"]["F1_ARMED_PREDECISION_ONLY"], 2)
        self.assertEqual(r["cohorts"]["NOT_ESTABLISHED_OR_INELIGIBLE"], 1)
        self.assertEqual(r["eligible_rejected_cohort"], "NOT_ESTABLISHED")
        self.assertTrue(r["no_fill_or_pnl_inference"])

    def test_f3_states_cannot_masquerade_as_f1(self):
        for state in ("REJECTED", "TRIGGERED"):
            with self.subTest(state=state), self.assertRaises(EvidenceError):
                ResearchSelectionV1.from_snapshot(snapshot(state=state))

    def test_rejected_not_automatically_eligible(self):
        s = snapshot(eligibility="NOT_ESTABLISHED")
        self.assertEqual(ResearchSelectionV1.from_snapshot(s).cohort,
                         "NOT_ESTABLISHED_OR_INELIGIBLE")

    def test_typed_f3_is_separate_and_exact_join(self):
        from research_wp_r0.aql_w1_typed_contract import F3EffectV1
        a = snapshot()
        effect = F3EffectV1(a.trial_id, a.opportunity_id, a.producer_event_id,
                            a.envelope_sha256, "REJECTED",
                            "POSITION_ALREADY_OPEN_AT_DECISION", None,
                            "receipt", "archive-v1", "MODELED_NON_EXECUTABLE")
        report = project([a], [outcome(a)], f3_effects=[effect])
        self.assertEqual(report["source_states"], {"ARMED": 1})
        self.assertEqual(report["f3_final_effects"], {"REJECTED": 1})
        with self.assertRaises(EvidenceError):
            project([a], [outcome(a)], f3_effects=[effect, effect])

    def test_no_duplicate_generations_without_explicit_resolution(self):
        s = snapshot()
        with self.assertRaises(EvidenceError):
            project([s], [outcome(s), outcome(s, generation="correction-001")])

    def test_orphan_and_identity_tampering_fail_closed(self):
        s = snapshot()
        other = snapshot("other")
        with self.assertRaises(EvidenceError):
            project([s], [outcome(other)])
        with self.assertRaises(EvidenceError):
            project([s], [{**outcome(s), "source_version": "tampered"}])

    def test_no_executable_or_paper_results(self):
        s = snapshot()
        with self.assertRaises(EvidenceError):
            project([s], [{**outcome(s), "execution_status": "FILLED"}])
        with self.assertRaises(EvidenceError):
            project([s], [{**outcome(s), "reference_kind": "EXECUTABLE_FILL"}])

    def test_evaluated_requires_complete_market_and_metrics(self):
        s = snapshot()
        with self.assertRaises(EvidenceError):
            project([s], [{**outcome(s), "mfe": None}])
        with self.assertRaises(EvidenceError):
            project([s], [{**outcome(s), "window_quality": "MISSING"}])

    def test_denominator_and_duplicate_source_fail_closed(self):
        s = snapshot()
        with self.assertRaises(EvidenceError):
            project([s], [], expected_total=653)
        with self.assertRaises(EvidenceError):
            project([s, s], [])


if __name__ == "__main__":
    unittest.main()
