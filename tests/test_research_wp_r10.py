"""WP-R10 independent-checkpoint handling and rollback regression scenarios."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import (
    OwnerCheckpoint, export_checkpoint, verify_owner_checkpoint,
)
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, fingerprint,
)

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family(tag="v1"):
    return FrozenSearchFamily("family-" + tag, "a", "b", "c", "metric",
                              "MAXIMIZE", ("one", "two"), 0.05, T)


def attempt(name):
    return Attempt(name, AttemptState.COMPLETE, "result:" + name,
                   T + timedelta(minutes=1), 0.4)


def rewrite_chain(path):
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    records[1]["data"]["marginal_p_value"] = 0.9
    prior = "0" * 64
    for record in records:
        record["prev_hash"] = prior
        record["hash"] = fingerprint({k: v for k, v in record.items() if k != "hash"})
        prior = record["hash"]
    path.write_bytes(b"".join(json.dumps(x, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True).encode("ascii") + b"\n"
                              for x in records))


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "evidence.jsonl"

    def make_checkpoint(self):
        with DurableTrialJournal(self.path, family()) as j:
            j.record_attempt(attempt("one"), event_id="attempt-one")
            return export_checkpoint(j)

    def test_canonical_export_roundtrip(self):
        checkpoint = self.make_checkpoint()
        self.assertEqual(OwnerCheckpoint.from_json_bytes(checkpoint.to_json_bytes()), checkpoint)
        self.assertEqual(len(checkpoint.receipt_digest), 64)

    def test_requires_external_trust_explicitly(self):
        checkpoint = self.make_checkpoint()
        with DurableTrialJournal(self.path, family()) as j:
            with self.assertRaises(JournalIntegrityError):
                verify_owner_checkpoint(j, checkpoint, independently_trusted=False)
            verify_owner_checkpoint(j, checkpoint, independently_trusted=True)

    def test_tampered_full_chain_rejected_with_trusted_checkpoint(self):
        checkpoint = self.make_checkpoint()
        rewrite_chain(self.path)
        with DurableTrialJournal(self.path, family()) as j:
            # An unanchored reader cannot authenticate recomputed history.
            self.assertEqual(j.report().missing, 1)
            with self.assertRaises(JournalIntegrityError):
                verify_owner_checkpoint(j, checkpoint, independently_trusted=True)

    def test_tampering_after_pin_blocks_further_write(self):
        checkpoint = self.make_checkpoint()
        with DurableTrialJournal(self.path, family()) as j:
            verify_owner_checkpoint(j, checkpoint, independently_trusted=True)
            rewrite_chain(self.path)
            with self.assertRaises(JournalIntegrityError):
                j.record_attempt(attempt("two"), event_id="attempt-two")

    def test_legitimate_append_after_owner_checkpoint(self):
        checkpoint = self.make_checkpoint()
        with DurableTrialJournal(self.path, family()) as j:
            verify_owner_checkpoint(j, checkpoint, independently_trusted=True)
            j.record_attempt(attempt("two"), event_id="attempt-two")
            self.assertEqual(j.report().complete, 2)
        with DurableTrialJournal(self.path, family()) as j:
            verify_owner_checkpoint(j, checkpoint, independently_trusted=True)
            self.assertEqual(j.report().complete, 2)

    def test_checkpoint_from_other_family_is_rejected(self):
        checkpoint = self.make_checkpoint()
        foreign = OwnerCheckpoint(family("other").digest, checkpoint.sequence, checkpoint.head)
        with DurableTrialJournal(self.path, family()) as j:
            with self.assertRaises(JournalIntegrityError):
                verify_owner_checkpoint(j, foreign, independently_trusted=True)

    def test_invalid_or_noncanonical_checkpoint_rejected(self):
        c = self.make_checkpoint()
        for raw in (
            c.to_json_bytes().replace(b"\n", b"\r\n"),
            c.to_json_bytes()[:-1],
            c.to_json_bytes().replace(b'"sequence":2', b'"sequence":true'),
            b"{}\n",
            b"\xff\n",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                OwnerCheckpoint.from_json_bytes(raw)

    def test_rollback_before_checkpoint_rejected(self):
        checkpoint = self.make_checkpoint()
        lines = self.path.read_bytes().splitlines(keepends=True)
        self.path.write_bytes(lines[0])
        with DurableTrialJournal(self.path, family()) as j:
            with self.assertRaises(JournalIntegrityError):
                verify_owner_checkpoint(j, checkpoint, independently_trusted=True)

    def test_export_does_not_write_sidecar_checkpoint(self):
        self.make_checkpoint()
        self.assertEqual(sorted(x.name for x in self.path.parent.iterdir()), ["evidence.jsonl"])


if __name__ == "__main__":
    unittest.main()
