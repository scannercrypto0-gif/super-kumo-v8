"""Core D permitted-symbol end-to-end source→Scanner positive software probe."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_d.core_query_adapter import scan_same_core_source
from research_wp_r0.aql_core_d_permitted_cohort_v1 import create_permitted_synthetic_cohort
from research_wp_r0.aql_core_d_same_source_route_v1 import verify_scanner_d_for_core_route


class PermittedSameSourceCoreD(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"core"
        self.raw=Path(self.tmp.name)/"raw"
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.c=create_permitted_synthetic_cohort(self.root,self.raw,self.work)
        self.actions={
            (w["payload"]["strategy_id"],w["payload"]["strategy_version"]):{
                "action":"APPROVE_TEST_ONLY",
                "governance_policy_id":"ATLAS_D_ONLY",
                "approver_id":"explicit_research_test",
                "approval_nonce":w["payload"]["strategy_id"],
            } for w in self.work
        }
        c=self.c
        self.produced=scan_same_core_source(
            self.root,c["warehouse"],c["native"],c["local"],
            c["mapping"],c["witness"],self.work,
            governance_actions=self.actions,symbol_budget=1)
        self.service=Frozen.restore(
            self.produced.data["scanner_c_canonical_service_receipt"]).data

    def gate(self,index=0,**kwargs):
        c=self.c
        d=self.service
        r=Frozen.restore(d["strategy_route_requests"][index]).data
        si=next(i for i,p in enumerate(d["native15m_policies"])
                if p["payload"]["strategy_id"]==r["strategy_id"])
        n=next(q for q in d["scanner_run"]["payload"]["nominations"]
               if q["sha256"]==r["scanner_nomination_sha256"])
        args=dict(core_root=self.root,warehouse=c["warehouse"],
            native_price_query=c["native"],local_query=c["local"],
            identity_map=c["mapping"],core_d_witness=c["witness"],
            scanner_d_handoff=self.produced.receipt(),
            scanner_c_request=d["strategy_route_requests"][index],
            scanner_c_approval=d["strategy_approvals"][si],
            scanner_run=d["scanner_run"],scanner_nomination=n,
            work_spec=self.work[si],native_policy=d["native15m_policies"][si])
        args.update(kwargs)
        return verify_scanner_d_for_core_route(**args)

    def test_policy_permitted_symbol_source_dual_sha_and_replay(self):
        self.assertEqual(self.c["receipt"]["symbol"],"AAA")
        self.assertEqual(self.c["receipt"]["source_bars"],8)
        self.assertNotEqual(self.c["receipt"]["core_245_price_query_sha256"],
                            self.c["receipt"]["core_253_query_local_sha256"])
        self.assertEqual(self.c["warehouse"]["symbol"],"AAA")
        self.assertEqual(self.produced.data["source_binding_status"],
                         "CORE_QUERY_TO_SCANNER_BYTES_VERIFIED_SOFTWARE_ONLY")
        self.assertEqual(self.service["total_attempts"],2)
        statuses=[Frozen.restore(r).data["scanner_nomination_status"] for r in self.service["strategy_route_requests"]]
        self.assertTrue(all(x in ("SELECTED","REJECTED","UNKNOWN","INELIGIBLE","UNSCANNED","FAILED") for x in statuses))
        self.assertIn("SELECTED",statuses)
        for n in range(2):
            x=self.gate(n)
            self.assertEqual(x,self.gate(n))
            self.assertEqual(x["historical_pit"],"NOT_ATTESTED")
            self.assertEqual(x["trading_authority"],"NONE")
            self.assertEqual(x["orders_created"],0)

    def test_wrong_policy_symbol_is_rejected_before_source(self):
        with self.assertRaisesRegex(ValueError,"CORE_D_COHORT_FROZEN_WORK_POLICY_SYMBOL"):
            create_permitted_synthetic_cohort(
                Path(self.tmp.name)/"bad",Path(self.tmp.name)/"raw2",
                self.work,symbol="BTCUSDT")

    def test_mutated_canonical_request_denied(self):
        bad=deepcopy(self.service["strategy_route_requests"][0])
        bad["payload"]["source_raw_sha256"]="0"*64
        bad=Frozen.build(bad["payload"]).receipt()
        with self.assertRaises(ValueError):
            self.gate(0,scanner_c_request=bad)

    def test_synthetic_clock_missing_denied(self):
        bad=deepcopy(self.c["witness"])
        bad["payload"]["synthetic_available_at_ms_by_bar"]=[]
        with self.assertRaises(ValueError):
            self.gate(0,core_d_witness=Frozen.build(bad["payload"]).receipt())


if __name__=="__main__":
    unittest.main()
