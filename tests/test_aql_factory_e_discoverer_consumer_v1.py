"""Factory E owner-side independent Discoverer admission to immutable results."""
import copy
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace

from research_wp_r0.aql_factory_e_discoverer_consumer_v1 import accept_discoverer_research
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, read_experiment,
)
from tools.strategy_discoverer_offline.tests.test_package_e_membership import (
    setup_case, admission,
)


class FactoryEDiscovererConsumerTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db = Path(t.name) / "factory-e.sqlite"
        self.case = setup_case()
        _, self.decision, self.intake, self.membership = admission(self.case)

    def run_intake(self, **changes):
        evidence, package, ledger, attempt, checkpoint, receipt, log_head = self.case
        args = dict(
            trusted_ledger_snapshot=ledger.to_dict_list(),
            package=package, evidence=evidence, receipt=receipt,
            intake=self.intake, handoff_decision=self.decision,
            membership=self.membership,
            experiment_id="DISC-E-001", store_path=self.db,
            code_sha256="1"*64, environment_sha256="2"*64,
            config_sha256="3"*64, core_source_sha256="4"*64,
            core_245_query_sha256="5"*64, core_253_query_sha256="6"*64,
        )
        args.update(changes)
        return accept_discoverer_research(**args)

    def test_independently_verified_admission_store_and_replay(self):
        a = self.run_intake()
        b = self.run_intake()
        self.assertEqual(a["receipt_sha256"], b["receipt_sha256"])
        self.assertEqual(a["status"], "RESEARCH_INTAKE_RECORDED_NOT_EVALUATED")
        stored = read_experiment(self.db, "DISC-E-001")
        self.assertEqual(stored["lane"], "DISCOVERER")
        self.assertEqual(stored["source_status"], "SYNTHETIC_ENGINEERING_PASS")
        self.assertEqual(stored["attempt_states"]["SELECTED"], 1)
        self.assertIsNone(stored["lab_receipt_sha256"])
        self.assertIsNone(stored["paper_receipt_sha256"])
        self.assertEqual(stored["historical_pit"], "NOT_ATTESTED")
        self.assertEqual(a["orders_created"], 0)
        self.assertEqual(a["factory_lab_evaluation"], "NOT_EVALUATED")

    def test_forged_membership_rejected(self):
        fake = replace(self.membership, entry_digest="f"*64)
        with self.assertRaises(ResultsStoreError):
            self.run_intake(membership=fake)

    def test_swapped_trusted_ledger_rejected(self):
        rows = self.case[2].to_dict_list()
        rows[0]["reason"] = "tampered"
        with self.assertRaises(ValueError):
            self.run_intake(trusted_ledger_snapshot=rows)

    def test_wrong_package_or_handoff_rejected(self):
        with self.assertRaises(ResultsStoreError):
            self.run_intake(handoff_decision=replace(self.decision,
                                                     intake_digest="a"*64))
        bad_receipt = copy.copy(self.case[5])
        object.__setattr__(bad_receipt, "package_digest", "a"*64)
        with self.assertRaises(ResultsStoreError):
            self.run_intake(receipt=bad_receipt)

    def test_immutable_same_experiment_conflict(self):
        self.run_intake()
        with self.assertRaisesRegex(ResultsStoreError, "IDEMPOTENCY_CONFLICT"):
            self.run_intake(environment_sha256="f"*64)

    def test_legacy_intake_not_self_attested(self):
        self.assertEqual(self.intake.ledger_membership_status, "NOT_VERIFIED")
        self.assertEqual(self.intake.evaluation_status, "NOT_EVALUATED")
        self.assertEqual(self.intake.factory_consumer_connected,
                         "FACTORY_CONSUMER_NOT_CONNECTED")


if __name__ == "__main__":
    unittest.main()
