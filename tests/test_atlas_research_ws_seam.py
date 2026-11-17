"""Exercise the extracted research wire without opening a socket."""
from unittest.mock import Mock, patch

import pytest
import websocket

from aql.collector.research_ws import ResearchWebSocket, receive_fault_context


def test_foreign_endpoint_is_denied_before_socket_construction():
    with patch.object(websocket, "WebSocket", side_effect=AssertionError("network forbidden")):
        with pytest.raises(ValueError, match="WS_ENDPOINT_NOT_ALLOWED"):
            with ResearchWebSocket().stream(5, endpoint="wss://example.invalid"):
                pytest.fail("foreign endpoint connected")


def test_partial_header_reset_keeps_original_error_and_sanitized_phase():
    error = ConnectionResetError("private transport detail")
    connection = websocket.WebSocket()
    original = Mock(side_effect=[b"\x81", error])
    connection.frame_buffer.recv = original
    with pytest.raises(ConnectionResetError) as caught:
        ResearchWebSocket().frame(connection, 30)
    assert caught.value is error and connection.frame_buffer.recv is original
    assert receive_fault_context(connection, error) == {
        "receive_phase": "PARTIAL_HEADER", "deadline_origin": "CONNECTION_RESET",
    }
