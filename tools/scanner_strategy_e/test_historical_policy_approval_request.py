"""Historical #273 owner approval request: no self-authorization or source/PIT promotion."""
from __future__ import annotations

import copy
import json
import unittest
from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_e.historical_research_policy import (
    propose_historical_research_policy,
)
from tools.scanner_strategy_e.historical_policy_approval_request import (
    prepare_historical_policy_approval_request,
    verify_historical_policy_approval_request,
)


class ScannerEPolicyOwnerApprovalRequest(unittest.TestCase):
    def setUp(self):
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.policy=propose_historical_research_policy(self.work)

    def test_sealed_owner_review_ticket_exact_strategy_scope_and_replay(self):
        request=prepare_historical_policy_approval_request(self.policy,self.work)
        record=verify_historical_policy_approval_request(
            request,self.policy,self.work).data
        self.assertEqual(request,prepare_historical_policy_approval_request(
            self.policy,self.work))
        self.assertEqual(record["governance_issue"],"273")
        self.assertEqual(record["policy_proposal_sha256"],self.policy["sha256"])
        self.assertEqual(record["target_symbols"],["BTCUSDT"])
        self.assertEqual(record["policy_approval_status"],"PENDING_INDEPENDENT_OWNER")
        self.assertEqual(record["core_secretary_historical_route"],"NOT_AUTHORIZED")
        self.assertEqual(record["factory_historical_lab"],"NOT_AUTHORIZED")
        self.assertIsNone(record["source_authentication_receipt_sha256"])
        self.assertIsNone(record["issuer_known_at_receipt_sha256"])
        self.assertIsNone(record["independent_policy_approval_receipt_sha256"])
        self.assertEqual(record["trading_authority"],"NONE")

    def test_untrusted_self_attested_source_and_pit_rejected(self):
        for argument in (
            {"source_authentication_receipt":{"claimed":"publisher"}},
            {"core_245_query_receipt":{"price_query_sha256":"a"*64}},
            {"core_253_query_receipt":{"query_sha256":"b"*64}},
            {"issuer_historical_known_at_receipt":{"available_at":1}},
        ):
            with self.subTest(argument=argument),self.assertRaises(ValueError):
                prepare_historical_policy_approval_request(
                    self.policy,self.work,**argument)

    def test_forged_resigned_independent_owner_approval_or_scope_denied(self):
        original=prepare_historical_policy_approval_request(
            self.policy,self.work)
        for patch in (
            {"policy_approval_status":"APPROVED"},
            {"source_authorization":"ATTESTED"},
            {"issuer_known_at_status":"ATTESTED"},
            {"historical_pit":"ATTESTED"},
            {"independent_policy_approval_receipt_sha256":"f"*64},
            {"core_secretary_historical_route":"ACKED"},
            {"factory_historical_lab":"AUTHORIZED"},
            {"trading_authority":"PAPER"},
            {"owner_review_ticket":"untrusted"},
            {"target_symbols":["ETHUSDT"]},
        ):
            with self.subTest(patch=patch):
                forged=copy.deepcopy(original["payload"])
                forged.update(patch)
                with self.assertRaises(ValueError):
                    verify_historical_policy_approval_request(
                        Frozen.build(forged).receipt(),self.policy,self.work)

    def test_bad_policy_and_wrong_frozen_config_fail(self):
        with self.assertRaises(ValueError):
            prepare_historical_policy_approval_request(
                self.policy,self.work,owner_review_ticket="fake")
        changed=copy.deepcopy(self.work)
        changed[0]["payload"]["market"]="not_fixture"
        with self.assertRaises(ValueError):
            prepare_historical_policy_approval_request(
                self.policy,changed)
        forged=copy.deepcopy(self.policy["payload"])
        forged["target_symbols"]=["ETHUSDT"]
        with self.assertRaises(ValueError):
            prepare_historical_policy_approval_request(
                Frozen.build(forged).receipt(),self.work)


if __name__=="__main__":
    unittest.main()
