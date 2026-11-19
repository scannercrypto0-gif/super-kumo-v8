"""Generated-only one-shot pinned source integration tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aql.research_offline_one_shot import run_one_shot


def ws_frame(open_ms):
    return json.dumps({
        "e": "kline", "E": open_ms + 60000, "s": "BTCUSDT",
        "k": {"t": open_ms, "T": open_ms + 59999, "s": "BTCUSDT",
              "i": "1m", "x": True, "o": "10", "h": "12",
              "l": "9", "c": "11", "v": "2"},
    }, separators=(",", ":")).encode()


class OneShotTest(unittest.TestCase):
    def test_ws_source_to_durable_5m_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jsonl"
            source.write_bytes(b"\n".join(ws_frame(i * 60000) for i in range(5)) + b"\n")
            kwargs = dict(store_path=Path(tmp) / "research.sqlite", source_path=source,
                          sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          source_kind="ws_jsonl", source_clock_ms=300001)
            first = run_one_shot(**kwargs)
            self.assertEqual(first["status"], "OFFLINE_PINNED_SOURCE_DURABILITY_PASS")
            self.assertEqual(first["durability"]["constituent_count"], 5)
            self.assertEqual(first["operational_core_scanner_factory_secretary"], "NOT_ATTESTED")
            self.assertEqual(run_one_shot(**kwargs), first)

    def test_incomplete_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jsonl"
            source.write_bytes(ws_frame(0) + b"\n")
            with self.assertRaisesRegex(ValueError, "SOURCE_WINDOW_INCOMPLETE"):
                run_one_shot(store_path=Path(tmp) / "research.sqlite",
                             source_path=source,
                             sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                             source_kind="ws_jsonl", source_clock_ms=60001)


if __name__ == "__main__":
    unittest.main()
