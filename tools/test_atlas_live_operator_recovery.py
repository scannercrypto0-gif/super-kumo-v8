"""Focused offline contract for distinguishing a reconnect from a resumed segment."""
from datetime import datetime, timezone
import unittest

from aql.observation.contracts import digest
from tools.atlas_operator_report import live_windows_view

STEP = 900_000


def entry(status, at, slot, reason=""):
    return dict(status=status, utc=datetime.fromtimestamp(at / 1000, timezone.utc).isoformat(),
                slot_ms=slot, reason=reason)


def receipt(slot, previous=None, failure=None, missing=0):
    final = slot + STEP
    factory = {"status": "synthetic"}
    factory["sha256"] = digest(factory)
    body = dict(observation=dict(slot=slot, event_ms=final, received_ms=final + 1,
                                 committed_ms=final + 2),
                factory=factory, heartbeat_ms=final + 3, connection_attempts=2 if failure else 1,
                last_failure=failure, previous_sha256=previous, missing_slots=missing,
                retention="SANITIZED_RECEIPTS_ONLY", orders=0, dispatch=None,
                secretary="WAIT", telegram="NOT_SENT")
    return {**body, "sha256": digest(body)}


class LiveRecoveryReportTest(unittest.TestCase):
    def test_hold_then_new_segment_final_leaves_gap_and_resolves_fault(self):
        timeout = {"error": "TimeoutError", "utc_ms": 1_000_000}
        reset = {"error": "ConnectionResetError", "utc_ms": 1_900_000}
        first = receipt(STEP, failure=timeout)
        started = [entry("STARTED", 1000, 0), entry("FAILED", 1_900_001, 0, "PILOT_STOP_ConnectionResetError")]
        snapshot = dict(as_of_ms=2_000_000, receipts=[first], supervisor=started,
                        transport=[dict(status="TRANSPORT_INTERRUPTED", **item)
                                   for item in (timeout, reset)],
                        task_state="Ready", task_enabled=True, last_task_result=1,
                        writer_policy="IgnoreNew", last_heartbeat_ms=1_899_999,
                        hold={"reason": "PILOT_STOP_ConnectionResetError"}, stop_requested=False,
                        config_sha256="0" * 64, daily={"unchanged": True})
        held = live_windows_view(snapshot)
        self.assertEqual(held["status"], "HELD")
        self.assertEqual(held["recovery"], "REAL_RECONNECT_ATTESTED")
        self.assertEqual([row["unresolved"] for row in held["errors"]], [True, False, True])

        resumed = receipt(3 * STEP, previous=first["sha256"], missing=1)
        recovered = live_windows_view({**snapshot, "hold": None, "task_state": "Running",
                                       "as_of_ms": 4 * STEP + 4, "last_heartbeat_ms": 4 * STEP + 3,
                                       "receipts": [first, resumed],
                                       "supervisor": started + [entry("STARTED", 3 * STEP + 4, 3 * STEP)]})
        self.assertEqual(recovered["status"], "ACTIVE_RESEARCH_ONLY")
        self.assertEqual(recovered["segment_rollover"], "NOT_YET_ATTESTED")
        self.assertEqual(recovered["missing_slots_in_window"], 1)
        self.assertFalse(any(row["unresolved"] for row in recovered["errors"]))
        self.assertEqual(recovered["errors"][-1]["recovery"], "FINAL_RECEIPT_AFTER_NEW_SEGMENT")


if __name__ == "__main__":
    unittest.main()
