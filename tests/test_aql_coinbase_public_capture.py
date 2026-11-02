"""Offline tests: no network, no trading, and no journal authority changes."""
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_coinbase_public_capture import capture


class CaptureTests(unittest.TestCase):
    def test_one_request_retains_raw_and_reports_unverified(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            now = (1800000000 + 900) * 1000
            raw = json.dumps([[1800000000, 100, 110, 102, 108, 15]]).encode()
            def request(url):
                calls.append(url)
                return raw
            out = Path(root) / "capture"
            result = capture(product_id="BTC-USD", folder=out, request=request, now_ms=now)
            self.assertEqual(result["status"], "UNVERIFIED_CAPTURED")
            self.assertFalse(result["collector_journal_connected"])
            self.assertFalse(result["binance_execution_price_verified"])
            self.assertEqual((out / "raw-response.json").read_bytes(), raw)
            self.assertTrue((out / "normalized-bars.json").exists())\n            self.assertIn("normalized_sha256", result)\n            self.assertEqual(len(calls), 1)
            self.assertIn("granularity=900", calls[0])

    def test_malformed_response_fails_closed_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "capture"
            result = capture(product_id="BTC-USD", folder=out,
                             request=lambda _: b'{"error":"unavailable"}',
                             now_ms=(1800000000 + 900) * 1000)
            self.assertEqual(result["status"], "NOT_ESTABLISHED")
            self.assertEqual((out / "raw-response.json").read_bytes(),
                             b'{"error":"unavailable"}')

    def test_transport_error_still_records_failure(self):
        with tempfile.TemporaryDirectory() as root:
            def fail(_):
                raise ConnectionError("restricted")
            out = Path(root) / "capture"
            result = capture(product_id="BTC-USD", folder=out, request=fail,
                             now_ms=(1800000000 + 900) * 1000)
            self.assertEqual(result["status"], "NOT_ESTABLISHED")
            self.assertTrue((out / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
