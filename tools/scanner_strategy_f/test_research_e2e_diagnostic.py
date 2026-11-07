"""Diagnostic original read-only market path: separate from signed F5.

These are unit checks of scanner-only authority, frozen two-strategy AST
kernel, original 15m query shape, complete 24-attempt accounting, and
future/source alteration rejection. No private E: bytes are accessible in CI.
"""
from __future__ import annotations
import copy
import json
import unittest
from unittest.mock import patch

from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from tools.scanner_strategy_f.research_e2e_diagnostic import (
    _eval_strategy,diagnostic_original_cohort,
)
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2


class LocalResearchDiagnostic(unittest.TestCase):
    def setUp(self):
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.proposal=propose_historical_research_policy(self.work)
        self.request=prepare_historical_policy_approval_request(self.proposal,self.work)
        self.draft=create_retrospective_policy_draft(
            self.proposal,self.request,self.work)

    def test_real_frozen_strategy_ast_over_closed_bars_no_future(self):
        # Three observed bars are enough for period 3 SMA: warmup is UNKNOWN.
        spec=self.work[0]["payload"]["definition"]["definition"]
        definition=StrategyDefinition.from_dict(spec,registry=IndicatorRegistryV2())
        start=1735689600000
        bars=[
            {"bar_open_ms":start+i*900000,"bar_close_ms":start+(i+1)*900000-1,
             "open":float(100+i),"high":float(101+i),
             "low":float(99+i),"close":float(100+i),"volume":1.0}
            for i in range(5)
        ]
        signals=_eval_strategy(definition,bars)
        self.assertEqual(len(signals),len(bars))
        self.assertEqual(signals[0][1],"UNKNOWN")
        self.assertTrue(all(s[1] in (
            "UNKNOWN","ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL")
            for s in signals))
        # Appending a future candle never changes historical signal states.
        later={**bars[-1],
               "bar_open_ms":start+5*900000,
               "bar_close_ms":start+6*900000-1,
               "open":500.0,"high":501.0,"low":499.0,"close":500.0}
        self.assertEqual(_eval_strategy(definition,bars),
                         _eval_strategy(definition,bars+[later])[:-1])

    def test_no_fake_query_coverage_allowed(self):
        # The operator must pass exactly 10 genuine Core query receipts.
        with self.assertRaises(ValueError):
            diagnostic_original_cohort(
                warehouse_root="/missing",
                month_queries={},
                policy_draft=self.draft,proposal=self.proposal,
                approval_request=self.request,work_specs=self.work)
        with self.assertRaises(ValueError):
            diagnostic_original_cohort(
                warehouse_root="/missing",
                month_queries={m:{} for m in (
                    "2024-01","2024-02","2024-03","2024-04",
                    "2024-05","2024-06","2024-07","2024-09",
                    "2024-10","2024-11")},
                policy_draft=self.draft,proposal=self.proposal,
                approval_request=self.request,work_specs=self.work)

    def test_wrong_issuer_source_and_future_time_rejected_before_query(self):
        months=(
            "2024-01","2024-03","2024-04","2024-05","2024-06",
            "2024-07","2024-09","2024-10","2024-11","2024-12",
        )
        examples={
            m:{"schema":"aql.core.local-history-query.v1",
               "source_bytes_sha256":"a"*64,"historical_pit":"NOT_ATTESTED",
               "coverage":"COMPLETE","query_sha256":"b"*64,
               "start_ms":0,"end_exclusive_ms":0,
               "decision_cutoff_ms":0,"available_bar_count":0}
            for m in months
        }
        with patch("tools.scanner_strategy_f.research_e2e_diagnostic.query_local") as query:
            with self.assertRaises(ValueError):
                diagnostic_original_cohort(
                    warehouse_root="/irrelevant",month_queries=examples,
                    policy_draft=self.draft,proposal=self.proposal,
                    approval_request=self.request,work_specs=self.work)
            query.assert_not_called()
        changed=copy.deepcopy(examples)
        changed["2024-01"]["historical_pit"]="ATTESTED"
        with self.assertRaises(ValueError):
            diagnostic_original_cohort(
                warehouse_root="/irrelevant",month_queries=changed,
                policy_draft=self.draft,proposal=self.proposal,
                approval_request=self.request,work_specs=self.work)

if __name__=="__main__":
    unittest.main()
