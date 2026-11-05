"""Factory-owned ACK, tested against actual Core D canonical Secretary fixture.

Run in a pinned integration workspace containing Core D #264 and Scanner D #262.
No Lab or Paper execution is claimed by this focused test.
"""
import copy
import unittest

from research_wp_r0.aql_factory_d_canonical_consumer_v1 import accept_pending_strategy_test_only
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_d_canonical_secretary_v1 import (
    ack_scanner_d_strategy_consumer, strategy_d_snapshot)
from test_aql_core_d_canonical_secretary_v1 import CoreDCanonicalSecretary


class FactoryDCanonicalConsumer(unittest.TestCase):
    def setUp(self):
        self.fixture = CoreDCanonicalSecretary(
            methodName="test_real_scanner_selected_approval_enters_durable_pending_not_acked")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.pending = self.fixture.enqueue()

    def accept(self, **changes):
        args = dict(snapshot=self.pending, gate=self.fixture.gate,
                    source_ack=self.fixture.source_ack,
                    route_id="CORE-D-STRATEGY",
                    accepted_at_ms=self.fixture.now + 1,
                    expires_at_ms=self.fixture.exp)
        args.update(changes)
        return accept_pending_strategy_test_only(**args)

    def test_real_factory_ack_core_durable_ack_and_replay(self):
        ack = self.accept()
        self.assertEqual(ack, self.accept())
        self.assertEqual(ack["schema"], "aql.factory.d.canonical-strategy-consumer-ack.v1")
        self.assertEqual(ack["consumer_ack_sha256"],
                         digest({k:v for k,v in ack.items() if k != "consumer_ack_sha256"}))
        done = ack_scanner_d_strategy_consumer(
            self.fixture.root, "CORE-D-STRATEGY", ack,
            now_ms=self.fixture.now + 2)
        self.assertEqual(done["state"], "ACKED_CONSUMER")
        self.assertTrue(done["route_ready_for_factory_test_only"])
        self.assertEqual(done["consumer_ack_sha256"], ack["consumer_ack_sha256"])
        self.assertEqual(done, strategy_d_snapshot(
            self.fixture.root, "CORE-D-STRATEGY", now_ms=self.fixture.now + 2))
        self.assertEqual(done["orders_created"], 0)
        self.assertIsNone(done["actual_fills"])

    def test_resealed_wrong_parent_denied(self):
        for field in ("scanner_c_approval_sha256", "source_zip_sha256",
                      "core_245_price_query_sha256", "strategy_version",
                      "config_digest", "scanner_d_handoff_sha256"):
            with self.subTest(field=field):
                bad = copy.deepcopy(self.pending)
                bad[field] = "f" * 64
                bad["route_receipt_sha256"] = digest({
                    k:v for k,v in bad.items() if k != "route_receipt_sha256"})
                with self.assertRaises(LabHandoffError):
                    self.accept(snapshot=bad)

    def test_denied_gate_and_expiry_fail_closed(self):
        gate = copy.deepcopy(self.fixture.gate)
        gate["scanner_c_governance_action"] = "DENY_TEST_ONLY"
        gate["gate_sha256"] = digest({
            k:v for k,v in gate.items() if k != "gate_sha256"})
        with self.assertRaises(LabHandoffError):
            self.accept(gate=gate)
        with self.assertRaises(LabHandoffError):
            self.accept(accepted_at_ms=self.fixture.exp)

    def test_fake_acked_snapshot_rejected(self):
        fake = copy.deepcopy(self.pending)
        fake["state"] = "ACKED_CONSUMER"
        fake["route_receipt_sha256"] = digest({
            k:v for k,v in fake.items() if k != "route_receipt_sha256"})
        with self.assertRaises(LabHandoffError):
            self.accept(snapshot=fake)


if __name__ == "__main__":
    unittest.main()
