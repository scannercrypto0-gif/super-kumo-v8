"""Offline G1/G2 integration contract: no trading, networking, or activation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.observation.position_journal import DurablePositionJournal
from aql.observation.positions import PositionEvent


class CoreG2OfflineIntegrationAcceptance(unittest.TestCase):
    def test_independent_g1_commits_and_g2_position_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            g1_path = root / "core.sqlite"
            g2_path = root / "positions.jsonl"
            opened = PositionEvent("paper-1", "open-1", "opened", 0, 0, "offline")
            self.assertEqual(DurablePositionJournal(g2_path).append(opened), "inserted")

            def commit_core_bars():
                journal = DurableJournal(str(g1_path))
                for i in range(12):
                    bar = MarketBar(
                        "BTCUSDT", "1m", i * 60000, (i + 1) * 60000 - 1,
                        100., 101., 99., 100., 1., True,
                        "synthetic-offline", (i + 1) * 60000,
                    )
                    self.assertTrue(journal.commit(bar))
                return len(journal.replay())

            def append_position_quotes():
                journal = DurablePositionJournal(g2_path)
                for i in range(1, 13):
                    self.assertEqual(journal.append(PositionEvent(
                        "paper-1", f"quote-{i}", "quote",
                        i * 60000, i * 60000, "offline", price="100",
                    )), "inserted")
                return journal.ledger.status("paper-1", 366 * 86400000)

            with ThreadPoolExecutor(max_workers=2) as pool:
                core = pool.submit(commit_core_bars)
                positions = pool.submit(append_position_quotes)
                self.assertEqual(core.result(timeout=30), 12)
                self.assertEqual(positions.result(timeout=30), "open")

            self.assertEqual(len(DurableJournal(str(g1_path)).replay()), 12)
            restored = DurablePositionJournal(g2_path)
            self.assertEqual(restored.ledger.status("paper-1", 366 * 86400000), "open")
            self.assertEqual(restored.append(opened), "duplicate")
            self.assertEqual(restored.ledger.status("paper-1", 366 * 86400000), "open")

            self.assertEqual(restored.append(PositionEvent(
                "paper-1", "close-1", "closed", 367 * 86400000,
                367 * 86400000, "offline", reason="explicit-exit",
            )), "inserted")
            self.assertEqual(
                DurablePositionJournal(g2_path).ledger.status(
                    "paper-1", 368 * 86400000,
                ), "closed",
            )


if __name__ == "__main__":
    unittest.main()
