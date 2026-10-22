"""Adversarial report-read, checkpoint-trust and frozen-reference regressions."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import export_checkpoint, verify_owner_checkpoint
from research_wp_r0.temporal_contract import FrozenTemporalManifest, TemporalOpportunity
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, HoldoutEvent, fingerprint,
)

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family():
    return FrozenSearchFamily("read-audit", "protocol", "manifest", "synthetic-v1",
                              "net", "MAXIMIZE", ("a", "b"), 0.05, T)


def attempt(name):
    return Attempt(name, AttemptState.COMPLETE, "result-" + name,
                   T + timedelta(minutes=1), 0.1)


def temporal():
    return TemporalOpportunity("a", T, T, T, T + timedelta(hours=1),
                               T + timedelta(hours=1), T + timedelta(hours=1),
                               T + timedelta(hours=1), "shock")


def rewrite_chain(path):
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    records[1]["data"]["marginal_p_value"] = 0.9
    prior = "0" * 64
    for record in records:
        record["prev_hash"] = prior
        record["hash"] = fingerprint({k: v for k, v in record.items() if k != "hash"})
        prior = record["hash"]
    path.write_bytes(b"".join(json.dumps(r, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True).encode("ascii") + b"\n"
                              for r in records))


class ReportReadIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "evidence.jsonl"
        self.journal = DurableTrialJournal(self.path, family())
        self.addCleanup(self.journal.close)
        self.journal.record_attempt(attempt("a"), event_id="a")

    def test_report_rejects_corruption_without_a_subsequent_write(self):
        self.path.write_bytes(b"BROKEN\n")
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()

    def test_report_rejects_same_length_hash_tamper(self):
        raw = self.path.read_bytes()
        changed = raw.replace(b'"marginal_p_value":0.1', b'"marginal_p_value":0.9')
        self.assertNotEqual(raw, changed)
        self.assertEqual(len(raw), len(changed))
        self.path.write_bytes(changed)
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()

    def test_report_rejects_torn_tail(self):
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()

    def test_report_rejects_missing_file(self):
        self.path.unlink()
        with self.assertRaises((JournalIntegrityError, OSError)):
            self.journal.report()

    def test_report_rejects_file_replacement_even_with_identical_bytes(self):
        replacement = self.path.with_name("replacement.jsonl")
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()

    def test_report_rejects_rehashed_history_against_pinned_checkpoint(self):
        c = export_checkpoint(self.journal)
        verify_owner_checkpoint(self.journal, c, independently_trusted=True)
        rewrite_chain(self.path)
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()

    def test_report_rejects_rollback_against_pinned_checkpoint(self):
        c = export_checkpoint(self.journal)
        verify_owner_checkpoint(self.journal, c, independently_trusted=True)
        self.path.write_bytes(self.path.read_bytes().splitlines(keepends=True)[0])
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()

    def test_failed_report_poisoning_cannot_be_repaired_silently(self):
        raw = self.path.read_bytes()
        self.path.write_bytes(b"BROKEN\n")
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()
        self.path.write_bytes(raw)
        with self.assertRaises(JournalIntegrityError):
            self.journal.report()
        with self.assertRaises(JournalIntegrityError):
            self.journal.record_attempt(attempt("b"), event_id="b")

    def test_healthy_report_does_not_write_or_change_committed_head(self):
        raw, head, sequence = self.path.read_bytes(), self.journal.head, self.journal.sequence
        self.assertEqual(self.journal.report().complete, 1)
        self.assertEqual(self.journal.report().missing, 1)
        self.assertEqual((self.path.read_bytes(), self.journal.head, self.journal.sequence),
                         (raw, head, sequence))

    def test_holdout_contamination_and_counts_survive_anchored_restart(self):
        self.journal.record_attempt(attempt("b"), event_id="b")
        self.journal.select("a", at=T + timedelta(minutes=2), event_id="select")
        self.journal.holdout_event(HoldoutEvent("OPEN", T + timedelta(minutes=3), "open"), event_id="open")
        self.journal.holdout_event(HoldoutEvent("TUNE", T + timedelta(minutes=4), "tune"), event_id="tune")
        c = export_checkpoint(self.journal)
        self.journal.close()
        with DurableTrialJournal(self.path, family(), expected_head=c.head, expected_sequence=c.sequence) as j:
            report = j.report()
            self.assertEqual(report.complete, 2)
            self.assertEqual(report.status, "HOLDOUT_CONTAMINATED")
            self.assertFalse(report.confirmatory_eligible)

    def test_rehashed_unanchored_history_is_still_not_authenticated(self):
        # Deliberately document the limitation: local hashes cannot detect a
        # full adversarial rewrite without an independently trusted checkpoint.
        rewrite_chain(self.path)
        self.journal.close()
        with DurableTrialJournal(self.path, family()) as j:
            report = j.report()
            self.assertEqual(report.complete, 1)
            self.assertFalse(report.confirmatory_eligible)


class CheckpointTrustTypeTests(unittest.TestCase):
    def test_truthy_non_boolean_cannot_assert_independent_custody(self):
        with tempfile.TemporaryDirectory() as tmp:
            with DurableTrialJournal(Path(tmp) / "j.jsonl", family()) as j:
                c = export_checkpoint(j)
                for flag in ("false", "true", 1, [True], {"trusted": True}):
                    with self.subTest(flag=flag), self.assertRaises(JournalIntegrityError):
                        verify_owner_checkpoint(j, c, independently_trusted=flag)
                verify_owner_checkpoint(j, c, independently_trusted=True)

    def test_false_none_and_zero_remain_untrusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with DurableTrialJournal(Path(tmp) / "j.jsonl", family()) as j:
                c = export_checkpoint(j)
                for flag in (False, None, 0, "", []):
                    with self.subTest(flag=flag), self.assertRaises(JournalIntegrityError):
                        verify_owner_checkpoint(j, c, independently_trusted=flag)


class FrozenReferenceTypeTests(unittest.TestCase):
    def test_family_metadata_rejects_mutable_non_string_references(self):
        f = family()
        for field in ("family_id", "protocol_digest", "temporal_manifest_digest", "dataset_version", "metric_name"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(f, **{field: ["mutable"]})

    def test_manifest_metadata_rejects_mutable_non_string_references(self):
        m = FrozenTemporalManifest("protocol", "source", "60m", (temporal(),))
        for field in ("protocol_digest", "source_version", "horizon_name"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(m, **{field: ["mutable"]})

    def test_temporal_event_rejects_mutable_identities(self):
        for field in ("opportunity_id", "opportunity_group_id"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(temporal(), **{field: ["mutable"]})


if __name__ == "__main__":
    unittest.main()
