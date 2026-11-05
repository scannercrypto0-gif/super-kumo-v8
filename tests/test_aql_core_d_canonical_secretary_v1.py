"""Core D actual canonical Scanner Frozen approval → durable Secretary tests."""
import unittest
from copy import deepcopy
from datetime import datetime, timezone

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_secretary_routing_v1 import enqueue_nomination, acknowledge_nomination
from research_wp_r0.aql_core_d_canonical_secretary_v1 import (
    enqueue_scanner_d_strategy,ack_scanner_d_strategy_consumer,strategy_d_snapshot)
from tools.strategy_service_offline.common import Frozen
from test_aql_core_d_permitted_cohort_v1 import PermittedSameSourceCoreD


def seal(body):
    return {**body,"consumer_ack_sha256":digest(body)}


class CoreDCanonicalSecretary(unittest.TestCase):
    def setUp(self):
        self.f=PermittedSameSourceCoreD(methodName="test_policy_permitted_symbol_source_dual_sha_and_replay")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.w=self.f.c["warehouse"]
        self.now=self.w["decision_cutoff_ms"]+5
        self.exp=self.now+120_000
        self.selected=[self.f.gate(i) for i in range(2)
                       if self.f.gate(i)["nomination_status"]=="SELECTED"]
        self.assertTrue(self.selected)
        self.gate=self.selected[0]
        self.nom_id=self.gate["strategy_id"]
        self.nom_version=self.gate["strategy_version"]
        cutoff=datetime.fromtimestamp(self.w["decision_cutoff_ms"]/1000,timezone.utc).isoformat()
        source_nom={
            "schema_version":"AQL-SCANNER-V1",
            "scanner_id":"CORE_D_SYNTHETIC_SOURCE",
            "candidate_id":self.w["symbol"]+":TEST:D",
            "profile_id":"RESEARCH_D_TEST",
            "market":"BINANCE:SPOT:USDT","cutoff_at":cutoff,
            "availability_class":"RETROSPECTIVE_NON_PIT",
            "stage":"UNKNOWN","source_manifest":{
               "dataset_id":self.w["dataset_id"],
               "dataset_sha":self.w["source_zip_sha256"],
               "schema_version":"AQL-SCANNER-V1",
               "cutoff_at":cutoff,"created_at":cutoff,
            },
            "feature_snapshot":{},"reasons":["SYNTHETIC_TEST_ONLY_NOT_PIT"],
            "coverage":{"historical_pit":"NOT_ATTESTED"},
            "score":None,"score_status":"SCORE_UNAVAILABLE",
            "publishable":False,"delivery_authorized":False,
        }
        source_nom["digest"]=digest(source_nom)
        self.source_nom=source_nom
        q=enqueue_nomination(self.root,self.source_nom,
            strategy_id=self.nom_id,strategy_version=self.nom_version,
            warehouse_receipt=self.w,lane="SLOW",idempotency_key="CORE-D-SOURCE")
        self.source_ack=acknowledge_nomination(self.root,
            message_id=q["message_id"],payload_sha256=q["payload_sha256"],
            acknowledgement_sha256="d"*64)
        self.gate=self.f.gate(
            next(i for i in range(2) if self.f.gate(i)["strategy_id"]==self.nom_id),
            source_ack=self.source_ack)

    def enqueue(self,gate=None,source_ack=None,route_id="CORE-D-STRATEGY"):
        return enqueue_scanner_d_strategy(
            self.root,gate=self.gate if gate is None else gate,
            source_ack=self.source_ack if source_ack is None else source_ack,
            source_nomination_sha256=self.source_nom["digest"],
            route_id=route_id,now_ms=self.now,expires_at_ms=self.exp)

    def make_ack(self,gate=None):
        g=gate or self.gate
        return seal({
            "schema":"aql.factory.d.canonical-strategy-consumer-ack.v1",
            "route_id":"CORE-D-STRATEGY",
            "decision":"ACCEPTED_TEST_ONLY_RESEARCH",
            "strategy_gate_sha256":g["gate_sha256"],
            "scanner_c_approval_sha256":g["scanner_c_approval_sha256"],
            "source_ack_sha256":self.source_ack["receipt_sha256"],
            "strategy_id":g["strategy_id"],
            "strategy_version":g["strategy_version"],
            "config_digest":g["config_digest"],
            "source_zip_sha256":g["source_zip_sha256"],
            "core_245_price_query_sha256":g["core_245_price_query_sha256"],
            "core_253_query_local_sha256":g["core_253_query_local_sha256"],
            "cutoff_ms":g["cutoff_ms"],"accepted_at_ms":self.now+1,
            "trading_authority":"NONE","paper_authority":"NONE",
            "orders_created":0,"paper_positions":0,"actual_fills":None,
        })

    def test_real_scanner_selected_approval_enters_durable_pending_not_acked(self):
        snap=self.enqueue()
        self.assertEqual(snap["state"],"PENDING_CONSUMER")
        self.assertIsNone(snap["consumer_ack_sha256"])
        self.assertFalse(snap["source_ack_is_strategy_approval"])
        self.assertEqual(snap,self.enqueue())
        self.assertEqual(snap,strategy_d_snapshot(self.root,"CORE-D-STRATEGY",now_ms=self.now))
        self.assertEqual(snap["route_ready_for_factory_test_only"],False)

    def test_explicit_consumer_ack_is_separate_replay_and_no_trading(self):
        self.enqueue()
        ack=self.make_ack()
        result=ack_scanner_d_strategy_consumer(
            self.root,"CORE-D-STRATEGY",ack,now_ms=self.now+2)
        self.assertEqual(result["state"],"ACKED_CONSUMER")
        self.assertTrue(result["route_ready_for_factory_test_only"])
        self.assertEqual(result["trading_authority"],"NONE")
        self.assertEqual(result["orders_created"],0)
        self.assertEqual(result,ack_scanner_d_strategy_consumer(
            self.root,"CORE-D-STRATEGY",ack,now_ms=self.now+2))

    def test_source_ack_forgery_conflict_and_expiry_fail_closed(self):
        self.enqueue()
        fake=deepcopy(self.source_ack)
        fake["acknowledgement_sha256"]="e"*64
        fake["receipt_sha256"]=digest({k:v for k,v in fake.items() if k!="receipt_sha256"})
        with self.assertRaises(ValueError):
            self.enqueue(source_ack=fake,route_id="CORE-D-FORGED")
        with self.assertRaises(ValueError):
            self.enqueue(route_id="CORE-D-DUPLICATE")
        self.assertEqual(strategy_d_snapshot(self.root,"CORE-D-STRATEGY",
            now_ms=self.exp+1)["state"],"EXPIRED")

    def test_consumer_wrong_approval_parent_is_denied(self):
        self.enqueue()
        ack=self.make_ack()
        ack["scanner_c_approval_sha256"]="0"*64
        ack["consumer_ack_sha256"]=digest({k:v for k,v in ack.items() if k!="consumer_ack_sha256"})
        with self.assertRaises(ValueError):
            ack_scanner_d_strategy_consumer(
                self.root,"CORE-D-STRATEGY",ack,now_ms=self.now+2)


if __name__=="__main__":
    unittest.main()
