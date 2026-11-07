"""Diagnostic original read-only market path: separate from signed F5.

These are unit checks of scanner-only authority, frozen two-strategy AST
kernel, original 15m query shape, complete 24-attempt accounting, and
future/source alteration rejection. No private E: bytes are accessible in CI.
"""
from __future__ import annotations
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from calendar import monthrange

from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from tools.scanner_strategy_f.research_e2e_diagnostic import (
    _eval_strategy,diagnostic_original_cohort,ADMITTED,_month_ms,SAFE_COHORT_PHASES,
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
        spec=self.work[0]["payload"]["definition"]
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

    def test_complete_synthetic_cohort_real_ast_kernel_and_bounded_phases(self):
        """Unmocked cohort/AST/Factory kernels; only immutable Core I/O is mocked.

        These 10-month OHLCV bars are generated TEST_ONLY and are not the
        owner-private source or evidence of original F2 issuer authority.
        """
        month_queries={}
        for month in ADMITTED:
            start,end=_month_ms(month)
            length=monthrange(2024,int(month[-2:]))[1]*96
            bars=[]
            for i in range(length):
                price=100.0+(i%97)*0.01
                opened=start+i*900000
                bars.append({
                    "bar_open_ms":opened,
                    "bar_close_ms":opened+899999,
                    "open":price,"high":price+1.0,
                    "low":price-1.0,"close":price,
                    "volume":1.0,"bar_checksum":"0"*64,
                    "observation_lower_bound_ms":end,
                    "historical_known_at_ms":None,
                })
            month_queries[month]={
                "schema":"aql.core.local-history-query.v1",
                "dataset_id":"TEST-ONLY-"+month,
                "version":1,"source_bytes_sha256":"a"*64,
                "manifest_integrity_sha256":"b"*64,
                "start_ms":start,"end_exclusive_ms":end,
                "decision_cutoff_ms":end+1000,
                "coverage":"COMPLETE","missing_bar_opens":[],
                "required_bar_count":length,"available_bar_count":length,
                "bars":bars,"source_availability":"RETROSPECTIVE_NON_PIT",
                "historical_pit":"NOT_ATTESTED","universe":"NOT_ATTESTED",
                "query_sha256":"c"*64,
            }
        phases=[]
        # The kernel and Frozen policy/AST code are *not* patched.
        with patch("tools.scanner_strategy_f.research_e2e_diagnostic.query_local",
                   side_effect=lambda *args,**kwargs:
                       month_queries[args[1].split("TEST-ONLY-")[1]]) as query:
            out=diagnostic_original_cohort(
                warehouse_root="/no-private-source",
                month_queries=month_queries,
                policy_draft=self.draft,proposal=self.proposal,
                approval_request=self.request,work_specs=self.work,
                phase_callback=phases.append)
        body=Frozen.restore(out).data
        self.assertEqual(body["native15m_month_bars"],29376)
        self.assertEqual(body["diagnostic_evaluated_attempts"],20)
        self.assertEqual(body["unknown_feb_aug_attempts"],4)
        self.assertEqual(body["selected"],0)
        self.assertEqual(body["trading_authority"],"NONE")
        self.assertEqual(query.call_count,10)
        self.assertTrue(all(x.kwargs["sqlite_immutable"] for x in
                            query.call_args_list))
        self.assertEqual(set(phases),SAFE_COHORT_PHASES)
        self.assertEqual(phases.count("COHORT_FACTORY_KERNEL"),20)
        self.assertEqual(phases[-1],"COHORT_FINAL_RECEIPT")
        blocked=[]
        with patch("tools.scanner_strategy_f.research_e2e_diagnostic.query_local",
                   side_effect=ValueError("PRIVATE_DO_NOT_EXPOSE")), \
             self.assertRaises(ValueError):
            diagnostic_original_cohort(
                warehouse_root="/no-private-source",
                month_queries=month_queries,
                policy_draft=self.draft,proposal=self.proposal,
                approval_request=self.request,work_specs=self.work,
                phase_callback=blocked.append)
        self.assertEqual(blocked[-1],"COHORT_CORE253_REPLAY")
        self.assertNotIn("PRIVATE_DO_NOT_EXPOSE",str(blocked))

    def test_exact_integration_windows_path_subclass_scope(self):
        """Integration passes concrete Path: verify real policy and scope."""
        from tools.scanner_strategy_f import research_e2e_diagnostic as diag
        phases=[]
        with patch.object(diag,"_code_sha",
                          side_effect=ValueError("TEST_STOP_AFTER_AST")):
            with self.assertRaises(ValueError) as ctx:
                diag.diagnostic_original_cohort(
                    warehouse_root=Path("/synthetic-only"),
                    month_queries={m:{} for m in diag.ADMITTED},
                    policy_draft=self.draft,proposal=self.proposal,
                    approval_request=self.request,work_specs=self.work,
                    phase_callback=phases.append)
        self.assertEqual(str(ctx.exception),"TEST_STOP_AFTER_AST")
        self.assertIn("COHORT_AST_RECONSTRUCT",phases)
        self.assertEqual(phases[-1],"COHORT_CODE_FINGERPRINT")
        self.assertTrue(issubclass(type(Path(".")),Path))

    def test_scope_failures_distinguishable_without_private_values(self):
        from tools.scanner_strategy_f import research_e2e_diagnostic as diag
        with self.assertRaises(ValueError) as ctx:
            diag.diagnostic_original_cohort(
                warehouse_root=Path("/synthetic-only"),
                month_queries={},
                policy_draft=self.draft,proposal=self.proposal,
                approval_request=self.request,work_specs=self.work)
        self.assertEqual(str(ctx.exception),
                         "F_DIAGNOSTIC_SCOPE_TEN_MONTH_QUERIES")


if __name__=="__main__":
    unittest.main()
