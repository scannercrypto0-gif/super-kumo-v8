"""Scanner F3 actual Core F manifest consumer boundary — no historical promotion."""
from __future__ import annotations
import copy
import json
import unittest

from research_wp_r0.aql_core_f_bulk_source_v1 import (
    build_manifest,build_coverage_ledger
)
from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from tools.scanner_strategy_f.bulk_census import historical_bulk_intake_census


class ScannerF3ActualCoreFIntake(unittest.TestCase):
    def setUp(self):
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.proposal=propose_historical_research_policy(self.work)
        self.request=prepare_historical_policy_approval_request(self.proposal,self.work)
        self.policy=create_retrospective_policy_draft(
            self.proposal,self.request,self.work)
        self.manifest=build_manifest()
        self.outcomes={}
        for row in self.manifest["rows"]:
            if row["inventory_status"]=="TARGET_NOT_ACQUIRED":
                self.outcomes[row["month"]]={
                    "status":"ACCEPTED_PREFLIGHT",
                    # Engineering *contract fixture*, NOT real ZIP bytes or
                    # source issuer authentication, cannot produce a route.
                    "archive_sha256":("a"*64),
                    "checksum_file_sha256":("b"*64),
                    "preflight_receipt_sha256":("c"*64),
                    "observed_bars":row["expected_native_15m_bars"],
                    "raw_vault":"NOT_YET_ADMITTED",
                    "warehouse":"NOT_YET_ADMITTED",
                    "historical_pit":"NOT_ATTESTED"}
        self.ledger=build_coverage_ledger(self.manifest,self.outcomes)

    def call(self,**overrides):
        q=dict(manifest=self.manifest,coverage_ledger=self.ledger,
               policy_draft=self.policy,proposal=self.proposal,
               approval_request=self.request,work_specs=self.work)
        q.update(overrides)
        return historical_bulk_intake_census(**q)

    def test_all_12_months_10_preflight_2_retained_24_unknown_attempts(self):
        receipt=self.call()
        d=Frozen.restore(receipt).data
        self.assertEqual(receipt,self.call())
        self.assertEqual(d["strategy_count"],2)
        self.assertEqual(d["months_censused"],12)
        self.assertEqual(d["total_attempts"],24)
        self.assertEqual(d["attempt_status_census"],{
            "UNKNOWN_PREFLIGHT_ONLY":20,"QUARANTINED":0,
            "UNKNOWN_MISSING_SOURCE":0,"UNKNOWN_RETAINED_NOT_READBACK":4})
        self.assertEqual(d["selected_count"],0)
        self.assertEqual(d["source_status"],"CORE_F1_PREFLIGHT_ONLY")
        self.assertEqual(d["factory_lab"],"NOT_EVALUATED")
        self.assertEqual(d["decision"],
                         "WAIT_CORE_F2_AND_INDEPENDENT_POLICY_APPROVAL")
        self.assertIsNone(d["core_245_native_query_sha256"])
        self.assertIsNone(d["core_253_local_query_sha256"])
        self.assertIsNone(d["independent_owner_approval_sha256"])
        for row in d["attempts"]:
            a=row["payload"]
            self.assertIsNone(a["source_ack_sha256"])
            self.assertIsNone(a["strategy_approval_sha256"])
            self.assertIsNone(a["factory_consumer_ack_sha256"])
            self.assertEqual(a["trading_authority"],"NONE")

    def test_missing_rejected_retained_are_censused_without_fabricated_sha(self):
        outcomes=copy.deepcopy(self.outcomes)
        del outcomes["2024-01"]
        outcomes["2024-03"]={"status":"REJECTED_QUARANTINED",
                             "reason":"INVALID_PUBLISHER_CHECKSUM"}
        ledger=build_coverage_ledger(self.manifest,outcomes)
        d=Frozen.restore(self.call(coverage_ledger=ledger)).data
        self.assertEqual(d["attempt_status_census"],{
            "UNKNOWN_PREFLIGHT_ONLY":16,"QUARANTINED":2,
            "UNKNOWN_MISSING_SOURCE":2,"UNKNOWN_RETAINED_NOT_READBACK":4})
        self.assertEqual(d["selected_count"],0)
        for row in d["attempts"]:
            x=row["payload"]
            if x["month"] in ("2024-01","2024-03","2024-02","2024-08"):
                self.assertIsNone(x["source_archive_sha256"])

    def test_tampered_manifest_and_ledger_source_identity_denied(self):
        bad=copy.deepcopy(self.manifest)
        bad["source"]="SYNTHETIC_TEST_ONLY"
        with self.assertRaises(ValueError):
            self.call(manifest=bad)
        bad=copy.deepcopy(self.ledger)
        bad["entries"][0]["status"]="ACCEPTED_PREFLIGHT"
        with self.assertRaises(ValueError):
            self.call(coverage_ledger=bad)
        bad=copy.deepcopy(self.ledger)
        bad["core_245_native_query_sha256"]="f"*64
        with self.assertRaises(ValueError):
            self.call(coverage_ledger=bad)

    def test_untrusted_signed_approval_core_query_and_source_ack_denied(self):
        for key in ("core_custody","core_245_query","core_253_query",
                    "independent_policy_approval","source_ack"):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.call(**{key:{"sha256":"f"*64}})

    def test_policy_strategy_config_or_month_swap_denied(self):
        bad=copy.deepcopy(self.work)
        bad[0]["payload"]["strategy_id"]="wrong"
        with self.assertRaises(ValueError):
            self.call(work_specs=bad)
        subset=create_retrospective_policy_draft(
            self.proposal,self.request,self.work,target_months=("2024-03",))
        with self.assertRaises(ValueError):
            self.call(policy_draft=subset)
        bad=copy.deepcopy(self.ledger)
        bad["entries"][1]["month"]="2025-01"
        with self.assertRaises(ValueError):
            self.call(coverage_ledger=bad)


if __name__=="__main__":
    unittest.main()
