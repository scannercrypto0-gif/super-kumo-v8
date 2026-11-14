"""Focused integration checks; never opens a socket."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from time import time_ns
import unittest

from tools import atlas_single_receipt as adapt
from tools.binance_live_feed.quota import Limits, Quota

SLOT = 1794268800000
END = SLOT + adapt.STEP - 1
RECEIVED = END + 500


def payload(**changes):
    return json.dumps({"E": END + 20, "k": {
        "s": "BTCUSDT", "i": "15m", "t": SLOT, "T": END,
        "o": "100", "h": "102", "l": "99", "c": "101", "v": "3", "x": True,
        **changes,
    }}).encode()


def persist(root, raw):
    adapt.persist_frame(root, raw, slot=SLOT, received=RECEIVED, uncertainty=1,
                        monotonic_ns=1, session="offline-fixture")


class ReceiptTests(unittest.TestCase):
    def test_native_reopen_after_capture_process_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = ("from pathlib import Path; from tools.test_atlas_single_receipt "
                    "import persist,payload; import sys,os; "
                    "persist(Path(sys.argv[1]),payload()); os._exit(73)")
            self.assertEqual(subprocess.run([sys.executable, "-B", "-c", code, tmp]).returncode, 73)
            persist(root, payload())
            with self.assertRaisesRegex(ValueError, "CANDLE_REVISION"):
                persist(root, payload(c="102"))
            adapt.materialize(root, synthetic=True)
            cutoff = time_ns() // 1000000 + 1000
            result = adapt.readback(root, cutoff_ms=cutoff, synthetic=True)
            self.assertEqual(result["factory"]["decision_counts"], {"UNKNOWN": 1})
            self.assertEqual(result["factory_admission"], "WAIT_AUTHENTICATED_PARENTS")
            self.assertFalse(result["factory"]["orders_enabled"])
            self.assertFalse(result["factory"]["secretary_enqueued"])
            code = ("from tools.atlas_single_receipt import readback; from pathlib import Path; "
                    "import json,sys; print(json.dumps(readback(Path(sys.argv[1]),"
                    "cutoff_ms=int(sys.argv[2]),synthetic=True)))")
            reopened = subprocess.check_output([sys.executable, "-B", "-c", code, tmp, str(cutoff)])
            self.assertEqual(json.loads(reopened), result)
            with self.assertRaisesRegex(ValueError, "CUTOFF_CLOCK_OVERLAP"):
                adapt.readback(root, cutoff_ms=result["committed_ms"], synthetic=True)
            with sqlite3.connect(root / "receipt.sqlite") as db:
                db.execute("UPDATE frame SET raw=?", (payload(c="102"),))
            with self.assertRaisesRegex(ValueError, "CUSTODY_TAMPER"):
                adapt.readback(root, cutoff_ms=cutoff, synthetic=True)

    def test_temporal_fail_closed(self):
        for frame, receive, uncertainty, reason in (
            (payload(x=False), RECEIVED, 1, "CANDLE_NOT_FINAL"),
            (payload(t=SLOT-900000), RECEIVED, 1, "CANDLE_IDENTITY"),
            (payload(), END + 300001, 1, "RECEIPT_OUTSIDE_WINDOW"),
            (payload(), RECEIVED, 251, "CLOCK_OR_SLOT"),
            (payload(), END + 1, 1, "EVENT_CLOCK"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                adapt.parse_final(frame, SLOT, receive, uncertainty)

    def test_local_reservation_and_provider_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            quota = Quota(Path(tmp) / "budget.sqlite", Limits(rest_weight=40))
            self.assertEqual(adapt.reserve_once(quota, RECEIVED), "SHARED_EGRESS_UNVERIFIED")
            with self.assertRaisesRegex(ValueError, "ONE_SHOT_CONSUMED"):
                adapt.reserve_once(quota, RECEIVED)
            self.assertTrue(quota.ws("receipt-15m", RECEIVED, "PONG"))
            self.assertTrue(quota.ws("receipt-15m", RECEIVED, "PONG"))
            self.assertFalse(quota.ws("receipt-15m", RECEIVED, "PONG"))
        for code in (418, 429):
            with self.assertRaisesRegex(ValueError, "PROVIDER_RATE_STOP"):
                adapt.ws_upgrade_status(code)
        adapt.ws_upgrade_status(101)
