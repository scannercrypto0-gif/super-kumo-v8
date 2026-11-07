"""Exact immutable research-only handoff retains separate Core/Factory ACK boundaries."""
from __future__ import annotations
import copy
import unittest
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.secretary_factory_handoff import (
    create_research_handoff,verify_research_handoff,
)
from tools.scanner_strategy_f.test_source_bound_intake import SourceBoundIntake


class SecretaryFactoryResearchHandoff(SourceBoundIntake):
    def test_handoff_is_exact_but_not_ack_or_strategy_selected(self):
        census=self.run_bridge()
        receipt=create_research_handoff(census)
        self.assertEqual(receipt,create_research_handoff(census))
        d=verify_research_handoff(receipt,census).data
        self.assertEqual(d["core_f2_report_sha256"],
                         Frozen.restore(census).data["core_f2_report_sha256"])
        self.assertEqual(d["source_verified_month_attempts"],20)
        self.assertEqual(d["retained_inventory_unknown_attempts"],4)
        self.assertEqual(d["research_strategy_selection"],
                         "PENDING_ACTUAL_ORIGINAL_BAR_EVALUATION")
        self.assertIsNone(d["source_ack_sha256"])
        self.assertIsNone(d["strategy_approval_sha256"])
        self.assertIsNone(d["factory_consumer_ack_sha256"])
        self.assertEqual(d["secretary_route"],"NOT_ENQUEUED")
        self.assertEqual(d["trading_authority"],"NONE")

    def test_signed_source_census_does_not_authorize_fake_strategy_ack(self):
        c=self.run_bridge()
        a=create_research_handoff(c)
        for key,val in (
            ("source_ack_sha256","f"*64),
            ("strategy_approval_sha256","e"*64),
            ("factory_consumer_ack_sha256","d"*64),
            ("research_strategy_selection","SELECTED"),
            ("secretary_route","ACKED"),
            ("factory_lab","EVALUATED"),
            ("trading_authority","PAPER"),
        ):
            with self.subTest(key=key):
                d=copy.deepcopy(a["payload"])
                d[key]=val
                with self.assertRaises(ValueError):
                    verify_research_handoff(Frozen.build(d).receipt(),c)


if __name__=="__main__":
    unittest.main()
