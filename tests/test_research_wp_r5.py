"""WP-R5 fail-closed timestamp, universe and comparator acceptance cases."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from research_wp_r0.evaluation import OpportunityOutcome, OpportunityPair, Resolution, evaluate_paired
from research_wp_r0.opportunity_clusters import (
    ClusteredPair, FrozenAccountingPolicy, evaluate_opportunity_clusters,
)
from research_wp_r0.temporal_contract import (
    FrozenTemporalManifest, TemporalOpportunity, validate_temporal_pairs,
)


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(i):
    d = T0 + timedelta(hours=i * 4)
    return TemporalOpportunity(
        opportunity_id=str(i),
        decision_at=d,
        baseline_feature_available_at=d - timedelta(minutes=1),
        candidate_feature_available_at=d - timedelta(minutes=2),
        baseline_horizon_end_at=d + timedelta(hours=1),
        candidate_horizon_end_at=d + timedelta(hours=1),
        baseline_label_available_at=d + timedelta(hours=1, minutes=5),
        candidate_label_available_at=d + timedelta(hours=1, minutes=7),
        opportunity_group_id=f"shock-{i // 2}",
    )


def pair(i):
    g = f"shock-{i // 2}"
    return OpportunityPair(
        OpportunityOutcome(str(i), g, Resolution.KNOWN, 0.01, 0.002),
        OpportunityOutcome(str(i), g, Resolution.KNOWN, 0.012, 0.002),
    )


def manifest(n=12):
    return FrozenTemporalManifest("protocol-sha", "source-snapshot-v1", "60m",
                                  tuple(event(i) for i in range(n)))


class TemporalContractTests(unittest.TestCase):
    def test_structurally_valid_full_ordered_universe(self):
        m = manifest()
        self.assertEqual(validate_temporal_pairs([pair(i) for i in range(12)], m), m.digest)
        self.assertEqual(m.digest, manifest().digest)
        r = evaluate_paired([pair(i) for i in range(12)], block_length=2,
                            replicates=100, seed=3, minimum_paired=4,
                            temporal_manifest=m)
        self.assertTrue(any("STRUCTURALLY_VALIDATED_TEMPORAL_CONTEXT" in x for x in r.notes))
        self.assertEqual(r.decision, "FURTHER_INDEPENDENT_VALIDATION")

    def test_future_feature_receipt_is_rejected(self):
        e = event(1)
        with self.assertRaises(ValueError):
            replace(e, candidate_feature_available_at=e.decision_at + timedelta(seconds=1))

    def test_horizon_mismatch_or_premature_label(self):
        e = event(1)
        with self.assertRaises(ValueError):
            replace(e, candidate_horizon_end_at=e.candidate_horizon_end_at + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            replace(e, baseline_label_available_at=e.baseline_horizon_end_at - timedelta(seconds=1))

    def test_cross_opportunity_horizon_mismatch_rejected(self):
        m = manifest()
        e = m.ordered[3]
        changed = replace(e,
            baseline_horizon_end_at=e.baseline_horizon_end_at + timedelta(minutes=1),
            candidate_horizon_end_at=e.candidate_horizon_end_at + timedelta(minutes=1),
            baseline_label_available_at=e.baseline_label_available_at + timedelta(minutes=1),
            candidate_label_available_at=e.candidate_label_available_at + timedelta(minutes=1))
        with self.assertRaises(ValueError):
            replace(m, ordered=m.ordered[:3] + (changed,) + m.ordered[4:])
        with self.assertRaises(ValueError):
            replace(m, horizon_seconds=0)

    def test_backwards_or_equal_decision_time_rejected(self):
        events = list(manifest().ordered)
        events[1], events[2] = events[2], events[1]
        with self.assertRaises(ValueError):
            replace(manifest(), ordered=tuple(events))
        with self.assertRaises(ValueError):
            replace(manifest(), ordered=(event(0), event(0)))

    def test_no_silent_dropped_no_fill_or_missing(self):
        m = manifest()
        with self.assertRaises(ValueError):
            validate_temporal_pairs([pair(i) for i in range(11)], m)
        wrong = [pair(i) for i in range(12)]
        wrong[0], wrong[1] = wrong[1], wrong[0]
        with self.assertRaises(ValueError):
            validate_temporal_pairs(wrong, m)

    def test_group_and_identity_drift_rejected(self):
        altered = [pair(i) for i in range(12)]
        altered[0] = OpportunityPair(
            OpportunityOutcome("0", "fabricated-group", Resolution.NO_FILL),
            OpportunityOutcome("0", "fabricated-group", Resolution.NO_FILL))
        with self.assertRaises(ValueError):
            validate_temporal_pairs(altered, manifest())

    def test_timezone_required_but_equivalent_offset_canonical(self):
        e = event(2)
        with self.assertRaises(ValueError):
            replace(e, decision_at=e.decision_at.replace(tzinfo=None))
        offset = timezone(timedelta(hours=3))
        changed = replace(e, decision_at=e.decision_at.astimezone(offset))
        self.assertEqual(replace(manifest(), ordered=tuple(
            changed if i == 2 else x for i, x in enumerate(manifest().ordered)
        )).digest, manifest().digest)

    def test_digest_tracks_source_version_and_receipts(self):
        m = manifest()
        self.assertNotEqual(m.digest, replace(m, source_version="corrected-v2").digest)
        e = m.ordered[0]
        changed = replace(e, baseline_feature_available_at=e.baseline_feature_available_at - timedelta(seconds=1))
        self.assertNotEqual(m.digest, replace(m, ordered=(changed,) + m.ordered[1:]).digest)

    def test_r3_adapter_rejects_wrong_denominator(self):
        rows = [ClusteredPair(pair(i), f"shock-{i // 2}", f"sector-{i % 6}")
                for i in range(11)]
        with self.assertRaises(ValueError):
            evaluate_opportunity_clusters(rows,
                policy=FrozenAccountingPolicy("test-v1", True, True),
                replicates=100, seed=2, temporal_manifest=manifest())

    def test_research_screening_still_cannot_promote(self):
        rows = [ClusteredPair(pair(i), f"shock-{i // 2}", f"sector-{i % 6}")
                for i in range(12)]
        result = evaluate_opportunity_clusters(rows,
            policy=FrozenAccountingPolicy("test-v1", True, True),
            replicates=100, seed=2, temporal_manifest=manifest())
        self.assertFalse(result.screening_positive)
        self.assertTrue(any("STRUCTURALLY_VALIDATED_TEMPORAL_CONTEXT" in w
                            for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
