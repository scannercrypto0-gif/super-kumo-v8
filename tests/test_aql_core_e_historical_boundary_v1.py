import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_core_e_historical_boundary_v1 import (
    BLOCKED, VERIFIED, preflight_historical_source, verify_preflight_receipt,
)


class HistoricalBoundaryTests(unittest.TestCase):
    def test_missing_original_fails_closed(self):
        receipt = preflight_historical_source(
            zip_path=None, publisher_checksum_sha256=None,
            dataset_id="BTCUSDT-2024-03", source_kind="ORIGINAL_PUBLISHER")
        self.assertEqual(receipt["status"], BLOCKED)
        self.assertTrue(verify_preflight_receipt(receipt))

    def test_synthetic_never_promoted_even_with_matching_checksum(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "synthetic.zip"
            p.write_bytes(b"test-only")
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            receipt = preflight_historical_source(
                zip_path=p, publisher_checksum_sha256=sha,
                dataset_id="AAA-TEST", source_kind="SYNTHETIC_TEST_ONLY")
            self.assertEqual(receipt["status"], BLOCKED)
            self.assertEqual(receipt["reason"], "SYNTHETIC_NEVER_HISTORICAL")

    def test_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "original.zip"
            p.write_bytes(b"untrusted")
            receipt = preflight_historical_source(
                zip_path=p, publisher_checksum_sha256="0" * 64,
                dataset_id="BTCUSDT-2024-03", source_kind="ORIGINAL_PUBLISHER")
            self.assertEqual(receipt["status"], BLOCKED)
            self.assertEqual(receipt["reason"], "PUBLISHER_CHECKSUM_MISMATCH")

    def test_matching_bytes_custody_only_never_pit(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "original.zip"
            p.write_bytes(b"fixture not actual publisher history")
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            receipt = preflight_historical_source(
                zip_path=p, publisher_checksum_sha256=sha,
                dataset_id="FIXTURE-ONLY", source_kind="ORIGINAL_PUBLISHER")
            self.assertEqual(receipt["status"], VERIFIED)
            self.assertEqual(receipt["historical_pit"], "NOT_ATTESTED")
            self.assertEqual(receipt["trading_authority"], "NONE")
            self.assertTrue(verify_preflight_receipt(receipt))
            receipt["dataset_id"] = "swapped"
            self.assertFalse(verify_preflight_receipt(receipt))

    def test_invalid_identity_and_timeframe(self):
        for dataset, timeframe in [("", "15m"), ("BTCUSDT", "1m")]:
            with self.assertRaises(ValueError):
                preflight_historical_source(
                    zip_path=None, publisher_checksum_sha256=None,
                    dataset_id=dataset, source_kind="ORIGINAL_PUBLISHER",
                    expected_timeframe=timeframe)

    def test_missing_file_and_checksum_are_blocked(self):
        for path, checksum in [("/not/available.zip", "a" * 64), (None, "invalid")]:
            receipt = preflight_historical_source(
                zip_path=path, publisher_checksum_sha256=checksum,
                dataset_id="BTCUSDT-2024-03", source_kind="ORIGINAL_PUBLISHER")
            self.assertEqual(receipt["status"], BLOCKED)
            self.assertTrue(verify_preflight_receipt(receipt))

    def test_malformed_verified_receipt_never_raises(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "original.zip"
            p.write_bytes(b"synthetic fixture bytes only")
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            original = preflight_historical_source(
                zip_path=p, publisher_checksum_sha256=sha,
                dataset_id="TEST-NOT-PUBLISHER", source_kind="ORIGINAL_PUBLISHER")
            for bad in (None, 3, [], {}, True):
                attempt = dict(original)
                attempt["publisher_checksum_sha256"] = bad
                self.assertFalse(verify_preflight_receipt(attempt))
            for bad in (None, 7, False):
                attempt = dict(original)
                attempt["source_sha256"] = bad
                self.assertFalse(verify_preflight_receipt(attempt))


if __name__ == "__main__":
    unittest.main()
