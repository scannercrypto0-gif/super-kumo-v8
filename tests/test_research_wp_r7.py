"""WP-R7 journal recovery, tampering, torn tail and idempotency tests."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, HoldoutEvent,
)

T = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)


def family():
    return FrozenSearchFamily(
        "family-r7", "proto-hash", "temporal-hash", "fixture-v1",
        "mean-net", "MAXIMIZE", ("a", "b"), 0.05, T,
    )


def attempt(candidate, p=0.01):
    return Attempt(candidate, AttemptState.COMPLETE, "sha-" + candidate,
                   T + timedelta(minutes=1), p)


def write_complete(path):
    with DurableTrialJournal(path, family()) as ledger:
        ledger.record_attempt(attempt("a"), event_id="trial-a")
        ledger.record_attempt(attempt("b", 0.2), event_id="trial-b")
        ledger.select("a", at=T + timedelta(minutes=2), event_id="choose-a")
        ledger.holdout_event(
            HoldoutEvent("OPEN", T + timedelta(minutes=3), "holdout-receipt"),
            event_id="holdout-open",
        )
        return ledger.sequence, ledger.head


class JournalAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "family.jsonl"

    def test_recovery_after_restart_and_head_stable(self):
        seq, head = write_complete(self.path)
        self.assertEqual(seq, 5)
        with DurableTrialJournal(self.path, family()) as ledger:
            self.assertEqual(ledger.sequence, seq)
            self.assertEqual(ledger.head, head)
            self.assertEqual(ledger.report().status, "EXPLORATORY_HOLDOUT_OPENED")

    def test_identical_retry_is_idempotent_across_restart(self):
        with DurableTrialJournal(self.path, family()) as ledger:
            ledger.record_attempt(attempt("a"), event_id="trial-a")
            seq, head = ledger.sequence, ledger.head
        with DurableTrialJournal(self.path, family()) as ledger:
            ledger.record_attempt(attempt("a"), event_id="trial-a")
            self.assertEqual((ledger.sequence, ledger.head), (seq, head))
            with self.assertRaises(JournalIntegrityError):
                ledger.record_attempt(attempt("a", p=0.0001), event_id="trial-a")

    def test_failed_trial_recoverable_and_not_hidden(self):
        with DurableTrialJournal(self.path, family()) as ledger:
            ledger.record_attempt(attempt("a"), event_id="trial-a")
            ledger.record_attempt(Attempt("b", AttemptState.FAILED, "failed-run",
                                          T + timedelta(minutes=1)),
                                  event_id="trial-b")
        with DurableTrialJournal(self.path, family()) as ledger:
            r = ledger.report()
            self.assertEqual((r.total_declared, r.failed, r.missing), (2, 1, 0))
            ledger.select("a", at=T + timedelta(minutes=2), event_id="choose-a")

    def test_single_writer_lock_blocks_second_instance(self):
        with DurableTrialJournal(self.path, family()):
            with self.assertRaises(FileExistsError):
                DurableTrialJournal(self.path, family())
        self.assertFalse(self.path.with_name("family.jsonl.lock").exists())

    def test_change_existing_journal_record_detected(self):
        write_complete(self.path)
        data = self.path.read_bytes()
        self.path.write_bytes(data.replace(b"sha-a", b"sha-z"))
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, family())

    def test_truncated_tail_rejected_without_repair(self):
        write_complete(self.path)
        raw = self.path.read_bytes()
        self.path.write_bytes(raw[:-2])
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, family())
        self.assertEqual(self.path.read_bytes(), raw[:-2])

    def test_reorder_lines_rejected(self):
        write_complete(self.path)
        lines = self.path.read_bytes().splitlines(keepends=True)
        lines[1], lines[2] = lines[2], lines[1]
        self.path.write_bytes(b"".join(lines))
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, family())

    def test_delete_entire_middle_record_rejected(self):
        write_complete(self.path)
        lines = self.path.read_bytes().splitlines(keepends=True)
        self.path.write_bytes(b"".join(lines[:2] + lines[3:]))
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, family())

    def test_frozen_family_changed_detected(self):
        write_complete(self.path)
        wrong = FrozenSearchFamily(
            "family-r7", "proto-hash", "temporal-hash", "other-data",
            "mean-net", "MAXIMIZE", ("a", "b"), 0.05, T)
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, wrong)

    def test_invalid_state_transition_with_valid_rehashed_chain(self):
        write_complete(self.path)
        # No need to rehash: an invalid event type is already rejected, but
        # also exercise a structurally correct hash with invalid replay state.
        records = [json.loads(x) for x in self.path.read_text().splitlines()]
        from research_wp_r0.trial_holdout import fingerprint
        records[-1]["data"]["event_type"] = "TUNE"
        record = {k: v for k, v in records[-1].items() if k != "hash"}
        records[-1]["hash"] = fingerprint(record)
        encoded = "".join(
            json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            for r in records
        )
        self.path.write_text(encoded)
        # Even a fully recomputed *valid hash* must not bypass the replay
        # state machine: the first holdout event can only be OPEN.
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, family())

    def test_existing_same_size_tampering_detected_before_append(self):
        with DurableTrialJournal(self.path, family()) as ledger:
            ledger.record_attempt(attempt("a"), event_id="trial-a")
            data = self.path.read_bytes()
            self.path.write_bytes(data.replace(b"sha-a", b"sha-z"))
            with self.assertRaises(JournalIntegrityError):
                ledger.record_attempt(attempt("b"), event_id="trial-b")
            with self.assertRaises(JournalIntegrityError):
                ledger.report()

    def test_can_not_append_after_holdout_or_mutate_selection(self):
        with DurableTrialJournal(self.path, family()) as ledger:
            ledger.record_attempt(attempt("a"), event_id="trial-a")
            ledger.record_attempt(attempt("b"), event_id="trial-b")
            ledger.select("a", at=T + timedelta(minutes=2), event_id="select-a")
            with self.assertRaises(JournalIntegrityError):
                ledger.select("b", at=T + timedelta(minutes=3), event_id="select-b")
            with self.assertRaises(JournalIntegrityError):
                ledger.record_attempt(attempt("a", 0.02), event_id="alter-a")

    def test_recovery_requires_no_implicit_repair(self):
        write_complete(self.path)
        raw = self.path.read_bytes()
        self.path.write_bytes(raw + b"partial")
        with self.assertRaises(JournalIntegrityError):
            DurableTrialJournal(self.path, family())
        self.assertEqual(self.path.read_bytes(), raw + b"partial")


if __name__ == "__main__":
    unittest.main()
