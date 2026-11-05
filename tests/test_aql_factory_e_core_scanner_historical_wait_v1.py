import copy
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_core_e_historical_boundary_v1 import preflight_historical_source
from research_wp_r0.aql_core_e_status_evidence_v1 import make_core_e_status
from research_wp_r0.aql_factory_e_core_scanner_historical_wait_v1 import record_historical_core_scanner_wait
from research_wp_r0.aql_factory_e_research_results_store_v1 import read_experiment, ResultsStoreError
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.strategy_service_offline.run import FIXTURES

class FactoryEFinalHistoricalPolicyGate(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db=Path(t.name)/"e.sqlite"
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.preflight=preflight_historical_source(
            zip_path=None,publisher_checksum_sha256=None,
            dataset_id="BTCUSDT-2024-03",source_kind="ORIGINAL_PUBLISHER")
        self.status=make_core_e_status(preflight_receipt=self.preflight)
        self.policy=propose_historical_research_policy(self.work)
    def consume(self,**changes):
        data=dict(store_path=self.db,experiment_id="HIST-E-FINAL-WAIT",
                  core_preflight=self.preflight,core_status=self.status,
                  scanner_policy_proposal=self.policy,frozen_work_specs=self.work,
                  code_sha256="1"*64,environment_sha256="2"*64)
        data.update(changes)
        return record_historical_core_scanner_wait(**data)
    def test_original_missing_source_policy_proposal_census_replay(self):
        a=self.consume()
        b=self.consume()
        self.assertEqual(a,b)
        self.assertEqual(a["strategy_count"],len(self.work))
        self.assertEqual(a["symbol_count"],1)
        self.assertEqual(a["selected_count"],0)
        self.assertEqual(a["unknown_count"],len(self.work))
        saved=read_experiment(self.db,"HIST-E-FINAL-WAIT")
        self.assertEqual(saved["attempt_states"]["UNKNOWN"],len(self.work))
        self.assertIsNone(saved["source_sha256"])
        self.assertIsNone(saved["core_245_price_query_sha256"])
        self.assertIsNone(saved["lab_receipt_sha256"])
        self.assertEqual(a["trading_authority"],"NONE")
    def test_forged_core_status_denied(self):
        v=copy.deepcopy(self.status)
        v["historical_policy_approval"]="APPROVED"
        with self.assertRaises(ResultsStoreError):
            self.consume(core_status=v)
    def test_forged_scanner_approval_denied(self):
        v=copy.deepcopy(self.policy)
        v["payload"]["policy_status"]="APPROVED"
        with self.assertRaises((ResultsStoreError,ValueError)):
            self.consume(scanner_policy_proposal=v)
    def test_wrong_policy_source_parent_denied(self):
        v=copy.deepcopy(self.policy)
        v["payload"]["actual_historical_source_receipt_sha256"]="f"*64
        with self.assertRaises((ResultsStoreError,ValueError)):
            self.consume(scanner_policy_proposal=v)
    def test_changed_frozen_strategy_list_denied(self):
        with self.assertRaises((ResultsStoreError,ValueError)):
            self.consume(frozen_work_specs=self.work[:1])

if __name__=="__main__":
    unittest.main()
