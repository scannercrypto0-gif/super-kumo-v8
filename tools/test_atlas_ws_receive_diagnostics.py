"""Exercise the pinned #305 parser with synthetic byte fragments and faults."""
import unittest
from unittest.mock import Mock, patch

import websocket

from tools.atlas_ws_receive_diagnostics import receive_fault_context
from tools.binance_live_feed.run_pilot import PublicTransport


class ReceiveDiagnostics(unittest.TestCase):
    def read(self, fragments, *, monotonic, error=TimeoutError):
        connection = websocket.WebSocket()
        original = Mock(side_effect=fragments)
        connection.frame_buffer.recv = original
        with patch("tools.binance_live_feed.run_pilot.time.monotonic", side_effect=monotonic):
            with self.assertRaises(error) as caught:
                PublicTransport().frame(connection, 30)
        self.assertIs(connection.frame_buffer.recv, original)
        if error is TimeoutError:
            self.assertEqual(str(caught.exception), "WS_READ_TIMEOUT")
        return receive_fault_context(connection, caught.exception)

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
        self.assertEqual(receive_fault_context(None, TimeoutError()), {})

    def test_connection_reset_is_distinct_at_boundary_and_mid_frame(self):
        for fragments, ticks, phase in (
            ([ConnectionResetError("test reset")], (0, 1), "FRAME_BOUNDARY"),
            ([b"\x81\x7e", b"\x01", ConnectionResetError("test reset")],
             (0, 1, 2, 3), "EXTENDED_LENGTH"),
        ):
            with self.subTest(phase=phase):
                self.assertEqual(self.read(fragments, monotonic=ticks, error=ConnectionResetError),
                                 {"receive_phase": phase, "deadline_origin": "CONNECTION_RESET"})

    def test_unsupported_frame_does_not_become_a_transport_retry(self):
        connection = websocket.WebSocket()
        original = Mock(side_effect=[b"\x82\x01", b"x"])
        connection.frame_buffer.recv = original
        with self.assertRaisesRegex(ValueError, "WS_CLOSED_OR_UNSUPPORTED_FRAME"):
            PublicTransport().frame(connection, 30)
        self.assertIs(connection.frame_buffer.recv, original)


if __name__ == "__main__":
    unittest.main()


def test_verified_ping_token_is_bound_one_use_and_complete():
    import websocket
    from unittest.mock import patch
    from tools.atlas_ws_receive_diagnostics import remember_complete_ping,consume_recent_ping
    c=websocket.WebSocket();other=websocket.WebSocket()
    f=websocket.ABNF(fin=1,opcode=9,mask_value=0,data=b'ping')
    with patch('time.monotonic_ns',return_value=100):
        assert remember_complete_ping(c,f)
        assert consume_recent_ping(c,b'ping')
        assert not consume_recent_ping(c,b'ping')
        assert remember_complete_ping(c,f)
        other._atlas_verified_ping=c._atlas_verified_ping
        assert not consume_recent_ping(other,b'ping')
        assert not consume_recent_ping(c,b'wrong')
        assert remember_complete_ping(c,f)
    # A scheduling pause does not invalidate the one-read PING proof; the next read clears it.\n    with patch('time.monotonic_ns',return_value=1000000101):assert consume_recent_ping(c,b'ping')
    for change in ('fin','mask_value','rsv1'):
        f=websocket.ABNF(fin=1,opcode=9,mask_value=0,data=b'ping')
        setattr(f,change,0 if change=='fin' else 1)
        assert not remember_complete_ping(c,f)
