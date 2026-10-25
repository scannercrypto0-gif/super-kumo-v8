"""Synthetic-only fills with explicit separately bound future bars."""
import unittest
from unittest.mock import patch

from research_wp_r0.future_bar_evidence import FutureBarEvidence
from research_wp_r0.historical_evaluation_bridge import OfflineInputs
from research_wp_r0.offline_simulator import simulate_single_long


class SyntheticExecutionTests(unittest.TestCase):
    def setUp(self):
        self.inputs = OfflineInputs({
            "strategy": {"digest": "a" * 64},
            "protocol": {"data_class": "SYNTHETIC_TEST", "fee_bps": 10,
                         "slippage_bps": 5},
            "protocol_digest": "b" * 64,
            "binding": {"binding": {"decision_cutoff_ms": 59999}},
            "dataset_manifest": {"symbol": "BTCUSDT", "interval": "1m"},
            "bars": [{"open_ms": 0}],
        })

    def evidence(self, **changes):
        value = {
            "schema_version": "research-future-bars-1",
            "inputs_digest": self.inputs.digest,
            "decision_cutoff_ms": 59999,
            "symbol": "BTCUSDT",
            "interval_ms": 60000,
            "independent_custody": "NOT_VERIFIED",
            "bars": [
                {"open_ms": 1000, "close_ms": 159999, "open": 100,
                 "high": 110, "low": 95, "close": 105, "volume": 10,
                 "observed_at_ms": 120000},
                {"open_ms": 2000, "close_ms": 259999, "open": 105,
                 "high": 115, "low": 100, "close": 110, "volume": 10,
                 "observed_at_ms": 180000},
            ],
        }
        value.update(changes)
        return FutureBarEvidence(value)

    def run_case(self, future, signal=True):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            return simulate_single_long(self.inputs, expected_digest=self.inputs.digest,
                                        signal=signal, future=future,
                                        expected_future_digest=future.digest if future else None)

    def test_synthetic_closed_and_round_trip_costs(self):
        result = self.run_case(self.evidence())
        self.assertEqual(result.spec["outcome"], "SIMULATED_CLOSED")
        self.assertAlmostEqual(result.spec["gross_return_bps"], 500)
        self.assertAlmostEqual(result.spec["fee_bps"], 20)
        self.assertAlmostEqual(result.spec["slippage_bps"], 10)
        self.assertAlmostEqual(result.spec["net_return_bps"], 470)

    def test_one_future_bar_is_unknown(self):
        evidence = self.evidence()
        value = evidence.spec
        value["bars"] = value["bars"][:1]
        result = self.run_case(FutureBarEvidence(value))
        self.assertEqual(result.spec["outcome"], "UNRESOLVED")
        self.assertIsNone(result.spec["net_return_bps"])

    def test_mismatched_commitment_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.run_case(self.evidence(inputs_digest="c" * 64))

    def test_missing_first_eligible_bar_is_unresolved_gap(self):
        evidence = self.evidence()
        value = evidence.spec
        for bar in value["bars"]:
            bar["open_ms"] += 60000
            bar["close_ms"] += 60000
            bar["observed_at_ms"] += 60000
        result = self.run_case(FutureBarEvidence(value))
        self.assertEqual(result.spec["outcome"], "UNRESOLVED")
        self.assertEqual(result.spec["reason"], "DATA_GAP")
        self.assertIsNone(result.spec["net_return_bps"])

    def test_wrong_interval_rejected(self):
        evidence = self.evidence()
        value = evidence.spec
        value["interval_ms"] = 120000
        for bar in value["bars"]:
            bar["close_ms"] = bar["open_ms"] + 119999
            bar["observed_at_ms"] = bar["close_ms"] + 1
        value["bars"][1]["open_ms"] = value["bars"][0]["open_ms"] + 120000
        value["bars"][1]["close_ms"] = value["bars"][1]["open_ms"] + 119999
        value["bars"][1]["observed_at_ms"] = value["bars"][1]["close_ms"] + 1
        with self.assertRaisesRegex(ValueError, "interval"):
            self.run_case(FutureBarEvidence(value))

    def test_wrong_future_commitment_rejected(self):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            with self.assertRaisesRegex(ValueError, "future evidence digest"):
                simulate_single_long(self.inputs, expected_digest=self.inputs.digest,
                                     signal=True, future=self.evidence(),
                                     expected_future_digest="f" * 64)

    def test_future_without_separate_commitment_rejected(self):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            with self.assertRaisesRegex(ValueError, "future evidence digest"):
                simulate_single_long(self.inputs, expected_digest=self.inputs.digest,
                                     signal=True, future=self.evidence())

    def test_no_signal_remains_zero_exposure(self):
        result = self.run_case(self.evidence(), signal=False)
        self.assertEqual(result.spec["outcome"], "NO_SIGNAL")
        self.assertIsNone(result.spec["net_return_bps"])


if __name__ == "__main__":
    unittest.main()
