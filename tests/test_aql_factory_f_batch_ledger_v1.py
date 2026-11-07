"""Factory F historical blocked batch: exact denominator, restart, identity and safety."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_f_batch_ledger_v1 import (
    start_blocked_batch,batch_snapshot
)
from research_wp_r0.aql_factory_e_research_results_store_v1 import ResultsStoreError

class FactoryFBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"factory-f.sqlite"
        self.inputs=dict(
            batch_id="F-BTC-2024-RESEARCH",
            source_status_sha256="a"*64,
            policy_request_sha256="b"*64,
            policy_proposal_sha256="c"*64,
            attempt_manifest=[
                {"attempt_id":f"F-{i:03d}",
                 "candidate_id":f"WORK235-{i:03d}:BTCUSDT"}
                for i in range(30)])
    def test_restart_exact_denominator_and_idempotency(self):
        a=start_blocked_batch(self.db,**self.inputs)
        b=start_blocked_batch(self.db,**self.inputs)
        c=batch_snapshot(self.db,self.inputs["batch_id"])
        self.assertEqual(a,b)
        self.assertEqual(b,c)
        self.assertEqual(a["attempt_count"],30)
        self.assertEqual(a["unknown"],30)
        self.assertEqual(a["selected"],0)
        self.assertEqual(a["denied"],0)
        self.assertIsNone(a["source_ack_sha256"])
        self.assertIsNone(a["strategy_approval_sha256"])
        self.assertIsNone(a["factory_consumer_ack_sha256"])
        self.assertEqual(a["trading_authority"],"NONE")
        self.assertEqual(a["orders_created"],0)
    def test_changed_source_policy_or_population_no_overwrite(self):
        start_blocked_batch(self.db,**self.inputs)
        for key,val in (
            ("source_status_sha256","f"*64),
            ("policy_request_sha256","f"*64),
            ("attempt_manifest",self.inputs["attempt_manifest"][:1]),
        ):
            with self.subTest(key=key):
                changes={**self.inputs,key:val}
                with self.assertRaisesRegex(ResultsStoreError,"ID_CONFLICT"):
                    start_blocked_batch(self.db,**changes)
        self.assertEqual(batch_snapshot(self.db,self.inputs["batch_id"])["unknown"],30)
    def test_duplicate_attempt_denied_without_partial_write(self):
        rows=copy.deepcopy(self.inputs["attempt_manifest"])
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ResultsStoreError,"ATTEMPT_IDENTITY"):
            start_blocked_batch(self.db,**{**self.inputs,"attempt_manifest":rows})
        self.assertFalse(self.db.exists())
    def test_tampered_row_and_missing_row_fail_closed(self):
        start_blocked_batch(self.db,**self.inputs)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE f_attempts SET state='SELECTED' WHERE attempt_id='F-000'")
        with self.assertRaisesRegex(ResultsStoreError,"ATTEMPT_TAMPER"):
            batch_snapshot(self.db,self.inputs["batch_id"])
    def test_deleted_candidate_is_not_silent_denom_shrink(self):
        start_blocked_batch(self.db,**self.inputs)
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM f_attempts WHERE attempt_id='F-005'")
        with self.assertRaisesRegex(ResultsStoreError,"CENSUS_DRIFT"):
            batch_snapshot(self.db,self.inputs["batch_id"])

if __name__=="__main__":
    unittest.main()
