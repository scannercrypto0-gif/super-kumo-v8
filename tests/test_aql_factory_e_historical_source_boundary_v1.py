import copy
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_core_e_historical_boundary_v1 import preflight_historical_source
from research_wp_r0.aql_factory_e_historical_source_boundary_v1 import record_core_e_historical_boundary
from research_wp_r0.aql_factory_e_research_results_store_v1 import read_experiment, ResultsStoreError


class FactoryECoreHistoricalSourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db=Path(t.name)/"historical.sqlite"

    def receipt(self, **kw):
        args=dict(zip_path=None,publisher_checksum_sha256=None,
                  dataset_id="BTCUSDT-2024-03",source_kind="ORIGINAL_PUBLISHER")
        args.update(kw)
        return preflight_historical_source(**args)

    def call(self,receipt):
        return record_core_e_historical_boundary(
            preflight_receipt=receipt,store_path=self.db,
            experiment_id="E-HIST-BLOCKED",
            code_sha256="a"*64,environment_sha256="b"*64)

    def test_actual_missing_original_no_fabricated_sha_and_idempotent_replay(self):
        preflight=self.receipt()
        self.assertIsNone(preflight["source_sha256"])
        a=self.call(preflight)
        b=self.call(preflight)
        self.assertEqual(a,b)
        self.assertEqual(a["historical_source"],"HISTORICAL_SOURCE_BLOCKED")
        record=read_experiment(self.db,"E-HIST-BLOCKED")
        self.assertIsNone(record["source_sha256"])
        self.assertIsNone(record["core_245_price_query_sha256"])
        self.assertIsNone(record["core_253_query_local_sha256"])
        self.assertEqual(record["attempt_states"]["UNKNOWN"],1)
        self.assertEqual(a["orders_created"],0)

    def test_forged_preflight_refused(self):
        bad=self.receipt()
        bad["status"]="HISTORICAL_SOURCE_VERIFIED_CUSTODY_ONLY"
        with self.assertRaisesRegex(ResultsStoreError,"PREFLIGHT_TAMPER"):
            self.call(bad)

    def test_synthetic_source_never_admitted_as_original(self):
        with self.assertRaisesRegex(ResultsStoreError,"SYNTHETIC_NOT_HISTORICAL"):
            self.call(self.receipt(source_kind="SYNTHETIC_TEST_ONLY"))

    def test_changed_source_blocker_conflicts_with_same_id(self):
        self.call(self.receipt())
        with self.assertRaisesRegex(ResultsStoreError,"IDEMPOTENCY_CONFLICT"):
            self.call(self.receipt(dataset_id="BTCUSDT-2024-08"))


if __name__=="__main__":
    unittest.main()
