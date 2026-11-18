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
tree = ast.parse(cycle_path.read_text(encoding="utf-8"))
helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "send_research_pong")
scope = {}
exec(compile(ast.Module(body=[helper], type_ignores=[]), str(cycle_path), "exec"), scope)
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


if __name__ == "__main__":
    unittest.main()
