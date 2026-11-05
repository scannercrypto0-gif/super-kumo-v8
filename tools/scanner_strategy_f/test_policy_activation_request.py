"""F3 owner-policy request exact scope/immutable receipt replay and tamper tests."""
from __future__ import annotations
import copy
import json
import unittest
from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from tools.scanner_strategy_f.policy_activation_request import (
    REQUIRED_OWNER_FIELDS, make_historical_activation_request,
    verify_historical_activation_request,
)


class ScannerF3OwnerActivationRequest(unittest.TestCase):
    def setUp(self):
        self.specs=json.loads((FIXTURES/"strategies.json").read_text())
        self.e=propose_historical_research_policy(self.specs)
        self.er=prepare_historical_policy_approval_request(self.e,self.specs)
        self.f=create_retrospective_policy_draft(self.e,self.er,self.specs)

    def call(self,**args):
        kw=dict(policy_draft=self.f,proposal=self.e,request=self.er,
                work_specs=self.specs)
        kw.update(args)
        return make_historical_activation_request(**kw)

    def test_exact_scope_hash_and_replay(self):
        a=self.call()
        self.assertEqual(a,self.call())
        data=verify_historical_activation_request(
            a,self.f,self.e,self.er,self.specs).data
        s=data["scope"]
        self.assertEqual(s["policy_id"],"btc-spot-15m-retrospective-non-pit-v1")
        self.assertEqual(s["policy_draft_sha256"],self.f["sha256"])
        self.assertEqual(s["approved_symbol"],"BTCUSDT")
        self.assertEqual(s["approved_timeframe"],"15m")
        self.assertEqual(s["approved_market"],"BINANCE:SPOT:USDT")
        self.assertEqual(s["historical_pit"],"NOT_ATTESTED")
        self.assertEqual(s["evidence_class"],"RETROSPECTIVE_NON_PIT")
        self.assertEqual(data["owner_decision"],"PROVISIONAL_CONDITIONAL_A_DORMANT")
        self.assertEqual(data["request_status"],"PENDING_INDEPENDENT_APPROVAL")
        self.assertFalse(data["independent_approval_verified"])
        self.assertIsNone(data["independent_owner_approval_receipt_sha256"])
        self.assertEqual(tuple(data["required_owner_receipt_fields"]),REQUIRED_OWNER_FIELDS)
        self.assertEqual(data["historical_route_status"],
                         "WAIT_SOURCE_AND_INDEPENDENT_OWNER_APPROVAL")
        self.assertEqual(len(data["strategy_identity"]),len(self.specs))

    def test_resealed_and_unsealed_approval_pit_or_source_forgery_rejected(self):
        a=self.call()
        for field,value in (
            ("request_status","APPROVED"),
            ("owner_decision","APPROVED"),
            ("independent_approval_verified",True),
            ("independent_owner_approval_receipt_sha256","f"*64),
            ("source_authentication_verified",True),
            ("core_f2_raw_warehouse_query_receipt_sha256","f"*64),
            ("historical_route_status","SELECTED"),
            ("secretary_state","ACKED_CONSUMER"),
            ("factory_lab","EVALUATED"),
            ("paper_execution","ACTIVE"),
            ("holdout_access",True),
            ("orders",1),
        ):
            with self.subTest(field=field):
                changed=copy.deepcopy(a)
                changed["payload"][field]=value
                with self.assertRaises(ValueError):
                    verify_historical_activation_request(
                        changed,self.f,self.e,self.er,self.specs)
                with self.assertRaises(ValueError):
                    verify_historical_activation_request(
                        Frozen.build(changed["payload"]).receipt(),
                        self.f,self.e,self.er,self.specs)

    def test_resealed_scope_parent_cutoff_strategy_config_denied(self):
        a=self.call()
        for field,value in (
            ("policy_draft_sha256","e"*64),
            ("approved_symbol","ETHUSDT"),
            ("approved_timeframe","1m"),
            ("cutoff_rule","USE_FUTURE_BAR"),
            ("historical_pit","ATTESTED"),
            ("evidence_class","PIT"),
            ("source_gate","ACCEPTED_PREFLIGHT_IS_SUFFICIENT"),
            ("strategy_identity_digest","f"*64),
        ):
            with self.subTest(field=field):
                changed=copy.deepcopy(a["payload"])
                changed["scope"][field]=value
                with self.assertRaises(ValueError):
                    verify_historical_activation_request(
                        Frozen.build(changed).receipt(),
                        self.f,self.e,self.er,self.specs)
        other=copy.deepcopy(self.specs)
        other[0]["payload"]["strategy_id"]="changed"
        with self.assertRaises(ValueError):
            self.call(work_specs=other)

    def test_request_not_private_approver_or_signature(self):
        d=Frozen.restore(self.call()).data
        self.assertNotIn("signature",d)
        self.assertNotIn("approver_identity",d)
        self.assertIn("signature",d["required_owner_receipt_fields"])
        self.assertEqual(d["trading_authority"] if "trading_authority" in d else
                         d["scope"]["trading_authority"],"NONE")
        self.assertEqual(d["positions"],0)
        self.assertIsNone(d["fills"])


if __name__=="__main__":
    unittest.main()
