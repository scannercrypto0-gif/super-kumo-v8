import unittest
from research_wp_r0.synthetic_execution import execute_synthetic_long


def bars(high=101, low=99):
    return [
        {"bar_open": 0, "bar_close": 59999, "open": 100, "high": 101, "low": 99, "close": 100},
        {"bar_open": 60000, "bar_close": 119999, "open": 100, "high": high, "low": low, "close": 100},
    ]


def run(data, **kw):
    return execute_synthetic_long(data, 0, stop_fraction=.05, target_fraction=.05,
        ttl_bars=1, holding_bars=1, fee_bps=10, slippage_bps=0, **kw)


class TestSyntheticExecution(unittest.TestCase):
    def test_target_and_determinism(self):
        data = bars(high=106)
        a = run(data)
        self.assertEqual(a, run(data))
        self.assertEqual(a["status"], "RESOLVED_TARGET")
        self.assertAlmostEqual(a["details"]["net_return"], .05 - .001 - .00105)

    def test_stop(self):
        result = run(bars(low=94))
        self.assertEqual(result["status"], "RESOLVED_STOP")
        self.assertLess(result["details"]["net_return"], -.05)

    def test_same_bar_ambiguity(self):
        result = run(bars(high=106, low=94))
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["details"]["reason"], "SAME_BAR_STOP_TARGET")
        self.assertNotIn("net_return", result["details"])

    def test_gap_is_not_filled(self):
        data = bars()
        data[1]["bar_open"] = 60001
        self.assertEqual(run(data)["details"]["reason"], "ENTRY_GAP")

    def test_no_next_bar(self):
        data = bars()
        self.assertEqual(execute_synthetic_long(data, 1, stop_fraction=.05,
            target_fraction=.05, ttl_bars=1, holding_bars=1, fee_bps=10,
            slippage_bps=0)["status"], "NO_FILL")

    def test_target_gap_is_unresolved(self):
        data = bars()
        data.append({"bar_open": 120000, "bar_close": 179999,
                     "open": 108, "high": 109, "low": 107, "close": 108})
        result = execute_synthetic_long(data, 0, stop_fraction=.05,
            target_fraction=.05, ttl_bars=1, holding_bars=2,
            fee_bps=10, slippage_bps=0)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["details"]["reason"], "TARGET_GAP_UNRESOLVED")

    def test_stop_gap_uses_open(self):
        data = bars()
        data.append({"bar_open": 120000, "bar_close": 179999,
                     "open": 90, "high": 92, "low": 89, "close": 91})
        result = execute_synthetic_long(data, 0, stop_fraction=.05,
            target_fraction=.05, ttl_bars=1, holding_bars=2,
            fee_bps=10, slippage_bps=0)
        self.assertEqual(result["status"], "RESOLVED_STOP")
        self.assertAlmostEqual(result["details"]["gross_return"], -.10)

    def test_stop_gap_precedes_intrabar_target(self):
        data = bars()
        data.append({"bar_open": 120000, "bar_close": 179999,
                     "open": 90, "high": 110, "low": 89, "close": 100})
        result = execute_synthetic_long(data, 0, stop_fraction=.05,
            target_fraction=.05, ttl_bars=1, holding_bars=2,
            fee_bps=10, slippage_bps=0)
        self.assertEqual(result["status"], "RESOLVED_STOP")
        self.assertAlmostEqual(result["details"]["gross_return"], -.10)

    def test_mixed_bar_durations_rejected(self):
        data = bars()
        data[1]["bar_close"] = 120000
        with self.assertRaises(ValueError):
            run(data)

    def test_excessive_exit_slippage_rejected(self):
        with self.assertRaises(ValueError):
            execute_synthetic_long(bars(), 0, stop_fraction=.05,
                target_fraction=.05, ttl_bars=1, holding_bars=1,
                fee_bps=10, slippage_bps=10000)

    def test_unobserved_horizon_not_scored(self):
        result = execute_synthetic_long(bars(), 0, stop_fraction=.05,
            target_fraction=.05, ttl_bars=1, holding_bars=3,
            fee_bps=10, slippage_bps=0)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertNotIn("net_return", result["details"])

    def test_bad_ohlc_rejected(self):
        data = bars()
        data[1]["high"] = 90
        with self.assertRaises(ValueError):
            run(data)


if __name__ == "__main__":
    unittest.main()
