"""Offline regression tests for stale PONG admission using the pinned quota."""
import ast
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


cycle_path, quota_path = map(Path, sys.argv[1:3])
sys.argv = sys.argv[:1]
sys.path.insert(0,str(cycle_path.resolve().parents[1]))
from tools.atlas_ws_receive_diagnostics import _PingProof, consume_recent_ping
tree = ast.parse(cycle_path.read_text(encoding="utf-8"))
helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"send_research_pong", "read_research_frame"}]
scope = {}
exec(compile(ast.Module(body=helpers, type_ignores=[]), str(cycle_path), "exec"), scope)
send = scope["send_research_pong"]
spec = importlib.util.spec_from_file_location("pinned_quota", quota_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class PongAdmission(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.quota = module.Quota(Path(self.directory.name) / "quota.sqlite",
                                  module.Limits(rest_weight=2, connections=4))
        self.start = 100000
        self.assertTrue(self.quota.connect("research-15m", self.start, ["btcusdt@kline_15m"]))
        self.sent = []
        self.connection = types.SimpleNamespace(pong=self.sent.append)

    def test_fresh_pong_sent(self):
        send(self.quota, "research-15m", self.start + 20000, self.connection, b"ping")
        self.assertEqual(self.sent, [b"ping"])

    def test_fresh_ping_proof_allows_buffered_following_frame(self):
        self.connection.frame_buffer = types.SimpleNamespace(
            needs_header=lambda: True, recv_buffer=b"next-frame"
        )
        self.connection._atlas_verified_ping = _PingProof(self.connection, b"ping")
        send(self.quota, "research-15m", self.start + 71038, self.connection, b"ping")
        self.assertEqual(self.sent, [b"ping"])
        self.assertFalse(hasattr(self.connection, "_atlas_verified_ping"))

    def test_ping_proof_is_one_use_and_bound_to_connection_and_payload(self):
        self.connection._atlas_verified_ping = _PingProof(self.connection, b"ping")
        self.assertTrue(consume_recent_ping(self.connection, b"ping"))
        self.assertFalse(consume_recent_ping(self.connection, b"ping"))
        self.connection._atlas_verified_ping = _PingProof(self.connection, b"ping")
        other = types.SimpleNamespace(_atlas_verified_ping=self.connection._atlas_verified_ping)
        self.assertFalse(consume_recent_ping(other, b"ping"))
        self.connection._atlas_verified_ping = _PingProof(self.connection, b"ping")
        self.assertFalse(consume_recent_ping(self.connection, b"replay"))

    def test_stale_socket_is_retryable_without_sending(self):
        with self.assertRaisesRegex(TimeoutError, "^PONG_LIVENESS_EXPIRED$"):
            send(self.quota, "research-15m", self.start + 71038, self.connection, b"ping")
        self.assertEqual(self.sent, [])

    def test_exact_stale_boundary(self):
        with self.assertRaises(TimeoutError):
            send(self.quota, "research-15m", self.start + 60000, self.connection, b"ping")

    def test_actual_message_exhaustion_is_terminal(self):
        for _ in range(2):
            send(self.quota, "research-15m", self.start + 1, self.connection, b"ping")
        with self.assertRaisesRegex(ValueError, "^PONG_QUOTA_STOP$"):
            send(self.quota, "research-15m", self.start + 1, self.connection, b"ping")

    def test_ban_is_terminal_even_on_stale_socket(self):
        with self.quota.tx() as db:
            self.quota.set(db, "ban", 1)
        with self.assertRaises(ValueError):
            send(self.quota, "research-15m", self.start + 71038, self.connection, b"ping")

    def test_missing_socket_is_terminal(self):
        self.quota.disconnect("research-15m", self.start + 1, failed=False)
        with self.assertRaises(ValueError):
            send(self.quota, "research-15m", self.start + 71038, self.connection, b"ping")

    def test_expired_connection_is_terminal(self):
        with self.assertRaises(ValueError):
            send(self.quota, "research-15m", self.start + 86390000, self.connection, b"ping")

    def test_reconnect_keeps_attempt_budget_and_restores_pong(self):
        with self.quota.tx() as db:
            self.quota.set(db, "research_connection_attempts", 1)
        with self.assertRaises(TimeoutError):
            send(self.quota, "research-15m", self.start + 71038, self.connection, b"ping")
        self.quota.disconnect("research-15m", self.start + 71038)
        later = self.start + 75000
        self.assertTrue(self.quota.connect("research-15m", later, ["btcusdt@kline_15m"]))
        with self.quota.tx() as db:
            self.assertEqual(self.quota.get(db, "research_connection_attempts"), 1)
        send(self.quota, "research-15m", later + 20000, self.connection, b"ping")
        self.assertEqual(self.sent, [b"ping"])


class ClosedSocketAdmission(unittest.TestCase):
    def test_library_close_is_retryable_and_preserves_cause(self):
        from websocket import WebSocketConnectionClosedException
        original = WebSocketConnectionClosedException("provider text must not be logged")
        transport = types.SimpleNamespace(frame=lambda *args: (_ for _ in ()).throw(original))
        with self.assertRaises(ConnectionResetError) as captured:
            scope["read_research_frame"](transport, object(), 30)
        self.assertEqual(str(captured.exception), "WS_CONNECTION_CLOSED")
        self.assertIs(captured.exception.__cause__, original)

    def test_next_attempt_can_receive_after_close(self):
        from websocket import WebSocketConnectionClosedException
        calls = []
        def frame(connection, timeout):
            calls.append(connection)
            if len(calls) == 1:
                raise WebSocketConnectionClosedException("closed")
            return "ping", b"token"
        transport = types.SimpleNamespace(frame=frame)
        with self.assertRaises(ConnectionResetError):
            scope["read_research_frame"](transport, "first", 30)
        self.assertEqual(scope["read_research_frame"](transport, "second", 30), ("ping", b"token"))
        self.assertEqual(calls, ["first", "second"])

    def test_integrity_error_stays_terminal(self):
        original = ValueError("WS_UNEXPECTED_FRAMING")
        transport = types.SimpleNamespace(frame=lambda *args: (_ for _ in ()).throw(original))
        with self.assertRaises(ValueError) as captured:
            scope["read_research_frame"](transport, object(), 30)
        self.assertIs(captured.exception, original)

    def test_timeout_keeps_existing_classification(self):
        original = TimeoutError("WS_READ_TIMEOUT")
        transport = types.SimpleNamespace(frame=lambda *args: (_ for _ in ()).throw(original))
        with self.assertRaises(TimeoutError) as captured:
            scope["read_research_frame"](transport, object(), 30)
        self.assertIs(captured.exception, original)


if __name__ == "__main__":
    unittest.main()
