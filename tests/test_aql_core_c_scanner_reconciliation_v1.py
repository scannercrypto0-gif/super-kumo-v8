"""Core C real Scanner #259 Frozen-contract reconciliation (read-only, no B retest).

Actual pinned Scanner C / Scanner B / Work235 validators and real Core B
source outbox are exercised with TEST_ONLY synthetic fixtures. The scanner
JSON source is NOT silently reclassified as the original Core ZIP.
"""
from copy import deepcopy
import unittest

import test_aql_core_c_strategy_secretary_route_v1 as corefixture
from tools.scanner_strategy_c import test_contract as scannerfixture
from tools.scanner_strategy_c.approval_route import seal_strategy_route_request
from tools.strategy_service_offline.common import Frozen
from research_wp_r0.aql_core_c_scanner_reconciliation_v1 import (
    reconcile_scanner_c_candidate,
)
from research_wp_r0.aql_core_backbone_local_v1 import BackboneError


class CoreCActualScannerContract(unittest.TestCase):
    def setUp(self):
        self.core=corefixture.CoreCSecretaryContract(
            methodName="test_source_ack_is_not_strategy_approval_or_consumer_ack")
        self.core.setUp()
        self.addCleanup(self.core.doCleanups)
        self.scan=scannerfixture.ScannerCContractGate(
            methodName="test_explicit_approval_and_approved_route_are_separate_seals")
        self.scan.setUp()
        self.addCleanup(self.scan.doCleanups)
        self.pins={
            "source_custody_receipt_sha256":
                self.core.warehouse["receipt_sha256"],
            "core245_price_query_sha256":
                self.core.mapping["core_245_native_price_query_sha256"],
            "core253_query_local_sha256":
                self.core.mapping["core_253_query_local_sha256"],
            "source_zip_sha256":
                self.core.warehouse["source_zip_sha256"],
            "source_custody_status":"TEST_ONLY_ATTESTED",
        }
        self.approval=self.scan.approval.receipt()
        self.route=self.scan.make_route(**self.pins).receipt()

    def runit(self,route=None,approval=None,policy=None,identity=None,
              warehouse=None,source_ack=None):
        return reconcile_scanner_c_candidate(
            self.core.root,
            scanner_route_receipt=self.route if route is None else route,
            scanner_approval_receipt=self.approval if approval is None else approval,
            scanner_run_receipt=self.scan.run.receipt(),
            scanner_nomination_receipt=self.scan.selected,
            work235_spec_receipt=self.scan.work,
            native15m_policy_receipt=self.scan.native if policy is None else policy,
            identity_map=self.core.mapping if identity is None else identity,
            warehouse_receipt=self.core.warehouse if warehouse is None else warehouse,
            source_ack_receipt=self.core.source_ack if source_ack is None else source_ack,
        )

    def test_authentic_scanner_c_envelopes_verify_but_source_waits(self):
        receipt=self.runit()
        self.assertEqual(receipt,self.runit())
        self.assertEqual(receipt["decision"],"WAIT")
        self.assertEqual(receipt["reason"],"WAIT_SOURCE_PROVENANCE_NOT_CONNECTED")
        self.assertEqual(receipt["scanner_envelope_seal_key"],"sha256")
        self.assertEqual(receipt["core_source_ack_seal_key"],"receipt_sha256")
        self.assertTrue(receipt["factory_provisional_artifact_sha256_is_not_scanner_sha256"])
        self.assertIsNone(receipt["strategy_consumer_ack_sha256"])
        self.assertEqual(receipt["strategy_secretary_status"],"NOT_ENQUEUED")
        self.assertEqual(receipt["scanner_c_approval_sha256"],self.approval["sha256"])
        self.assertEqual(receipt["scanner_c_route_sha256"],self.route["sha256"])
        self.assertEqual(receipt["core_source_only_ack_sha256"],
                         self.core.source_ack["receipt_sha256"])
        self.assertEqual(receipt["core_245_price_query_sha256"],
                         self.core.mapping["core_245_native_price_query_sha256"])
        self.assertEqual(receipt["core_253_query_local_sha256"],
                         self.core.mapping["core_253_query_local_sha256"])
        self.assertIn("SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED",
                      receipt["blocking_conditions"])
        self.assertIn("SCANNER_SYMBOL_NOT_CORE_ORIGINAL",
                      receipt["blocking_conditions"])
        self.assertEqual(receipt["orders_created"],0)
        self.assertEqual(receipt["trading_authority"],"NONE")
        self.assertFalse(receipt["source_only_ack_is_strategy_approval"])

    def test_resealed_forgery_of_scanner_c_route_is_not_trusted(self):
        bad=deepcopy(self.route)
        bad["payload"]["source_secretary_ack_is_strategy_approval"]=True
        forged=Frozen.build(bad["payload"]).receipt()
        with self.assertRaisesRegex(BackboneError,"SCANNER_C_PROPOSAL_REPLAY_DRIFT"):
            self.runit(route=forged)

    def test_explicit_denied_governance_is_retained_as_wait(self):
        denied=self.scan.approve(action="DENY_TEST_ONLY").receipt()
        requested=seal_strategy_route_request(
            self.scan.work,self.scan.native,denied,
            self.scan.run.receipt(),self.scan.selected,**self.pins).receipt()
        got=self.runit(route=requested,approval=denied)
        self.assertEqual(got["scanner_c_strategy_governance_status"],
                         "DENIED_TEST_ONLY")
        self.assertIn("NO_EXPLICIT_TEST_ONLY_ROUTE_CANDIDATE",
                      got["blocking_conditions"])
        self.assertEqual(got["paper_execution"],"NOT_ACTIVATED")

    def test_wrong_core_parent_is_explicit_wait_not_connected(self):
        wrong=self.scan.make_route(source_zip_sha256="f"*64).receipt()
        got=self.runit(route=wrong)
        self.assertIn("SCANNER_DECLARED_CORE_ZIP_PARENT_DRIFT",
                      got["blocking_conditions"])
        self.assertEqual(got["decision"],"WAIT")
        self.assertEqual(got["reason"],"WAIT_SOURCE_PROVENANCE_NOT_CONNECTED")

    def test_broken_core_source_only_ack_is_rejected(self):
        fake=deepcopy(self.core.source_ack)
        fake["acknowledgement_sha256"]="0"*64
        from research_wp_r0.aql_archive_custody_bridge_v1 import digest
        fake["receipt_sha256"]=digest({k:v for k,v in fake.items()
                                       if k!="receipt_sha256"})
        with self.assertRaisesRegex(BackboneError,"SOURCE_ACK_NOT_DURABLE"):
            self.runit(source_ack=fake)

    def test_work235_native_policy_parent_tamper_fails_closed(self):
        bad=deepcopy(self.scan.native)
        bad["payload"]["strategy_id"]="test_reversion"
        bad=Frozen.build(bad["payload"]).receipt()
        with self.assertRaises(ValueError):
            self.runit(policy=bad)


if __name__=="__main__":
    unittest.main()
