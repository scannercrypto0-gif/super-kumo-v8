"""Changed-seam TEST_ONLY negative tests for Core P2 contract."""
import unittest
from dataclasses import replace

from research_wp_r0.aql_p2_core_producer import (
    BAR_MS, EMBARGO_MIN_MS, ContractError, FrozenTrialV1, HistoricalBarV1,
    HistoricalSourceV1, P2HistoricalOpportunityV1, schedule_pair, validate_bars,
)

H = "a" * 64
J = "b" * 64
K = "c" * 64
L = "d" * 64
START = 1704067200000


def fixture():
    source = HistoricalSourceV1("TEST_ONLY_SOURCE", "BINANCE", "SPOT",
                                "BTCUSDT", H, J, K, "TEST_ONLY_ORIGINAL")
    bars = tuple(HistoricalBarV1(START + i * BAR_MS,
                                START + (i + 1) * BAR_MS - 1, H)
                 for i in range(5))
    cutoff = START + 2 * BAR_MS
    trial = FrozenTrialV1.seal(
        trial_id="TEST_ONLY_TRIAL", hypothesis_sha256=H,
        base_definition_sha256=J, shadow_definition_sha256=K,
        preregistration_sha256=L,
        train_end_exclusive_ms=START + 6 * BAR_MS,
        holdout_start_ms=START + 6 * BAR_MS + EMBARGO_MIN_MS,
        holdout_end_exclusive_ms=START + 6 * BAR_MS + EMBARGO_MIN_MS + BAR_MS)
    item = P2HistoricalOpportunityV1(
        trial_id=trial.trial_id, opportunity_id="TEST_ONLY_OPP",
        producer_event_id="TEST_ONLY_EVENT", source_id=source.source_id,
        source_package_sha256=source.source_package_sha256,
        feature_prefix_sha256=H, policy_sha256=J,
        decision_cutoff_ms=cutoff, decision_ms=cutoff + 2000,
        disposition="NO_SIGNAL", direction=None, direction_evidence_ref=None,
        regime=None, regime_source_sha256=None)
    return trial, source, bars, item


