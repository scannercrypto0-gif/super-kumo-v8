import tempfile
import unittest
from pathlib import Path
from aql.research_bar_store import ResearchBarStore
from aql.research_forward_core_read import forward_core_window


class ForwardCoreReadTest(unittest.TestCase):
    def test_one_real_durable_15m_is_not_12_bar_strategy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bars.sqlite"
            with ResearchBarStore(path) as store:
                for i in range(15):
                    store.insert_1m({
                        "symbol": "BTCUSDT", "interval": "1m", "open_ms": i * 60000,
                        "final": True, "o": "10", "h": "12", "l": "9",
                        "c": "11", "v": "2",
                        "source_sha256": ("%064x" % (i + 1)),
                        "available_at_ms": 900001,
                    })
                store.project("BTCUSDT", "15m", 0)
            result = forward_core_window(path, start_ms=0)
            self.assertEqual(result["status"], "WAIT_MORE_FINALIZED_15M")
            self.assertEqual(result["available_bars"], 1)
            self.assertEqual(result["required_bars"], 12)
            self.assertEqual(result["bars"][0]["c"], "11")
            self.assertEqual(result["strategy_evaluation"], "NOT_EXECUTED")
            self.assertEqual(result["orders"], 0)

    def test_invalid_grid_rejected(self):
        with self.assertRaisesRegex(ValueError, "FORWARD_CORE_WINDOW_SCOPE"):
            forward_core_window("unused", start_ms=60000)


if __name__ == "__main__":
    unittest.main()
