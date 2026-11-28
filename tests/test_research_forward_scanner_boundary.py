import tempfile
import unittest
from pathlib import Path
from aql.research_bar_store import ResearchBarStore
from aql.research_forward_scanner_boundary import inspect_forward_15m


class ForwardScannerBoundaryTest(unittest.TestCase):
    def test_real_store_15m_read_only_wait(self):
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
            receipt = inspect_forward_15m(path, 0)
            self.assertEqual(receipt["status"], "FORWARD_15M_DURABLE_READABLE")
            self.assertEqual(receipt["constituent_count"], 15)
            self.assertEqual(receipt["scanner_attempts"], 0)
            self.assertEqual(receipt["scanner_e_historical_route"],
                             "WAIT_CORE_HISTORICAL_CONTRACT_NOT_SATISFIED")
            self.assertIsNone(receipt["core_253_local_query_receipt"])
            self.assertEqual(receipt["orders"], 0)

    def test_reject_non_aligned(self):
        with self.assertRaisesRegex(ValueError, "15M_GRID_REQUIRED"):
            inspect_forward_15m("unused.sqlite", 60000)


if __name__ == "__main__":
    unittest.main()
