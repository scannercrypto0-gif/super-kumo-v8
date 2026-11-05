"""Package D positive same-source software receipt and fail-closed negatives.

Actual Core immutable #211/#245/#253 query + Scanner D producer, synthetic
source only; never re-runs accepted real Feb/Aug or Bundle B gate.
"""
from copy import deepcopy
import unittest

from research_wp_r0.aql_core_d_same_source_witness_v1 import create_core_d_research_witness
from research_wp_r0.aql_core_d_same_source_route_v1 import verify_scanner_d_for_core_route
from tools.scanner_strategy_d.test_same_source import ScannerDReadOnlyCoreSource
from tools.scanner_strategy_d.core_query_adapter import scan_same_core_source
from tools.strategy_service_offline.common import Frozen


class CoreDSharedSource(unittest.TestCase):
    def setUp(self):
        self.fixture=ScannerDReadOnlyCoreSource(
            methodName="test_positive_actual_core_245_253_source_query_replay_and_full_census")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        x=self.fixture
        self.issued=create_core_d_research_witness(
            x.core.root,x.warehouse,x.native,x.local,x.mapping,
            scanner_source_id=x.witness_body["scanner_source_id"],
            scanner_generation_id=x.witness_body["scanner_generation_id"],
            scanner_market=x.witness_body["scanner_market"],
            synthetic_available_at_ms_by_bar=x.witness_body["synthetic_available_at_ms_by_bar"],
            research_universe_members=x.witness_body["research_universe_members"])
        self.produced=scan_same_core_source(
            x.core.root,x.warehouse,x.native,x.local,x.mapping,
            self.issued,x.work,governance_actions=x.actions,symbol_budget=1)
        self.service=Frozen.restore(
            self.produced.data["scanner_c_canonical_service_receipt"]).data
        self.req=self.service["strategy_route_requests"][0]
        self.appr=self.service["strategy_approvals"][0]
        self.nom=self.service["scanner_run"]["payload"]["nominations"][0]
        self.policy=self.service["native15m_policies"][0]

    def verify(self,**over):
        f=self.fixture
        args=dict(core_root=f.core.root,warehouse=f.warehouse,
             native_price_query=f.native,local_query=f.local,
             identity_map=f.mapping,core_d_witness=self.issued,
             scanner_d_handoff=self.produced.receipt(),
             scanner_c_request=self.req,scanner_c_approval=self.appr,
             scanner_run=self.service["scanner_run"],scanner_nomination=self.nom,
             work_spec=f.work[0],native_policy=self.policy)
        args.update(over)
        return verify_scanner_d_for_core_route(**args)

    def test_issued_witness_exact_scanner_consumed_bytes_replay(self):
        self.assertEqual(self.issued,self.issued)
        self.assertEqual(self.issued["payload"]["source_authority"],
                         "TEST_ONLY_NOT_PUBLISHER_ATTESTED")
        self.assertEqual(self.issued["payload"]["historical_known_at_ms"],None)
        got=self.verify()
        self.assertEqual(got,self.verify())
        self.assertEqual(got["decision"],"WAIT")
        self.assertEqual(got["reason"],"WAIT_STRATEGY_POLICY_OR_UNIVERSE_INELIGIBLE")
        self.assertEqual(got["strategy_secretary_state"],"NOT_ENQUEUED")
        self.assertEqual(got["scanner_raw_sha256"],self.produced.data["scanner_raw_sha256"])
        self.assertEqual(got["core_245_price_query_sha256"],self.fixture.native["price_query_sha256"])
        self.assertEqual(got["core_253_query_local_sha256"],self.fixture.local["query_sha256"])
        self.assertNotEqual(got["source_zip_sha256"],got["scanner_raw_sha256"])
        self.assertEqual(got["orders_created"],0)

    def test_resealed_wrong_clock_is_denied(self):
        f=self.fixture
        bad=deepcopy(f.witness_body)
        bad["synthetic_available_at_ms_by_bar"][0]["bar_checksum"]="0"*64
        with self.assertRaisesRegex(ValueError,"CORE_D_SYNTHETIC_CLOCK_BAR_OR_KNOWN_AT_DRIFT"):
            create_core_d_research_witness(
                f.core.root,f.warehouse,f.native,f.local,f.mapping,
                scanner_source_id=bad["scanner_source_id"],
                scanner_generation_id=bad["scanner_generation_id"],
                scanner_market=bad["scanner_market"],
                synthetic_available_at_ms_by_bar=bad["synthetic_available_at_ms_by_bar"],
                research_universe_members=bad["research_universe_members"])

    def test_wrong_handoff_and_nomination_denied(self):
        bad=deepcopy(self.produced.receipt())
        bad["payload"]["scanner_raw_sha256"]="0"*64
        bad=Frozen.build(bad["payload"]).receipt()
        with self.assertRaises(ValueError):
            self.verify(scanner_d_handoff=bad)
        with self.assertRaises(ValueError):
            self.verify(scanner_c_request=self.service["strategy_route_requests"][1])

    def test_unrelated_historical_scanner_json_never_promoted(self):
        self.assertEqual(self.verify()["trading_authority"],"NONE")
        self.assertEqual(self.verify()["historical_pit"],"NOT_ATTESTED")


if __name__=="__main__":
    unittest.main()
