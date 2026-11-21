import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aql.research_live_1m_capture import (
    AUTHORIZATION, ENDPOINT, capture_live,
)


def frame(i):
    t = i * 60000
    return json.dumps({"e": "kline", "E": t + 60000, "s": "BTCUSDT",
        "k": {"t": t, "T": t + 59999, "s": "BTCUSDT", "i": "1m",
              "x": True, "o": "10", "h": "12", "l": "9",
              "c": "11", "v": "2"}}).encode()


class FakeConnection:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.closed = False
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def recv_data(self, control_frame=False):
        assert control_frame
        return 1, next(self.frames)

    def close(self):
        self.closed = True


class LiveAdapterTest(unittest.TestCase):
    def test_no_network_without_explicit_authority(self):
        with self.assertRaisesRegex(ValueError, "ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED"):
            capture_live(spool_dir="unused", authorization="",
                         connection_factory=lambda *a, **kw: self.fail("network opened"))

    def test_injected_transport_seals_source_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = FakeConnection([frame(i) for i in range(5)])
            def connect(endpoint, **kwargs):
                self.assertEqual(endpoint, ENDPOINT)
                self.assertEqual(kwargs["timeout"], 5)
                return conn
            with patch("websocket.ABNF.OPCODE_TEXT", 1):
                result = capture_live(
                    spool_dir=Path(tmp), authorization=AUTHORIZATION,
                    frame_limit=5, connection_factory=connect,
                    monotonic=lambda: 0.0, clock_ms=lambda: 300001)
            self.assertEqual(result["frames"], 5)
            self.assertTrue(conn.closed)
            self.assertEqual(len(conn.timeouts), 5)
            self.assertTrue(Path(result["path"]).is_file())

    def test_failed_receive_closes_connection_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = FakeConnection([])
            with self.assertRaises(StopIteration):
                capture_live(spool_dir=Path(tmp), authorization=AUTHORIZATION,
                    frame_limit=1, connection_factory=lambda *a, **kw: conn,
                    monotonic=lambda: 0.0, clock_ms=lambda: 60001)
            self.assertTrue(conn.closed)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
