"""PIT-only boundary regression tests; no historical performance assertions."""
import unittest
from unittest.mock import patch

from research_wp_r0.historical_evaluation_bridge import OfflineInputs
from research_wp_r0.offline_simulator import simulate_single_long


class OfflineSimulatorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.inputs = OfflineInputs({
            "strategy": {"digest": "a" * 64},
            "protocol": {"data_class": "SYNTHETIC_TEST"},
            "protocol_digest": "b" * 64,
            "binding": {"binding": {"decision_cutoff_ms": 1000}},
        })

    def test_no_signal_keeps_zero_exposure(self):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            result = simulate_single_long(
                self.inputs, expected_digest=self.inputs.digest, signal=False)
        self.assertEqual(result.spec["outcome"], "NO_SIGNAL")
        self.assertIsNone(result.spec["net_return_bps"])

    def test_missing_future_is_unknown_not_no_fill(self):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            result = simulate_single_long(
                self.inputs, expected_digest=self.inputs.digest, signal=True)
        self.assertEqual(result.spec["outcome"], "UNRESOLVED")
        self.assertEqual(result.spec["reason"], "UNKNOWN")
        self.assertIsNone(result.spec["entry_bar_open_ms"])

    def test_audit_failure_propagates(self):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs",
                   side_effect=ValueError("tampered")):
            with self.assertRaisesRegex(ValueError, "tampered"):
                simulate_single_long(
                    self.inputs, expected_digest=self.inputs.digest, signal=True)

    def test_invalid_signal_and_ttl_fail_closed(self):
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            for change in ({"signal": 1}, {"signal": True, "ttl_bars": 2}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    simulate_single_long(
                        self.inputs, expected_digest=self.inputs.digest, **change)

    def test_historical_data_not_admitted(self):
        spec = self.inputs.spec
        spec["protocol"]["data_class"] = "HISTORICAL_RECORDED"
        historical = OfflineInputs(spec)
        with patch("research_wp_r0.offline_simulator.audit_offline_inputs"):
            with self.assertRaisesRegex(ValueError, "not yet admitted"):
                simulate_single_long(
                    historical, expected_digest=historical.digest, signal=True)


if __name__ == "__main__":
    unittest.main()
