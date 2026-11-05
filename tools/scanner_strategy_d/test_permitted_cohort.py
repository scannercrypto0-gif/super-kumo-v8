"""Scanner D one allowed-symbol Core RAW → #245/#253 → Scanner canonical C.

No frozen Work235 edit, original-market/PIT promotion, Lab or Paper activation.
"""
from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from copy import deepcopy
from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_d.permitted_test_cohort import (
    create_permitted_core_test_cohort, SOURCE_SYMBOL,
)
from research_wp_r0.aql_core_d_same_source_route_v1 import verify_scanner_d_for_core_route


class ScannerDEligiblePolicyCohort(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"core"
        self.vault=Path(self.temp.name)/"vault"
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.actions={
            (w["payload"]["strategy_id"], w["payload"]["strategy_version"]):{
                "action":"APPROVE_TEST_ONLY",
                "approver_id":"TEST_POLICY_FIXTURE_ONLY",
                "governance_policy_id":"SCANNER_D_SYNTHETIC_SCOPE",
                "approval_nonce":w["payload"]["strategy_id"],
            } for w in self.work
        }

    def build(self):
        return create_permitted_core_test_cohort(
            self.root,self.vault,self.work,self.actions)

    def test_positive_permitted_symbol_immutable_core_and_canonical_replay(self):
        cohort=self.build()
        self.assertEqual(cohort,self.build())
        self.assertEqual(cohort["warehouse"]["symbol"],SOURCE_SYMBOL)
        self.assertEqual(cohort["warehouse"]["interval"],"15m")
        self.assertNotEqual(cohort["scanner_raw_sha256"],cohort["source_zip_sha256"])
        self.assertNotEqual(cohort["core_245_price_query_sha256"],
                            cohort["core_253_query_local_sha256"])
        self.assertEqual(cohort["factory_lab_execution"],"NOT_PERFORMED")
        self.assertEqual(cohort["trading_authority"],"NONE")
        self.assertEqual(cohort["historical_known_at_ms"],None)
        self.assertTrue(all(x in ("SELECTED","REJECTED","UNKNOWN")
                            for x in cohort["scanner_nomination_statuses"]))
        service=Frozen.restore(
            cohort["scanner_d_handoff"]["payload"]["scanner_c_canonical_service_receipt"]).data
        self.assertEqual(service["total_attempts"],2)
        self.assertEqual(service["symbol_denominator"],1)
        self.assertEqual(service["strategy_count"],2)
        for x in service["strategy_route_requests"]:
            self.assertEqual(Frozen.restore(x).data["trading_authority"],"NONE")
        found=False
        for i,route in enumerate(service["strategy_route_requests"]):
            candidate=Frozen.restore(route).data
            if candidate["strategy_route_status"]!="ROUTE_CANDIDATE_TEST_ONLY":
                continue
            sid=candidate["strategy_id"]
            idx=next(j for j,w in enumerate(self.work)
                     if w["payload"]["strategy_id"]==sid)
            request=route
            approval=service["strategy_approvals"][idx]
            policy=service["native15m_policies"][idx]
            nomination=next(n for n in service["scanner_run"]["payload"]["nominations"]
                            if n["sha256"]==candidate["scanner_nomination_sha256"])
            receipt=verify_scanner_d_for_core_route(
                self.root,warehouse=cohort["warehouse"],
                native_price_query=cohort["native_price_query"],
                local_query=cohort["local_query"],
                identity_map=cohort["identity_map"],
                core_d_witness=cohort["core_d_issued_witness"],
                scanner_d_handoff=cohort["scanner_d_handoff"],
                scanner_c_request=request,scanner_c_approval=approval,
                scanner_run=service["scanner_run"],scanner_nomination=nomination,
                work_spec=self.work[idx],native_policy=policy)
            self.assertEqual(receipt["decision"],
                             "RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY")
            self.assertEqual(receipt["strategy_secretary_state"],"NOT_ENQUEUED")
            self.assertEqual(receipt["trading_authority"],"NONE")
            found=True
        self.assertTrue(found,"D_SAME_SOURCE_ALLOWED_POLICY_NOT_SELECTED")

    def test_wrong_explicit_policy_denies_route_without_paper(self):
        self.actions[next(iter(self.actions))]["action"]="DENY_TEST_ONLY"
        c=self.build()
        service=Frozen.restore(
            c["scanner_d_handoff"]["payload"]["scanner_c_canonical_service_receipt"]).data
        denied=[Frozen.restore(v).data for v in service["strategy_route_requests"]
                if Frozen.restore(v).data["strategy_governance_status"]=="DENIED_TEST_ONLY"]
        self.assertTrue(denied)
        self.assertTrue(all(z["strategy_route_status"]=="WAIT"
                            and z["trading_authority"]=="NONE"
                            for z in denied))

    def test_symbol_and_core_source_query_mismatch_fail_closed(self):
        c=self.build()
        service=Frozen.restore(
            c["scanner_d_handoff"]["payload"]["scanner_c_canonical_service_receipt"]).data
        self.assertEqual(len(service["strategy_route_requests"]),2)
        wrong=deepcopy(c["core_d_issued_witness"])
        wrong["payload"]["symbol"]="BTCUSDT"
        with self.assertRaises(ValueError):
            from tools.scanner_strategy_d.core_query_adapter import _project
            _project(self.root,c["warehouse"],c["native_price_query"],
                c["local_query"],c["identity_map"],wrong)
        bad=deepcopy(c["local_query"])
        bad["query_sha256"]="0"*64
        with self.assertRaises(ValueError):
            from tools.scanner_strategy_d.core_query_adapter import _project
            _project(self.root,c["warehouse"],c["native_price_query"],
                bad,c["identity_map"],c["core_d_issued_witness"])

if __name__=="__main__":
    unittest.main()
