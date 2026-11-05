"""Package C focused new-delta tests: no Bundle B suite retest."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_b.native15m import native_15m_policy
from tools.scanner_strategy_b.test_integration import Native15mGate
from .approval_route import (
    explicit_test_only_approval, verify_test_only_approval,
    seal_strategy_route_request, verify_strategy_route_request,
    no_operational_paper,
)
from .service import scan_and_prepare_test_only_routes


class ScannerCContractGate(unittest.TestCase):
    def setUp(self):
        fixture = Native15mGate(methodName="test_all_strategy_symbol_pairs_and_safety")
        fixture.setUp()
        self.fixture = fixture
        self.specs = fixture.work
        self.policies = fixture.policies
        self.run = fixture.run_scan()
        self.rows = [Frozen.restore(x).data for x in self.run.data["nominations"]]
        self.selected = next(x for x in self.run.data["nominations"]
                             if x["payload"]["status"] == "SELECTED")
        self.work, self.native = next((w, p) for p, w in zip(self.policies, self.specs)
                                      if p["payload"]["strategy_id"] == self.selected["payload"]["strategy_id"])
        self.actions = dict(action="APPROVE_TEST_ONLY", governance_policy_id="ATLAS_TEST_POLICY_C",
                            approver_id="officer_test", approval_nonce="C-001")
        self.pins = dict(source_custody_receipt_sha256="a"*64,
                         core245_price_query_sha256="b"*64,
                         core253_query_local_sha256="c"*64,
                         source_zip_sha256="d"*64,
                         source_custody_status="TEST_ONLY_ATTESTED")
        self.approval = self.approve()
        self.route = self.make_route()

    def approve(self, **override):
        return explicit_test_only_approval(
            self.work, self.native, **{**self.actions, **override})

    def make_route(self, **override):
        return seal_strategy_route_request(
            self.work, self.native, self.approval.receipt(),
            self.run.receipt(), self.selected,
            **{**self.pins, **override})

    def test_explicit_approval_and_approved_route_are_separate_seals(self):
        a, route = self.approval.data, self.route.data
        self.assertEqual(a["decision"], "APPROVED_TEST_ONLY")
        self.assertNotEqual(self.approval.sha256, self.route.sha256)
        self.assertEqual(route["strategy_governance_status"], "APPROVED_TEST_ONLY")
        self.assertEqual(route["scanner_nomination_status"], "SELECTED")
        self.assertEqual(route["scanner_operational_status"], "UNKNOWN")
        self.assertEqual(route["strategy_route_status"], "ROUTE_CANDIDATE_TEST_ONLY")
        self.assertEqual(route["strategy_secretary_status"], "NOT_ENQUEUED")
        self.assertFalse(route["source_secretary_ack_is_strategy_approval"])
        self.assertEqual(route["core245_price_query_sha256"], self.pins["core245_price_query_sha256"])
        self.assertEqual(route["core253_query_local_sha256"], self.pins["core253_query_local_sha256"])
        self.assertEqual(route["denominator"], 5)
        self.assertEqual(sum(route["strategy_census"].values()), 5)
        self.assertEqual(route["trading_authority"], "NONE")
        self.assertEqual(no_operational_paper(self.route.receipt()).data["decision"], "WAIT")
        self.assertEqual(self.route.payload, self.make_route().payload)
        self.assertEqual(verify_strategy_route_request(
            self.route.receipt(), self.work, self.native, self.approval.receipt(),
            self.run.receipt(), self.selected,
            source_custody_receipt_sha256="a"*64,
            core245_price_query_sha256="b"*64,
            core253_query_local_sha256="c"*64,
            source_zip_sha256="d"*64).sha256, self.route.sha256)

    def test_denied_and_no_selected_never_candidate(self):
        denied = self.approve(action="DENY_TEST_ONLY").receipt()
        x = seal_strategy_route_request(
            self.work, self.native, denied, self.run.receipt(), self.selected, **self.pins).data
        self.assertEqual(x["strategy_route_status"], "WAIT")
        self.assertEqual(x["strategy_governance_status"], "DENIED_TEST_ONLY")
        nonselected = next(x for x in self.run.data["nominations"]
                           if x["payload"]["strategy_id"] == self.selected["payload"]["strategy_id"]
                           and x["payload"]["status"] != "SELECTED")
        y = seal_strategy_route_request(
            self.work, self.native, self.approval.receipt(), self.run.receipt(), nonselected, **self.pins).data
        self.assertEqual(y["strategy_route_status"], "WAIT")

    def test_no_inferred_approval_from_core_ack_or_scanner_selection(self):
        with self.assertRaisesRegex(ValueError, "EXPLICIT_GOVERNANCE_ACTION_REQUIRED"):
            self.approve(action="ACKED_SOURCE_ONLY")
        with self.assertRaisesRegex(ValueError, "EXPLICIT_GOVERNANCE_ACTION_REQUIRED"):
            self.approve(action="SELECTED")
        with self.assertRaisesRegex(ValueError, "EXPLICIT_GOVERNANCE_ACTION_REQUIRED"):
            self.approve(action=None)

    def test_policy_config_version_and_approval_receipt_tamper(self):
        other_work = next(w for w in self.specs if w["payload"]["strategy_id"] != self.selected["payload"]["strategy_id"])
        with self.assertRaises(ValueError):
            verify_test_only_approval(self.approval.receipt(), other_work, self.native)
        changed = deepcopy(self.approval.receipt())
        changed["payload"]["decision"] = "APPROVED_OPERATIONAL"
        changed = Frozen.build(changed["payload"]).receipt()
        with self.assertRaisesRegex(ValueError, "APPROVAL_ACTION_SEAL_DRIFT"):
            verify_test_only_approval(changed, self.work, self.native)

    def test_alias_sha_and_missing_pit_refuse_route_promotion(self):
        with self.assertRaisesRegex(ValueError, "CORE_QUERY_SHA_DOMAINS_ALIASED"):
            self.make_route(core253_query_local_sha256="b"*64)
        with self.assertRaisesRegex(ValueError, "HISTORICAL_KNOWN_AT_NOT_ATTESTED"):
            seal_strategy_route_request(
                self.work, self.native, self.approval.receipt(),
                self.run.receipt(), self.selected,
                historical_known_at_ms=42, **self.pins)

    def test_mismatched_strategy_source_timeframe_and_cutoff_rejected(self):
        changed = deepcopy(self.selected)
        changed["payload"]["timeframe"] = "5m"
        changed = Frozen.build(changed["payload"]).receipt()
        with self.assertRaisesRegex(ValueError, "SCANNER_C_NOMINATION_PARENT"):
            seal_strategy_route_request(
                self.work, self.native, self.approval.receipt(),
                self.run.receipt(), changed, **self.pins)
        changed = deepcopy(self.selected)
        changed["payload"]["cutoff_ms"] += 900_000
        changed = Frozen.build(changed["payload"]).receipt()
        with self.assertRaisesRegex(ValueError, "SCANNER_C_NOMINATION_PARENT"):
            seal_strategy_route_request(
                self.work, self.native, self.approval.receipt(),
                self.run.receipt(), changed, **self.pins)
        with self.assertRaisesRegex(ValueError, "SOURCE_OR_SECRETARY_STATUS_AUTHORITY"):
            seal_strategy_route_request(
                self.work, self.native, self.approval.receipt(), self.run.receipt(),
                self.selected, strategy_secretary_status="ACKED", **self.pins)

    def test_historical_retrospective_not_test_candidate(self):
        x = self.make_route(source_custody_status="RETROSPECTIVE_NON_PIT").data
        self.assertEqual(x["strategy_route_status"], "WAIT")
        self.assertIsNone(x["historical_known_at_ms"])
        self.assertEqual(x["paper_authority"], "NONE")

    def test_resealed_forgery_of_route_never_passes_independent_parent_recompute(self):
        forged = deepcopy(self.route.receipt())
        forged["payload"]["strategy_route_status"] = "PAPER_APPROVED"
        forged = Frozen.build(forged["payload"]).receipt()
        with self.assertRaisesRegex(ValueError, "STRATEGY_ROUTE_PARENT_DRIFT"):
            verify_strategy_route_request(
                forged, self.work, self.native, self.approval.receipt(), self.run.receipt(),
                self.selected,
                source_custody_receipt_sha256="a"*64,
                core245_price_query_sha256="b"*64,
                core253_query_local_sha256="c"*64, source_zip_sha256="d"*64)

    def test_replay_determinism_and_universe_denominator_two_strategies(self):
        governance = {
            (p["payload"]["strategy_id"], p["payload"]["strategy_version"]):
            dict(self.actions, approval_nonce=p["payload"]["strategy_id"])
            for p in self.policies
        }
        bundled = scan_and_prepare_test_only_routes(
            self.specs, self.fixture.raw, self.fixture.manifest, self.fixture.universe,
            cutoff_ms=self.fixture.cutoff, symbol_budget=3,
            governance_actions=governance, core_query_pins=self.pins)
        self.assertEqual(bundled.data["total_attempts"], 10)
        self.assertEqual(bundled.data["strategy_count"], 2)
        self.assertEqual(bundled.data["symbol_denominator"], 5)
        self.assertEqual(len(bundled.data["strategy_route_requests"]), 10)
        self.assertEqual(len(bundled.data["strategy_approvals"]), 2)
        self.assertEqual(bundled.data["strategy_secretary_integration"],
                         "NOT_CONNECTED_CORE_C_REQUIRED")
        self.assertTrue(all(Frozen.restore(x).data["trading_authority"] == "NONE"
                            for x in bundled.data["strategy_route_requests"]))
        again = scan_and_prepare_test_only_routes(
            self.specs, self.fixture.raw, self.fixture.manifest, self.fixture.universe,
            cutoff_ms=self.fixture.cutoff, symbol_budget=3,
            governance_actions=governance, core_query_pins=self.pins)
        self.assertEqual(bundled.payload, again.payload)

    def test_service_refuses_unapproved_or_duplicate_governance_action(self):
        good = {(p["payload"]["strategy_id"], p["payload"]["strategy_version"]):
                dict(self.actions) for p in self.policies}
        good.pop(next(iter(good)))
        with self.assertRaisesRegex(ValueError, "C_EXACT_GOVERNANCE_ACTION_SET"):
            scan_and_prepare_test_only_routes(
                self.specs, self.fixture.raw, self.fixture.manifest, self.fixture.universe,
                cutoff_ms=self.fixture.cutoff, symbol_budget=3,
                governance_actions=good, core_query_pins=self.pins)

if __name__ == "__main__":
    unittest.main()
