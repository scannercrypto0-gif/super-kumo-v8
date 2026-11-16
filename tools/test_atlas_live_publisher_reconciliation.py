"""Changed-delta acceptance for the two-lane receipt, with generated prices."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_live_publisher_reconciliation import (
    DAY, ENDPOINT, MINUTE, STEP, factory_view, observation_meta, publish, reconcile, sealed,
)

START = 20_000 * DAY
UNCERTAINTY = 100
NOW = START + DAY + 3 * STEP
SHA = "a" * 64


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(slot=START, endpoint=ENDPOINT, bar_count=4, wall_ms=3_900_000,
                         rest_requests=0, retention="SANITIZED_RECEIPTS_ONLY")
        self.plan_pin = digest(self.plan)
        self.frames = {}
        bars = []
        for i in range(4):
            slot = START + i * STEP
            event = slot + STEP + 10
            raw = json.dumps({"E": event, "k": dict(s="BTCUSDT", i="15m", t=slot, T=slot + STEP - 1,
                x=True, o="100.125", h="110", l="90", c="101", v="1.5")}).encode()
            self.frames[slot] = raw
            row = dict(slot=slot, event_ms=event, received_ms=event + 110,
                       committed_ms=event + 112, payload_sha256=sha256(raw).hexdigest(),
                       ack_sha256=SHA, scanner_sha256=SHA)
            row["source_sha256"] = digest(observation_meta(row, self.plan_pin, UNCERTAINTY))
            bars.append(row)
        self.live = sealed(dict(plan_sha256=self.plan_pin, retention="SANITIZED_RECEIPTS_ONLY",
                        rest_requests=0, bars=bars, admission="WAIT_AUTHENTICATED_PARENTS",
                        factory=sealed(dict(schema="aql.factory.prospective-research-read.v1",
                                     evidence_mode="SYNTHETIC_TESTED", as_of_ms=START + 5 * STEP,
                                     orders_enabled=False, secretary_enqueued=False, trading_authority="NONE"))))
        self.day = dict(start_ms=START, end_ms=START + DAY, manifest_sha256=SHA, archive_sha256=SHA,
                        checksum_sha256=SHA, result_sha256=SHA, core253=SHA,
                        published_at_ms=START + DAY + 1, source_cutoff_ms=START + DAY + STEP,
                        bars=[dict(bar_open_ms=slot, bar_close_ms=slot + MINUTE - 1,
                                   open=100.125, high=110, low=90, close=101, volume=0.1)
                              for slot in range(START, START + DAY, MINUTE)])

    def run_receipt(self, *days, live=None, **kw):
        live = self.live if live is None else live
        with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
            return reconcile(live, live["sha256"], self.plan, self.plan_pin, UNCERTAINTY,
                             NOW, days, **kw)

    def test_pending_and_metadata_only(self):
        pending = self.run_receipt()
        self.assertEqual({row["publisher_status"] for row in pending["rows"]}, {"PUBLISHER_PENDING"})
        detached = self.run_receipt(self.day)
        self.assertEqual({row["comparison"] for row in detached["rows"]}, {"COMPARISON_NOT_POSSIBLE"})
        self.assertEqual({row["reason"] for row in detached["rows"]}, {"LIVE_VALUES_NOT_RETAINED"})
        self.assertTrue(all(row["freshness_at_as_of"] == "STALE" for row in detached["rows"]))

    def test_comparable_values_quarantine_and_preserve_prior(self):
        same = self.run_receipt(self.day, live_frames=self.frames)
        self.assertEqual({row["comparison"] for row in same["rows"]}, {"MATCH"})
        revision = deepcopy(self.day)
        revision["archive_sha256"] = "b" * 64
        revision["bars"][14]["close"] = 102
        changed = self.run_receipt(revision, live_frames=self.frames, previous=same, previous_pin=same["sha256"])
        self.assertEqual(changed["rows"][0]["comparison"], "MISMATCH")
        self.assertEqual(changed["rows"][0]["publisher_status"], "DISCREPANCY_QUARANTINED")
        self.assertEqual(changed["rows"][0]["reason"], "PUBLISHER_ARCHIVE_REVISION")
        self.assertEqual(changed["previous_sha256"], same["sha256"])
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for receipt in (same, same, changed):
                publish(root / f'{receipt["sha256"]}.json', receipt)
            self.assertEqual(len(list(root.iterdir())), 2)
            for path in root.iterdir():
                body = path.read_bytes()
                self.assertNotIn(b'"open"', body)
                self.assertNotIn(b'100.125', body)
                self.assertNotIn(b'"payload"', body)
            original = json.loads((root / f'{same["sha256"]}.json').read_bytes())
            self.assertEqual(original, same)
            self.assertEqual(factory_view(original, same["sha256"])["current_entry"], "NO_CURRENT_ENTRY")

    def test_missing_partial_late_and_unknown_release(self):
        partial = {**self.day, "bars": self.day["bars"][1:]}
        self.assertEqual(self.run_receipt(partial, live_frames=self.frames)["rows"][0]["publisher_status"], "SOURCE_MISSING")
        unknown = {**self.day, "published_at_ms": None}
        self.assertEqual(self.run_receipt(unknown, live_frames=self.frames)["rows"][0]["reason"], "PUBLISHER_FIRST_AVAILABLE_UNKNOWN")
        late = {**self.day, "source_cutoff_ms": NOW + 1}
        self.assertIsNone(self.run_receipt(late, live_frames=self.frames)["rows"][0]["publisher"])
        with self.assertRaisesRegex(ValueError, "PUBLISHER_DUPLICATE_DAY"):
            self.run_receipt(self.day, self.day)

    def test_foreign_session_duplicate_slot_and_future_clock(self):
        for key, value, error in (("slot", START + STEP, "LIVE_FINAL_ORDER_OR_GAP"),
                                  ("source_sha256", SHA, "LIVE_SOURCE_SESSION"),
                                  ("received_ms", NOW + 1, "LIVE_SOURCE_CLOCK")):
            tampered = deepcopy(self.live)
            tampered["bars"][0][key] = value
            self.assertRaisesRegex(ValueError, error, self.run_receipt,
                                  live=sealed({k: v for k, v in tampered.items() if k != "sha256"}))
        with self.assertRaisesRegex(ValueError, "COMPARABLE_LIVE_PIN"):
            self.run_receipt(self.day, live_frames={START: b"tampered"})
        with self.assertRaisesRegex(ValueError, "FOREIGN_COMPARABLE_SLOT"):
            self.run_receipt(self.day, live_frames={START + DAY: b"foreign"})
        partial = deepcopy(self.live)
        frame = json.loads(self.frames[START])
        frame["k"]["x"] = False
        raw = json.dumps(frame).encode()
        row = partial["bars"][0]
        row["payload_sha256"] = sha256(raw).hexdigest()
        row["source_sha256"] = digest(observation_meta(row, self.plan_pin, UNCERTAINTY))
        with self.assertRaisesRegex(ValueError, "CANDLE_NOT_FINAL"):
            self.run_receipt(self.day, live_frames={START: raw},
                             live=sealed({k: v for k, v in partial.items() if k != "sha256"}))


if __name__ == "__main__":
    unittest.main()
