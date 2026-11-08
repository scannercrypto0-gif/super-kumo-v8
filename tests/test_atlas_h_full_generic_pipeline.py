"""Real Scanner AST -> Factory modeled fills/Lab -> Core durable SQLite WAIT.

Synthetic only. Scanner's query_local is replaced by the bounded synthetic
fixture (not a real warehouse); Factory/Scientific Lab/Secretary are unmocked.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import run_factory_h_generic_research
from tools.atlas_h_generic_secretary_bridge import deliver_generic_research_wait
from research_wp_r0.aql_core_h_research_secretary_v1 import read_generic_research_result_route
from test_aql_factory_h_generic_signal_adapter_v1 import case_for


class FullGenericH(unittest.TestCase):
    def test_frozen_two_and_distinct_manual_ast_to_durable_secretary(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"factory.sqlite"
            root=Path(d)/"secretary"
            migrate_store_v2(db)
            seen=set()
            for i in (0,1,2):
                with self.subTest(strategy=i):
                    packet=case_for(i)
                    if i==2:
                        self.assertEqual(packet["strategy_plugin"]["payload"]["strategy_id"],
                                         "h_manual_distinct_test")
                    seen.add(packet["strategy_definition_sha256"])
                    first=run_factory_h_generic_research(packet,db)
                    second=run_factory_h_generic_research(packet,db)
                    self.assertEqual(second["store_status"],"REPLAY_IDENTICAL")
                    self.assertEqual(first["package_sha256"],second["package_sha256"])
                    # Factory returns the immutable nested package as part of result.
                    package=first["factory_h_package"]
                    result=deliver_generic_research_wait(
                        secretary_root=root,packet=packet,
                        factory_package=package,factory_result=first)
                    saved=read_generic_research_result_route(root,packet["experiment_id"])
                    self.assertEqual(result["secretary_route_sha256"],saved["receipt_sha256"])
                    self.assertEqual(saved["state"],"WAIT_RESEARCH_REVIEW")
                    self.assertIsNone(saved["strategy_approval_sha256"])
                    self.assertEqual(saved["trading_authority"],"NONE")
            self.assertEqual(len(seen),3)


if __name__=="__main__":
    unittest.main()
