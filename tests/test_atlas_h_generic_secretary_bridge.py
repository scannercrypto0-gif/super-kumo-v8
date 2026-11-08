"""Integration H: real SQLite Secretary, no mocked Core routes, synthetic only."""
import copy
import tempfile
import unittest
from pathlib import Path

from tools.atlas_h_generic_secretary_bridge import deliver_generic_research_wait
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    read_generic_research_result_route,
)
from test_aql_core_h_generic_research_secretary_v1 import docs


class GenericIntegration(unittest.TestCase):
    def test_three_strategies_durable_restart_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            shas=set()
            for index in range(3):
                p,h,r=docs(experiment="RESEARCH-H-GENERIC-INTEGRATION-"+str(index))
                first=deliver_generic_research_wait(
                    secretary_root=root,packet=p,factory_package=h,
                    factory_result=r)
                second=deliver_generic_research_wait(
                    secretary_root=root,packet=p,factory_package=h,
                    factory_result=r)
                self.assertEqual(first,second)
                reread=read_generic_research_result_route(root,p["experiment_id"])
                self.assertEqual(first["secretary_route_sha256"],reread["receipt_sha256"])
                self.assertEqual(reread["state"],"WAIT_RESEARCH_REVIEW")
                self.assertIsNone(reread["strategy_approval_sha256"])
                shas.add(reread["receipt_sha256"])
            self.assertEqual(len(shas),3)

    def test_partial_unknown_preserved_without_approval(self):
        with tempfile.TemporaryDirectory() as d:
            p,h,r=docs(n=6,observed=4,experiment="RESEARCH-H-GENERIC-PARTIAL")
            result=deliver_generic_research_wait(
                secretary_root=Path(d),packet=p,factory_package=h,
                factory_result=r)
            saved=read_generic_research_result_route(Path(d),p["experiment_id"])
            self.assertEqual(saved["coverage"],"PARTIAL")
            self.assertEqual(saved["unknown_signal_count"],6)
            self.assertEqual(saved["modeled_trades"],0)
            self.assertEqual(result["trading_authority"],"NONE")

    def test_forged_ack_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p,h,r=docs()
            p=copy.deepcopy(p)
            p["strategy_approval_sha256"]="a"*64
            with self.assertRaises(ValueError):
                deliver_generic_research_wait(
                    secretary_root=Path(d),packet=p,factory_package=h,
                    factory_result=r)

    def test_mutated_result_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p,h,r=docs()
            r=copy.deepcopy(r)
            r["factory_report_sha256"]="f"*64
            with self.assertRaises(ValueError):
                deliver_generic_research_wait(
                    secretary_root=Path(d),packet=p,factory_package=h,
                    factory_result=r)


if __name__=="__main__":
    unittest.main()
