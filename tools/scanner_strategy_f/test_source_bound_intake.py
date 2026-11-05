"""Scanner F3 source-bound Core F2 negative/real-signature integration tests.

Synthetic HASH-ONLY *contract fixture*, NOT actual publisher evidence. Exact
separate F2 issuer/custodian approval is intentionally required before the
private research runner may trust any report.
"""
from __future__ import annotations
import copy
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from research_wp_r0.aql_core_f_bulk_source_v1 import build_manifest,build_coverage_ledger
from research_wp_r0.aql_core_f_private_f2_v1 import digest as core_digest
from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from tools.scanner_strategy_f.policy_activation_request import make_historical_activation_request
from tools.scanner_strategy_f.independent_policy_verification import SCHEMA,_canonical
from tools.scanner_strategy_f.source_bound_intake import (
    verify_core_f2_report,bind_original_research_census
)


class SourceBoundIntake(unittest.TestCase):
    def setUp(self):
        self.specs=json.loads((FIXTURES/"strategies.json").read_text())
        self.e=propose_historical_research_policy(self.specs)
        self.er=prepare_historical_policy_approval_request(self.e,self.specs)
        self.policy=create_retrospective_policy_draft(self.e,self.er,self.specs)
        self.act=make_historical_activation_request(
            self.policy,self.e,self.er,self.specs)
        self.manifest=build_manifest()
        outcomes={}
        entries=[]
        for row in self.manifest["rows"]:
            month=row["month"]
            if month in ("2024-02","2024-08"):
                continue
            n=int(month[-2:])
            source=f"{n:064x}"
            checks=f"{n+100:064x}"
            outcomes[month]={
                "status":"ACCEPTED_PREFLIGHT",
                "archive_sha256":source,
                "checksum_file_sha256":checks,
                "preflight_receipt_sha256":f"{n+200:064x}",
                "observed_bars":row["expected_native_15m_bars"],
                "raw_vault":"NOT_YET_ADMITTED",
                "warehouse":"NOT_YET_ADMITTED",
                "historical_pit":"NOT_ATTESTED",
            }
            entries.append({
                "month":month,"state":"RAW_AND_DUAL_QUERY_READBACK",
                "source_sha256":source,
                "checksum_file_sha256":checks,
                "csv_member_sha256":f"{n+300:064x}",
                "warehouse_receipt_sha256":f"{n+400:064x}",
                "core_245_native_price_query_sha256":f"{n+500:064x}",
                "core_253_local_query_sha256":f"{n+600:064x}",
                "dual_query_map_sha256":f"{n+700:064x}",
                "bars":row["expected_native_15m_bars"],
                "historical_pit":"NOT_ATTESTED",
            })
        self.coverage=build_coverage_ledger(self.manifest,outcomes)
        self.source_authority_sha="a"*64
        report={
            "schema":"aql.core.f.private-raw-warehouse-dual-query-report.v1",
            "manifest_sha256":self.manifest["manifest_sha256"],
            "f1_coverage_ledger_sha256":self.coverage["coverage_ledger_sha256"],
            "authorization_document_sha256":self.source_authority_sha,
            "provenance":"CURRENT_PUBLISHER_TLS_CHECKSUM_OPERATOR_ATTESTED_NOT_HISTORICAL_ISSUER_SIGNATURE",
            "f2_new_admitted_count":10,
            "f2_previous_retained_inventory_only_count":2,
            "entries":entries,
            "strategy_policy_approval":"NOT_ATTESTED_BY_CORE",
            "secretary_historical_strategy_route":"NOT_AUTHORIZED",
            "factory_consumer_ack":None,
            "historical_pit":"NOT_ATTESTED",
            "trading_authority":"NONE",
        }
        self.report={**report,"report_sha256":core_digest(report)}
        self.private=Ed25519PrivateKey.generate() # TEST KEY only, not GitHub authority
        pub=self.private.public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.keys={"k1":{"public_key_hex":pub.hex(),
                         "approver_identity":"owner-research-approver",
                         "authority":"INDEPENDENT_STRATEGY_POLICY_OWNER",
                         "enabled":True}}
        self.approval={
            "schema":SCHEMA,
            "decision":"APPROVE_RESEARCH_ONLY_RETROSPECTIVE_NON_PIT",
            "activation_request_sha256":self.act["sha256"],
            **self.act["payload"]["scope"],
            "approver_identity":"owner-research-approver",
            "approval_time_utc":"2026-11-05T12:00:00Z",
            "expires_at_utc":"2026-12-05T12:00:00Z",
            "trusted_record_reference":"governance://approved/f3/1",
            "signature_scheme":"Ed25519","key_id":"k1",
        }
        self.approval["signature"]=self.private.sign(_canonical(self.approval)).hex()

    def run_bridge(self,**kw):
        args=dict(
            manifest=self.manifest,coverage=self.coverage,
            policy_draft=self.policy,proposal=self.e,
            approval_request=self.er,work_specs=self.specs,
            core_f2_report=self.report,
            expected_core_f2_sha256=self.report["report_sha256"],
            external_source_authorization_sha256=self.source_authority_sha,
            signed_owner_policy_approval=self.approval,
            trusted_policy_keyring=self.keys,
            observed_at_utc="2026-11-05T13:00:00Z",
        )
        args.update(kw)
        return bind_original_research_census(**args)

    def test_source_and_signature_both_verified_never_auto_select(self):
        result=self.run_bridge()
        body=Frozen.restore(result).data
        self.assertEqual(result,self.run_bridge())
        self.assertEqual(body["attempt_count"],24)
        self.assertEqual(body["ready_for_independent_research_screening"],20)
        self.assertEqual(body["unknown_retained"],4)
        self.assertEqual(body["selected"],0)
        self.assertEqual(body["secretary_state"],"NOT_ENQUEUED")
        self.assertIsNone(body["factory_consumer_ack_sha256"])
        self.assertEqual(body["trading_authority"],"NONE")
        for item in body["attempts"]:
            row=Frozen.restore(item).data
            if row["month"] in ("2024-02","2024-08"):
                self.assertIsNone(row["original_source_sha256"])
                self.assertEqual(row["status"],"UNKNOWN_RETAINED_NOT_READBACK")

    def test_no_source_or_mismatched_source_authority_denied(self):
        for kwargs in (
            {"expected_core_f2_sha256":"b"*64},
            {"external_source_authorization_sha256":"b"*64},
            {"core_f2_report":None},
            {"trusted_policy_keyring":{}},
        ):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                self.run_bridge(**kwargs)

    def test_source_month_and_query_drift_are_denied_even_resealed(self):
        for field,value in (
            ("source_sha256","f"*64),
            ("checksum_file_sha256","f"*64),
            ("bars",1),
            ("core_253_local_query_sha256",f"{1+500:064x}"),
            ("month","2024-02"),
        ):
            with self.subTest(field=field):
                wrong=copy.deepcopy(self.report)
                wrong["entries"][0][field]=value
                wrong["report_sha256"]=core_digest({
                    k:v for k,v in wrong.items() if k!="report_sha256"})
                with self.assertRaises(ValueError):
                    self.run_bridge(core_f2_report=wrong,
                                    expected_core_f2_sha256=wrong["report_sha256"])

    def test_resealed_report_scope_forged_pit_or_missing_month_denied(self):
        for field,value in (
            ("historical_pit","ATTESTED"),
            ("f2_new_admitted_count",12),
            ("f2_previous_retained_inventory_only_count",0),
            ("strategy_policy_approval","APPROVED_BY_CORE"),
            ("trading_authority","LIVE"),
        ):
            with self.subTest(field=field):
                wrong=copy.deepcopy(self.report)
                wrong[field]=value
                wrong["report_sha256"]=core_digest({
                    k:v for k,v in wrong.items() if k!="report_sha256"})
                with self.assertRaises(ValueError):
                    self.run_bridge(core_f2_report=wrong,
                                    expected_core_f2_sha256=wrong["report_sha256"])
        wrong=copy.deepcopy(self.report)
        wrong["entries"].pop(0)
        wrong["report_sha256"]=core_digest({
            k:v for k,v in wrong.items() if k!="report_sha256"})
        with self.assertRaises(ValueError):
            self.run_bridge(core_f2_report=wrong,
                            expected_core_f2_sha256=wrong["report_sha256"])

    def test_unsigned_and_wrong_policy_scope_denied(self):
        for field,value in (
            ("approved_symbol","ETHUSDT"),
            ("approved_months",["2024-01"]),
            ("cutoff_rule","FUTURE_ALLOWED"),
            ("signature","f"*128),
        ):
            with self.subTest(field=field):
                wrong=copy.deepcopy(self.approval)
                wrong[field]=value
                with self.assertRaises(ValueError):
                    self.run_bridge(signed_owner_policy_approval=wrong)

if __name__=="__main__":
    unittest.main()
