"""Pinned Binance Spot research WebSocket framing; no scheduler or REST entry point."""
from contextlib import contextmanager
import ssl
import time

ENDPOINT = "wss://data-stream.binance.vision/ws/btcusdt@kline_15m"


def need(condition, code):
    if not condition:
        raise ValueError(code)


class ResearchWebSocket:
    @contextmanager
    def stream(self, timeout, *, endpoint=ENDPOINT):
        need(endpoint == ENDPOINT, "WS_ENDPOINT_NOT_ALLOWED")
        import websocket

        connection = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True})
        try:
            connection.settimeout(timeout)
            connection.connect(endpoint, redirect_limit=0, http_no_proxy=["data-stream.binance.vision"])
            need(connection.getstatus() == 101, "WS_UPGRADE")
            receive = connection.frame_buffer.recv_strict

            def bounded_receive(size):
                need(size <= 4096, "WS_FRAME_BOUND")
                return receive(size)

            connection.frame_buffer.recv_strict = bounded_receive
            yield connection
        finally:
            connection.shutdown()

    def frame(self, connection, timeout):
        import websocket

        end = time.monotonic() + timeout
        receive = connection.frame_buffer.recv

        def timed_receive(size):
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise websocket.WebSocketTimeoutException("frame deadline")
            connection.settimeout(remaining)
            return receive(size)

        connection.frame_buffer.recv = timed_receive
        try:
            frame = connection.recv_frame()
        except websocket.WebSocketTimeoutException as exc:
            # A timeout can interrupt a frame. Stop instead of resuming mid-frame.
            raise TimeoutError("WS_READ_TIMEOUT") from exc
        finally:
            connection.frame_buffer.recv = receive
        need(frame.fin and not frame.mask_value and not (frame.rsv1 or frame.rsv2 or frame.rsv3),
             "WS_UNEXPECTED_FRAMING")
        kind = {websocket.ABNF.OPCODE_TEXT: "text", websocket.ABNF.OPCODE_PING: "ping"}.get(frame.opcode)
        need(kind is not None, "WS_CLOSED_OR_UNSUPPORTED_FRAME")
        return kind, frame.data


def receive_fault_context(connection, error):
    """Expose parser progress and fault origin without inspecting payload bytes."""
    wrapped = error.__cause__
    if isinstance(error, ConnectionResetError):
        origin = "CONNECTION_RESET"
    elif type(error) is TimeoutError and str(error) == "WS_READ_TIMEOUT" and wrapped is not None:
        origin = "OUTER_FRAME_DEADLINE" if str(wrapped) == "frame deadline" else "UNDERLYING_RECEIVE_TIMEOUT"
    else:
        return {}
    buffer = connection.frame_buffer
    if not buffer.needs_header():
        phase = "EXTENDED_LENGTH" if buffer.needs_length() else "FRAME_PAYLOAD"
    else:
        phase = "PARTIAL_HEADER" if buffer.recv_buffer else "FRAME_BOUNDARY"
    return {"receive_phase": phase, "deadline_origin": origin}
