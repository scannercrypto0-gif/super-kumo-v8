"""Adversarial custody checks: no overwrite, rollback, or trusted-anchor mismatch."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.factory_custody_export import export_custody_envelope, verify_exported_custody


class CustodyAdversarialTests(unittest.TestCase):
    def test_anchored_ledger_rejects_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deleted.sqlite"
            with self.assertRaises(ValueError):
                AttemptLedger(path, expected_checkpoint=(1, "a" * 64))

    def test_anchor_rejects_rollback_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            anchor = Path(tmp) / "anchor.json"
            export_custody_envelope(anchor, plan_digest="a" * 64,
                                   ledger_checkpoint=(3, "b" * 64))
            with self.assertRaises(ValueError):
                verify_exported_custody(anchor, plan_digest="a" * 64,
                                        ledger_checkpoint=(2, "c" * 64))

    def test_anchor_refuses_symlink_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            original = directory / "original"
            original.write_bytes(b"protected")
            link = directory / "link"
            try:
                link.symlink_to(original)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with self.assertRaises(ValueError):
                export_custody_envelope(link, plan_digest="a" * 64,
                                       ledger_checkpoint=(0, "0" * 64))
            self.assertEqual(original.read_bytes(), b"protected")

    def test_bad_plan_digest_never_creates_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "anchor.json"
            with self.assertRaises(ValueError):
                export_custody_envelope(target, plan_digest="invalid",
                                       ledger_checkpoint=(0, "0" * 64))
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
