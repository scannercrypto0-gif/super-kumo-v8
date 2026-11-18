"""Acceptance tests for isolated WP-R0; no external dependencies or credentials."""
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import FrozenInstanceError

from research_wp_r0.integrity import (
    Availability, EvidenceGraph, EvidenceState, ExperimentRegistry,
    FrozenProtocol, HoldoutCustody, ResearchAuthority, RunManifest, TemporalFact,
    classify_visibility, deterministic_run, digest, simulate_null_search,
)

UTC = timezone.utc


def t(hour, minute=0, second=0):
    return datetime(2026, 10, 22, hour, minute, second, tzinfo=UTC)


def protocol():
    return FrozenProtocol(
        "hyp-1", digest({"dataset": 1}), "net_expectancy", "all_eligible",
        "simple_momentum", "walkforward_purged", "fee_stress_v1",
        "family_1", "4h",
    )


class TemporalAcceptance(unittest.TestCase):
    def test_future_news_published_before_decision_but_received_after(self):
        news = TemporalFact("news", t(12), t(12, 7), True, "v1")
        result = classify_visibility(news, t(12, 3))
        self.assertEqual(result.classification, Availability.INELIGIBLE)
        self.assertFalse(result.allowed_for_live_equivalent)

    def test_final_candle_after_decision(self):
        candle = TemporalFact("bar", t(12), t(12, 5, 2), True, "v1",
                              final_at=t(12, 5), is_final_bar=True)
        self.assertEqual(classify_visibility(candle, t(12, 4, 59)).reason,
                         "BAR_NOT_FINAL_AT_DECISION")

    def test_missing_receipt_never_live_known(self):
        unknown = TemporalFact("news", t(12), None, False, "v1")
        self.assertEqual(classify_visibility(unknown, t(13)).classification,
                         Availability.UNVERIFIED)

    def test_modeled_replay_separate_from_verified_live(self):
        modeled = TemporalFact("event", t(12), t(12, 1), False, "v1")
        d = classify_visibility(modeled, t(13), allow_modeled_replay=True)
        self.assertEqual(d.classification, Availability.MODELED)
        self.assertFalse(d.allowed_for_live_equivalent)

    def test_final_known_bar_eligible(self):
        bar = TemporalFact("bar", t(12), t(12, 1), True, "v1",
                           final_at=t(12), is_final_bar=True)
        self.assertTrue(classify_visibility(bar, t(12, 2)).allowed_for_live_equivalent)

    def test_final_bar_cannot_be_available_before_finalization(self):
        with self.assertRaises(ValueError):
            TemporalFact("bar", t(12), t(12, 1), True, "v1",
                         final_at=t(12, 5), is_final_bar=True)

    def test_bad_timestamps_fail_closed(self):
        with self.assertRaises(ValueError):
            TemporalFact("bar", datetime(2026, 1, 1), t(12), True, "v1")


class ExperimentAcceptance(unittest.TestCase):
    def test_protocol_immutable_and_digest_stable(self):
        x = protocol()
        self.assertEqual(x.protocol_digest, protocol().protocol_digest)
        with self.assertRaises(FrozenInstanceError):
            x.primary_metric = "different"

    def test_deterministic_replay(self):
        x = protocol()
        manifest = RunManifest(x.protocol_digest, digest([1, 2, 3]),
                               "commit-test", "config-test", "py-stdlib", 14)
        self.assertEqual(deterministic_run(manifest, [1, 2, 3]),
                         deterministic_run(manifest, [1, 2, 3]))
        self.assertNotEqual(deterministic_run(manifest, [1, 2, 3]),
                            deterministic_run(manifest, [1, 2, 4]))

    def test_holdout_peek_then_retune_taints(self):
        custody = HoldoutCustody()
        custody.tune("x")
        self.assertTrue(custody.untouched("x"))
        custody.open("x")
        custody.tune("x")
        self.assertFalse(custody.untouched("x"))
        self.assertIn(("x", "TUNED_AFTER_HOLDOUT"), custody.audit)

    def test_incomplete_publication_blocked_retry_is_idempotent(self):
        r = ExperimentRegistry()
        r.register("exp", protocol())
        r.log_trial("exp", "candidate0", "REJECTED")
        with self.assertRaises(ValueError):
            r.publish("exp", "hash1", complete=False)
        r.publish("exp", "hash1", complete=True)
        r.publish("exp", "hash1", complete=True)
        self.assertEqual(len(r.results), 1)
        self.assertEqual(r.trials["exp"], [("candidate0", "REJECTED")])
        with self.assertRaises(ValueError):
            r.publish("exp", "different", complete=True)
        with self.assertRaises(ValueError):
            r.log_trial("exp", "candidate1", "ACCEPTED")

    def test_null_search_bonferroni_sanity(self):
        result = simulate_null_search(seed=123, replicates=1200, candidates=30)
        # Wide predeclared demonstration bound; not a production statistical certification.
        self.assertLess(result.family_false_positive_rate, 0.09)
        self.assertEqual(result.candidates_per_replicate, 30)
        self.assertGreaterEqual(result.standard_error, 0)


class LineageAcceptance(unittest.TestCase):
    def test_correction_blast_radius(self):
        g = EvidenceGraph()
        g.add_artifact("A")
        g.add_artifact("B")
        g.add_artifact("X", ("A",))
        g.add_artifact("Y", ("X",))
        g.add_artifact("Z", ("B",))
        g.revise("Z", EvidenceState.VALID, "VERIFIED")
        affected = g.invalidate_source("A", "revised")
        self.assertEqual(affected, frozenset({"A", "X", "Y"}))
        self.assertEqual(g.history("Z")[-1].state, EvidenceState.VALID)
        self.assertEqual(g.history("Y")[-1].state, EvidenceState.INVALID)
        self.assertEqual(g.history("Y")[0].state, EvidenceState.UNVERIFIED)

    def test_unknown_parent_rejected_not_silently_valid(self):
        g = EvidenceGraph()
        with self.assertRaises(ValueError):
            g.add_artifact("report", ("missing_partition",))

    def test_research_cannot_promote_or_write_operational_state(self):
        self.assertTrue(ResearchAuthority.authorize("write_research_experiment"))
        for action in ("trader:modify", "gate:approve", "billing:purchase", "operations:modify"):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                ResearchAuthority.authorize(action)


if __name__ == "__main__":
    unittest.main()
