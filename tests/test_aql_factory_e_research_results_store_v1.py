"""Factory E immutable results ledger and fail-closed historical boundary."""
import copy
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, build_experiment, register_experiment,
    read_experiment, compare_experiments,
)


class FactoryEResultsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "results.sqlite"

    def record(self, **kw):
        params = dict(
            experiment_id="E-AAA-1", lane="SCANNER",
            source_status="SYNTHETIC_ENGINEERING_PASS",
            source_sha256="1" * 64,
            source_query_245_sha256="2" * 64,
            source_query_253_sha256="3" * 64,
            strategy_definition_sha256="4" * 64,
            config_sha256="5" * 64,
            code_sha256="6" * 64,
            environment_sha256="7" * 64,
            parent_receipt_sha256="8" * 64,
            attempts=[
                dict(attempt_id="a1", candidate_id="c1",
                     state="SELECTED", source_receipt_sha256="9" * 64),
                dict(attempt_id="a2", candidate_id="c2",
                     state="REJECTED", source_receipt_sha256="9" * 64),
                dict(attempt_id="a3", candidate_id="c3",
                     state="UNKNOWN", source_receipt_sha256="9" * 64),
            ],
            lab_receipt_sha256="a" * 64, paper_receipt_sha256="b" * 64,
            result_sha256="c" * 64)
        params.update(kw)
        return build_experiment(**params)

    def test_store_replay_restart_census_and_comparison(self):
        exp = self.record()
        first = register_experiment(self.db, exp)
        again = register_experiment(self.db, exp)
        self.assertEqual(first["status"], "STORED_IMMUTABLE")
        self.assertEqual(again["status"], "REPLAY_IDENTICAL")
        self.assertEqual(read_experiment(self.db, "E-AAA-1"), exp)
        self.assertEqual(exp["attempt_count"], 3)
        self.assertEqual(exp["attempt_states"]["REJECTED"], 1)
        other = self.record(experiment_id="E-AAA-2", environment_sha256="e"*64)
        register_experiment(self.db, other)
        comparison = compare_experiments(self.db, "E-AAA-1", "E-AAA-2")
        self.assertEqual(comparison["comparison_status"], "SAME_ELIGIBLE_PARENT_SCOPE")
        self.assertEqual(comparison["profitability_comparison"], "NOT_AUTHORIZED")
        self.assertNotEqual(exp["sha256"], other["sha256"])

    def test_swapped_parent_same_id_is_conflict(self):
        register_experiment(self.db, self.record())
        with self.assertRaisesRegex(ResultsStoreError, "IDEMPOTENCY_CONFLICT"):
            register_experiment(self.db, self.record(source_sha256="f" * 64))

    def test_mutated_receipt_and_resealed_authority_refused(self):
        record = self.record()
        fake = copy.deepcopy(record)
        fake["attempts"][0]["state"] = "REJECTED"
        with self.assertRaisesRegex(ResultsStoreError, "SEALED_DOCUMENT_TAMPER"):
            register_experiment(self.db, fake)
        with self.assertRaisesRegex(ResultsStoreError, "EVIDENCE_AUTHORITY"):
            self.record(trading_authority="LIVE")
        with self.assertRaisesRegex(ResultsStoreError, "EVIDENCE_AUTHORITY"):
            self.record(orders_created=1)
        with self.assertRaisesRegex(ResultsStoreError, "CORE_NATIVE_LOCAL_SHA_ALIAS"):
            self.record(source_query_253_sha256="2" * 64)

    def test_blocked_historical_is_recorded_not_promoted(self):
        blocked = self.record(
            experiment_id="E-BTC-BLOCKED", lane="HISTORICAL_SOURCE",
            source_status="HISTORICAL_SOURCE_BLOCKED",
            evidence_class="RETROSPECTIVE_NON_PIT",
            lab_receipt_sha256=None,
            paper_receipt_sha256=None, result_sha256=None)
        register_experiment(self.db, blocked)
        self.assertEqual(
            read_experiment(self.db, "E-BTC-BLOCKED")["source_status"],
            "HISTORICAL_SOURCE_BLOCKED")
        self.assertEqual(
            compare_experiments(self.db, "E-BTC-BLOCKED", "E-BTC-BLOCKED")[
                "comparison_status"], "NOT_COMPARABLE_DISTINCT_OR_BLOCKED_SCOPE")
        with self.assertRaisesRegex(ResultsStoreError, "BLOCKED_CANNOT_HAVE_RESULTS"):
            self.record(source_status="HISTORICAL_SOURCE_BLOCKED")

    def test_all_attempts_and_duplicate_fail_closed(self):
        with self.assertRaisesRegex(ResultsStoreError, "ATTEMPT_ID_OR_POLICY"):
            self.record(attempts=[
                dict(attempt_id="a1",candidate_id="c1",state="SELECTED",
                     source_receipt_sha256="9"*64),
                dict(attempt_id="a1",candidate_id="c2",state="REJECTED",
                     source_receipt_sha256="9"*64)])
        with self.assertRaisesRegex(ResultsStoreError, "ATTEMPT_DENOMINATOR"):
            self.record(attempts=[])

    def test_store_rejects_external_ledger_promotion_without_proof(self):
        with self.assertRaisesRegex(ResultsStoreError, "DISCOVERER_SOURCE_NOT_ATTESTED"):
            self.record(lane="DISCOVERER",
                        source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT")


if __name__ == "__main__":
    unittest.main()
