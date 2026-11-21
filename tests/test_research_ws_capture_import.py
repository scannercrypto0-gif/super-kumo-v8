"""Generated-only offline websocket capture replay and rollback tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_ws_capture_import import import_pinned_ws_jsonl


def frame(opened, close="11"):
    return json.dumps({
        "e": "kline", "E": opened + 60000, "s": "BTCUSDT",
        "k": {"t": opened, "T": opened + 59999, "s": "BTCUSDT", "i": "1m",
              "x": True, "o": "10", "h": "12", "l": "9", "c": close, "v": "2"},
    }, separators=(",", ":")).encode()


class CaptureTest(unittest.TestCase):
    def test_replay_and_atomic_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.jsonl"
            path.write_bytes(frame(0) + b"\n" + frame(60000) + b"\n")
            pin = hashlib.sha256(path.read_bytes()).hexdigest()
            with ResearchBarStore(Path(tmp) / "store.sqlite") as store:
                opts = dict(expected_sha256=pin, received_at_ms=120001)
                self.assertEqual(import_pinned_ws_jsonl(store, path, **opts)["frame_count"], 2)
                self.assertEqual(import_pinned_ws_jsonl(store, path, **opts)["frame_count"], 2)
                with self.assertRaisesRegex(ValueError, "SOURCE_PIN_MISMATCH"):
                    import_pinned_ws_jsonl(store, path, expected_sha256="0"*64,
                                           received_at_ms=120001)
            path.write_bytes(frame(120000) + b"\n" + frame(180000) + b"\n")
            pin = hashlib.sha256(path.read_bytes()).hexdigest()
            with ResearchBarStore(Path(tmp) / "store.sqlite") as store:
                store.insert_1m(dict(symbol="BTCUSDT", interval="1m", open_ms=180000,
                                     final=True, o="10", h="12", l="9", c="10", v="2",
                                     source_sha256="a"*64, available_at_ms=240001))
                with self.assertRaisesRegex(ValueError, "SOURCE_REWRITE_DENIED"):
                    import_pinned_ws_jsonl(store, path, expected_sha256=pin,
                                           received_at_ms=240001)
                self.assertIsNone(store.read("BTCUSDT", "1m", 120000))

    def test_gap_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.jsonl"
            path.write_bytes(frame(0) + b"\n" + frame(120000) + b"\n")
            with ResearchBarStore(Path(tmp) / "store.sqlite") as store:
                with self.assertRaisesRegex(ValueError, "SOURCE_GAP_DUPLICATE"):
                    import_pinned_ws_jsonl(store, path,
                                           expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                           received_at_ms=180001)
                self.assertIsNone(store.read("BTCUSDT", "1m", 0))


if __name__ == "__main__":
    unittest.main()
