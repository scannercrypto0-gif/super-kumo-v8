"""Scanner F3: independently pending historical NON_PIT policy and source trust gates."""
from __future__ import annotations
import copy
import json
import unittest
from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import (
    MONTHS,create_retrospective_policy_draft,verify_retrospective_policy_draft,
    historical_route_gate,
)

class ScannerF3Policy(unittest.TestCase):
    def setUp(self):
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.original=copy.deepcopy(self.work)
        self.proposal=propose_historical_research_policy(self.work)
        self.request=prepare_historical_policy_approval_request(self.proposal,self.work)
        self.policy=create_retrospective_policy_draft(self.proposal,self.request,self.work)

    def test_full_year_scope_determinism_exact_strategy_no_work235_mutation(self):
        self.assertEqual(self.policy,create_retrospective_policy_draft(
            self.proposal,self.request,self.work))
        p=verify_retrospective_policy_draft(
            self.policy,self.proposal,self.request,self.work).data
        self.assertEqual(self.work,self.original)
        self.assertEqual(p["target_months"],list(MONTHS))
        self.assertEqual(p["symbol"],"BTCUSDT")
        self.assertEqual(p["timeframe"],"15m")
        self.assertEqual(p["historical_pit"],"NOT_ATTESTED")
        self.assertEqual(p["policy_status"],
                         "DRAFT_PENDING_INDEPENDENT_OWNER_APPROVAL")
        self.assertEqual(len(p["strategy_identity"]),2)
        self.assertTrue(all(not x["source_policy_inherited"]
                            for x in p["strategy_identity"]))
        self.assertIsNone(p["independent_owner_approval_receipt_sha256"])
        self.assertIsNone(p["independent_source_authority_sha256"])

    def test_bounded_partial_months_and_bad_scope_deny(self):
        for months in (("2024-02","2024-08"),("2024-09",)):
            r=create_retrospective_policy_draft(
                self.proposal,self.request,self.work,target_months=months)
            self.assertEqual(
                verify_retrospective_policy_draft(
                    r,self.proposal,self.request,self.work).data["target_months"],
                sorted(months))
        for months in ((),("2024-02","2024-02"),("2025-01",),
                       ("2024-01",None)):
            with self.assertRaises(ValueError):
                create_retrospective_policy_draft(
                    self.proposal,self.request,self.work,target_months=months)

    def test_forged_resigned_owner_approval_source_and_pit_denied(self):
        for patch in (
            {"policy_status":"APPROVED"},
            {"independent_owner_approval_receipt_sha256":"a"*64},
            {"independent_source_authority_sha256":"b"*64},
            {"historical_pit":"ATTESTED"},
            {"strategy_route_status":"SELECTED"},
            {"trading_authority":"PAPER"},
            {"symbol":"ETHUSDT"},
            {"target_months":["2024-01","2024-01"]},
        ):
            with self.subTest(patch=patch):
                tampered=copy.deepcopy(self.policy["payload"])
                tampered.update(patch)
                with self.assertRaises(ValueError):
                    verify_retrospective_policy_draft(
                        Frozen.build(tampered).receipt(),
                        self.proposal,self.request,self.work)

    def test_wrong_config_strategy_identity_and_untrusted_source_denied(self):
        other=copy.deepcopy(self.work)
        other[0]["payload"]["strategy_id"]="swapped"
        with self.assertRaises(ValueError):
            verify_retrospective_policy_draft(
                self.policy,self.proposal,self.request,other)
        tampered=copy.deepcopy(self.policy["payload"])
        tampered["strategy_identity"][0]["dna_digest"]="f"*64
        with self.assertRaises(ValueError):
            verify_retrospective_policy_draft(
                Frozen.build(tampered).receipt(),
                self.proposal,self.request,self.work)
        for arg in ("core_source_authentication","owner_policy_approval",
                    "core_245_query","core_253_query","source_ack"):
            with self.subTest(arg=arg),self.assertRaises(ValueError):
                historical_route_gate(
                    self.policy,self.proposal,self.request,self.work,
                    **{arg:{"sha256":"f"*64}})

    def test_pending_cannot_enqueue_secretary_or_factory(self):
        a=historical_route_gate(
            self.policy,self.proposal,self.request,self.work)
        self.assertEqual(a,historical_route_gate(
            self.policy,self.proposal,self.request,self.work))
        d=Frozen.restore(a).data
        self.assertEqual(d["decision"],
                         "WAIT_SOURCE_AND_INDEPENDENT_OWNER_APPROVAL")
        self.assertEqual(d["research_scope"],"RETROSPECTIVE_NON_PIT")
        self.assertEqual(d["strategy_secretary_state"],"NOT_ENQUEUED")
        self.assertIsNone(d["factory_consumer_ack"])
        self.assertEqual(d["trading_authority"],"NONE")

if __name__=="__main__":
    unittest.main()
