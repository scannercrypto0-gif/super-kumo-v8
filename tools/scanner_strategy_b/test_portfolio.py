"""Focused heterogeneous timeframe tests, synthetic fixtures only."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from .test_integration import Native15mGate
from .portfolio import scan_strategy_groups


class PortfolioGate(unittest.TestCase):
    def setUp(self):
        fixture = Native15mGate(methodName="test_all_strategy_symbol_pairs_and_safety")
        fixture.setUp()
        self.synthetic = fixture
        specs = json.loads((FIXTURES/"strategies.json").read_text())
        self.g5 = {
            "work235_specs": specs,
            "raw": (FIXTURES/"source.json").read_bytes(),
            "manifest": json.loads((FIXTURES/"source-manifest.json").read_text()),
            "universe": json.loads((FIXTURES/"universe.json").read_text()),
            "cutoff_ms": 7_200_000,
            "symbol_budget": 3,
        }
        self.g15 = {
            "work235_specs": self.synthetic.work,
            "raw": self.synthetic.raw,
            "manifest": self.synthetic.manifest,
            "universe": self.synthetic.universe,
            "cutoff_ms": self.synthetic.cutoff,
            "symbol_budget": 3,
        }

    def test_two_native_timeframes_same_strategy_independent_censuses(self):
        result = scan_strategy_groups([self.g5, self.g15])
        data = result.data
        self.assertEqual(data["group_count"], 2)
        self.assertEqual(data["total_strategy_symbol_attempts"], 20)
        self.assertEqual(data["denominator"], 20)
        self.assertEqual(data["groups"][0]["adapter"], "EXISTING_WORK235_SCANNER227")
        self.assertEqual(data["groups"][1]["adapter"], "SCANNER_NATIVE_15M_TEST_ONLY")
        for group in data["groups"]:
            rows = [Frozen.restore(n).data for n in Frozen.restore(group["result"]).data["nominations"]]
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(n["timeframe"] == group["timeframe"] for n in rows))
            self.assertTrue(all(n["denominator"] == 5 for n in rows))
            self.assertTrue(all(n["trading_authority"] == "NONE" for n in rows))
        self.assertEqual(result.payload, scan_strategy_groups([self.g5,self.g15]).payload)
        self.assertEqual(data["operational_work235_15m"], "NOT_CONNECTED_15M_UNSUPPORTED")

    def test_reject_silent_5m_to_30m_relabel(self):
        self.g5["manifest"]["timeframe"] = "30m"
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_TIMEFRAME_CONFIG_MISMATCH"):
            scan_strategy_groups([self.g5])

    def test_duplicate_same_strategy_source_never_double_counts(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PORTFOLIO_STRATEGY_SOURCE"):
            scan_strategy_groups([self.g5, deepcopy(self.g5)])

    def test_wrong_source_bytes_are_unknown_not_selected(self):
        self.g15["raw"] = self.g5["raw"]
        r = scan_strategy_groups([self.g5, self.g15]).data
        native = Frozen.restore(r["groups"][1]["result"]).data
        rows = [Frozen.restore(n).data for n in native["nominations"]]
        self.assertEqual({n["status"] for n in rows if n["symbol"] in ("AAA", "BBB")},
                         {"UNKNOWN"})
        self.assertEqual(len(rows), 10)
        self.assertEqual(r["total_strategy_symbol_attempts"], 20)


if __name__ == "__main__":
    unittest.main()
