import json
import tempfile
import unittest
from pathlib import Path

from aql.research_capture_spool import seal_capture
from aql.research_live_one_shot import run_live_research_one_shot
from aql.research_live_1m_capture import AUTHORIZATION


def frame(i):
    t = i * 60000
    return json.dumps({"e": "kline", "E": t + 60000, "s": "BTCUSDT",
        "k": {"t": t, "T": t + 59999, "s": "BTCUSDT", "i": "1m",
              "x": True, "o": "10", "h": "12", "l": "9",
              "c": "11", "v": "2"}}).encode()


class LiveOneShotTest(unittest.TestCase):
    def test_capture_to_independent_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def capture(**kwargs):
                self.assertEqual(kwargs["alignment_minutes"], 5)
                return seal_capture(kwargs["spool_dir"], [frame(i) for i in range(5)], 300001)
            result = run_live_research_one_shot(
                spool_dir=root / "spool", store_path=root / "store.sqlite",
                authorization=AUTHORIZATION, capture=capture)
            self.assertEqual(result["status"], "CAPTURE_TO_DURABLE_RESEARCH_PASS")
            self.assertEqual(result["durability"]["status"], "OFFLINE_PINNED_SOURCE_DURABILITY_PASS")
            self.assertEqual(result["trading_authority"], "NONE")

    def test_refuse_unapproved_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED"):
                run_live_research_one_shot(spool_dir=tmp, store_path=Path(tmp) / "db",
                    authorization="", capture=lambda **kw: self.fail("must not capture"))

    def test_refuse_incomplete_timeframe_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "CAPTURE_TOO_SHORT_FOR_INTERVAL"):
                run_live_research_one_shot(spool_dir=tmp, store_path=Path(tmp) / "db",
                    authorization=AUTHORIZATION, interval="15m", frame_limit=5,
                    capture=lambda **kw: self.fail("must not capture"))


if __name__ == "__main__":
    unittest.main()
