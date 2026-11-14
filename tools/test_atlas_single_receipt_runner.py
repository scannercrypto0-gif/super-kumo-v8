"""Socket-free tests for the one-shot runner with native SQLite consumers."""
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_single_receipt_runner import ENDPOINT, STEP, prepare, run
from tools.binance_live_feed.quota import Limits, Quota


class Clock:
    elapsed = 0

    def __init__(self):
        self.slot = (time.time_ns() // 1000000 // STEP - 1) * STEP

    def now(self):
        return self.slot + self.elapsed

    def monotonic_ns(self):
        return self.elapsed * 1000000


class Wire:
    attempts = 0

    def __init__(self, clock, *, status=101, bad=None):
        self.clock, self.status, self.bad = clock, status, bad

    @contextmanager
    def stream(self, endpoint, timeout):
        assert endpoint == ENDPOINT and 0 < timeout <= 5
        self.attempts += 1
        yield self

    def getstatus(self):
        return self.status

    def frame(self, connection, timeout):
        assert connection is self and 0 < timeout <= 1200
        start = self.clock.slot
        end = start + STEP - 1
        self.clock.elapsed = STEP + 500 if self.bad != "late" else STEP + 300000
        k = dict(s="BTCUSDT", i="15m", t=start, T=end, o="100",
                 h="102", l="99", c="101", v="3", x=True)
        if self.bad == "slot":
            k["t"] -= STEP
        if self.bad == "nonfinal":
            k["x"] = False
            self.bad = "late"
        return "text", json.dumps({"E": end + 10, "k": k}).encode()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "run"
        self.clock = Clock()
        self.plan = prepare(self.clock.slot, 0)
        self.quota = Quota(Path(tmp.name) / "budget.sqlite", Limits(rest_weight=40))
        guard = patch.object(socket, "socket", side_effect=AssertionError("NETWORK_NOT_ALLOWED"))
        guard.start()
        self.addCleanup(guard.stop)

    def execute(self, wire, offline=True):
        return run(self.root, plan=self.plan, pin=digest(self.plan), clock=self.clock,
                   clock_checked_ms=self.clock.slot, quota=self.quota, transport=wire, offline=offline)

    def test_end_to_end_and_process_reopen(self):
        wire = Wire(self.clock)
        # Fix only G1's UTC for deterministic commit-order verification.
        with patch("time.time", side_effect=lambda: self.clock.now() / 1000), \
             patch("tools.atlas_single_receipt.time_ns", side_effect=lambda: self.clock.now() * 1000000), \
             patch("aql.observation.prospective.time_ns", side_effect=lambda: self.clock.now() * 1000000):
            result = self.execute(wire)
        self.assertEqual(wire.attempts, 1)
        self.assertEqual(result["factory"]["decision_counts"], {"UNKNOWN": 1})
        self.assertEqual(result["factory_admission"], "WAIT_AUTHENTICATED_PARENTS")
        self.assertFalse(result["factory"]["orders_enabled"])
        self.assertFalse(result["factory"]["secretary_enqueued"])
        script = ("from tools.atlas_single_receipt import readback; from pathlib import Path;"
                  "import sys,json; print(json.dumps(readback(Path(sys.argv[1]),"
                  "cutoff_ms=int(sys.argv[2]),synthetic=True)))")
        raw = subprocess.check_output([sys.executable, "-B", "-c", script, str(self.root),
                                       str(result["factory"]["as_of_ms"])])
        self.assertEqual(json.loads(raw), result)
        print("FIXTURE_READBACK_SHA256=" + result["sha256"])
        self.clock.elapsed = 0
        with self.assertRaises(FileExistsError):
            self.execute(wire)
        self.assertEqual(wire.attempts, 1)

    def test_unqualified_egress_stops_before_reservation(self):
        wire = Wire(self.clock)
        with self.assertRaisesRegex(ValueError, "SHARED_EGRESS_UNVERIFIED"):
            self.execute(wire, offline=False)
        self.assertFalse(self.root.exists())
        self.assertEqual(wire.attempts, 0)

    def test_rate_limit_and_bad_frames_consume_only_one_attempt(self):
        for bad, status, reason in (
            (None, 418, "PROVIDER_RATE_STOP"), (None, 429, "PROVIDER_RATE_STOP"),
            ("slot", 101, "CANDLE_IDENTITY"), ("late", 101, "DEADLINE"),
            ("nonfinal", 101, "DEADLINE"),
        ):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp) / "run"
                self.quota = Quota(Path(tmp) / "budget.sqlite", Limits(rest_weight=40))
                self.clock.elapsed = 0
                wire = Wire(self.clock, status=status, bad=bad)
                with self.assertRaisesRegex(ValueError, reason):
                    self.execute(wire)
                self.assertEqual(wire.attempts, 1)
                self.assertFalse((self.root / "receipt.sqlite").exists())
