"""WP-R13: preserved commit boundaries and verified replay state."""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.trial_holdout import Attempt, AttemptState, FrozenSearchFamily

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family():
    return FrozenSearchFamily("benchmark", "protocol", "temporal", "source",
                              "net", "MAXIMIZE", ("a", "b", "c"), 0.05, T)


def attempt(n):
    return Attempt(n, AttemptState.COMPLETE, "result-" + n,
                   T + timedelta(minutes=1), 0.2)


class JournalFastReplayAcceptance(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "journal.jsonl"

    def test_committed_state_survives_multiple_fast_appends_and_restart(self):
        with DurableTrialJournal(self.path, family()) as j:
            for n in ("a", "b", "c"):
                j.record_attempt(attempt(n), event_id="event-" + n)
            final_head = j.head
            self.assertEqual(j.report().complete, 3)
        with DurableTrialJournal(self.path, family()) as j:
            self.assertEqual(j.head, final_head)
            self.assertEqual(j.report().complete, 3)

    def test_invalid_transition_cannot_be_written_or_counted(self):
        with DurableTrialJournal(self.path, family()) as j:
            j.record_attempt(attempt("a"), event_id="a")
            head_before = j.head
            with self.assertRaises(JournalIntegrityError):
                j.record_attempt(attempt("a"), event_id="duplicate")
            self.assertEqual(j.head, head_before)
            self.assertEqual(j.report().complete, 1)

    def test_fsync_failure_poisoned_and_no_false_commit(self):
        with DurableTrialJournal(self.path, family()) as j:
            head_before = j.head
            with patch("research_wp_r0.durable_journal.os.fsync",
                       side_effect=OSError("synthetic fsync failure")):
                with self.assertRaises(OSError):
                    j.record_attempt(attempt("a"), event_id="a")
            self.assertEqual(j.head, head_before)
            with self.assertRaises(JournalIntegrityError):
                j.report()
            with self.assertRaises(JournalIntegrityError):
                j.record_attempt(attempt("b"), event_id="b")

    def test_tampered_file_rejected_before_fast_append(self):
        with DurableTrialJournal(self.path, family()) as j:
            j.record_attempt(attempt("a"), event_id="a")
            raw = self.path.read_bytes()
            self.path.write_bytes(raw.replace(b"result-a", b"result-z"))
            with self.assertRaises(JournalIntegrityError):
                j.record_attempt(attempt("b"), event_id="b")

    def test_replayed_trusted_prefix_still_controls_future_appends(self):
        with DurableTrialJournal(self.path, family()) as j:
            j.record_attempt(attempt("a"), event_id="a")
            head, sequence = j.head, j.sequence
        with DurableTrialJournal(self.path, family(),
                                 expected_head=head, expected_sequence=sequence) as j:
            j.record_attempt(attempt("b"), event_id="b")
        with DurableTrialJournal(self.path, family(),
                                 expected_head=head, expected_sequence=sequence) as j:
            self.assertEqual(j.report().complete, 2)


if __name__ == "__main__":
    unittest.main()
