"""WP-R11 adversarial tests for immutable external custody *protocol*.

Fake store is deliberately ONLY a test double, never a real external custodian.
"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.external_custody import (
    CustodyPolicy, checkpoint_key, publish_checkpoint, verify_stored_checkpoint,
)
from research_wp_r0.owner_checkpoints import export_checkpoint
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, fingerprint,
)

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


def family():
    return FrozenSearchFamily("research-a", "protocol", "temporal", "dataset",
                              "net", "MAXIMIZE", ("a", "b"), 0.05, T)


def attempt(candidate):
    return Attempt(candidate, AttemptState.COMPLETE, "evidence-" + candidate,
                   T + timedelta(minutes=1), 0.2)


POLICY = CustodyPolicy("owner-1", "store-independent", "research", True)
UNAPPROVED = CustodyPolicy("owner-1", "store-independent", "research", False)


class FakeImmutableStore:
    def __init__(self):
        self.records = {}
        self.attempts = 0
        self.fail_after_commit = False
        self.fail_read = False

    def put_once(self, key, content):
        self.attempts += 1
        if key in self.records and self.records[key] != content:
            raise JournalIntegrityError("Immutable conflict")
        self.records.setdefault(key, content)
        if self.fail_after_commit:
            raise OSError("Remote acknowledgement lost after commit")

    def read(self, key):
        if self.fail_read:
            raise OSError("External evidence store is unavailable")
        return self.records[key]


class CustodyContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "trials.jsonl"
        self.store = FakeImmutableStore()

    def test_unapproved_store_never_receives_evidence(self):
        with DurableTrialJournal(self.path, family()) as j:
            with self.assertRaises(JournalIntegrityError):
                publish_checkpoint(j, policy=UNAPPROVED, store=self.store)
            self.assertEqual(self.store.attempts, 0)

    def test_store_and_exact_readback_then_validate_journal(self):
        with DurableTrialJournal(self.path, family()) as j:
            j.record_attempt(attempt("a"), event_id="a")
            result = publish_checkpoint(j, policy=POLICY, store=self.store)
            self.assertEqual(result.status, "READBACK_VERIFIED")
            self.assertEqual(result.checkpoint.family_digest, family().digest)
            self.assertEqual(self.store.records[result.key],
                             result.checkpoint.to_json_bytes())
            ok = verify_stored_checkpoint(
                j, policy=POLICY, store=self.store, checkpoint=result.checkpoint
            )
            self.assertEqual(ok.payload_digest, result.payload_digest)
            j.record_attempt(attempt("b"), event_id="b")
            verify_stored_checkpoint(j, policy=POLICY, store=self.store,
                                     checkpoint=result.checkpoint)

    def test_idempotent_retry_same_key_and_bytes(self):
        with DurableTrialJournal(self.path, family()) as j:
            first = publish_checkpoint(j, policy=POLICY, store=self.store)
            again = publish_checkpoint(j, policy=POLICY, store=self.store)
            self.assertEqual(first, again)
            self.assertEqual(len(self.store.records), 1)

    def test_different_checkpoint_cannot_overwrite_prior(self):
        with DurableTrialJournal(self.path, family()) as j:
            first = publish_checkpoint(j, policy=POLICY, store=self.store)
            j.record_attempt(attempt("a"), event_id="a")
            second = publish_checkpoint(j, policy=POLICY, store=self.store)
            self.assertNotEqual(first.key, second.key)
            self.assertEqual(len(self.store.records), 2)
            self.assertEqual(self.store.records[first.key], first.checkpoint.to_json_bytes())

    def test_failed_acknowledgement_fails_closed_but_retry_idempotent(self):
        with DurableTrialJournal(self.path, family()) as j:
            self.store.fail_after_commit = True
            with self.assertRaises(OSError):
                publish_checkpoint(j, policy=POLICY, store=self.store)
            self.store.fail_after_commit = False
            receipt = publish_checkpoint(j, policy=POLICY, store=self.store)
            self.assertEqual(self.store.attempts, 2)
            self.assertEqual(len(self.store.records), 1)
            self.assertEqual(receipt.status, "READBACK_VERIFIED")

    def test_missing_or_tampered_remote_receipt_blocks_verification(self):
        with DurableTrialJournal(self.path, family()) as j:
            receipt = publish_checkpoint(j, policy=POLICY, store=self.store)
            self.store.records[receipt.key] = b"forged"
            with self.assertRaises(JournalIntegrityError):
                verify_stored_checkpoint(j, policy=POLICY, store=self.store,
                                         checkpoint=receipt.checkpoint)

    def test_remote_read_outage_blocks_success(self):
        with DurableTrialJournal(self.path, family()) as j:
            self.store.fail_read = True
            with self.assertRaises(OSError):
                publish_checkpoint(j, policy=POLICY, store=self.store)

    def test_wrong_family_or_namespace_fails_closed(self):
        with DurableTrialJournal(self.path, family()) as j:
            receipt = publish_checkpoint(j, policy=POLICY, store=self.store)
            other = CustodyPolicy("another-owner", "store-independent", "research", True)
            with self.assertRaises(KeyError):
                verify_stored_checkpoint(j, policy=other, store=self.store,
                                         checkpoint=receipt.checkpoint)
            self.assertNotEqual(
                checkpoint_key(other, receipt.checkpoint), receipt.key
            )

    def test_caller_cannot_use_unapproved_receipt_to_promote(self):
        with DurableTrialJournal(self.path, family()) as j:
            checkpoint = export_checkpoint(j)
            with self.assertRaises(JournalIntegrityError):
                verify_stored_checkpoint(j, policy=UNAPPROVED, store=self.store,
                                         checkpoint=checkpoint)
            self.assertFalse(j.report().confirmatory_eligible)

    def test_policy_rejects_path_injection(self):
        for name in ("../bad", "x/y", "", "owner space", ":", "a" * 129):
            with self.subTest(name=name), self.assertRaises(ValueError):
                CustodyPolicy(name, "provider", "research", True)

    def test_local_fake_store_not_independent_evidence(self):
        self.assertTrue(POLICY.external_independence_verified)
        # The flag is caller supplied, not audited here. Fake store proves
        # protocol behavior only, not any actual external custody or trust.
        self.assertEqual(type(self.store).__name__, "FakeImmutableStore")


if __name__ == "__main__":
    unittest.main()