class CoreP2ContractsTests(unittest.TestCase):
    def test_valid_deterministic_two_arm_schedule(self):
        trial, source, bars, item = fixture()
        first = schedule_pair(trial, source, bars, (item,))
        self.assertEqual(first, schedule_pair(trial, source, bars, (item,)))
        self.assertEqual([arm["arm"] for arm in first["pairs"][0]["arms"]],
                         ["BASE", "SHADOW"])
        self.assertEqual(first["scheduled_total"], 1)
        self.assertEqual(first["outcome_evaluation"], "NOT_PERFORMED")
        self.assertEqual(first["holdout_status"], "SEALED_UNOPENED")
        self.assertEqual(first["pairs"][0]["opportunity"]["disposition"], "NO_SIGNAL")
        self.assertIsNone(first["pairs"][0]["opportunity"]["direction"])

    def test_native_gap_rejected(self):
        _, source, bars, _ = fixture()
        with self.assertRaisesRegex(ContractError, "SOURCE_GAP"):
            validate_bars(source, (bars[0], bars[2]))

    def test_duplicate_bar_rejected(self):
        _, source, bars, _ = fixture()
        with self.assertRaisesRegex(ContractError, "DUPLICATE"):
            validate_bars(source, (bars[0], bars[0]))

    def test_unfinalized_bar_rejected(self):
        _, source, bars, _ = fixture()
        with self.assertRaisesRegex(ContractError, "UNFINALIZED"):
            validate_bars(source, (replace(bars[0], finalized=False),))

    def test_wrong_interval_rejected(self):
        with self.assertRaisesRegex(ContractError, "BAD_NATIVE_INTERVAL"):
            HistoricalBarV1(START, START + BAR_MS, H)

    def test_availability_without_evidence_rejected(self):
        with self.assertRaisesRegex(ContractError, "UNSUPPORTED_KNOWN_AT"):
            HistoricalBarV1(START, START + BAR_MS - 1, H,
                            available_at_ms=START + BAR_MS)

    def test_future_available_prefix_rejected(self):
        trial, source, bars, item = fixture()
        updated = replace(bars[0], available_at_ms=item.decision_cutoff_ms + 1,
                          availability_evidence_ref="TEST_ONLY_REF")
        with self.assertRaisesRegex(ContractError, "KNOWN_AFTER_CUTOFF"):
            schedule_pair(trial, source, (updated,) + bars[1:], (item,))

    def test_pit_upgrade_rejected(self):
        trial, source, bars, item = fixture()
        with self.assertRaisesRegex(ContractError, "NO_HISTORICAL_PIT"):
            replace(source, evidence_class="HISTORICAL_PIT")
        with self.assertRaisesRegex(ContractError, "NO_PIT_UPGRADE"):
            replace(item, evidence_class="PIT")

    def test_unverified_direction_rejected(self):
        _, _, _, item = fixture()
        with self.assertRaisesRegex(ContractError, "DIRECTION_WITHOUT"):
            replace(item, direction="LONG")

    def test_unverified_regime_rejected(self):
        _, _, _, item = fixture()
        with self.assertRaisesRegex(ContractError, "REGIME_WITHOUT"):
            replace(item, regime="VOLATILE")

    def test_missing_state_preserved(self):
        trial, source, bars, item = fixture()
        for state in ("UNKNOWN", "REJECTED", "NO_SIGNAL", "TRIGGERED"):
            got = schedule_pair(trial, source, bars, (replace(item, disposition=state),))
            self.assertEqual(got["pairs"][0]["opportunity"]["disposition"], state)

    def test_protocol_digest_tamper_rejected(self):
        trial, _, _, _ = fixture()
        with self.assertRaisesRegex(ContractError, "UNSEALED"):
            replace(trial, hypothesis_sha256=K)

    def test_shadow_same_as_base_rejected(self):
        trial, _, _, _ = fixture()
        with self.assertRaisesRegex(ContractError, "SHADOW_NOT"):
            FrozenTrialV1.seal(trial_id=trial.trial_id, hypothesis_sha256=H,
                               base_definition_sha256=J, shadow_definition_sha256=J,
                               preregistration_sha256=L,
                               train_end_exclusive_ms=trial.train_end_exclusive_ms,
                               holdout_start_ms=trial.holdout_start_ms,
                               holdout_end_exclusive_ms=trial.holdout_end_exclusive_ms)

    def test_short_embargo_rejected(self):
        trial, _, _, _ = fixture()
        with self.assertRaisesRegex(ContractError, "EMBARGO_TOO_SHORT"):
            FrozenTrialV1.seal(trial_id=trial.trial_id, hypothesis_sha256=H,
                               base_definition_sha256=J, shadow_definition_sha256=K,
                               preregistration_sha256=L,
                               train_end_exclusive_ms=trial.train_end_exclusive_ms,
                               holdout_start_ms=trial.holdout_start_ms,
                               holdout_end_exclusive_ms=trial.holdout_end_exclusive_ms,
                               embargo_ms=EMBARGO_MIN_MS - 1)

    def test_holdout_access_rejected(self):
        trial, source, bars, item = fixture()
        with self.assertRaisesRegex(ContractError, "HOLDOUT_LOCKED"):
            schedule_pair(trial, source, bars, (item,), permit_holdout=True)
        with self.assertRaisesRegex(ContractError, "HOLDOUT_OR_EMBARGO"):
            schedule_pair(trial, source, bars,
                          (replace(item, decision_cutoff_ms=trial.holdout_start_ms,
                                   decision_ms=trial.holdout_start_ms + 1),))

    def test_duplicate_opportunities_rejected(self):
        trial, source, bars, item = fixture()
        with self.assertRaisesRegex(ContractError, "DUPLICATE_OPPORTUNITY"):
            schedule_pair(trial, source, bars, (item, item))

    def test_cross_source_rejected(self):
        trial, source, bars, item = fixture()
        with self.assertRaisesRegex(ContractError, "CROSS_TRIAL_OR_SOURCE"):
            schedule_pair(trial, source, bars, (replace(item, source_package_sha256=K),))

    def test_no_outcome_dependent_schedule(self):
        trial, source, bars, item = fixture()
        result = schedule_pair(trial, source, bars, (item,))
        self.assertNotIn("profit", str(result).lower())
        self.assertNotIn("uplift", str(result).lower())
        self.assertEqual(len(result["pairs"][0]["arms"]), 2)


if __name__ == "__main__":
    unittest.main()
