"""TEST_ONLY negative/positive tests: no original market outcomes or intake replay."""
import unittest
from dataclasses import replace
from unittest.mock import patch

from research_wp_r0.aql_p2_core_producer import (
    BAR_MS, ContractError, HistoricalBarV1, HistoricalSourceV1,
)
from research_wp_r0 import aql_p2_breakout_trial as module

H = "a" * 64
J = "b" * 64
K = "c" * 64
PROOF = "c224025885b5186732fa21755c0f3fa7042f03c44d19f1b566be454a31518b44"
DATASET = "BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1"
N = 35


def synthetic_cohort():
    """35 invented bars; the original 2784/2976 source bytes are NOT used."""
    pin = module.SOURCE_ARCHIVES[DATASET]
    source = HistoricalSourceV1(
        DATASET, "BINANCE", "SPOT", "BTCUSDT",
        pin[2], module.MANIFEST_SHA, pin[3], "UNKNOWN_NOT_ATTESTED")
    bars, rows = [], []
    for i in range(N):
        op = module.FEB_START + i * BAR_MS
        content_hash = H if i != 20 else K
        bars.append(HistoricalBarV1(op, op + BAR_MS - 1, content_hash))
        high = "103" if i == 20 else "112" if i == 25 else "121" if i == 33 else "101"
        close = "102" if i == 20 else "111" if i == 25 else "120" if i == 33 else "100"
        rows.append({
            "dataset_id": DATASET, "open_ms": op, "close_ms": op+BAR_MS-1,
            "bar_sha256": content_hash, "open": "100", "high": high,
            "low": "99", "close": close,
        })
    return source, tuple(bars), tuple(rows)


class BreakoutTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._patch = patch.dict(module.SOURCE_ARCHIVES, {
            DATASET: (module.FEB_START, module.FEB_START + N*BAR_MS,
                      module.SOURCE_ARCHIVES[DATASET][2], J)
        }, clear=True)
        cls._patch.start()

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()

    def setUp(self):
        self.source, self.bars, self.rows = synthetic_cohort()
        self.spec, self.trial = module.seal_protocol()

    def handoff(self, *, rows=None, bars=None, source=None, trial=None, proof=PROOF):
        return module.build_factory_handoff(
            source or self.source, bars or self.bars,
            self.rows if rows is None else rows, trial or self.trial,
            source_authentication_receipt_sha256=proof)

    def test_frozen_protocol_and_distinct_arms(self):
        self.assertEqual((self.spec, self.trial), module.seal_protocol())
        self.assertNotEqual(self.trial.base_definition_sha256,
                            self.trial.shadow_definition_sha256)
        self.assertEqual(self.spec["shadow_exclude"],
                         "volatility > 0.03; equality allowed")
        self.assertEqual(self.spec["modeled_exit"].split(",")[0], "open[i+11]")

    def test_source_backed_opportunity_signal_no_future_features(self):
        got = module.produce_cohort(self.source, self.bars, self.rows, self.trial)
        self.assertEqual(len(got), N-21)
        self.assertEqual(got[0].disposition, "TRIGGERED")
        self.assertEqual(got[0].direction, "LONG")
        self.assertTrue(got[0].direction_evidence_ref.startswith("P2_MODELED_BREAKOUT:"))
        self.assertEqual(got[1].disposition, "NO_SIGNAL")
        changed = list(self.rows)
        changed[21] = {**changed[21], "close": "101"}
        other = module.produce_cohort(self.source, self.bars, changed, self.trial)
        self.assertEqual(got[0], other[0])

    def test_two_independent_arm_decisions_and_common_denominator(self):
        handoff = self.handoff()
        schedule, arms = handoff["schedule"], handoff["arm_decisions"]
        self.assertEqual(schedule["scheduled_total"], N-21)
        self.assertEqual(len(arms), 2*(N-21))
        self.assertEqual(schedule["outcome_evaluation"], "NOT_PERFORMED")
        self.assertEqual(handoff["windows"], None)
        first = schedule["pairs"][0]
        self.assertEqual([x["pair_id"] for x in arms[:2]], [first["pair_id"]]*2)
        self.assertEqual({a["arm"] for a in arms[:2]}, {"BASE", "SHADOW"})
        self.assertEqual([a["disposition"] for a in arms[:2]],
                         ["TRIGGERED", "TRIGGERED"])
        self.assertEqual(arms[0]["direction"], "LONG")
        self.assertEqual(arms[1]["direction"], "LONG")
        self.assertNotEqual(arms[0]["decision_sha256"], arms[1]["decision_sha256"])
        for item in arms:
            self.assertEqual(item["decision_sha256"],
                             module._hash({k: v for k, v in item.items()
                                           if k != "decision_sha256"}))
        self.assertEqual(arms[0]["modeled_entry_open_ms"], self.bars[21].open_ms)
        self.assertEqual(arms[0]["modeled_exit_open_ms"], self.bars[31].open_ms)

    def test_shadow_rejects_high_volatility_but_base_stays_triggered(self):
        arms = self.handoff()["arm_decisions"]
        # signal i=25 is the sixth scheduled cutoff (index 5).
        base, shadow = arms[10:12]
        self.assertEqual((base["disposition"], base["direction"]),
                         ("UNKNOWN", None))  # i+11 beyond cohort end
        self.assertEqual((shadow["disposition"], shadow["direction"]),
                         ("REJECTED", None))
        self.assertEqual(shadow["signal_disposition"], "TRIGGERED")

    def test_tail_unknown_keeps_signal_truth_and_source_coverage(self):
        handoff = self.handoff()
        last_pair = handoff["schedule"]["pairs"][-1]
        last_base, last_shadow = handoff["arm_decisions"][-2:]
        self.assertEqual(last_pair["opportunity"]["disposition"], "TRIGGERED")
        self.assertEqual(last_base["signal_disposition"], "TRIGGERED")
        self.assertEqual(last_base["disposition"], "UNKNOWN")
        self.assertIsNone(last_base["direction"])
        self.assertEqual(last_base["modeled_exit_missingness_reason"],
                         "END_OF_COHORT_NO_I_PLUS_11")
        self.assertEqual(last_shadow["disposition"], "REJECTED")

    def test_factory_prereg_and_cost_bindings(self):
        prereg, cost = module.build_factory_prereg(self.source, self.trial)
        self.assertEqual(prereg["schema"], "aql.p2.breakout.preregistration.v1")
        self.assertEqual(prereg["outcome_rule"],
                         "CUTOFF_REFERENCE_TO_4_24_72H_CLOSE_AND_EXCURSIONS_V1")
        self.assertEqual(prereg["horizons_hours"], [4, 24, 72])
        self.assertEqual(prereg["protocol_sha256"], self.trial.protocol_sha256)
        self.assertEqual(prereg["source_package_sha256"],
                         self.source.source_package_sha256)
        self.assertEqual(prereg["artifact_sha256"],
                         module._hash({k: v for k, v in prereg.items()
                                       if k != "artifact_sha256"}))
        self.assertEqual(cost["preregistration_sha256"], prereg["artifact_sha256"])
        self.assertEqual(cost["round_trip_fee_bps"], "20")
        self.assertEqual(cost["round_trip_slippage_bps"], "10")
        self.assertEqual(cost["artifact_sha256"],
                         module._hash({k: v for k, v in cost.items()
                                       if k != "artifact_sha256"}))

    def test_exact_three_percent_volatility_equality_is_not_rejected(self):
        rows = list(self.rows)
        for i in range(20):
            rows[i] = {**rows[i], "high": "102", "low": "99", "close": "100"}
        rows[20] = {**rows[20], "high": "104", "close": "103"}
        handoff = self.handoff(rows=rows)
        first_base, first_shadow = handoff["arm_decisions"][:2]
        self.assertEqual(first_base["disposition"], "TRIGGERED")
        self.assertEqual(first_shadow["disposition"], "TRIGGERED")

    def test_tampered_price_mapping_rejected(self):
        rows = list(self.rows)
        rows[0] = {**rows[0], "bar_sha256": K}
        with self.assertRaisesRegex(ContractError, "UNVERIFIED_BAR_MAPPING"):
            self.handoff(rows=rows)

    def test_unfinalized_and_missing_cohort_rejected(self):
        with self.assertRaisesRegex(ContractError, "UNFINALIZED"):
            self.handoff(bars=(replace(self.bars[0], finalized=False),)+self.bars[1:])
        with self.assertRaisesRegex(ContractError, "COHORT_COVERAGE_MISMATCH"):
            self.handoff(rows=self.rows[:-1], bars=self.bars[:-1])

    def test_wrong_source_and_protocol_pins_rejected(self):
        with self.assertRaisesRegex(ContractError, "SOURCE_PIN_DRIFT"):
            self.handoff(source=replace(self.source, source_package_sha256=K))
        with self.assertRaisesRegex(ContractError, "UNSEALED_OR_MUTATED_PROTOCOL"):
            self.handoff(trial=replace(self.trial, trial_id="FALSIFIED"))

    def test_bad_ohlc_rejected(self):
        rows = list(self.rows)
        rows[0] = {**rows[0], "high": "98"}
        with self.assertRaisesRegex(ContractError, "INVALID_OHLC_RANGE"):
            self.handoff(rows=rows)

    def test_missing_source_receipt_fails_closed(self):
        with self.assertRaisesRegex(ContractError, "MISSING_INDEPENDENT_SOURCE_ATTESTATION"):
            self.handoff(proof=None)


if __name__ == "__main__":
    unittest.main()
