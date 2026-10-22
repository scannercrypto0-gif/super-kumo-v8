"""R40 owner checkpoint handoff rehearsal gates."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from research_wp_r0.offline_owner_handoff import (
    rehearsal, _family, _write_owner_copy, _load_owner_copy,
)
from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import (
    OwnerCheckpoint, export_checkpoint, verify_owner_checkpoint,
)
from research_wp_r0.trial_holdout import Attempt, AttemptState

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


class OwnerHandoffAcceptance(unittest.TestCase):
    def test_export_import_and_three_adversarial_checks(self):
        output = rehearsal()
        self.assertFalse(output["external_owner_custody_verified"])
        self.assertEqual(output["journal_events"], 3)
        self.assertTrue(output["existing_owner_copy_not_overwritten"])
        self.assertTrue(output["exact_bytes_restored"])
        self.assertEqual(output["adversarial_cases_rejected"], {
            "full_chain_rewrite": True,
            "rollback": True,
            "owner_copy_modified": True,
        })

    def test_owner_copy_is_create_only(self):
        with tempfile.TemporaryDirectory() as base:
            path = Path(base) / "checkpoint"
            cp = OwnerCheckpoint("a" * 64, 3, "b" * 64)
            _write_owner_copy(path, cp)
            with self.assertRaises(FileExistsError):
                _write_owner_copy(path, cp)
            self.assertEqual(_load_owner_copy(path), cp)

    def test_fsync_failure_never_publishes_final_checkpoint(self):
        with tempfile.TemporaryDirectory() as base:
            directory = Path(base)
            path = directory / "checkpoint.json"
            cp = OwnerCheckpoint("a" * 64, 3, "b" * 64)
            with patch("research_wp_r0.offline_owner_handoff.os.fsync",
                       side_effect=OSError("simulated disk sync failure")):
                with self.assertRaises(OSError):
                    _write_owner_copy(path, cp)
            self.assertFalse(path.exists())
            self.assertEqual(list(directory.iterdir()), [])
            _write_owner_copy(path, cp)
            self.assertEqual(_load_owner_copy(path), cp)

    def test_preexisting_receipt_preserved_and_temporary_file_cleaned(self):
        with tempfile.TemporaryDirectory() as base:
            directory = Path(base)
            path = directory / "checkpoint.json"
            first = OwnerCheckpoint("a" * 64, 3, "b" * 64)
            different = OwnerCheckpoint("a" * 64, 4, "c" * 64)
            _write_owner_copy(path, first)
            with self.assertRaises(FileExistsError):
                _write_owner_copy(path, different)
            self.assertEqual(_load_owner_copy(path), first)
            self.assertEqual([entry.name for entry in directory.iterdir()],
                             ["checkpoint.json"])

    def test_untrusted_snapshot_cannot_be_verified_as_owner_approved(self):
        with tempfile.TemporaryDirectory() as base:
            journal_path = Path(base) / "journal.jsonl"
            with DurableTrialJournal(journal_path, _family()) as journal:
                journal.record_attempt(Attempt(
                    "a", AttemptState.COMPLETE, "result-a",
                    T + timedelta(minutes=1), 0.4,
                ), event_id="attempt-a")
                checkpoint = export_checkpoint(journal)
                for untrusted in (False, None, "true", 1):
                    with self.subTest(untrusted=untrusted):
                        with self.assertRaises(JournalIntegrityError):
                            verify_owner_checkpoint(
                                journal, checkpoint,
                                independently_trusted=untrusted,
                            )

    def test_strict_canonical_bytes_reject_modified_checkpoint(self):
        cp = OwnerCheckpoint("a" * 64, 3, "b" * 64)
        valid = cp.to_json_bytes()
        for raw in (valid[:-1], valid + b" ", valid.replace(b'"sequence":3', b'"sequence":2'),
                    valid.replace(b"\\n", b"\\r\\n")):
            if raw == valid:
                continue
            with self.subTest(raw=raw):
                if b'"sequence":2' in raw:
                    # A canonically encoded *different* checkpoint parses,
                    # but cannot match the original owner-controlled digest.
                    changed = OwnerCheckpoint.from_json_bytes(raw)
                    self.assertNotEqual(changed, cp)
                else:
                    with self.assertRaises(ValueError):
                        OwnerCheckpoint.from_json_bytes(raw)


if __name__ == "__main__":
    unittest.main()
