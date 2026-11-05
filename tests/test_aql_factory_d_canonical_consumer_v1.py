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



from research_wp_r0.aql_factory_d_lab_paper_v1 import (
    run_factory_d_same_source_lab_paper,
)


class FactoryDActualLabPaper(unittest.TestCase):
    """One pinned Core D / Scanner D source, actual Factory computation and Paper."""

    def setUp(self):
        self.fixture = CoreDCanonicalSecretary(
            methodName="test_real_scanner_selected_approval_enters_durable_pending_not_acked")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.pending = self.fixture.enqueue()
        self.ack = accept_pending_strategy_test_only(
            snapshot=self.pending, gate=self.fixture.gate,
            source_ack=self.fixture.source_ack,
            route_id="CORE-D-STRATEGY",
            accepted_at_ms=self.fixture.now+1, expires_at_ms=self.fixture.exp)

    def run_lane(self, **changes):
        args = dict(
            core_root=self.fixture.root,
            route_id="CORE-D-STRATEGY", now_ms=self.fixture.now+3,
            factory_ack=self.ack, gate=self.fixture.gate,
            warehouse=self.fixture.f.c["warehouse"],
            native_price_query=self.fixture.f.c["native"],
            local_query=self.fixture.f.c["local"],
            identity_map=self.fixture.f.c["mapping"],
            core_d_witness=self.fixture.f.c["witness"],
            scanner_d_handoff=self.fixture.f.produced.receipt(),
            work_spec=next(w for w in self.fixture.f.work
                           if w["payload"]["strategy_id"]
                           == self.fixture.gate["strategy_id"]),
        )
        args.update(changes)
        return run_factory_d_same_source_lab_paper(**args)

    def ack_core(self):
        done = ack_scanner_d_strategy_consumer(
            self.fixture.root, "CORE-D-STRATEGY", self.ack,
            now_ms=self.fixture.now+2)
        self.assertEqual(done["state"], "ACKED_CONSUMER")

    def test_real_same_source_lab_and_declined_native_paper_replay(self):
        self.ack_core()
        a = self.run_lane()
        b = self.run_lane()
        self.assertEqual(a, b)
        self.assertEqual(a["lab"]["observed_bar_count"], 8)
        self.assertEqual(a["lab"]["observed_one_bar_denominator"], 7)
        self.assertEqual(len(a["lab"]["post_hoc_one_bar_observations"]), 7)
        self.assertEqual(sum(a["lab"]["bar_direction_census"].values()), 8)
        self.assertEqual(a["lab"]["strategy_rule_performance"],
                         "RULES_COMPUTED_NO_VALIDATED_TRADE_TIMELINE")
        self.assertEqual(a["lab"]["rule_evaluation"],
                         "ACTUAL_FACTORY_INDICATOR_PREFIX_ONLY")
        self.assertEqual(a["lab"]["rule_decision_denominator"], 7)
        self.assertEqual(sum(a["lab"]["rule_decision_counts"].values()), 7)
        self.assertGreater(a["lab"]["rule_decision_counts"]["ENTRY_TRIGGERED"], 0)
        self.assertTrue(a["batch"]["rule_interpreter_executed"])
        self.assertEqual(a["paper"]["decision"], "REJECT")
        self.assertTrue(a["paper"]["native_position_ledger_invoked"])
        self.assertEqual(a["paper"]["native_paper_intent"]["status"], "declined")
        self.assertEqual(a["paper"]["orders_created"], 0)
        self.assertEqual(a["paper"]["paper_positions"], 0)
        self.assertEqual(a["paper"]["paper_position_events"], 0)
        self.assertIsNone(a["paper"]["actual_fills"])
        self.assertEqual(a["batch"]["lab_sha256"], a["lab"]["lab_sha256"])
        self.assertEqual(a["batch"]["isolated_paper_sha256"],
                         a["paper"]["paper_sha256"])
        self.assertEqual(a["batch"]["trading_authority"], "NONE")
        self.assertEqual(a["batch"]["historical_pit"], "NOT_ATTESTED")

    def test_no_core_durable_consumer_ack_no_lab_or_paper(self):
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane()

    def test_resealed_wrong_query_and_source_parent_fail_closed(self):
        self.ack_core()
        query = copy.deepcopy(self.fixture.f.c["local"])
        query["bars"][0]["close"] = 999
        query["query_sha256"] = digest(
            {k:v for k,v in query.items() if k != "query_sha256"})
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(local_query=query)
        warehouse = copy.deepcopy(self.fixture.f.c["warehouse"])
        warehouse["source_zip_sha256"] = "f"*64
        warehouse["receipt_sha256"] = digest(
            {k:v for k,v in warehouse.items() if k != "receipt_sha256"})
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(warehouse=warehouse)

    def test_forged_ack_approval_and_witness_fail_closed(self):
        self.ack_core()
        fake = copy.deepcopy(self.ack)
        fake["paper_authority"] = "GRANTED"
        fake["consumer_ack_sha256"] = digest(
            {k:v for k,v in fake.items() if k != "consumer_ack_sha256"})
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(factory_ack=fake)
        gate = copy.deepcopy(self.fixture.gate)
        gate["scanner_c_governance_action"] = "DENY_TEST_ONLY"
        gate["gate_sha256"] = digest(
            {k:v for k,v in gate.items() if k != "gate_sha256"})
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(gate=gate)
        witness = copy.deepcopy(self.fixture.f.c["witness"])
        witness["payload"]["scanner_source_id"] = "unverified"
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(core_d_witness=witness)

    def test_wrong_frozen_strategy_spec_fails_closed(self):
        self.ack_core()
        foreign_spec = next(w for w in self.fixture.f.work
                            if w["payload"]["strategy_id"]
                            != self.fixture.gate["strategy_id"])
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(work_spec=foreign_spec)

    def test_expired_secretary_denies_lab_paper(self):
        self.ack_core()
        with self.assertRaises((ValueError, LabHandoffError)):
            self.run_lane(now_ms=self.fixture.exp+1)

if __name__ == "__main__":
    unittest.main()
