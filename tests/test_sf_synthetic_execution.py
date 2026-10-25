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
                                        signal=signal, future=future)

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

    def test_no_signal_remains_zero_exposure(self):
        result = self.run_case(self.evidence(), signal=False)
        self.assertEqual(result.spec["outcome"], "NO_SIGNAL")
        self.assertIsNone(result.spec["net_return_bps"])


if __name__ == "__main__":
    unittest.main()
