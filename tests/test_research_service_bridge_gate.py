import json
import tempfile
import unittest
from pathlib import Path

from aql.research_service_bridge_gate import inspect_service_bridge


class BridgeGateTest(unittest.TestCase):
    def test_missing_receipts_cannot_certify_1m(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_service_bridge(Path(tmp) / "missing")
            self.assertFalse(result["research_source_compatible"])

    def test_sanitized_service_receipt_cannot_be_promoted_to_ohlc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "100.json").write_text(json.dumps({
                "schema": "atlas.live-research-service.receipt.v1",
                "retention": "SANITIZED_RECEIPTS_ONLY",
            }), encoding="utf-8")
            result = inspect_service_bridge(root)
            self.assertEqual(result["service_receipts_seen"], 1)
            self.assertFalse(result["research_source_compatible"])
            self.assertEqual(result["original_1m_ohlcv"], "NOT_ATTESTED")

    def test_unknown_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "100.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "RECEIPT_SCHEMA_UNEXPECTED"):
                inspect_service_bridge(root)


if __name__ == "__main__":
    unittest.main()
