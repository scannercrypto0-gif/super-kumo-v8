"""Package H synthetic research-only durable Secretary route tests."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    build_research_result_route, read_research_result_route,
    route_research_result,
)


def factory():
    report = {
        "schema": "aql.factory.f.f2-recovery-research-report.v2",
        "status": "RECOVERY_RESEARCH_ONLY_NOT_F5",
        "experiment_id": "synthetic-test-experiment",
        "input_sha256": "1" * 64,
        "core_receipt_graph_sha256": "2" * 64,
        "scanner_receipt_sha256": "3" * 64,
        "lab_sha256": "4" * 64,
        "experiment_sha256": "5" * 64,
        "result_sha256": "6" * 64,
        "attempt_count": 24,
        "diagnostic_evaluated": 20,
        "feb_aug_inventory_unknown": 4,
        "source_ack_sha256": None,
        "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "historical_pit": "NOT_ATTESTED",
        "trading_authority": "NONE",
        "holdout": "SEALED_UNOPENED",
        "paper": "NOT_ACTIVATED",
        "selected": False,
        "orders_created": 0,
        "positions": 0,
    }
    return {**report, "receipt_sha256": digest(report)}


PARENTS = dict(
    strategy_definition_sha256="a" * 64,
    strategy_config_sha256="b" * 64,
    code_sha256="c" * 64,
    cost_policy_sha256="d" * 64,
    lab_report_sha256="e" * 64,
)


class SecretaryResearchOnlyTests(unittest.TestCase):
    def test_durable_replay_and_no_authority_promotion(self):
        with TemporaryDirectory() as temp:
            a = route_research_result(temp, factory(), **PARENTS)
            b = route_research_result(temp, factory(), **PARENTS)
            c = read_research_result_route(temp, factory()["experiment_id"])
            self.assertEqual(a, b)
            self.assertEqual(a, c)
            self.assertEqual(a["state"], "WAIT_RESEARCH_REVIEW")
            self.assertEqual(a["f5_approval"], "NOT_GRANTED")
            self.assertIsNone(a["source_ack_sha256"])
            self.assertIsNone(a["strategy_approval_sha256"])
            self.assertIsNone(a["factory_consumer_ack_sha256"])
            self.assertIsNone(a["research_review_ack_sha256"])
            self.assertEqual(a["trading_authority"], "NONE")
            con = sqlite3.connect(Path(temp) / "warehouse.sqlite")
            try:
                self.assertEqual(con.execute(
                    "SELECT count(*) FROM h_research_result_events").fetchone()[0], 1)
                self.assertEqual(con.execute(
                    "SELECT count(*) FROM price_bars").fetchone()[0], 0)
            finally:
                con.close()

    def test_replay_with_changed_policy_parent_is_rejected(self):
        with TemporaryDirectory() as temp:
            route_research_result(temp, factory(), **PARENTS)
            with self.assertRaisesRegex(ValueError, "IDEMPOTENCY_CONFLICT"):
                route_research_result(temp, factory(), **{
                    **PARENTS, "cost_policy_sha256": "f" * 64})

    def test_forged_factory_ack_and_promotions_rejected(self):
        for key, value in [
            ("source_ack_sha256", "a" * 64),
            ("strategy_approval_sha256", "a" * 64),
            ("factory_consumer_ack_sha256", "a" * 64),
            ("selected", True),
            ("trading_authority", "LIVE"),
            ("paper", "ACTIVATED"),
            ("historical_pit", "ATTESTED"),
            ("attempt_count", 25),
            ("diagnostic_evaluated", 24),
            ("feb_aug_inventory_unknown", 0),
            ("orders_created", 1),
            ("positions", True),
        ]:
            report = factory()
            report[key] = value
            report["receipt_sha256"] = digest({
                k: v for k, v in report.items() if k != "receipt_sha256"})
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "AUTHORITY_OR_DENOMINATOR_DRIFT"):
                build_research_result_route(report, **PARENTS)

    def test_invalid_seal_and_missing_lab_or_cost_policy(self):
        report = factory()
        report["receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "FACTORY_SEALED_RESULT_REQUIRED"):
            build_research_result_route(report, **PARENTS)
        with self.assertRaisesRegex(ValueError, "LAB_EVALUATION_MUST_BE_DISTINCT"):
            build_research_result_route(factory(), **{
                **PARENTS, "lab_report_sha256": "4" * 64})
        with self.assertRaisesRegex(ValueError, "EXPLICIT_PARENT_REQUIRED"):
            build_research_result_route(factory(), **{
                **PARENTS, "cost_policy_sha256": None})

    def test_trace_mutation_detected(self):
        with TemporaryDirectory() as temp:
            route_research_result(temp, factory(), **PARENTS)
            con = sqlite3.connect(Path(temp) / "warehouse.sqlite")
            try:
                con.execute("UPDATE h_research_result_events "
                            "SET event_sha='0' WHERE seq=1")
                con.commit()
            finally:
                con.close()
            with self.assertRaisesRegex(ValueError, "TRACE_TAMPER"):
                read_research_result_route(temp, factory()["experiment_id"])


if __name__ == "__main__":
    unittest.main()
