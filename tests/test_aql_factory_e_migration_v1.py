"""Factory E layout v1->v2 atomic migration/rollback/restart fault matrix."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, register_experiment, read_experiment,
    migrate_store_v2, rollback_store_v1, audit_store_layout,
    ResultsStoreError,
)

class FactoryEMigrationTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db=Path(t.name)/"research.sqlite"
        self.record=build_experiment(
            experiment_id="MIGRATE-E-1",lane="SCANNER",
            source_status="SYNTHETIC_ENGINEERING_PASS",
            source_sha256="1"*64,source_query_245_sha256="2"*64,
            source_query_253_sha256="3"*64,
            strategy_definition_sha256="4"*64,
            config_sha256="5"*64,code_sha256="6"*64,
            environment_sha256="7"*64,
            parent_receipt_sha256="8"*64,
            attempts=[dict(attempt_id="a1",candidate_id="c1",
                           state="REJECTED",source_receipt_sha256="9"*64)])
        register_experiment(self.db,self.record)

    def test_atomic_upgrade_readback_replay_rollback_upgrade(self):
        baseline=audit_store_layout(self.db)
        self.assertEqual(baseline["experiment_count"],1)
        up=migrate_store_v2(self.db)
        self.assertEqual(up["status"],"UPGRADED_V2")
        self.assertEqual(audit_store_layout(self.db)["layout_version"],2)
        self.assertEqual(read_experiment(self.db,"MIGRATE-E-1"),self.record)
        self.assertEqual(migrate_store_v2(self.db)["status"],"ALREADY_V2")
        self.assertEqual(register_experiment(self.db,self.record)["status"],
                         "REPLAY_IDENTICAL")
        down=rollback_store_v1(self.db)
        self.assertEqual(down["status"],"ROLLED_BACK_V1")
        self.assertEqual(audit_store_layout(self.db)["layout_version"],1)
        self.assertEqual(read_experiment(self.db,"MIGRATE-E-1"),self.record)
        migrate_store_v2(self.db)
        self.assertEqual(audit_store_layout(self.db)["all_document_shas"],
                         baseline["all_document_shas"])

    def test_partial_upgrade_faults_are_atomic(self):
        for point in ("metadata","backfill"):
            with self.subTest(point=point):
                with self.assertRaisesRegex(ResultsStoreError,
                                             "INJECTED_MIGRATION_CRASH"):
                    migrate_store_v2(self.db,fail_after_step=point)
                self.assertEqual(audit_store_layout(self.db)["layout_version"],0)
                with sqlite3.connect(self.db) as con:
                    self.assertNotIn("experiment_index_v2",
                                     {row[0] for row in con.execute(
                                         "SELECT name FROM sqlite_master WHERE type='table'")})
                self.assertEqual(read_experiment(self.db,"MIGRATE-E-1"),self.record)

    def test_rollback_crash_recover_and_replay(self):
        migrate_store_v2(self.db)
        with self.assertRaisesRegex(ResultsStoreError,
                                     "INJECTED_ROLLBACK_CRASH"):
            rollback_store_v1(self.db,fail_before_commit=True)
        self.assertEqual(audit_store_layout(self.db)["layout_version"],2)
        self.assertEqual(read_experiment(self.db,"MIGRATE-E-1"),self.record)

    def test_index_mutation_detected(self):
        migrate_store_v2(self.db)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE experiment_index_v2 SET canonical_sha256=?",
                        ("f"*64,))
        with self.assertRaisesRegex(ResultsStoreError, "INDEX_MISMATCH"):
            audit_store_layout(self.db)
        with self.assertRaisesRegex(ResultsStoreError, "PARENT_DRIFT"):
            rollback_store_v1(self.db)

    def test_document_mutation_denied_across_layouts(self):
        migrate_store_v2(self.db)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE experiments SET sha=? WHERE experiment_id=?",
                        ("f"*64,"MIGRATE-E-1"))
        with self.assertRaisesRegex(ResultsStoreError, "ROW_MUTATION"):
            audit_store_layout(self.db)

if __name__=="__main__":
    unittest.main()
