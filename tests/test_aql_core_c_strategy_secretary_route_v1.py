"""Core Package C — actual B source-outbox / dual-query parent strategy route tests.

All source bytes are synthetic native-format ZIP. Test approval/consumer ACK
are explicit dummy sealed receipts, never production approval or trading.
"""
import json
import sqlite3
import unittest
from copy import deepcopy
from datetime import datetime,timezone

import test_aql_core_dual_query_identity_map_v1 as fixtures
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination, acknowledge_nomination,
)
from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import (
    REQUEST_SCHEMA, APPROVAL_SCHEMA, make_strategy_route_request,
    enqueue_strategy_route, approve_strategy_route, acknowledge_strategy_consumer,
    retry_strategy_route, strategy_route_snapshot, strategy_route_trace,
)
from research_wp_r0.aql_core_backbone_local_v1 import BackboneError


def seal(body,field):
    return {**body,field:digest(body)}


class CoreCSecretaryContract(unittest.TestCase):
    def setUp(self):
        self.gate=fixtures.DualQueryIdentity()
        self.gate.setUp()
        self.addCleanup(self.gate.doCleanups)
        self.root=self.gate.root
        self.now=self.gate.cutoff+2
        self.warehouse=self.gate.warehouse
        self.mapping=self.gate.mapped()
        cutoff_iso=datetime.fromtimestamp(self.gate.cutoff/1000,
                                         timezone.utc).isoformat()
        native={
            "schema_version":"AQL-SCANNER-V1",
            "scanner_id":"CORE_C_NATIVE_TEST",
            "candidate_id":"BTCUSDT:TEST:C",
            "profile_id":"RESEARCH_C_TEST",
            "market":"BINANCE:SPOT:USDT","cutoff_at":cutoff_iso,
            "availability_class":"RETROSPECTIVE_NON_PIT",
            "stage":"UNKNOWN",
            "source_manifest":{
                "dataset_id":self.warehouse["dataset_id"],
                "dataset_sha":self.warehouse["source_zip_sha256"],
                "schema_version":"AQL-SCANNER-V1","cutoff_at":cutoff_iso,
                "created_at":cutoff_iso,
            },
            "feature_snapshot":{},"reasons":["HISTORICAL_KNOWN_AT_UNKNOWN"],
            "coverage":{"historical_pit":"NOT_ATTESTED"},
            "score":None,"score_status":"SCORE_UNAVAILABLE",
            "publishable":False,"delivery_authorized":False,
        }
        self.nomination=seal(native,"digest")
        queued=enqueue_nomination(
            self.root,self.nomination,strategy_id="test_momentum",
            strategy_version="v1",warehouse_receipt=self.warehouse,
            lane="SLOW",idempotency_key="C-SOURCE-1",
        )
        self.source_ack=acknowledge_nomination(
            self.root,message_id=queued["message_id"],
            payload_sha256=queued["payload_sha256"],
            acknowledgement_sha256="c"*64,
        )
        policy={
            "schema":"aql.scanner.native15m-policy.v1",
            "strategy_id":"test_momentum","strategy_version":"v1",
            "definition":{"digest":"b"*64},"timeframe":"15m",
            "override_is_explicit":True,"evidence_class":"TEST_ONLY",
            "approved_paper_registry":"NOT_CONNECTED",
            "operational_work235_15m":"NOT_CONNECTED_15M_UNSUPPORTED",
            "trading_authority":"NONE",
        }
        policy["config_digest"]=digest(policy)
        self.policy={"payload":policy,"sha256":digest(policy)}
        self.request=make_strategy_route_request(
            identity_map=self.mapping,warehouse=self.warehouse,
            nomination=self.nomination,source_ack=self.source_ack,
            strategy_policy_receipt=self.policy,
            strategy_id="test_momentum",strategy_version="v1",
            config_digest=policy["config_digest"],
            strategy_definition_digest=policy["definition"]["digest"],
            expires_at_ms=self.now+100000,
        )
        self.approval=self.make_approval()

    def make_approval(self):
        r=self.request
        body={
            "schema":APPROVAL_SCHEMA,"decision":"APPROVED_TEST_ONLY",
            "scope":"TEST_ONLY","approved_by":"EXPLICIT_RESEARCH_POLICY_GATE",
            "strategy_id":r["strategy_id"],"strategy_version":r["strategy_version"],
            "config_digest":r["config_digest"],
            "strategy_definition_digest":r["strategy_definition_digest"],
            "timeframe":r["timeframe"],"symbol":r["symbol"],
            "source_zip_sha256":r["source_zip_sha256"],
            "manifest_integrity_sha256":r["manifest_integrity_sha256"],
            "core_245_price_query_sha256":r["core_245_price_query_sha256"],
            "core_253_query_local_sha256":r["core_253_query_local_sha256"],
            "scanner_nomination_sha256":r["scanner_nomination_sha256"],
            "source_ack_sha256":r["source_ack_sha256"],
            "policy_receipt_sha256":r["policy_receipt_sha256"],
            "request_sha256":r["request_sha256"],"cutoff_ms":r["cutoff_ms"],
            "issued_at_ms":self.now-1,"expires_at_ms":self.now+60000,
            "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
            "source_ack_is_approval":False,
            "paper_authority":"NONE","trading_authority":"NONE",
        }
        return seal(body,"approval_sha256")

    def make_consumer(self,route_id="CORE-C-1"):
        r=self.request
        body={
            "schema":"aql.factory.c.strategy-consumer-ack.v1",
            "decision":"ACCEPTED_TEST_ONLY_RESEARCH",
            "route_id":route_id,"request_sha256":r["request_sha256"],
            "approval_sha256":self.approval["approval_sha256"],
            "source_ack_sha256":r["source_ack_sha256"],
            "policy_receipt_sha256":r["policy_receipt_sha256"],
            "strategy_id":r["strategy_id"],"strategy_version":r["strategy_version"],
            "config_digest":r["config_digest"],
            "source_zip_sha256":r["source_zip_sha256"],
            "core_245_price_query_sha256":r["core_245_price_query_sha256"],
            "core_253_query_local_sha256":r["core_253_query_local_sha256"],
            "warehouse_receipt_sha256":r["warehouse_receipt_sha256"],
            "scanner_nomination_sha256":r["scanner_nomination_sha256"],
            "manifest_integrity_sha256":r["manifest_integrity_sha256"],
            "cutoff_ms":r["cutoff_ms"],"accepted_at_ms":self.now+3,
            "paper_authority":"NONE","trading_authority":"NONE",
        }
        return seal(body,"consumer_ack_sha256")

    def enqueue(self,*,approval=None,request=None,source_ack=None,
                nomination=None,identity_map=None,warehouse=None,
                strategy_policy_receipt=None,route_id="CORE-C-1"):
        return enqueue_strategy_route(
            self.root,self.request if request is None else request,
            self.mapping if identity_map is None else identity_map,
            self.warehouse if warehouse is None else warehouse,
            self.nomination if nomination is None else nomination,
            self.source_ack if source_ack is None else source_ack,
            self.policy if strategy_policy_receipt is None else strategy_policy_receipt,
            approval=approval,now_ms=self.now,route_id=route_id,
        )

    def test_source_ack_is_not_strategy_approval_or_consumer_ack(self):
        wait=self.enqueue()
        self.assertEqual(wait["state"],"WAIT_APPROVAL")
        self.assertIsNone(wait["approval_sha256"])
        self.assertFalse(wait["route_ready_for_isolated_lab"])
        with self.assertRaisesRegex(BackboneError,"ACK_NOT_ALLOWED"):
            acknowledge_strategy_consumer(
                self.root,"CORE-C-1",self.make_consumer(),now_ms=self.now+3)

    def test_three_separate_receipts_transition_and_idempotent_replay(self):
        initial=self.enqueue()
        self.assertEqual(self.enqueue(),initial)
        pending=approve_strategy_route(self.root,"CORE-C-1",self.approval,
                                      now_ms=self.now)
        self.assertEqual(pending["state"],"PENDING_CONSUMER")
        self.assertNotEqual(pending["source_ack_sha256"],pending["approval_sha256"])
        self.assertIsNone(pending["consumer_ack_sha256"])
        consumer=self.make_consumer()
        accepted=acknowledge_strategy_consumer(
            self.root,"CORE-C-1",consumer,now_ms=self.now+3)
        self.assertEqual(accepted["state"],"ACKED_CONSUMER")
        self.assertTrue(accepted["route_ready_for_isolated_lab"])
        self.assertEqual(acknowledge_strategy_consumer(
            self.root,"CORE-C-1",consumer,now_ms=self.now+4)["state"],
            "ACKED_CONSUMER")
        self.assertEqual(strategy_route_snapshot(
            self.root,"CORE-C-1",now_ms=self.now+4),accepted)
        self.assertEqual([e["state"] for e in strategy_route_trace(
            self.root,"CORE-C-1")],
            ["WAIT_APPROVAL","PENDING_CONSUMER","ACKED_CONSUMER"])
        self.assertEqual(accepted["trading_authority"],"NONE")
        self.assertEqual(accepted["operational_scanner_status"],"UNKNOWN")

    def test_explicit_initial_approval_and_same_route_id_conflict(self):
        first=self.enqueue(approval=self.approval)
        self.assertEqual(first["state"],"PENDING_CONSUMER")
        self.assertEqual(self.enqueue(approval=self.approval),first)
        with self.assertRaisesRegex(BackboneError,"IDEMPOTENCY_CONFLICT"):
            self.enqueue()
        with self.assertRaisesRegex(BackboneError,"INVALID_APPROVAL_TRANSITION"):
            approve_strategy_route(self.root,"CORE-C-1",
                                   self.approval,now_ms=self.now)

    def test_signed_source_ack_must_exist_in_durable_original_outbox(self):
        bad=deepcopy(self.source_ack)
        bad["acknowledgement_sha256"]="d"*64
        bad=seal({k:v for k,v in bad.items() if k!="receipt_sha256"},
                 "receipt_sha256")
        req=deepcopy(self.request)
        req["source_ack_sha256"]=bad["receipt_sha256"]
        req=seal({k:v for k,v in req.items() if k!="request_sha256"},
                 "request_sha256")
        with self.assertRaisesRegex(BackboneError,"SOURCE_ACK_NOT_DURABLE"):
            self.enqueue(request=req,source_ack=bad)
        with sqlite3.connect(self.root/"warehouse.sqlite") as con:
            count=con.execute("SELECT COUNT(*) FROM c_strategy_routes").fetchone()[0]
        self.assertEqual(count,0)

    def test_source_strategy_mismatch_resealed_fails_closed(self):
        bad=deepcopy(self.request)
        bad["strategy_id"]="wrong_strategy"
        bad=seal({k:v for k,v in bad.items() if k!="request_sha256"},
                 "request_sha256")
        with self.assertRaisesRegex(BackboneError,"SOURCE_ACK_OUTBOX_PARENT_DRIFT"):
            self.enqueue(request=bad)

    def test_native_245_local_253_sha_and_cutoff_drift_rejected(self):
        bad=deepcopy(self.request)
        bad["core_253_query_local_sha256"]=self.gate.native["price_query_sha256"]
        bad=seal({k:v for k,v in bad.items() if k!="request_sha256"},
                 "request_sha256")
        with self.assertRaisesRegex(BackboneError,"DUAL_QUERY_PARENT_DRIFT"):
            self.enqueue(request=bad)
        bad=deepcopy(self.request)
        bad["cutoff_ms"]+=1
        bad=seal({k:v for k,v in bad.items() if k!="request_sha256"},
                 "request_sha256")
        with self.assertRaisesRegex(BackboneError,"DUAL_QUERY_PARENT_DRIFT"):
            self.enqueue(request=bad)

    def test_resealed_expired_and_mismatched_approval_denied(self):
        bad=deepcopy(self.approval)
        bad["expires_at_ms"]=self.now-1
        bad=seal({k:v for k,v in bad.items() if k!="approval_sha256"},
                 "approval_sha256")
        with self.assertRaisesRegex(BackboneError,"APPROVAL_EXPIRED"):
            self.enqueue(approval=bad)
        bad=deepcopy(self.approval)
        bad["config_digest"]="f"*64
        bad=seal({k:v for k,v in bad.items() if k!="approval_sha256"},
                 "approval_sha256")
        with self.assertRaisesRegex(BackboneError,"APPROVAL_IDENTITY"):
            self.enqueue(approval=bad)

    def test_consumer_ack_cannot_be_source_only_or_paper_authority(self):
        self.enqueue(approval=self.approval)
        bad=deepcopy(self.make_consumer())
        bad["trading_authority"]="LIVE"
        bad=seal({k:v for k,v in bad.items() if k!="consumer_ack_sha256"},
                 "consumer_ack_sha256")
        with self.assertRaisesRegex(BackboneError,"CONSUMER_ACK_PARENT"):
            acknowledge_strategy_consumer(
                self.root,"CORE-C-1",bad,now_ms=self.now+3)
        bad=deepcopy(self.make_consumer())
        bad["request_sha256"]=self.source_ack["receipt_sha256"]
        bad=seal({k:v for k,v in bad.items() if k!="consumer_ack_sha256"},
                 "consumer_ack_sha256")
        with self.assertRaisesRegex(BackboneError,"CONSUMER_ACK_PARENT"):
            acknowledge_strategy_consumer(
                self.root,"CORE-C-1",bad,now_ms=self.now+3)
        self.assertEqual(strategy_route_snapshot(
            self.root,"CORE-C-1",now_ms=self.now+4)["state"],"PENDING_CONSUMER")

    def test_retry_backoff_then_quarantine_no_late_ack(self):
        self.enqueue(approval=self.approval)
        retry=retry_strategy_route(self.root,"CORE-C-1",reason="TEMP",
                                   now_ms=self.now,max_attempts=2)
        self.assertEqual(retry["state"],"RETRY")
        with self.assertRaisesRegex(BackboneError,"CONSUMER_BACKOFF"):
            acknowledge_strategy_consumer(
                self.root,"CORE-C-1",self.make_consumer(),now_ms=self.now+3)
        terminal=retry_strategy_route(
            self.root,"CORE-C-1",reason="REJECTED",
            now_ms=self.now+1000,max_attempts=2)
        self.assertEqual(terminal["state"],"QUARANTINED")
        with self.assertRaisesRegex(BackboneError,"TERMINAL_STATE"):
            acknowledge_strategy_consumer(
                self.root,"CORE-C-1",self.make_consumer(),now_ms=self.now+1001)

    def test_expired_route_is_not_readied_for_lab(self):
        self.enqueue(approval=self.approval)
        later=self.request["expires_at_ms"]
        result=strategy_route_snapshot(self.root,"CORE-C-1",now_ms=later)
        self.assertEqual(result["state"],"EXPIRED")
        self.assertFalse(result["route_ready_for_isolated_lab"])
        self.assertEqual(retry_strategy_route(
            self.root,"CORE-C-1",reason="LATE",now_ms=later)["state"],"EXPIRED")

    def test_policy_parent_is_required_and_cannot_be_aliased(self):
        bad=deepcopy(self.policy)
        bad["payload"]["config_digest"]="0"*64
        bad["sha256"]=digest(bad["payload"])
        with self.assertRaisesRegex(BackboneError,"POLICY_CONFIG_DIGEST_DRIFT"):
            self.enqueue(strategy_policy_receipt=bad)
        bad=deepcopy(self.policy)
        bad["payload"]["strategy_id"]="test_reversion"
        body={k:v for k,v in bad["payload"].items() if k!="config_digest"}
        bad["payload"]["config_digest"]=digest(body)
        bad["sha256"]=digest(bad["payload"])
        with self.assertRaisesRegex(BackboneError,"POLICY_REQUEST_IDENTITY_DRIFT"):
            self.enqueue(strategy_policy_receipt=bad)

    def test_one_route_per_request_and_expired_ack_not_lab_ready(self):
        self.enqueue(approval=self.approval)
        with self.assertRaisesRegex(BackboneError,"AMBIGUOUS_DUPLICATE_REQUEST_ROUTE"):
            self.enqueue(approval=self.approval,route_id="CORE-C-ANOTHER")
        ack=self.make_consumer()
        accepted=acknowledge_strategy_consumer(
            self.root,"CORE-C-1",ack,now_ms=self.now+3)
        self.assertTrue(accepted["route_ready_for_isolated_lab"])
        after=strategy_route_snapshot(
            self.root,"CORE-C-1",now_ms=self.approval["expires_at_ms"])
        self.assertEqual(after["state"],"ACKED_CONSUMER")
        self.assertFalse(after["approval_valid_at_now"])
        self.assertFalse(after["route_ready_for_isolated_lab"])
        self.assertEqual(after["trading_authority"],"NONE")

    def test_restart_tamper_source_outbox_and_hash_chain(self):
        self.enqueue(approval=self.approval)
        with sqlite3.connect(self.root/"warehouse.sqlite") as con:
            con.execute("UPDATE distribution_outbox SET ack_sha=? "
                        "WHERE message_id=?",("0"*64,"C-SOURCE-1"))
        with self.assertRaisesRegex(BackboneError,"SOURCE_ACK_NOT_DURABLE"):
            strategy_route_snapshot(self.root,"CORE-C-1",now_ms=self.now)
        # The second route has intact Core ACK, but tamper the C event hash.
        with sqlite3.connect(self.root/"warehouse.sqlite") as con:
            con.execute("UPDATE distribution_outbox SET ack_sha=? "
                        "WHERE message_id=?",("c"*64,"C-SOURCE-1"))
            con.execute("UPDATE c_strategy_events SET event_sha=? "
                        "WHERE route_id=?",("0"*64,"CORE-C-1"))
        with self.assertRaisesRegex(BackboneError,"TRACE_TAMPER"):
            strategy_route_snapshot(self.root,"CORE-C-1",now_ms=self.now)


if __name__=="__main__":
    unittest.main()
