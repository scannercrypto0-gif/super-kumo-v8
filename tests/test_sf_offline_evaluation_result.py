"""Bounded contract tests; no simulated trades are executed."""
import unittest

from research_wp_r0.offline_evaluation_result import OfflineEvaluationResult


def receipt(outcome="NO_SIGNAL", reason="NO_SIGNAL", **changes):
    value = {
        "schema_version": "research-eval-result-1",
        "inputs_digest": "a" * 64,
        "strategy_digest": "b" * 64,
        "protocol_digest": "c" * 64,
        "outcome": outcome,
        "reason": reason,
        "decision_cutoff_ms": 1000,
        "entry_bar_open_ms": None,
        "exit_bar_open_ms": None,
        "gross_return_bps": None,
        "fee_bps": None,
        "slippage_bps": None,
        "net_return_bps": None,
        "independent_custody": "NOT_VERIFIED",
    }
    value.update(changes)
    return value


class OfflineResultContractTests(unittest.TestCase):
    def test_no_signal_is_deterministic(self):
        a = OfflineEvaluationResult(receipt())
        b = OfflineEvaluationResult(receipt())
        self.assertEqual(a.digest, b.digest)
        self.assertEqual(a.spec["outcome"], "NO_SIGNAL")

    def test_no_fill_ttl(self):
        self.assertEqual(OfflineEvaluationResult(
            receipt("NO_FILL", "TTL_EXPIRED")).spec["reason"], "TTL_EXPIRED")

    def test_unresolved_gap_has_no_pnl(self):
        self.assertEqual(OfflineEvaluationResult(
            receipt("UNRESOLVED", "DATA_GAP")).spec["outcome"], "UNRESOLVED")

    def test_closed_result_costs_and_strict_timing(self):
        value = receipt("SIMULATED_CLOSED", "NONE", entry_bar_open_ms=2000,
                        exit_bar_open_ms=3000, gross_return_bps=150,
                        fee_bps=20, slippage_bps=10, net_return_bps=120)
        self.assertEqual(OfflineEvaluationResult(value).spec["net_return_bps"], 120)
        for change in ({"entry_bar_open_ms": 1000},
                       {"exit_bar_open_ms": 2000},
                       {"net_return_bps": 130}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                OfflineEvaluationResult({**value, **change})

    def test_rejects_false_pnl_or_fill(self):
        for change in ({"net_return_bps": 0},
                       {"entry_bar_open_ms": 2000},
                       {"independent_custody": "VERIFIED"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                OfflineEvaluationResult(receipt(**change))

    def test_rejects_invalid_state_pair(self):
        with self.assertRaises(ValueError):
            OfflineEvaluationResult(receipt("NO_FILL", "DATA_GAP"))

    def test_rejects_invalid_digest_and_unknown_fields(self):
        for change in ({"inputs_digest": "g" * 64}, {"unknown": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                OfflineEvaluationResult(receipt(**change))


if __name__ == "__main__":
    unittest.main()
