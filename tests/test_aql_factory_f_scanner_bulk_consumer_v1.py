"""Owner F4 actual Core F -> Scanner F3 -> Factory E immutable metadata consumer."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_core_f_bulk_source_v1 import build_manifest,build_coverage_ledger
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from research_wp_r0.aql_factory_f_scanner_bulk_consumer_v1 import consume_scanner_f_bulk_preflight
from research_wp_r0.aql_factory_e_research_results_store_v1 import read_experiment,ResultsStoreError


class FactoryFScannerBulkConsumer(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db=Path(t.name)/"factory.sqlite"
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.proposal=propose_historical_research_policy(self.work)
        self.request=prepare_historical_policy_approval_request(self.proposal,self.work)
        self.policy=create_retrospective_policy_draft(self.proposal,self.request,self.work)
        self.manifest=build_manifest()
        self.outcomes={}
        for row in self.manifest["rows"]:
            if row["inventory_status"]=="TARGET_NOT_ACQUIRED":
                self.outcomes[row["month"]]={
                    "status":"ACCEPTED_PREFLIGHT",
                    "archive_sha256":"a"*64,
                    "checksum_file_sha256":"b"*64,
                    "preflight_receipt_sha256":"c"*64,
                    "observed_bars":row["expected_native_15m_bars"],
                    "raw_vault":"NOT_YET_ADMITTED",
                    "warehouse":"NOT_YET_ADMITTED",
                    "historical_pit":"NOT_ATTESTED"}
        self.coverage=build_coverage_ledger(self.manifest,self.outcomes)

    def run_consumer(self,**kw):
        args=dict(manifest=self.manifest,coverage_ledger=self.coverage,
                  policy_draft=self.policy,proposal=self.proposal,
                  approval_request=self.request,work_specs=self.work,
                  store_path=self.db,experiment_id="F-12-MONTH-BTCUSDT",
                  code_sha256="1"*64,environment_sha256="2"*64)
        args.update(kw)
        return consume_scanner_f_bulk_preflight(**args)

    def test_full_census_and_replay(self):
        a=self.run_consumer()
        b=self.run_consumer()
        self.assertEqual(a,b)
        self.assertEqual(a["month_count"],12)
        self.assertEqual(a["attempt_count"],24)
        self.assertEqual(a["attempt_census"]["UNKNOWN"],24)
        self.assertEqual(a["attempt_census"]["SELECTED"],0)
        self.assertEqual(a["factory_consumer_ack_sha256"],None)
        self.assertEqual(a["orders_created"],0)
        record=read_experiment(self.db,"F-12-MONTH-BTCUSDT")
        self.assertEqual(record["attempt_count"],24)
        self.assertEqual(record["source_sha256"],None)
        self.assertEqual(record["core_245_price_query_sha256"],None)
        self.assertEqual(record["lab_receipt_sha256"],None)

    def test_missing_rejected_retained_denominator(self):
        outcomes=copy.deepcopy(self.outcomes)
        del outcomes["2024-01"]
        outcomes["2024-03"]={"status":"REJECTED_QUARANTINED",
                             "reason":"INVALID_PUBLISHER_CHECKSUM"}
        changed=build_coverage_ledger(self.manifest,outcomes)
        v=self.run_consumer(coverage_ledger=changed)
        self.assertEqual(v["attempt_count"],24)
        self.assertEqual(v["attempt_census"]["UNKNOWN"],22)
        self.assertEqual(v["attempt_census"]["QUARANTINED"],2)
        self.assertEqual(v["attempt_census"]["SELECTED"],0)

    def test_changed_manifest_and_invalid_paper_denied(self):
        bad=copy.deepcopy(self.manifest)
        bad["source"]="TEST_ONLY"
        with self.assertRaises(ResultsStoreError):
            self.run_consumer(manifest=bad)
        with self.assertRaises(ResultsStoreError):
            self.run_consumer(environment_sha256=None)

    def test_immutable_same_id_conflicting_coverage(self):
        self.run_consumer()
        changed=copy.deepcopy(self.outcomes)
        del changed["2024-01"]
        replacement=build_coverage_ledger(self.manifest,changed)
        with self.assertRaisesRegex(ResultsStoreError,"IMMUTABLE_IDEMPOTENCY_CONFLICT"):
            self.run_consumer(coverage_ledger=replacement)

    def test_forged_source_parent_no_promotion(self):
        bad=copy.deepcopy(self.coverage)
        bad["core_245_native_query_sha256"]="f"*64
        with self.assertRaises(ResultsStoreError):
            self.run_consumer(coverage_ledger=bad)

if __name__=="__main__":
    unittest.main()
