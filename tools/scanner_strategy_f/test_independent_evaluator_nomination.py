"""Scanner F — cryptographic evaluator-to-nomination bridge, contract-only.

Fixture signatures are ephemeral test keys, NOT an original historical run.
No original E: warehouse bytes are available to this GitHub runner.
"""
from __future__ import annotations
import copy
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.independent_evaluator_nomination import (
    RECEIPT_SCHEMA, _canonical,verify_external_evaluator_receipt,
    create_independent_research_nomination,verify_research_nomination,
)
from tools.scanner_strategy_f.test_source_bound_intake import SourceBoundIntake


class F3ExternalEvaluatorNomination(SourceBoundIntake):
    def setUp(self):
        super().setUp()
        self.census=self.run_bridge()
        self.record=next(
            Frozen.restore(item).data for item in
            Frozen.restore(self.census).data["attempts"]
            if Frozen.restore(item).data["month"]=="2024-01"
            and Frozen.restore(item).data["strategy_id"]=="test_momentum")
        # Deliberately test an UNTRUSTED synthetic strategy decision: only
        # exercises cryptographic binding and contract states, never asserts
        # data-derived indicators or an independently verified source.
        r=self.record
        self.decision=Frozen.build({
            "schema":"aql.scanner-f.historical-original-strategy-decision.v1",
            "source_bound_census_sha256":self.census["sha256"],
            "strategy_id":r["strategy_id"],"strategy_version":r["strategy_version"],
            "month":r["month"],"symbol":"BTCUSDT",
            "market":"BINANCE:SPOT:USDT","timeframe":"15m",
            "strategy_definition_digest":r["strategy_definition_digest"],
            "dna_digest":r["dna_digest"],
            "native15m_config_digest":r["native15m_config_digest"],
            "warehouse_receipt_sha256":r["warehouse_receipt_sha256"],
            "core245_native_query_sha256":r["core245_native_query_sha256"],
            "core253_local_query_sha256":r["core253_local_query_sha256"],
            "dual_query_map_sha256":r["dual_query_map_sha256"],
            "cutoff_ms":1738368000000,
            "last_evaluated_open_ms":1735688700000,
            "external_indicator_receipt_sha256":"2"*64,
            "external_signal_digest":"3"*64,
            "signal_observation":"PROPOSED_RESEARCH_ONLY",
            "decision":"WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL",
            "selected":False,
            "research_scope":"RETROSPECTIVE_NON_PIT",
            "historical_pit":"NOT_ATTESTED",
            "source_ack_sha256":None,
            "strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None,
            "secretary_state":"NOT_ENQUEUED",
            "trading_authority":"NONE",
        }).receipt()
        self.key=Ed25519PrivateKey.generate()
        pub=self.key.public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.evaluator_keys={"evaluator-authorized":{
            "public_key_hex":pub.hex(),
            "approver_identity":"external-evaluator-owner",
            "authority":"INDEPENDENT_EVALUATOR",
            "enabled":True
        }}
        x=self.decision["payload"]
        c=self.census["payload"]
        self.receipt={
            "schema":RECEIPT_SCHEMA,
            "decision_sha256":self.decision["sha256"],
            "source_bound_census_sha256":self.census["sha256"],
            "policy_approval_sha256":c["verified_owner_policy_receipt_sha256"],
            "core_f2_report_sha256":c["core_f2_report_sha256"],
            **{k:x[k] for k in (
                "strategy_id","strategy_version","month","symbol","market",
                "timeframe","strategy_definition_digest","dna_digest",
                "native15m_config_digest","warehouse_receipt_sha256",
                "core245_native_query_sha256","core253_local_query_sha256",
                "dual_query_map_sha256","cutoff_ms",
                "last_evaluated_open_ms")},
            "indicator_receipt_sha256":x["external_indicator_receipt_sha256"],
            "signal_digest":x["external_signal_digest"],
            "evaluator_code_sha256":"a"*64,
            "evaluator_version":"historical-evaluator-v1",
            "evaluation_result":"RESEARCH_CANDIDATE",
            "approver_identity":"external-evaluator-owner",
            "key_id":"evaluator-authorized",
            "not_before_utc":"2026-11-07T08:00:00Z",
            "expires_at_utc":"2026-12-07T08:00:00Z",
            "signature_scheme":"Ed25519",
        }
        self.receipt["signature"]=self.key.sign(_canonical(self.receipt)).hex()

    def verify(self,**kw):
        args=dict(signed_evaluation=self.receipt,
                  strategy_decision=self.decision,
                  source_bound_census=self.census,
                  trusted_evaluator_keyring=self.evaluator_keys,
                  observed_at_utc="2026-11-07T09:00:00Z")
        args.update(kw)
        return verify_external_evaluator_receipt(**args)

    def test_ephemeral_signed_candidate_is_nomination_only_not_selected(self):
        verified=self.verify()
        nomination=create_independent_research_nomination(
            verified,self.decision,self.census)
        self.assertEqual(nomination,create_independent_research_nomination(
            verified,self.decision,self.census))
        data=verify_research_nomination(
            nomination,verified,self.decision,self.census).data
        self.assertEqual(data["decision"],"NOMINATED_RESEARCH_ONLY")
        self.assertIs(data["selected"],False)
        self.assertIsNone(data["core_source_ack_sha256"])
        self.assertIsNone(data["core_secretary_strategy_approval_sha256"])
        self.assertIsNone(data["factory_consumer_ack_sha256"])
        self.assertEqual(data["secretary_status"],"NOT_ENQUEUED")
        self.assertEqual(data["historical_pit"],"NOT_ATTESTED")
        self.assertEqual(data["trading_authority"],"NONE")

    def test_wrong_missing_disabled_root_and_signer_rejected(self):
        for keys in (
            {},
            {"evaluator-authorized":{**self.evaluator_keys["evaluator-authorized"],
                "authority":"SCANNER_SELF"}},
            {"evaluator-authorized":{**self.evaluator_keys["evaluator-authorized"],
                "enabled":False}},
            {"evaluator-authorized":{**self.evaluator_keys["evaluator-authorized"],
                "approver_identity":"other"}},
        ):
            with self.subTest(keys=keys),self.assertRaises(ValueError):
                self.verify(trusted_evaluator_keyring=keys)
        badkey=Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        keys=copy.deepcopy(self.evaluator_keys)
        keys["evaluator-authorized"]["public_key_hex"]=badkey.hex()
        with self.assertRaises(ValueError):
            self.verify(trusted_evaluator_keyring=keys)

    def test_resigned_and_tampered_strategy_source_query_scope_denied(self):
        for field,value in (
            ("strategy_id","test_reversion"),
            ("month","2024-02"),
            ("symbol","ETHUSDT"),
            ("timeframe","1m"),
            ("policy_approval_sha256","f"*64),
            ("core_f2_report_sha256","b"*64),
            ("core245_native_query_sha256","e"*64),
            ("core253_local_query_sha256","c"*64),
            ("indicator_receipt_sha256","d"*64),
            ("cutoff_ms",111),
            ("evaluation_result","APPROVED_FOR_TRADING"),
            ("signature","f"*128),
        ):
            with self.subTest(field=field):
                bad=copy.deepcopy(self.receipt)
                bad[field]=value
                if field!="signature":
                    bad["signature"]=self.key.sign(_canonical({
                        k:v for k,v in bad.items() if k!="signature"})).hex()
                with self.assertRaises(ValueError):
                    self.verify(signed_evaluation=bad)

    def test_invalid_time_and_expiration_fail_closed(self):
        for now in ("2026-11-07T07:00:00Z",
                    "2026-12-07T08:00:00Z",
                    "not-a-time"):
            with self.subTest(now=now),self.assertRaises(ValueError):
                self.verify(observed_at_utc=now)

    def test_rejected_unknown_and_resigned_nomination_cannot_be_selected(self):
        for result,expected in (
            ("RESEARCH_REJECTED","REJECTED_RESEARCH_ONLY"),
            ("UNKNOWN","UNKNOWN"),
        ):
            with self.subTest(result=result):
                bad=copy.deepcopy(self.receipt)
                bad["evaluation_result"]=result
                bad["signature"]=self.key.sign(_canonical({
                    k:v for k,v in bad.items() if k!="signature"})).hex()
                e=self.verify(signed_evaluation=bad)
                nomination=create_independent_research_nomination(
                    e,self.decision,self.census)
                self.assertEqual(nomination["payload"]["decision"],expected)
        e=self.verify()
        n=create_independent_research_nomination(e,self.decision,self.census)
        for change,value in (
            ("selected",True),
            ("core_source_ack_sha256","f"*64),
            ("core_secretary_strategy_approval_sha256","e"*64),
            ("factory_consumer_ack_sha256","d"*64),
            ("secretary_status","ENQUEUED"),
            ("trading_authority","PAPER"),
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                tampered=copy.deepcopy(n["payload"])
                tampered[change]=value
                verify_research_nomination(
                    Frozen.build(tampered).receipt(),e,self.decision,self.census)


if __name__=="__main__":
    unittest.main()
