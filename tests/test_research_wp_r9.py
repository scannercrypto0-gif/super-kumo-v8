"""WP-R9: Windows audit regressions for frozen inputs, LF and disk-pinned anchors."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.temporal_contract import FrozenTemporalManifest, TemporalOpportunity, validate_temporal_pairs
from research_wp_r0.evaluation import OpportunityOutcome, OpportunityPair, Resolution
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, TrialFamilyLedger, fingerprint,
)

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family(ids=None):
    return FrozenSearchFamily(
        "family", "protocol", "temporal", "version-1", "mean-net",
        "MAXIMIZE", ids if ids is not None else ["a", "b"], 0.05, NOW,
    )


def attempt(candidate):
    return Attempt(candidate, AttemptState.COMPLETE, "result-" + candidate,
                   NOW + timedelta(minutes=1), 0.1)


def temporal(i):
    at = NOW + timedelta(hours=i * 2)
    return TemporalOpportunity(
        str(i), at, at - timedelta(minutes=1), at - timedelta(minutes=2),
        at + timedelta(hours=1), at + timedelta(hours=1),
        at + timedelta(hours=1, minutes=1),
        at + timedelta(hours=1, minutes=2),
        "shock-" + str(i),
    )


def pair(i):
    group = "shock-" + str(i)
    return OpportunityPair(
        OpportunityOutcome(str(i), group, Resolution.KNOWN, 0.01, 0.001),
        OpportunityOutcome(str(i), group, Resolution.KNOWN, 0.02, 0.002),
    )


def rehash_all_records(path, *, new_p=0.4):
    records = [json.loads(line) for line in path.read_bytes().split(b"\n") if line]
    records[1]["data"]["marginal_p_value"] = new_p
    previous = "0" * 64
    for record in records:
        record["prev_hash"] = previous
        record["hash"] = fingerprint({k: v for k, v in record.items() if k != "hash"})
        previous = record["hash"]
    path.write_bytes(b"".join(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
        for record in records
    ))


class FrozenInputAuditTests(unittest.TestCase):
    def test_candidate_list_mutation_cannot_disappear_undeclared_trial(self):
        ids = ["a", "b"]
        frozen = family(ids)
        digest = frozen.digest
        ledger = TrialFamilyLedger(frozen)
        ledger.record_attempt(attempt("a"))
        ids.pop()
        self.assertEqual(frozen.candidate_ids, ("a", "b"))
        self.assertEqual(frozen.digest, digest)
        self.assertEqual(ledger.report().missing, 1)
        with self.assertRaises(ValueError):
            ledger.select("a", at=NOW + timedelta(minutes=2))

    def test_candidate_identity_type_rejected(self):
        for ids in (["a", 7], [None], ["a", ""], ["a", ["b"]]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                family(ids)

    def test_temporal_list_mutation_cannot_reorder_manifest(self):
        ordered = [temporal(i) for i in range(3)]
        frozen = FrozenTemporalManifest("proto", "source", "60m", ordered)
        digest = frozen.digest
        ordered.reverse()
        self.assertEqual(frozen.digest, digest)
        self.assertEqual(tuple(x.opportunity_id for x in frozen.ordered), ("0", "1", "2"))
        self.assertEqual(validate_temporal_pairs([pair(i) for i in range(3)], frozen), digest)
        with self.assertRaises(ValueError):
            validate_temporal_pairs([pair(i) for i in reversed(range(3))], frozen)

    def test_manifest_rejects_invalid_collection_members(self):
        with self.assertRaises(ValueError):
            FrozenTemporalManifest("proto", "source", "60m", [temporal(0), "bad"])
        with self.assertRaises(ValueError):
            FrozenTemporalManifest("proto", "source", "60m", 3)


class WindowsJournalAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "audit.jsonl"

    def create(self):
        with DurableTrialJournal(self.path, family()) as journal:
            journal.record_attempt(attempt("a"), event_id="a")
            return journal.head, journal.sequence

    def test_raw_windows_binary_lf_round_trip(self):
        self.create()
        raw = self.path.read_bytes()
        self.assertIn(b"\n", raw)
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.endswith(b"\n"))
        with DurableTrialJournal(self.path, family()) as journal:
            self.assertEqual(journal.report().missing, 1)

    def test_verify_anchor_pins_and_reads_disk(self):
        head, sequence = self.create()
        with DurableTrialJournal(self.path, family()) as journal:
            journal.verify_anchor(expected_head=head, expected_sequence=sequence)
            rehash_all_records(self.path)
            with self.assertRaises(JournalIntegrityError):
                journal.select("a", at=NOW + timedelta(minutes=2), event_id="pick")
            with self.assertRaises(JournalIntegrityError):
                journal.report()

    def test_verify_anchor_rejects_broken_disk_even_when_cache_matches(self):
        head, sequence = self.create()
        with DurableTrialJournal(self.path, family()) as journal:
            self.path.write_bytes(b"BROKEN")
            with self.assertRaises(JournalIntegrityError):
                journal.verify_anchor(expected_head=head, expected_sequence=sequence)

    def test_anchor_requires_pair_and_refuses_repinning(self):
        head, sequence = self.create()
        with DurableTrialJournal(self.path, family()) as journal:
            for head_arg, seq_arg in ((head, None), (None, sequence),
                                      ("BAD", sequence), (head, True)):
                with self.subTest(head=head_arg, seq=seq_arg), self.assertRaises(ValueError):
                    journal.verify_anchor(expected_head=head_arg, expected_sequence=seq_arg)
            journal.verify_anchor(expected_head=head, expected_sequence=sequence)
            with self.assertRaises(JournalIntegrityError):
                journal.verify_anchor(expected_head="f" * 64, expected_sequence=sequence)

    def test_anchored_prefix_accepts_later_append(self):
        head, sequence = self.create()
        with DurableTrialJournal(self.path, family()) as journal:
            journal.verify_anchor(expected_head=head, expected_sequence=sequence)
            journal.record_attempt(attempt("b"), event_id="b")
            self.assertEqual(journal.report().complete, 2)
        with DurableTrialJournal(self.path, family(),
                                 expected_head=head, expected_sequence=sequence) as journal:
            self.assertEqual(journal.report().complete, 2)

    def test_fully_rehashed_unanchored_history_still_not_authenticated(self):
        self.create()
        rehash_all_records(self.path)
        with DurableTrialJournal(self.path, family()) as journal:
            self.assertEqual(journal.report().missing, 1)


if __name__ == "__main__":
    unittest.main()
