"""ATLAS B single contiguous synthetic acceptance: G1 -> actual Scanner -> Core G2 -> Secretary.

No source network, trading, Paper, private owner data, or H2 replay. The
actual Scanner #277 is checked out at its exact SHA by the workflow.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

# Reuse the already accepted exact-Scanner G1 fixture/producer without
# rerunning its independent test cases or creating a fake scanner receipt.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_g1_g2_scanner_exact_head as pinned_scanner

from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, BridgeStop
from aql.observation.secretary_g2_readonly_v1 import (
    ACK_FIELDS, SecretaryReadStop, consume_verified_opportunity,
    read_secretary_receipt,
)


class AtlasBOneContiguousGate(unittest.TestCase):
    def test_actual_scanner_to_durable_g2_to_secretary_with_restart_and_denials(self):
        scope = pinned_scanner.ExactHeadScannerProducerToCore(
            methodName="test_actual_scanner_emission_through_restart_and_three_horizons"
        )
        scope.setUp()
        try:
            event = scope.actual_emitter()  # REAL pinned Scanner code, separate process.
            self.assertEqual(event["trading_authority"], "NONE")
            self.assertFalse(event["orders_enabled"])
            self.assertIsNone(event["source_ack_sha256"])
            self.assertIsNone(event["strategy_approval_sha256"])
            self.assertIsNone(event["factory_consumer_ack_sha256"])
            self.assertEqual(event["g1_receipt_sha256"], digest(scope.commit))

            sid, status = scope.g.accept(
                scope.j, scope.s, scope.bar, event, now_ms=scope.now + 1
            )
            self.assertEqual(status, "STORED_DURABLE")
            self.assertEqual(
                scope.g.accept(scope.j, scope.s, scope.bar, event, now_ms=scope.now + 1),
                (sid, "REPLAY_IDENTICAL"),
            )

            # Inter-stage restart and no invented observation on any horizon.
            scope.g = DurableG2Bridge(scope.g2_path)
            self.assertEqual(scope.g.readback()["snapshots"], 1)
            first_as_of = scope.now + HORIZONS_MS[0] + 1
            first = read_secretary_receipt(scope.g, sid, as_of_ms=first_as_of)
            self.assertEqual(
                [x["state"] for x in first["horizons"]],
                ["UNKNOWN", "pending", "pending"],
            )

            # One genuine synthetic outcome, one explicit missing, third UNKNOWN.
            for i, (h, missing) in enumerate(zip(HORIZONS_MS[:2], (False, True))):
                at = scope.now + h
                params = dict(
                    observed_ms=at, received_ms=at + 1, source="TEST_ONLY",
                    evidence_id=f"atlas-b-pinned-scanner-evidence-{i}",
                )
                if missing:
                    params["missing_reason"] = "NO_ELIGIBLE_SOURCE"
                else:
                    params["value"] = "UP"
                self.assertEqual(scope.g.observe(sid, h, **params), "STORED_DURABLE")
                self.assertEqual(scope.g.observe(sid, h, **params), "REPLAY_IDENTICAL")

            late_as_of = scope.now + HORIZONS_MS[2] + 2
            intermediate = read_secretary_receipt(scope.g, sid, as_of_ms=late_as_of)
            self.assertEqual(
                [x["state"] for x in intermediate["horizons"]],
                ["mature", "missing", "UNKNOWN"],
            )
            self.assertIsNone(intermediate["horizons"][2]["evidence_sha256"])

            # A future observation is invisible until its actual received_ms.
            last_h = HORIZONS_MS[2]
            last_at = scope.now + last_h
            self.assertEqual(
                scope.g.observe(
                    sid, last_h, observed_ms=last_at, received_ms=last_at + 3,
                    source="TEST_ONLY", evidence_id="atlas-b-third", value="UP",
                ),
                "STORED_DURABLE",
            )
            self.assertEqual(
                [x["state"] for x in read_secretary_receipt(
                    scope.g, sid, as_of_ms=late_as_of
                )["horizons"]],
                ["mature", "missing", "UNKNOWN"],
            )
            final_as_of = last_at + 3
            sealed_export = scope.g.read_verified_opportunity(sid, as_of_ms=final_as_of)
            receipt = read_secretary_receipt(scope.g, sid, as_of_ms=final_as_of)
            self.assertEqual(receipt, consume_verified_opportunity(sealed_export))
            self.assertEqual(
                [x["state"] for x in receipt["horizons"]],
                ["mature", "missing", "mature"],
            )
            self.assertEqual(
                receipt["receipt_sha256"],
                digest({k: v for k, v in receipt.items() if k != "receipt_sha256"}),
            )
            self.assertTrue(all(receipt[k] is None for k in ACK_FIELDS))
            self.assertEqual(receipt["trading_authority"], "NONE")
            self.assertFalse(receipt["orders_enabled"])
            self.assertEqual((receipt["orders"], receipt["fills"]), (0, 0))
            self.assertEqual(receipt["scanner_opportunity_sha256"], event["sha256"])
            self.assertEqual(receipt["g1_receipt_sha256"], digest(scope.commit))

            before = scope.g.readback()
            scope.g = DurableG2Bridge(scope.g2_path)
            self.assertEqual(read_secretary_receipt(
                scope.g, sid, as_of_ms=final_as_of
            ), receipt)
            self.assertEqual(scope.g.readback(), before)
            self.assertEqual((before["snapshots"], before["observations"]), (1, 3))
            self.assertEqual(before["trading_authority"], "NONE")

            # Fail closed: forged acknowledgement, missing horizon and source receipt.
            forged_ack = dict(sealed_export, source_ack_sha256="a" * 64)
            with self.assertRaises(SecretaryReadStop):
                consume_verified_opportunity(forged_ack)
            missing_horizon = copy.deepcopy(sealed_export)
            missing_horizon["horizons"].pop()
            missing_horizon["sha256"] = digest({
                k: v for k, v in missing_horizon.items() if k != "sha256"
            })
            with self.assertRaises(SecretaryReadStop):
                consume_verified_opportunity(missing_horizon)
            corrupted_receipt = dict(event, g1_receipt_ms=event["g1_receipt_ms"] - 1)
            corrupted_receipt["sha256"] = digest({
                k: v for k, v in corrupted_receipt.items() if k != "sha256"
            })
            with self.assertRaises(BridgeStop):
                scope.g.accept(
                    scope.j, scope.s, scope.bar, corrupted_receipt,
                    now_ms=scope.now + 1,
                )
            self.assertEqual(scope.g.readback(), before)
        finally:
            scope.tearDown()


if __name__ == "__main__":
    unittest.main()
