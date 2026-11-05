"""Factory C: actual Scanner Frozen + Core C SHA-sealed reconciliation.

These are synthetic code-only tests using the owner-provided canonical fixture
classes, not a market-source replay or a strategy approval for trading.
"""
import copy
import unittest

from research_wp_r0.aql_factory_c_canonical_wait_adapter_v1 import (
    consume_canonical_scanner_core_wait,
)
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError
from research_wp_r0.aql_factory_unified_backbone_v1 import freeze
from tools.strategy_service_offline.common import Frozen
from test_aql_core_c_scanner_reconciliation_v1 import CoreCActualScannerContract


class FactoryCCanonicalWait(unittest.TestCase):
    def setUp(self):
        self.case = CoreCActualScannerContract(
            "test_authentic_scanner_c_envelopes_verify_but_source_waits")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def execute(self, *, route=None, approval=None, reconciliation=None,
                source_ack=None):
        return consume_canonical_scanner_core_wait(
            scanner_route_receipt=self.case.route if route is None else route,
            scanner_approval_receipt=self.case.approval if approval is None else approval,
            reconciliation_receipt=(self.case.runit() if reconciliation is None
                                    else reconciliation),
            warehouse_receipt=self.case.core.warehouse,
            source_only_ack_receipt=(self.case.core.source_ack if source_ack is None
                                     else source_ack),
        )

    def test_real_scanner_frozen_and_core_wait_replay(self):
        a=self.execute()
        b=self.execute()
        self.assertEqual(a,b)
        self.assertEqual(a["reason"],"WAIT_SOURCE_PROVENANCE_NOT_CONNECTED")
        self.assertEqual(a["scanner_route_sha256"],self.case.route["sha256"])
        self.assertEqual(a["scanner_approval_sha256"],self.case.approval["sha256"])
        self.assertEqual(a["core_reconciliation_sha256"],self.case.runit()["reconciliation_sha256"])
        self.assertNotEqual(a["core_245_price_query_sha256"],
                            a["core_253_query_local_sha256"])
        self.assertFalse(a["factory_lab_invoked"])
        self.assertFalse(a["isolated_paper_invoked"])
        self.assertEqual(a["orders_created"],0)
        self.assertIsNone(a["actual_fills"])

    def test_resealed_parent_mismatch_fails_closed(self):
        old=self.case.runit()
        for patch in (
            {"scanner_c_route_sha256":"f"*64},
            {"scanner_c_source_raw_sha256":"f"*64},
            {"decision":"APPROVED"},
            {"reason":"SOURCE_CONNECTED"},
            {"strategy_secretary_status":"ACKED_CONSUMER"},
            {"source_only_ack_is_strategy_approval":True},
            {"core_245_price_query_sha256":"f"*64},
            {"core_253_query_local_sha256":"f"*64},
            {"core_cutoff_ms":1},
            {"orders_created":1},
            {"blocking_conditions":[]},
        ):
            with self.subTest(patch=patch):
                new=freeze({**{k:copy.deepcopy(v) for k,v in old.items()
                               if k!="reconciliation_sha256"},**patch},
                           "reconciliation_sha256")
                with self.assertRaises(LabHandoffError):
                    self.execute(reconciliation=new)

    def test_forged_scanner_frozen_receipt_or_ack_rejected(self):
        route=copy.deepcopy(self.case.route)
        route["payload"]["trading_authority"]="PAPER"
        with self.assertRaises((ValueError,LabHandoffError)):
            self.execute(route=route)
        fake=copy.deepcopy(self.case.core.source_ack)
        fake["acknowledgement_sha256"]="0"*64
        with self.assertRaises(LabHandoffError):
            self.execute(source_ack=fake)

    def test_denied_governance_wait_without_paper(self):
        from tools.scanner_strategy_c.approval_route import seal_strategy_route_request
        denied=self.case.scan.approve(action="DENY_TEST_ONLY").receipt()
        route=seal_strategy_route_request(
            self.case.scan.work,self.case.scan.native,denied,
            self.case.scan.run.receipt(),self.case.scan.selected,
            **self.case.pins).receipt()
        reconciled=self.case.runit(route=route,approval=denied)
        got=self.execute(route=route,approval=denied,reconciliation=reconciled)
        self.assertEqual(got["decision"],"WAIT")
        self.assertFalse(got["factory_lab_invoked"])
        self.assertFalse(got["isolated_paper_invoked"])


if __name__=="__main__":
    unittest.main()
