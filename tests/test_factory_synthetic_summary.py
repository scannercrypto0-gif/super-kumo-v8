import copy
import unittest
from research_wp_r0.synthetic_opportunities import run_synthetic_opportunities
from research_wp_r0.synthetic_summary import summarize_synthetic_opportunities


def bars():
    return [
        {"bar_open": i * 60000, "bar_close": (i + 1) * 60000 - 1,
         "open": 100, "high": 106 if i == 1 else 101,
         "low": 99, "close": 100}
        for i in range(4)
    ]


def ledger():
    return run_synthetic_opportunities(bars(), [0, 2],
        stop_fraction=.05, target_fraction=.05, ttl_bars=1,
        holding_bars=1, fee_bps=10, slippage_bps=0)


class TestSyntheticSummary(unittest.TestCase):
    def test_resolved_and_unresolved_separated(self):
        result = summarize_synthetic_opportunities(ledger())
        self.assertEqual(result["total_opportunities"], 2)
        self.assertEqual(result["resolved_trades"], 1)
        self.assertEqual(result["counts"]["UNRESOLVED"], 1)
        self.assertFalse(result["profitability_claim"])
        self.assertEqual(result, summarize_synthetic_opportunities(ledger()))

    def test_nested_receipt_tamper_rejected(self):
        modified = copy.deepcopy(ledger())
        modified["records"][0]["execution"]["details"]["net_return"] = 999
        from research_wp_r0.strategy_definition import digest
        modified["receipt_hash"] = digest({k: v for k, v in modified.items() if k != "receipt_hash"})
        with self.assertRaises(ValueError):
            summarize_synthetic_opportunities(modified)

    def test_receipt_tamper_rejected(self):
        modified = copy.deepcopy(ledger())
        modified["records"][0]["status"] = "RESOLVED_STOP"
        with self.assertRaises(ValueError):
            summarize_synthetic_opportunities(modified)


if __name__ == "__main__":
    unittest.main()
