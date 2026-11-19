import json
import tempfile
import unittest
from pathlib import Path

from aql.research_1m_collector import collect_authorized_1m
from aql.research_offline_one_shot import run_one_shot

AUTH = "OWNER_AUTHORIZED_ORIGINAL_1M_RESEARCH_CAPTURE"


def frame(i, final=True):
    t = i * 60000
    return json.dumps({"e": "kline", "E": t + 60000, "s": "BTCUSDT",
        "k": {"t": t, "T": t + 59999, "s": "BTCUSDT", "i": "1m",
              "x": final, "o": "10", "h": "12", "l": "9",
              "c": "11", "v": "2"}}).encode()


class CollectorTest(unittest.TestCase):
    def test_injected_frames_to_pinned_durable_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = iter([("text", frame(0, False))] +
                          [("text", frame(i)) for i in range(5)])
            sealed = collect_authorized_1m(
                reader=lambda: next(events), clock_ms=lambda: 300001,
                spool_dir=Path(tmp) / "spool", authorization=AUTH,
                frame_limit=5, event_limit=6)
            result = run_one_shot(store_path=Path(tmp) / "store.sqlite",
                source_path=Path(sealed["path"]), sha256=sealed["sha256"],
                source_kind="ws_jsonl", source_clock_ms=300001)
            self.assertEqual(result["status"], "OFFLINE_PINNED_SOURCE_DURABILITY_PASS")

    def test_authorization_required_before_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED"):
                collect_authorized_1m(reader=lambda: self.fail("must not read"),
                    clock_ms=lambda: 60001, spool_dir=Path(tmp), authorization="",
                    frame_limit=1)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_foreign_provisional_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads(frame(0, False))
            raw["s"] = "ETHUSDT"
            with self.assertRaisesRegex(ValueError, "PROVISIONAL_KLINE"):
                collect_authorized_1m(
                    reader=lambda: ("text", json.dumps(raw).encode()),
                    clock_ms=lambda: 60001, spool_dir=Path(tmp) / "spool",
                    authorization=AUTH, frame_limit=1, event_limit=1)
            self.assertFalse((Path(tmp) / "spool").exists())

    def test_gap_refuses_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = iter([("text", frame(0)), ("text", frame(2))])
            with self.assertRaisesRegex(ValueError, "CAPTURE_GAP_DUPLICATE"):
                collect_authorized_1m(reader=lambda: next(events),
                    clock_ms=lambda: 180001, spool_dir=Path(tmp) / "spool",
                    authorization=AUTH, frame_limit=2, event_limit=2)
            self.assertFalse((Path(tmp) / "spool").exists())


if __name__ == "__main__":
    unittest.main()
