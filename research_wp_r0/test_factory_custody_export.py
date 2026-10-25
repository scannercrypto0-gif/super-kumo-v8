"""Portable custody export tests, including restart and tamper detection."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.factory_custody_export import export_custody_envelope, verify_exported_custody


class CustodyExportTests(unittest.TestCase):
    def test_export_and_verify_after_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "anchor.json"
            export_custody_envelope(destination, plan_digest="a" * 64,
                                   ledger_checkpoint=(2, "b" * 64))
            self.assertEqual(verify_exported_custody(
                destination, plan_digest="a" * 64,
                ledger_checkpoint=(2, "b" * 64))["ledger_sequence"], 2)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "anchor.json"
            export_custody_envelope(destination, plan_digest="a" * 64,
                                   ledger_checkpoint=(0, "0" * 64))
            with self.assertRaises(ValueError):
                export_custody_envelope(destination, plan_digest="a" * 64,
                                       ledger_checkpoint=(1, "b" * 64))

    def test_tampered_anchor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "anchor.json"
            export_custody_envelope(destination, plan_digest="a" * 64,
                                   ledger_checkpoint=(0, "0" * 64))
            destination.write_bytes(b'{"tampered":true}')
            with self.assertRaises(ValueError):
                verify_exported_custody(destination, plan_digest="a" * 64,
                                        ledger_checkpoint=(0, "0" * 64))

    def test_wrong_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "anchor.json"
            export_custody_envelope(destination, plan_digest="a" * 64,
                                   ledger_checkpoint=(0, "0" * 64))
            with self.assertRaises(ValueError):
                verify_exported_custody(destination, plan_digest="a" * 64,
                                        ledger_checkpoint=(1, "b" * 64))


if __name__ == "__main__":
    unittest.main()
