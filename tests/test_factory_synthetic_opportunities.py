import unittest
from research_wp_r0.synthetic_opportunities import run_synthetic_opportunities


def bars():
    return [
        {"bar_open": i * 60000, "bar_close": (i + 1) * 60000 - 1,
         "open": 100, "high": 106 if i in (1, 3) else 101,
         "low": 99, "close": 100}
        for i in range(5)
    ]


def run(indices, data=None):
    return run_synthetic_opportunities(data or bars(), indices,
        stop_fraction=.05, target_fraction=.05,
        ttl_bars=1, holding_bars=1, fee_bps=10, slippage_bps=0)


class TestSyntheticOpportunities(unittest.TestCase):
    def test_independent_resolved_trades(self):
        result = run([0, 2])
        self.assertEqual([x["status"] for x in result["records"]],
                         ["RESOLVED_TARGET", "RESOLVED_TARGET"])
        self.assertEqual(result, run([0, 2]))

    def test_overlap_retained_without_second_fill(self):
        result = run([0, 1, 2])
        self.assertEqual(result["records"][1]["status"], "NO_SIGNAL_EXECUTION")
        self.assertEqual(result["records"][1]["reason"], "POSITION_ALREADY_ACTIVE")

    def test_unresolved_exposure_blocks_future_trades(self):
        data = bars()
        data[1]["high"] = 101
        result = run([0, 2], data)
        self.assertEqual(result["records"][0]["status"], "UNRESOLVED")
        self.assertEqual(result["records"][1]["status"], "NO_SIGNAL_EXECUTION")

    def test_duplicate_or_out_of_order_rejected(self):
        for indices in ([1, 1], [2, 1]):
            with self.assertRaises(ValueError):
                run(indices)


if __name__ == "__main__":
    unittest.main()
