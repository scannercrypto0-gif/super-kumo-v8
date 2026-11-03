"""TEST_ONLY negative/positive tests; synthetic records and pins never market evidence."""
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
PROOF = "d" * 64
DATASET = "BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1"
N = 35


def synthetic_rows():
    """Deliberately invented short source, never the retained Work private bars."""
    rows = []
    for i in range(N):
        op = module.FEB_START + i * BAR_MS
        high = "103" if i == 20 else "112" if i == 25 else "121" if i == 33 else "101"
        close = "102" if i == 20 else "111" if i == 25 else "120" if i == 33 else "100"
        rows.append({
            "dataset_id": DATASET, "open_ms": op, "close_ms": op+BAR_MS-1,
            "open": "100", "high": high, "low": "99", "close": close,
            "availability_mode": "RETROSPECTIVE_NON_PIT",
            "historical_known_at_ms": None,
            "historical_receipt_ms": None,
            "historical_publication_ms": None,
            "finality": "ARCHIVED_CLOSED_INTERVAL", "is_final": True,
        })
    return rows


def sealed_synthetic(rows):
    """Recompute Work's row/index digests only for TEST_ONLY invented fixtures."""
    indexed = []
    for row in rows:
        r = {k: v for k, v in row.items() if k != "bar_sha256"}
        indexed.append({**r, "bar_sha256": module._work_sha(module._work_canonical(r))})
    normalized_sha = module._work_sha(
        b"".join(module._work_canonical(r) for r in indexed))
    bars = tuple(HistoricalBarV1(
        r["open_ms"], r["close_ms"], r["bar_sha256"]) for r in indexed)
    return tuple(indexed), bars, normalized_sha


class BreakoutTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._manifest = patch.object(module, "MANIFEST_SHA", H)
        cls._source_proof = patch.object(module, "WORK_VERIFIED_SOURCE_RECEIPT_SHA", PROOF)
        cls._manifest.start()
        cls._source_proof.start()
        indexed, bars, normal = sealed_synthetic(synthetic_rows())
        cls._source = patch.dict(module.SOURCE_ARCHIVES, {
            DATASET: (module.FEB_START, module.FEB_START + N*BAR_MS, K, normal)
        }, clear=True)
        cls._source.start()

    @classmethod
    def tearDownClass(cls):
        cls._source.stop()
        cls._source_proof.stop()
        cls._manifest.stop()

    def setUp(self):
        self.rows, self.bars, _ = sealed_synthetic(synthetic_rows())
        pin = module.SOURCE_ARCHIVES[DATASET]
        self.source = HistoricalSourceV1(
            DATASET, "BINANCE", "SPOT", "BTCUSDT",
            pin[2], module.MANIFEST_SHA, pin[3], "UNKNOWN_NOT_ATTESTED")
        self.spec, self.trial = module.seal_protocol()

    def handoff(self, *, rows=None, bars=None, source=None, trial=None, proof=PROOF):
        return module.build_factory_handoff(
            source or self.source, bars or self.bars,
            self.rows if rows is None else rows, trial or self.trial,
            source_authentication_receipt_sha256=proof)

    def repinned_handoff(self, rows):
        rebuilt, bars, normal = sealed_synthetic(rows)
        new_pin = (module.FEB_START, module.FEB_START + N*BAR_MS, K, normal)
        with patch.dict(module.SOURCE_ARCHIVES, {DATASET: new_pin}, clear=True):
            _, trial = module.seal_protocol()
            source = replace(self.source, normalized_sha256=normal)
            return module.build_factory_handoff(
                source, bars, rebuilt, trial,
                source_authentication_receipt_sha256=PROOF)

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
        changed = [dict(r) for r in self.rows]
        changed[21]["close"] = "101"
        other = self.repinned_handoff(changed)["schedule"]["pairs"]
        self.assertEqual(got[0].disposition,
                         other[0]["opportunity"]["disposition"])
        self.assertEqual(got[0].feature_prefix_sha256,
                         other[0]["opportunity"]["feature_prefix_sha256"])

    def test_two_independent_arm_decisions_and_common_denominator(self):
        handoff = self.handoff()
        schedule, arms = handoff["schedule"], handoff["arm_decisions"]
        self.assertEqual(schedule["scheduled_total"], N-21)
        self.assertEqual(len(arms), 2*(N-21))
        self.assertEqual(schedule["outcome_evaluation"], "NOT_PERFORMED")
        self.assertIsNone(handoff["windows"])
        pair = schedule["pairs"][0]
        self.assertEqual([a["pair_id"] for a in arms[:2]], [pair["pair_id"]]*2)
        self.assertEqual({a["arm"] for a in arms[:2]}, {"BASE", "SHADOW"})
        self.assertEqual([a["disposition"] for a in arms[:2]],
                         ["TRIGGERED", "TRIGGERED"])
        self.assertEqual([a["direction"] for a in arms[:2]], ["LONG", "LONG"])
        self.assertNotEqual(arms[0]["decision_sha256"], arms[1]["decision_sha256"])
        for a in arms:
            self.assertEqual(a["decision_sha256"],
                             module._hash({k: v for k, v in a.items()
                                           if k != "decision_sha256"}))
        self.assertEqual(arms[0]["modeled_entry_open_ms"], self.bars[21].open_ms)
        self.assertEqual(arms[0]["modeled_exit_open_ms"], self.bars[31].open_ms)

    def test_shadow_rejects_high_volatility_but_base_keeps_signal(self):
        base, shadow = self.handoff()["arm_decisions"][10:12]
        self.assertEqual((base["disposition"], base["direction"]),
                         ("UNKNOWN", None))  # i+11 unavailable
        self.assertEqual((shadow["disposition"], shadow["direction"]),
                         ("REJECTED", None))
        self.assertEqual(shadow["signal_disposition"], "TRIGGERED")

    def test_tail_unknown_keeps_signal_truth(self):
        handoff = self.handoff()
        last_pair = handoff["schedule"]["pairs"][-1]
        last_base, last_shadow = handoff["arm_decisions"][-2:]
        self.assertEqual(last_pair["opportunity"]["disposition"], "TRIGGERED")
        self.assertEqual(last_base["signal_disposition"], "TRIGGERED")
        self.assertEqual((last_base["disposition"], last_base["direction"]),
                         ("UNKNOWN", None))
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

    def test_exact_three_percent_equality_not_rejected(self):
        changed = [dict(r) for r in self.rows]
        for i in range(20):
            changed[i].update(high="102", low="99", close="100")
        changed[20].update(high="104", close="103")
        base, shadow = self.repinned_handoff(changed)["arm_decisions"][:2]
        self.assertEqual(base["disposition"], "TRIGGERED")
        self.assertEqual(shadow["disposition"], "TRIGGERED")

    def test_changed_price_without_rehash_rejected(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["high"] = "100.5"
        with self.assertRaisesRegex(ContractError, "BAR_CONTENT_HASH_MISMATCH"):
            self.handoff(rows=rows)

    def test_wrong_bar_hash_rejected(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["bar_sha256"] = J
        with self.assertRaisesRegex(ContractError, "UNVERIFIED_BAR_MAPPING"):
            self.handoff(rows=rows)

    def test_unfinalized_and_missing_cohort_rejected(self):
        with self.assertRaisesRegex(ContractError, "UNFINALIZED"):
            self.handoff(bars=(replace(self.bars[0], finalized=False),)+self.bars[1:])
        with self.assertRaisesRegex(ContractError, "COHORT_COVERAGE_MISMATCH"):
            self.handoff(rows=self.rows[:-1], bars=self.bars[:-1])

    def test_wrong_source_and_protocol_pins_rejected(self):
        with self.assertRaisesRegex(ContractError, "SOURCE_PIN_DRIFT"):
            self.handoff(source=replace(self.source, source_package_sha256=J))
        with self.assertRaisesRegex(ContractError, "UNSEALED_OR_MUTATED_PROTOCOL"):
            self.handoff(trial=replace(self.trial, trial_id="FALSIFIED"))

    def test_invalid_ohlc_rejected_even_with_new_fake_index_pin(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["high"] = "98"
        with self.assertRaisesRegex(ContractError, "INVALID_OHLC_RANGE"):
            self.repinned_handoff(rows)

    def test_missing_or_unknown_source_receipt_fails_closed(self):
        with self.assertRaisesRegex(ContractError, "MISSING_INDEPENDENT_SOURCE_ATTESTATION"):
            self.handoff(proof=None)
        with self.assertRaisesRegex(ContractError, "UNRECOGNIZED_WORK_SOURCE_ATTESTATION"):
            self.handoff(proof=J)


if __name__ == "__main__":
    unittest.main()
