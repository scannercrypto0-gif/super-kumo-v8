"""Generated-only tests for independent SQLite readback."""
import tempfile
import unittest
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_durability_readback import verify_research_window


def bar(i):
    return dict(symbol="BTCUSDT", interval="1m", open_ms=i * 60000,
                final=True, o="10", h="12", l="9", c="11", v="2",
                source_sha256=f"{i + 1:064x}", available_at_ms=(i + 1) * 60000)


class ReadbackTest(unittest.TestCase):
    def test_second_connection_readback_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite"
            with ResearchBarStore(path) as store:
                for i in range(5):
                    store.insert_1m(bar(i))
                proof = verify_research_window(store, symbol="BTCUSDT", interval="5m",
                                               open_ms=0)
                self.assertEqual(proof["status"], "RESEARCH_DURABILITY_READBACK_PASS")
                self.assertEqual(proof["constituent_count"], 5)
                self.assertEqual(proof["core_scanner_factory_secretary_e2e"], "NOT_ATTESTED")
            with ResearchBarStore(path) as store:
                self.assertEqual(verify_research_window(
                    store, symbol="BTCUSDT", interval="5m", open_ms=0), proof)

    def test_gap_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ResearchBarStore(Path(tmp) / "store.sqlite") as store:
                store.insert_1m(bar(0))
                with self.assertRaisesRegex(ValueError, "SOURCE_GAP"):
                    verify_research_window(store, symbol="BTCUSDT", interval="5m", open_ms=0)


if __name__ == "__main__":
    unittest.main()
