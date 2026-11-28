"""Generated-only tests of closed 1m websocket frame adapter."""
import json
import tempfile
import unittest
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_ws_1m_ingest import ingest_closed_1m_frame


def frame(*, opened=0, final=True, close="11", interval="1m"):
    return json.dumps({
        "e": "kline", "E": opened + 60000, "s": "BTCUSDT",
        "k": {"t": opened, "T": opened + 59999, "s": "BTCUSDT", "i": interval,
              "x": final, "o": "10", "h": "12", "l": "9", "c": close, "v": "2"},
    }, separators=(",", ":")).encode()


class Ws1mTest(unittest.TestCase):
    def test_replay_rewrite_and_reject_provisional(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ResearchBarStore(Path(tmp) / "bars.sqlite") as store:
                raw = frame()
                first = ingest_closed_1m_frame(store, raw, received_at_ms=60001)
                again = ingest_closed_1m_frame(store, raw, received_at_ms=60001)
                self.assertEqual(first, again)
                self.assertEqual(store.read("BTCUSDT", "1m", 0)["c"], "11")
                with self.assertRaisesRegex(ValueError, "SOURCE_REWRITE_DENIED"):
                    ingest_closed_1m_frame(store, frame(close="10"), received_at_ms=60001)
                with self.assertRaisesRegex(ValueError, "PROVISIONAL_KLINE"):
                    ingest_closed_1m_frame(store, frame(opened=60000, final=False),
                                           received_at_ms=120001)
                self.assertIsNone(store.read("BTCUSDT", "1m", 60000))

    def test_clock_schema_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ResearchBarStore(Path(tmp) / "bars.sqlite") as store:
                for raw, received, error in [
                    (frame(), 59999, "RECEIVED_BEFORE_FINALITY"),
                    (frame(interval="15m"), 60001, "FOREIGN_KLINE"),
                    (b'{"e":"kline","e":"kline"}', 60001, "DUPLICATE_JSON_KEY"),
                    (b'{}', 60001, "BINANCE_KLINE_REQUIRED"),
                ]:
                    with self.subTest(error=error):
                        with self.assertRaisesRegex(ValueError, error):
                            ingest_closed_1m_frame(store, raw, received_at_ms=received)


if __name__ == "__main__":
    unittest.main()
