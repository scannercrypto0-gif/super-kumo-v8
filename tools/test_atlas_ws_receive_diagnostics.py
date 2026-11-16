"""Exercise the pinned #305 parser with synthetic byte fragments and faults."""
import unittest
from unittest.mock import Mock, patch

import websocket

from tools.atlas_ws_receive_diagnostics import receive_timeout_context
from tools.binance_live_feed.run_pilot import PublicTransport


class ReceiveDiagnostics(unittest.TestCase):
    def read(self, fragments, *, monotonic):
        connection = websocket.WebSocket()
        original = Mock(side_effect=fragments)
        connection.frame_buffer.recv = original
        with patch("tools.binance_live_feed.run_pilot.time.monotonic", side_effect=monotonic):
            with self.assertRaisesRegex(TimeoutError, "^WS_READ_TIMEOUT$") as caught:
                PublicTransport().frame(connection, 30)
        self.assertIs(connection.frame_buffer.recv, original)
        return receive_timeout_context(connection, caught.exception)

    def test_underlying_timeout_at_frame_boundary(self):
        info = self.read([websocket.WebSocketTimeoutException("timed out")], monotonic=(0, 1))
        self.assertEqual(info, {"receive_phase": "FRAME_BOUNDARY",
                                "deadline_origin": "UNDERLYING_RECEIVE_TIMEOUT"})

    def test_outer_deadline_during_partial_header(self):
        info = self.read([b"\x81"], monotonic=(0, 1, 31))
        self.assertEqual(info, {"receive_phase": "PARTIAL_HEADER", "deadline_origin": "OUTER_FRAME_DEADLINE"})

    def test_underlying_timeout_during_payload(self):
        info = self.read([b"\x81\x04", b"ab", websocket.WebSocketTimeoutException("timed out")],
                         monotonic=(0, 1, 2, 3))
        self.assertEqual(info, {"receive_phase": "FRAME_PAYLOAD",
                                "deadline_origin": "UNDERLYING_RECEIVE_TIMEOUT"})

    def test_unrelated_timeout_is_not_attributed_to_frame_reader(self):
        self.assertEqual(receive_timeout_context(None, TimeoutError()), {})


if __name__ == "__main__":
    unittest.main()
