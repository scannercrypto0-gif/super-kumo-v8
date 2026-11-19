import json
import tempfile
import unittest
from pathlib import Path

from aql.research_capture_spool import seal_capture
from aql.research_live_one_shot import run_live_research_one_shot
from aql.research_live_1m_capture import AUTHORIZATION, capture_live


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

    def test_real_adapter_mock_socket_to_durable_readback(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            class Socket:
                def __init__(self):
                    self.frames = iter([frame(i) for i in range(5)])
                    self.closed = False
                def settimeout(self, value):
                    assert 0 < value <= 5
                def recv_data(self, control_frame=False):
                    assert control_frame
                    return (1, next(self.frames))
                def close(self):
                    self.closed = True
            sock = Socket()
            def injected_capture(**kwargs):
                return capture_live(**kwargs,
                    connection_factory=lambda endpoint, **opts: sock,
                    monotonic=lambda: 0.0, clock_ms=lambda: 300001)
            with patch("websocket.ABNF.OPCODE_TEXT", 1):
                result = run_live_research_one_shot(
                    spool_dir=root / "spool", store_path=root / "research.sqlite",
                    authorization=AUTHORIZATION, capture=injected_capture)
            self.assertTrue(sock.closed)
            self.assertEqual(result["status"], "CAPTURE_TO_DURABLE_RESEARCH_PASS")
            self.assertEqual(result["durability"]["status"], "OFFLINE_PINNED_SOURCE_DURABILITY_PASS")
            self.assertEqual(result["core_scanner_factory_e2e"], "NOT_ATTESTED")

    def test_refuse_unapproved_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED"):
                run_live_research_one_shot(spool_dir=tmp, store_path=Path(tmp) / "db",
                    authorization="", capture=lambda **kw: self.fail("must not capture"))

    def test_refuse_incomplete_timeframe_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "LIVE_RESEARCH_INTERVAL_UNSUPPORTED"):
                run_live_research_one_shot(spool_dir=tmp, store_path=Path(tmp) / "db",
                    authorization=AUTHORIZATION, interval="15m", frame_limit=5,
                    capture=lambda **kw: self.fail("must not capture"))


if __name__ == "__main__":
    unittest.main()
