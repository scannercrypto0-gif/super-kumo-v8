"""Offline tests: durable research-only store; no network or original market data."""
import tempfile
import unittest
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_timeframes import MINUTE


def bar(i):
    return dict(symbol="BTCUSDT", interval="1m", open_ms=i * MINUTE,
                final=True, o="10", h="12", l="9", c="11", v="2",
                source_sha256=f"{i+1:064x}",
                available_at_ms=(i+1) * MINUTE + 100)


class StoreTest(unittest.TestCase):
    def test_restart_idempotence_and_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.sqlite"
            with ResearchBarStore(path) as store:
                for i in range(5):
                    store.insert_1m(bar(i))
                first = store.project("BTCUSDT", "5m", 0)
                self.assertEqual(first["v"], "10")
                self.assertEqual(first["trading_authority"], "NONE")
                self.assertEqual(first["pit_oos"], "NOT_ATTESTED")
            with ResearchBarStore(path) as store:
                self.assertEqual(store.project("BTCUSDT", "5m", 0), first)
                self.assertEqual(store.read("BTCUSDT", "1m", 0)["o"], "10")
                store.insert_1m(bar(0))
                changed = bar(0)
                changed["c"] = "10"
                with self.assertRaisesRegex(ValueError, "SOURCE_REWRITE_DENIED"):
                    store.insert_1m(changed)

    def test_missing_provisional_and_mixed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ResearchBarStore(Path(tmp) / "bars.sqlite") as store:
                for i in (0, 1, 3, 4):
                    store.insert_1m(bar(i))
                with self.assertRaisesRegex(ValueError, "SOURCE_GAP"):
                    store.project("BTCUSDT", "5m", 0)
                provisional = bar(2)
                provisional["final"] = False
                with self.assertRaisesRegex(ValueError, "GAP_DUPLICATE_OR_PROVISIONAL"):
                    store.insert_1m(provisional)
                store.insert_1m(bar(2), source_class="RETROSPECTIVE_NON_PIT")
                with self.assertRaisesRegex(ValueError, "MIXED_SOURCE_CLASS"):
                    store.project("BTCUSDT", "5m", 0)

    def test_digest_column_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ResearchBarStore(Path(tmp) / "bars.sqlite") as store:
                store.insert_1m(bar(0))
                with store.db:
                    store.db.execute("UPDATE finalized_bars SET sha256=?", ("0" * 64,))
                with self.assertRaisesRegex(ValueError, "STORE_INTEGRITY_FAILED"):
                    store.read("BTCUSDT", "1m", 0)

    def test_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ResearchBarStore(Path(tmp) / "bars.sqlite") as store:
                store.insert_1m(bar(0))
                with store.db:
                    store.db.execute("UPDATE finalized_bars SET payload='{}'")
                with self.assertRaisesRegex(ValueError, "STORE_INTEGRITY_FAILED"):
                    store.read("BTCUSDT", "1m", 0)


if __name__ == "__main__":
    unittest.main()
