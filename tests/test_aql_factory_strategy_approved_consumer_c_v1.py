"""Factory C policy/route contract tests. Synthetic fixtures only, B source unchanged."""
from __future__ import annotations
import copy
import unittest

from research_wp_r0.aql_factory_unified_backbone_v1 import freeze
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError
from research_wp_r0.aql_factory_strategy_approved_consumer_c_v1 import (
    consume_test_only_strategy_approval, wait_for_unapproved_strategy,
)
from test_aql_factory_core_query_bridge_v1 import fixture


def prepared():
    source,native,local,calculation=fixture()
    src={k:v for k,v in source.items() if k!="artifact_sha256"}
    src["symbol"]="BTCUSDT"
    source=freeze(src)
    values={
        "strategy_id":calculation["strategy_id"],
        "strategy_version":calculation["strategy_version"],
        "config_digest":"1"*64,
        "strategy_definition_digest":calculation["strategy_digest"],
        "symbol":"BTCUSDT",
        "timeframe":"15m",
        "source_zip_sha256":source["source_bytes_sha256"],
        "manifest_integrity_sha256":source["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":source["core_253_warehouse_receipt_sha256"],
        "core_245_price_query_sha256":native["price_query_sha256"],
        "core_253_query_local_sha256":local["query_sha256"],
        "decision_cutoff_ms":source["cutoff_ms"],
        "operational_scanner_status":"UNKNOWN",
        "historical_known_at_ms":None,
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
        "paper_execution":"NOT_ACTIVATED",
    }
    nomination=freeze({
        **values,
        "schema":"aql.scanner.native15m-strategy-nomination.factory-c.v1",
        "status":"UNKNOWN","publishable":False,"delivery_authorized":False,
        "evidence_class":"RETROSPECTIVE_NON_PIT",
    })
    approval=freeze({
        **values,
        "schema":"aql.scanner.strategy-approval-test-only.v1",
        "approval_status":"APPROVED_TEST_ONLY",
        "approval_class":"ENGINEERING_TEST_ONLY",
        "approval_kind":"EXPLICIT_STRATEGY_POLICY",
        "approved_by":"TEST_ONLY_POLICY_REVIEWER",
        "policy_status":"TEST_ONLY_UNAPPROVED_FOR_TRADING",
        "approval_time_ms":source["cutoff_ms"]-1000,
        "expires_at_ms":source["cutoff_ms"]+1000,
        "nomination_sha256":nomination["artifact_sha256"],
        "strategy_digest":calculation["strategy_digest"],
        "core_evaluation_sha256":calculation["evaluation_sha256"],
    })
    route=freeze({
        **values,
        "schema":"aql.core.secretary-strategy-route.v1",
        "approval_sha256":approval["artifact_sha256"],
        "nomination_sha256":nomination["artifact_sha256"],
        "delivery_status":"STRATEGY_ACKED",
        "source_ack_is_strategy_approval":False,
        "source_only_ack_sha256":None,
        "work235_actual_route":"NOT_CONNECTED_15M_UNSUPPORTED",
    })
    ack=freeze({
        **values,
        "schema":"aql.core.strategy-route-consumer-ack.v1",
        "strategy_route_sha256":route["artifact_sha256"],
        "ack_status":"ACKED_STRATEGY_CONSUMER",
        "ack_kind":"STRATEGY_CONSUMER_ONLY",
        "orders_created":0,"actual_fills":None,
    })
    return source,native,local,calculation,nomination,approval,route,ack


def reseal(item, **mutations):
    return freeze({**{k:copy.deepcopy(v) for k,v in item.items()
                      if k!="artifact_sha256"},**mutations})


class FactoryCApprovedRoute(unittest.TestCase):
    def test_all_signed_parents_test_only_and_replay(self):
        args=prepared()
        got=consume_test_only_strategy_approval(*args)
        self.assertEqual(got,consume_test_only_strategy_approval(*args))
        receipt=got["consumer"]
        self.assertEqual(receipt["nomination_sha256"],args[4]["artifact_sha256"])
        self.assertEqual(receipt["strategy_approval_sha256"],args[5]["artifact_sha256"])
        self.assertEqual(receipt["strategy_route_sha256"],args[6]["artifact_sha256"])
        self.assertEqual(receipt["strategy_consumer_ack_sha256"],
                         args[7]["artifact_sha256"])
        self.assertEqual(receipt["decision"],"REJECT")
        self.assertFalse(receipt["operational_strategy_approval"])
        self.assertTrue(receipt["engineering_test_only_approval"])
        self.assertEqual(receipt["trading_authority"],"NONE")
        self.assertEqual(receipt["orders_created"],0)
        self.assertIsNone(receipt["actual_fills"])
        self.assertNotEqual(receipt["core_245_price_query_sha256"],
                            receipt["core_253_query_local_sha256"])

    def test_absent_approval_or_delivery_ack_wait_not_paper(self):
        args=list(prepared())
        for position,reason in [(5,"MISSING_APPROVAL"),
                                (6,"MISSING_STRATEGY_ROUTE"),
                                (7,"MISSING_STRATEGY_CONSUMER_ACK")]:
            with self.subTest(reason=reason):
                altered=list(args)
                altered[position]=None
                outcome=consume_test_only_strategy_approval(*altered)
                self.assertEqual(outcome["decision"],"WAIT")
                self.assertEqual(outcome["reason"],reason)
                self.assertEqual(outcome["orders_created"],0)
        self.assertEqual(wait_for_unapproved_strategy("SOURCE_ONLY_ACK")["decision"],
                         "WAIT")

    def test_resigned_adversarial_parent_and_authority_mutations(self):
        cases=[
            (4,{"status":"SELECTED"}),
            (4,{"operational_scanner_status":"SELECTED"}),
            (4,{"publishable":True}),
            (4,{"symbol":"ETHUSDT"}),
            (5,{"approval_kind":"SOURCE_ACK"}),
            (5,{"approval_class":"OPERATIONAL_TRADING"}),
            (5,{"approved_by":"AUTO"}),
            (5,{"approval_status":"SOURCE_ACKED"}),
            (5,{"policy_status":"PAPER_APPROVED"}),
            (5,{"expires_at_ms":1}),
            (5,{"approval_time_ms":10**16}),
            (5,{"config_digest":"2"*64}),
            (5,{"strategy_digest":"f"*64}),
            (5,{"core_evaluation_sha256":"f"*64}),
            (6,{"source_ack_is_strategy_approval":True}),
            (6,{"work235_actual_route":"CONNECTED_15M"}),
            (6,{"delivery_status":"SOURCE_ACKED"}),
            (6,{"approval_sha256":"f"*64}),
            (6,{"core_245_price_query_sha256":"f"*64}),
            (6,{"core_253_query_local_sha256":"f"*64}),
            (7,{"ack_kind":"SOURCE_CONSUMER"}),
            (7,{"orders_created":1}),
            (7,{"actual_fills":1}),
            (7,{"historical_known_at_ms":1}),
            (7,{"decision_cutoff_ms":1}),
            (7,{"strategy_version":"unknown"}),
        ]
        for at,m in cases:
            with self.subTest(at=at,mutation=m):
                args=list(prepared())
                args[at]=reseal(args[at],**m)
                with self.assertRaises(LabHandoffError):
                    consume_test_only_strategy_approval(*args)

    def test_raw_unsealed_tamper_and_source_only_ack_not_approval(self):
        args=list(prepared())
        args[5]["approval_status"]="APPROVED_FOR_PAPER"
        with self.assertRaises(LabHandoffError):
            consume_test_only_strategy_approval(*args)
        args=list(prepared())
        source_ack=freeze({"schema":"aql.core.secretary-offline-ack.v1",
                           "state":"ACKED","trading_authority":"NONE"})
        with self.assertRaises(LabHandoffError):
            consume_test_only_strategy_approval(*args,source_only_ack=source_ack)

    def test_source_mutation_rejected_by_existing_factory_b_bridge(self):
        args=list(prepared())
        args[0]=reseal(args[0],core_253_warehouse_query_sha256="0"*64)
        with self.assertRaises(LabHandoffError):
            consume_test_only_strategy_approval(*args)


if __name__=="__main__":
    unittest.main()
