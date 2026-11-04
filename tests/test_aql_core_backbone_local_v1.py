"""Core #253 one bounded offline RAW→price→Scanner/Secretary flow.

Synthetic originals only, all checked against real existing Core ZIP/Bridge
APIs; no private Work retained bytes and no scientific or trading authority.
"""
from copy import deepcopy
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import raw_sha,digest
from research_wp_r0.aql_core_backbone_local_v1 import (
    BackboneError,admit_local_original,query_local,
)
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination,poll_nomination,acknowledge_nomination,
    retry_or_quarantine,route_trace,
)
from test_aql_archive_custody_bridge_v1 import START, WIDTH, N, spec
from test_aql_native_binance_zip_v1 import native_source

class CoreBackboneGate(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"warehouse"
        self.raw,self.csv,self.checksum,self.pin=native_source()
        self.spec=spec(source_label="native-monthly-zip")
        self.cutoff=START+N*WIDTH+2000

    def admit(self,*,raw=None,cs=None,pin=None,sp=None,cutoff=None):
        return admit_local_original(
            self.root,self.raw if raw is None else raw,
            self.checksum if cs is None else cs,
            self.pin if pin is None else pin,
            self.spec if sp is None else sp,
            decision_cutoff_ms=self.cutoff if cutoff is None else cutoff,
        )

    def query(self,receipt,*,cutoff=None,version=None,strict=True):
        return query_local(
            self.root,self.spec["dataset_id"],
            receipt["version"] if version is None else version,
            self.spec["start_ms"],self.spec["end_exclusive_ms"],
            self.cutoff if cutoff is None else cutoff,
            required_source_sha256=receipt["source_zip_sha256"],
            require_complete=strict,
        )

    def nomination(self,receipt,*,candidate="BTCUSDT:TEST:1",stage="NOMINATED"):
        return {
            "scanner_id":"SCANNER_TEST_ONLY",
            "candidate_id":candidate,
            "profile_id":"STRATEGY_TEST_PROFILE",
            "market":"BINANCE:SPOT:USDT",
            "cutoff_at":"TEST_ONLY_DATE",
            "availability_class":"RETROSPECTIVE_NON_PIT",
            "stage":stage,
            "source_manifest":{
                "dataset_id":receipt["dataset_id"],
                "dataset_sha":receipt["source_zip_sha256"],
                "schema_version":"AQL-SCANNER-V1",
            },
            "feature_snapshot":{},
            "reasons":["TEST_ONLY_NOT_APPROVED"],
            "coverage":{"historical_pit":"NOT_ATTESTED"},
            "score":None,"score_status":"NOT_SCORED",
            "publishable":False,"delivery_authorized":False,
        }

    def test_original_zip_to_durable_index_to_source_locked_price(self):
        a=self.admit()
        self.assertEqual(a["status"],"OFFLINE_LOCAL_STAGE_ONLY")
        self.assertEqual(a["bar_count"],N)
        self.assertEqual(a["vault"]["vault"],"NOT_CONNECTED_CORE_STAGE_ONLY")
        self.assertEqual(a["availability"],"RETROSPECTIVE_NON_PIT")
        self.assertEqual(self.admit(),a)
        q=self.query(a)
        self.assertEqual(q["coverage"],"COMPLETE")
        self.assertEqual(len(q["bars"]),N)
        self.assertEqual(q["bars"][0]["close"],101)
        self.assertIsNone(q["bars"][0]["historical_known_at_ms"])
        self.assertEqual(q["source_bytes_sha256"],raw_sha(self.raw))
        self.assertEqual(q["historical_pit"],"NOT_ATTESTED")
        # Close/reopen SQLite and replay Core stager, no reprocessing needed.
        self.assertEqual(self.query(a),q)

    def test_missing_witnesses_cutoff_and_partial_are_not_upgraded(self):
        a=self.admit()
        partial=self.query(a,cutoff=START+WIDTH+1000,strict=False)
        self.assertEqual(partial["coverage"],"PARTIAL")
        self.assertEqual(partial["available_bar_count"],1)
        self.assertEqual(len(partial["missing_bar_opens"]),N-1)
        unknown=self.query(a,cutoff=START,strict=False)
        self.assertEqual(unknown["coverage"],"UNKNOWN")
        self.assertEqual(unknown["available_bar_count"],0)
        with self.assertRaisesRegex(BackboneError,"INCOMPLETE_OR_FUTURE"):
            self.query(a,cutoff=START,strict=True)

    def test_bad_original_zip_or_checksum_denied(self):
        with self.assertRaisesRegex(ValueError,"ORIGINAL_BYTE_SHA_MISMATCH"):
            self.admit(raw=self.raw+b"!")
        with self.assertRaises(ValueError):
            self.admit(cs=self.checksum+b"0")
        self.assertFalse((self.root/"warehouse.sqlite").exists())

    def test_source_correction_append_only_and_replay(self):
        original=self.admit()
        raw,csv,check,pin=native_source(change=3)
        new=spec(version=2,source_label="native-monthly-zip",
                 parent_source_sha256=original["source_zip_sha256"],
                 correction_reason="TEST_CORRECTION")
        changed=self.admit(raw=raw,cs=check,pin=pin,sp=new)
        self.assertEqual(changed["version"],2)
        self.assertEqual(self.query(original)["source_bytes_sha256"],
                         original["source_zip_sha256"])
        self.assertEqual(self.query(changed)["source_bytes_sha256"],
                         raw_sha(raw))
        new_raw,new_csv,new_cs,new_pin=native_source(change=4)
        with self.assertRaises(ValueError):
            self.admit(raw=new_raw,cs=new_cs,pin=new_pin,sp=new)

    def test_index_tamper_is_denied_against_original_bridge_source(self):
        receipt=self.admit()
        with sqlite3.connect(self.root/"warehouse.sqlite") as c:
            c.execute("UPDATE price_bars SET close_px=999 WHERE dataset_id=?",
                      (receipt["dataset_id"],))
        with self.assertRaisesRegex(BackboneError,"INDEX_TAMPER"):
            self.query(receipt)
        # Restore all corrupted rows from sealed source, not one arbitrary
        # constant (the earlier UPDATE intentionally corrupted ALL N bars).
        with sqlite3.connect(self.root/"warehouse.sqlite") as c:
            for i in range(N):
                c.execute("UPDATE price_bars SET close_px=? WHERE open_ms=?",
                          (101+i,START+i*WIDTH))
        self.assertEqual(self.query(receipt)["coverage"],"COMPLETE")

    def test_strategy_route_fast_slow_and_idempotency(self):
        receipt=self.admit()
        fast=enqueue_nomination(
            self.root,self.nomination(receipt),strategy_id="STRAT_TEST",
            strategy_version="v1",warehouse_receipt=receipt,lane="FAST",
            idempotency_key="E1",
        )
        self.assertEqual(fast,enqueue_nomination(
            self.root,self.nomination(receipt),strategy_id="STRAT_TEST",
            strategy_version="v1",warehouse_receipt=receipt,lane="FAST",
            idempotency_key="E1",
        ))
        enqueue_nomination(
            self.root,self.nomination(receipt,candidate="SLOW:TEST"),
            strategy_id="STRAT_TEST",strategy_version="v1",
            warehouse_receipt=receipt,lane="SLOW",idempotency_key="E2",
        )
        next_item=poll_nomination(self.root,now_ms=0)
        self.assertEqual(next_item["message_id"],"E1")
        self.assertEqual(next_item["envelope"]["strategy_authority"],
                         "OFFLINE_RESEARCH_ONLY_NOT_APPROVED_PAPER")
        self.assertEqual(poll_nomination(self.root,now_ms=0,lane="SLOW")["message_id"],
                         "E2")
        ack=acknowledge_nomination(self.root,message_id="E1",
                 payload_sha256=fast["payload_sha256"],
                 acknowledgement_sha256="a"*64)
        self.assertEqual(ack["state"],"ACKED")
        self.assertEqual(poll_nomination(self.root,now_ms=0)["message_id"],"E2")
        self.assertEqual(ack,acknowledge_nomination(self.root,message_id="E1",
              payload_sha256=fast["payload_sha256"],
              acknowledgement_sha256="a"*64))

    def test_conflicting_idempotency_and_fake_paper_denied(self):
        receipt=self.admit()
        original=self.nomination(receipt)
        enqueue_nomination(self.root,original,strategy_id="STRAT",
                           strategy_version="v1",warehouse_receipt=receipt,
                           lane="FAST",idempotency_key="E1")
        with self.assertRaisesRegex(BackboneError,"IDEMPOTENCY_CONFLICT"):
            enqueue_nomination(self.root,self.nomination(receipt,candidate="ELSE"),
                strategy_id="STRAT",strategy_version="v1",warehouse_receipt=receipt,
                lane="FAST",idempotency_key="E1")
        fake=deepcopy(original);fake["delivery_authorized"]=True
        with self.assertRaisesRegex(BackboneError,"SCANNER_OFFLINE_AUTHORITY"):
            enqueue_nomination(self.root,fake,strategy_id="STRAT",
                    strategy_version="v1",warehouse_receipt=receipt,lane="SLOW",
                    idempotency_key="E3")
        forged=deepcopy(receipt);forged["source_zip_sha256"]="0"*64
        with self.assertRaisesRegex(BackboneError,"WAREHOUSE_RECEIPT_REQUIRED"):
            enqueue_nomination(self.root,original,strategy_id="STRAT",
                 strategy_version="v1",warehouse_receipt=forged,lane="SLOW",
                 idempotency_key="E4")

    def test_retry_backoff_terminal_quarantine_no_premature_ack(self):
        a=self.admit()
        msg=enqueue_nomination(self.root,self.nomination(a),
            strategy_id="S",strategy_version="v1",warehouse_receipt=a,
            lane="FAST",idempotency_key="R1")
        payload=msg["payload_sha256"]
        retry=retry_or_quarantine(self.root,message_id="R1",
              payload_sha256=payload,reason="TEMP_ERROR",now_ms=100,
              max_attempts=2)
        self.assertEqual(retry["state"],"RETRY")
        self.assertIsNone(poll_nomination(self.root,now_ms=500))
        self.assertEqual(poll_nomination(self.root,now_ms=1100)["message_id"],"R1")
        terminal=retry_or_quarantine(self.root,message_id="R1",
              payload_sha256=payload,reason="REJECTED",now_ms=1200,max_attempts=2)
        self.assertEqual(terminal["state"],"QUARANTINED")
        self.assertIsNone(poll_nomination(self.root,now_ms=10000))
        with self.assertRaisesRegex(BackboneError,"ACK_QUARANTINED"):
            acknowledge_nomination(self.root,message_id="R1",
                  payload_sha256=payload,acknowledgement_sha256="a"*64)

    def test_trace_ledger_enqueued_retry_ack_and_crash_reopen(self):
        a=self.admit()
        p=enqueue_nomination(
            self.root,self.nomination(a),strategy_id="S",
            strategy_version="v1",warehouse_receipt=a,
            lane="FAST",idempotency_key="AUDIT_TRACE",
        )
        self.assertEqual([x["state"] for x in
                         route_trace(self.root,"AUDIT_TRACE")],["PENDING"])
        retry_or_quarantine(self.root,message_id="AUDIT_TRACE",
               payload_sha256=p["payload_sha256"],reason="TEMP",
               now_ms=100,max_attempts=3)
        self.assertEqual([x["state"] for x in
                         route_trace(self.root,"AUDIT_TRACE")],
                         ["PENDING","RETRY"])
        acknowledge_nomination(self.root,message_id="AUDIT_TRACE",
               payload_sha256=p["payload_sha256"],
               acknowledgement_sha256="a"*64)
        self.assertEqual([x["state"] for x in
                         route_trace(self.root,"AUDIT_TRACE")],
                         ["PENDING","RETRY","ACKED"])
        self.assertIsNone(poll_nomination(self.root,now_ms=100000))
        with sqlite3.connect(self.root/"warehouse.sqlite") as c:
            c.execute("UPDATE distribution_events SET event_sha256=? "
                      "WHERE message_id=? AND state='RETRY'",
                      ("0"*64,"AUDIT_TRACE"))
        with self.assertRaisesRegex(BackboneError,"SECRETARY_TRACE_TAMPER"):
            route_trace(self.root,"AUDIT_TRACE")

    def test_queue_payload_tamper_fails_closed(self):
        receipt=self.admit()
        enqueue_nomination(self.root,self.nomination(receipt),
              strategy_id="S",strategy_version="v1",warehouse_receipt=receipt,
              lane="SLOW",idempotency_key="E1")
        with sqlite3.connect(self.root/"warehouse.sqlite") as c:
            c.execute("UPDATE distribution_outbox SET payload_hash=?",
                      ("0"*64,))
        with self.assertRaisesRegex(BackboneError,"SECRETARY_QUEUE_TAMPER"):
            poll_nomination(self.root,now_ms=0)

if __name__=="__main__":
    unittest.main()
