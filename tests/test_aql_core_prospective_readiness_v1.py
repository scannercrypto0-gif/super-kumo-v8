from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aql.g1_integrity import CommitEvidenceError
from aql.journal.durable_journal import DurableJournal
from research_wp_r0.aql_core_prospective_readiness_v1 import (
    ReadinessError, admit_sample, seal_readiness,
)
from tools.core_prospective_readiness_smoke import (
    commit_mock, fixture, mock_bar, run, sample_args,
)


class ProspectiveReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = fixture(self.root)
        self.seal = self.root / "freeze.json"

    def enroll(self):
        self.freeze = seal_readiness(self.seal, **self.config)
        self.bar = mock_bar()
        commit_mock(self.config["journal"], self.bar)
        return sample_args(self.config, self.freeze, self.bar)

    def test_executed_dry_run_negative_log_and_reproducibility(self):
        a, b = run(self.root / "a"), run(self.root / "b")
        self.assertEqual(a, b)
        self.assertEqual(len(a["negative_rejections"]), 10)
        self.assertEqual(a["real_cohort_status"], "BLOCKED_OWNER_AUTHORIZATION")

    def test_restart_receipt_and_identical_freeze_replay(self):
        args = self.enroll()
        first = admit_sample(self.seal, **args)
        self.assertEqual(seal_readiness(self.seal, **self.config), self.freeze)
        args["journal"] = DurableJournal(str(self.root / "journal.sqlite"))
        self.assertEqual(admit_sample(self.seal, **args), first)
        self.assertNotIn("bars", first)
        self.assertNotIn("close", first)

    def test_source_rights_versions_and_time_types_fail_closed(self):
        for field, value in (("rights_reference", ""), ("rights_sha256", None),
                             ("source_version", ""), ("committed_at_ms", True),
                             ("observed_at_ms", -1), ("available_at_ms", 5000),
                             ("evidence_class", "REAL_PROSPECTIVE")):
            with self.subTest(field=field):
                config = {**self.config, "source": {**self.config["source"], field: value}}
                with self.assertRaises(ReadinessError):
                    seal_readiness(self.seal, **config)
        self.assertFalse(self.seal.exists())

    def test_required_predeclared_bindings(self):
        for field in self.config["bindings"]:
            with self.subTest(field=field):
                bindings = dict(self.config["bindings"])
                del bindings[field]
                with self.assertRaisesRegex(ReadinessError, "PINS"):
                    seal_readiness(self.seal, **{**self.config, "bindings": bindings})

    def test_missing_late_witness(self):
        for value in (None, True, 3000, 900_000):
            with self.subTest(value=value), self.assertRaisesRegex(ReadinessError, "WITNESS"):
                seal_readiness(self.seal, **{**self.config, "witnessed_at_ms": value})

    def test_no_freeze_after_sample(self):
        commit_mock(self.config["journal"], mock_bar())
        with self.assertRaisesRegex(ReadinessError, "FREEZE_AFTER_FIRST_BAR"):
            seal_readiness(self.seal, **self.config)

    def test_frozen_plan_mutation_and_wrong_external_pin(self):
        args = self.enroll()
        with self.assertRaisesRegex(ReadinessError, "FREEZE_PIN"):
            admit_sample(self.seal, **{**args, "expected_freeze_sha256": "a" * 64})
        self.seal.write_bytes(self.seal.read_bytes().replace(b"fixture-v1", b"fixture-v2"))
        with self.assertRaisesRegex(ReadinessError, "FREEZE_PIN"):
            admit_sample(self.seal, **args)

    def test_source_journal_isolation(self):
        args = self.enroll()
        other = DurableJournal(str(self.root / "other.sqlite"))
        commit_mock(other, mock_bar())
        with self.assertRaisesRegex(ReadinessError, "SOURCE_ISOLATION"):
            admit_sample(self.seal, **{**args, "journal": other})

    def test_no_oos_peek_even_after_oos_end(self):
        args = self.enroll()
        oos = mock_bar(self.config["times"]["oos_start_ms"])
        commit_mock(self.config["journal"], oos)
        args = sample_args(self.config, self.freeze, oos)
        args["decision_cutoff_ms"] = self.config["times"]["oos_end_ms"] + 10000
        with self.assertRaisesRegex(ReadinessError, "OOS_SEALED_NO_PEEK"):
            admit_sample(self.seal, **args)

    def test_embargo_and_provisional_source_rejected(self):
        self.enroll()
        cases = [(mock_bar(self.config["times"]["validation_end_ms"]), "EMBARGO"),
                 (mock_bar(1_800_000, is_final=False), "FINAL_SOURCE_GRID"),
                 (mock_bar(2_700_000, source="binance_ws"), "FINAL_SOURCE_GRID")]
        for bar, code in cases:
            with self.subTest(code=code):
                commit_mock(self.config["journal"], bar)
                with self.assertRaisesRegex(ReadinessError, code):
                    admit_sample(self.seal, **sample_args(self.config, self.freeze, bar))

    def test_observation_availability_commit_cutoff(self):
        args = self.enroll()
        for updates in ({"observed_at_ms": self.bar.bar_close},
                        {"available_at_ms": self.bar.ingested_at + 1},
                        {"decision_cutoff_ms": self.bar.ingested_at},
                        {"observed_at_ms": True}):
            with self.subTest(updates=updates), self.assertRaises(ReadinessError):
                admit_sample(self.seal, **{**args, **updates})

    def test_missing_or_uncommitted_record_never_eligible(self):
        args = self.enroll()
        with self.assertRaisesRegex(ReadinessError, "COMMITTED_ELIGIBLE_SOURCE"):
            admit_sample(self.seal, **{**args, "stable_key": "BTC-USD:15m:0"})

    def test_plan_changed_after_freeze_denied(self):
        args = self.enroll()
        raw = self.config["plan_raw"].replace(b"net_r", b"gross")
        with self.assertRaises(ValueError):
            admit_sample(self.seal, **{**args, "plan_raw": raw})

    def test_data_commit_without_post_commit_receipt_cannot_admit(self):
        freeze = seal_readiness(self.seal, **self.config)
        bar = mock_bar()
        with patch("aql.journal.durable_journal.post_commit_receipt",
                   side_effect=CommitEvidenceError("fixture-crash-after-data-commit")):
            with self.assertRaises(CommitEvidenceError):
                commit_mock(self.config["journal"], bar)
        restarted = DurableJournal(str(self.root / "journal.sqlite"))
        args = sample_args(self.config, freeze, bar)
        args["journal"] = restarted
        with self.assertRaisesRegex(ReadinessError, "POST_COMMIT_CUTOFF_RECEIPT"):
            admit_sample(self.seal, **args)
        self.assertFalse(commit_mock(restarted, mock_bar()))
        with self.assertRaisesRegex(ReadinessError, "POST_COMMIT_CUTOFF_RECEIPT"):
            admit_sample(self.seal, **args)

    def test_each_source_clock_causal_mutation(self):
        for field, value in (("available_at_ms", 2500), ("observed_at_ms", 500),
                             ("committed_at_ms", 1999), ("committed_at_ms", 4001)):
            with self.subTest(field=field, value=value):
                source = {**self.config["source"], field: value}
                with self.assertRaisesRegex(ReadinessError, "SOURCE_NOT_AVAILABLE_AT_FREEZE"):
                    seal_readiness(self.seal, **{**self.config, "source": source})

    def test_same_content_file_replacement_keeps_pin_but_mutated_replacement_denied(self):
        args = self.enroll()
        expected = admit_sample(self.seal, **args)
        replacement = self.root / "replacement.json"
        replacement.write_bytes(self.seal.read_bytes())
        replacement.replace(self.seal)
        self.assertEqual(admit_sample(self.seal, **args), expected)
        replacement.write_bytes(self.seal.read_bytes().replace(b"fixture-v1", b"fixture-v9"))
        replacement.replace(self.seal)
        with self.assertRaisesRegex(ReadinessError, "FREEZE_PIN"):
            admit_sample(self.seal, **args)


if __name__ == "__main__":
    unittest.main()
