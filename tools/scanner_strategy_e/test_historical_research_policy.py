"""Scanner E separate historical-policy proposal and full frozen identity tests."""
from __future__ import annotations

import copy
import json
import unittest

from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_e.historical_research_policy import (
    propose_historical_research_policy,validate_historical_policy_proposal)


class HistoricalResearchPolicyProposal(unittest.TestCase):
    def setUp(self):
        self.work=json.loads((FIXTURES/"strategies.json").read_text())

    def test_deterministic_v1_policy_is_not_a_work235_mutation_or_approval(self):
        before=copy.deepcopy(self.work)
        receipt=propose_historical_research_policy(self.work)
        data=validate_historical_policy_proposal(receipt,self.work).data
        self.assertEqual(self.work,before)
        self.assertEqual(receipt,propose_historical_research_policy(self.work))
        self.assertEqual(data["policy_version"],"historical-research-v1")
        self.assertEqual(data["target_symbols"],["BTCUSDT"])
        self.assertEqual(data["policy_status"],"PROPOSED_NOT_APPROVED")
        self.assertIsNone(data["independent_approval_receipt_sha256"])
        self.assertIsNone(data["actual_historical_source_receipt_sha256"])
        self.assertEqual(data["historical_route_status"],"WAIT")
        self.assertEqual(data["strategy_secretary_state"],"NOT_ENQUEUED")
        self.assertEqual(data["trading_authority"],"NONE")
        self.assertEqual(len(data["strategies"]),len(self.work))
        for x in data["strategies"]:
            self.assertFalse(x["source_policy_dna_is_inherited"])
            self.assertNotEqual(x["work235_config_digest"],
                                x["scanner_native15m_config_digest"])

    def test_resealed_or_raw_tampered_promotion_fail_closed(self):
        a=propose_historical_research_policy(self.work)
        for change in (
            {"policy_status":"APPROVED"},
            {"historical_pit":"ATTESTED"},
            {"independent_approval_receipt_sha256":"f"*64},
            {"strategy_secretary_state":"ACKED_CONSUMER"},
            {"trading_authority":"LIVE"},
            {"target_symbols":["ETHUSDT"]},
        ):
            with self.subTest(change=change):
                fake=copy.deepcopy(a)
                fake["payload"].update(change)
                with self.assertRaises(ValueError):
                    validate_historical_policy_proposal(fake,self.work)
                resealed=Frozen.build(fake["payload"]).receipt()
                with self.assertRaises(ValueError):
                    validate_historical_policy_proposal(resealed,self.work)

    def test_wrong_strategy_definition_and_config_replay_denied(self):
        receipt=propose_historical_research_policy(self.work)
        malformed=copy.deepcopy(receipt)
        malformed["payload"]["strategies"][0]["work235_config_digest"]="f"*64
        with self.assertRaises(ValueError):
            validate_historical_policy_proposal(
                Frozen.build(malformed["payload"]).receipt(),self.work)
        other=copy.deepcopy(self.work)
        other[0]["payload"]["strategy_id"]="swapped"
        with self.assertRaises(ValueError):
            validate_historical_policy_proposal(receipt,other)

    def test_external_approval_never_minted_from_proposal(self):
        with self.assertRaises(ValueError):
            propose_historical_research_policy(
                self.work,authorization_evidence={"signed":True})
        with self.assertRaises(ValueError):
            propose_historical_research_policy(
                self.work,target_symbols=["BTCUSDT","BTCUSDT"])
        with self.assertRaises(ValueError):
            propose_historical_research_policy(
                self.work,market="fixture")
        with self.assertRaises(ValueError):
            propose_historical_research_policy(
                self.work,policy_version="operational")

if __name__=="__main__":
    unittest.main()
