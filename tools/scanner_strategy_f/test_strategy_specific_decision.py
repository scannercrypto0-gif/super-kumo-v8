"""Scanner F3 source-bound strategy-specific decision/Secretary ACK requirements.

No original OHLCV is available in GitHub; these tests verify strict negative
gates and real signature/strategy/source identity dependencies using existing
SHA-only contract fixture, never manufacture a historical SELECTED signal.
"""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch

from research_wp_r0.aql_core_f_private_f2_v1 import digest as core_digest
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.test_source_bound_intake import SourceBoundIntake
from tools.scanner_strategy_f.strategy_specific_decision import decide_source_bound_strategy
from tools.scanner_strategy_f.secretary_ack_requirements import (
    propose_secretary_ack_requirements,verify_secretary_ack_requirements,
)

class ScannerF3StrategyDecisionContract(SourceBoundIntake):
    def test_retained_feb_aug_denied_even_with_trusted_policy(self):
        c=self.run_bridge()
        for month in ("2024-02","2024-08"):
            with self.subTest(month=month), self.assertRaises(ValueError):
                decide_source_bound_strategy(
                    c,warehouse_root="/not-read",
                    core_f2_report=self.report,month=month,
                    warehouse_receipt=None,native_query_receipt=None,
                    local_query_receipt=None,identity_map_receipt=None,
                    strategy_id=self.specs[0]["payload"]["strategy_id"],
                    strategy_version="v1",observed_close_signal=None)

    def test_no_evaluator_or_query_receipts_cannot_self_select(self):
        c=self.run_bridge()
        for month,strategy in (
            ("2024-01","test_momentum"),
            ("2024-03","test_reversion"),
        ):
            with self.subTest(month=month,strategy=strategy),self.assertRaises(ValueError):
                decide_source_bound_strategy(
                    c,warehouse_root="/not-read",core_f2_report=self.report,
                    month=month,warehouse_receipt=None,
                    native_query_receipt=None,local_query_receipt=None,
                    identity_map_receipt=None,strategy_id=strategy,
                    strategy_version="v1",observed_close_signal=None)

    def test_tampered_resealed_f2_denied_before_no_query_path(self):
        c=self.run_bridge()
        report=copy.deepcopy(self.report)
        report["f2_new_admitted_count"]=12  # retain original report digest
        with self.assertRaises(ValueError):
            decide_source_bound_strategy(
                c,warehouse_root="/not-read",core_f2_report=report,
                month="2024-01",warehouse_receipt=None,
                native_query_receipt=None,local_query_receipt=None,
                identity_map_receipt=None,strategy_id="test_momentum",
                strategy_version="v1",observed_close_signal=None)

    def test_invalid_month_identity_and_strategy_swap_denied(self):
        c=self.run_bridge()
        for month,strategy in (
            ("2024-13","test_momentum"),
            ("2024-01","arbitrary"),
            ("2024-01","test_momentum_wrong"),
        ):
            with self.subTest(month=month,strategy=strategy),self.assertRaises(ValueError):
                decide_source_bound_strategy(
                    c,warehouse_root="/not-read",core_f2_report=self.report,
                    month=month,warehouse_receipt=None,
                    native_query_receipt=None,local_query_receipt=None,
                    identity_map_receipt=None,strategy_id=strategy,
                    strategy_version="v1",observed_close_signal=None)

    def test_secretary_ack_requirements_only_from_original_decision(self):
        c=self.run_bridge()
        d=Frozen.restore(c).data
        item=next(Frozen.restore(x).data for x in d["attempts"]
                  if Frozen.restore(x).data["month"]=="2024-01"
                  and Frozen.restore(x).data["strategy_id"]=="test_momentum")
        # This is an intentionally synthetic receipt used only to test the
        # requirements CONTRACT, never a positive historical route.
        proposal=Frozen.build({
            "schema":"aql.scanner-f.historical-original-strategy-decision.v1",
            "source_bound_census_sha256":c["sha256"],
            "decision":"WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL",
            "selected":False,"historical_pit":"NOT_ATTESTED",
            "research_scope":"RETROSPECTIVE_NON_PIT",
            "trading_authority":"NONE",
            "source_ack_sha256":None,
            "strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None,
            "secretary_state":"NOT_ENQUEUED",
            "strategy_id":item["strategy_id"],
            "strategy_version":item["strategy_version"],
            "month":item["month"],
            "strategy_definition_digest":item["strategy_definition_digest"],
            "native15m_config_digest":item["native15m_config_digest"],
            "source_zip_sha256":item["original_source_sha256"],
            "warehouse_receipt_sha256":item["warehouse_receipt_sha256"],
            "core245_native_query_sha256":item["core245_native_query_sha256"],
            "core253_local_query_sha256":item["core253_local_query_sha256"],
            "cutoff_ms":1738368000000,
        }).receipt()
        ack=propose_secretary_ack_requirements(proposal,c)
        a=verify_secretary_ack_requirements(ack,proposal,c).data
        self.assertEqual(a["source_ack_required_owner"],"CORE_SOURCE_SECRETARY")
        self.assertEqual(a["strategy_approval_required_owner"],"CORE_STRATEGY_SECRETARY")
        self.assertEqual(a["factory_consumer_ack_required_owner"],"FACTORY")
        self.assertEqual(a["research_scope"],"RETROSPECTIVE_NON_PIT")
        self.assertIsNone(a["source_ack_sha256"])
        self.assertIsNone(a["strategy_approval_sha256"])
        self.assertIsNone(a["factory_consumer_ack_sha256"])
        for field,value in (
            ("source_ack_sha256","f"*64),
            ("strategy_approval_sha256","e"*64),
            ("factory_consumer_ack_sha256","d"*64),
            ("secretary_state","ACKED"),
            ("historical_pit","ATTESTED"),
            ("trading_authority","PAPER"),
        ):
            with self.subTest(field=field):
                forged=copy.deepcopy(ack["payload"])
                forged[field]=value
                with self.assertRaises(ValueError):
                    verify_secretary_ack_requirements(
                        Frozen.build(forged).receipt(),proposal,c)


if __name__=="__main__":
    unittest.main()
