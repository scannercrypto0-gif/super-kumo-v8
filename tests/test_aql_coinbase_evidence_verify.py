"""Focused offline integrity checks for Coinbase evidence."""
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_coinbase_public_capture import capture
from research_wp_r0.aql_coinbase_evidence_verify import CoinbaseEvidenceError, verify_capture


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "capture"
        self.now = (1800000000 + 900) * 1000
        self.raw = json.dumps([[1800000000, 100, 110, 102, 108, 15]]).encode()
        result = capture(product_id="BTC-USD", folder=self.folder,
                         request=lambda _: self.raw, now_ms=self.now)
        self.assertEqual(result["status"], "UNVERIFIED_CAPTURED")

    def test_verified_source_is_still_not_pit_or_journal(self):
        verified = verify_capture(self.folder)
        self.assertEqual(verified["status"], "LOCAL_UNVERIFIED_EVIDENCE_VERIFIED")
        self.assertFalse(verified["journal_connected"])
        self.assertEqual(verified["external_pit"], "NOT_ESTABLISHED")

    def test_modified_raw_rejected(self):
        (self.folder / "raw-response.json").write_bytes(b"[]")
        with self.assertRaisesRegex(CoinbaseEvidenceError, "CONTENT_HASH_MISMATCH"):
            verify_capture(self.folder)

    def test_modified_normalized_rejected(self):
        (self.folder / "normalized-bars.json").write_bytes(b"[]")
        with self.assertRaisesRegex(CoinbaseEvidenceError, "CONTENT_HASH_MISMATCH"):
            verify_capture(self.folder)


if __name__ == "__main__":
    unittest.main()
