import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aql.research_capture_spool import seal_capture
from aql.research_offline_one_shot import run_one_shot


def frame(i):
    t = i * 60000
    return json.dumps({"e": "kline", "E": t + 60000, "s": "BTCUSDT",
        "k": {"t": t, "T": t + 59999, "s": "BTCUSDT", "i": "1m",
              "x": True, "o": "10", "h": "12", "l": "9",
              "c": "11", "v": "2"}}).encode()


class SpoolTest(unittest.TestCase):
    def test_seal_to_durable_research_one_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sealed = seal_capture(root / "spool", [frame(i) for i in range(5)], 300001)
            self.assertEqual(sealed["status"], "OFFLINE_CAPTURE_SEALED")
            self.assertEqual(seal_capture(root / "spool", [frame(i) for i in range(5)], 300001), sealed)
            result = run_one_shot(store_path=root / "research.sqlite",
                source_path=Path(sealed["path"]), sha256=sealed["sha256"],
                source_kind="ws_jsonl", source_clock_ms=300001)
            self.assertEqual(result["status"], "OFFLINE_PINNED_SOURCE_DURABILITY_PASS")
            self.assertEqual(result["trading_authority"], "NONE")

    def test_gap_rejected_without_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "spool"
            with self.assertRaisesRegex(ValueError, "CAPTURE_GAP_DUPLICATE"):
                seal_capture(root, [frame(0), frame(2)], 180001)
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
