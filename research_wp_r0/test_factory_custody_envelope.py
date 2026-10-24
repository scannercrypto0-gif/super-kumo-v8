"""Fail-closed verification of externally retained Factory custody evidence."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.factory_custody_envelope import custody_envelope, verify_custody_envelope


class CustodyEvidenceTests(unittest.TestCase):
    def test_roundtrip(self):
        raw = custody_envelope(plan_digest="a" * 64, ledger_checkpoint=(0, "0" * 64))
        self.assertEqual(verify_custody_envelope(
            raw, plan_digest="a" * 64, ledger_checkpoint=(0, "0" * 64)
        )["ledger_sequence"], 0)

    def test_reject_changed_plan(self):
        raw = custody_envelope(plan_digest="a" * 64, ledger_checkpoint=(0, "0" * 64))
        with self.assertRaises(ValueError):
            verify_custody_envelope(raw, plan_digest="b" * 64,
                                   ledger_checkpoint=(0, "0" * 64))

    def test_reject_changed_checkpoint(self):
        raw = custody_envelope(plan_digest="a" * 64, ledger_checkpoint=(1, "b" * 64))
        with self.assertRaises(ValueError):
            verify_custody_envelope(raw, plan_digest="a" * 64,
                                   ledger_checkpoint=(1, "c" * 64))

    def test_reject_tampered_envelope(self):
        raw = custody_envelope(plan_digest="a" * 64, ledger_checkpoint=(0, "0" * 64))
        with self.assertRaises(ValueError):
            verify_custody_envelope(raw.replace(b'"schema_version":"1"',
                                                b'"schema_version":"2"'),
                                   plan_digest="a" * 64, ledger_checkpoint=(0, "0" * 64))

    def test_real_ledger_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / "attempts.sqlite", require_admission=True)
            checkpoint = ledger.snapshot()[1]
            raw = custody_envelope(plan_digest="a" * 64, ledger_checkpoint=checkpoint)
            self.assertEqual(verify_custody_envelope(
                raw, plan_digest="a" * 64, ledger_checkpoint=ledger.snapshot()[1]
            )["ledger_sequence"], checkpoint[0])


if __name__ == "__main__":
    unittest.main()
