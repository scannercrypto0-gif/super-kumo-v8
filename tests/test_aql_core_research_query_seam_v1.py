"""C3 contract/negative tests for the read-only research seam.

The existing 21 Bridge G6 tests remain the owner of source corruption,
correction lineage and interrupted resume scenarios; do not duplicate them.
"""
import unittest
from unittest.mock import patch

from research_wp_r0.aql_archive_custody_bridge_v1 import BridgeError
from research_wp_r0.aql_core_research_query_seam_v1 import (
    REQUEST_SCHEMA, SCHEMA, query_custody,
)
from research_wp_r0.historical_library import HistoricalLibrary


def request(**updates):
    value = {
        "schema": REQUEST_SCHEMA, "dataset_id": "TEST_BTCUSDT_1m",
        "version": 1, "start_ms": 0, "end_exclusive_ms": 60000,
        "decision_cutoff_ms": 60000, "require_complete": True,
        "confirmed_only": False,
    }
    value.update(updates)
    return value


class TestCoreResearchQuerySeam(unittest.TestCase):
    def setUp(self):
        self.library = HistoricalLibrary()

    def test_wrong_schema_rejected(self):
        self.assertEqual(query_custody(self.library, request(schema="bad"))["error"]["code"],
                         "UNSUPPORTED_REQUEST_SCHEMA")

    def test_missing_or_extra_fields_rejected(self):
        for payload in ({}, {**request(), "secret": "bad"}):
            with self.subTest(payload=payload):
                self.assertEqual(query_custody(self.library, payload)["error"]["code"],
                                 "INVALID_REQUEST_FIELDS")

    def test_bool_not_accepted_as_integer_timestamp_or_version(self):
        for field in ("start_ms", "end_exclusive_ms", "decision_cutoff_ms", "version"):
            with self.subTest(field=field):
                self.assertEqual(query_custody(self.library, request(**{field: True}))["status"], "ERROR")

    def test_invalid_cutoff_and_grid_rejected(self):
        self.assertEqual(query_custody(self.library, request(decision_cutoff_ms=-1))["status"], "ERROR")
        self.assertEqual(query_custody(self.library, request(end_exclusive_ms=0))["status"], "ERROR")

    def test_flags_must_be_bool(self):
        self.assertEqual(query_custody(self.library, request(confirmed_only=1))["status"], "ERROR")
        self.assertEqual(query_custody(self.library, request(require_complete=0))["status"], "ERROR")

    def test_missing_dataset_fails_closed(self):
        result = query_custody(self.library, request())
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "ERROR")
        self.assertIsNone(result["result"])
        self.assertEqual(result["evidence_class"], "NO_EVIDENCE")

    def test_bridge_cutoff_and_coverage_errors_are_structured(self):
        for code in ("INCOMPLETE_OR_FUTURE_CUSTODY_RANGE", "INVALID_QUERY_GRID"):
            with self.subTest(code=code), patch(
                "research_wp_r0.aql_core_research_query_seam_v1.custody_range",
                side_effect=BridgeError(code),
            ):
                result = query_custody(self.library, request())
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(result["error"]["category"], "CUSTODY")
                self.assertFalse(result["error"]["retryable"])

    def test_read_only_forwards_exact_result_without_pit_promotion(self):
        original = {
            "schema": "aql.bridge.custody-range.v1",
            "availability_class": "RETROSPECTIVE_NOT_PIT",
            "status": "PARTIAL",
            "source_bytes_sha256": "0" * 64,
            "manifest_integrity_sha256": "1" * 64,
            "missing_bar_opens": [60000],
            "version": 2,
        }
        with patch("research_wp_r0.aql_core_research_query_seam_v1.custody_range",
                   return_value=original) as mock:
            result = query_custody(self.library, request(version=2, require_complete=False))
        self.assertIs(result["result"], original)
        self.assertEqual(result["evidence_class"], "RETROSPECTIVE_NON_PIT")
        self.assertEqual(result["status"], "OK")
        mock.assert_called_once()

    def test_synthetic_and_confirmed_query_never_claim_attestation(self):
        for klass, expected in (
            ("SYNTHETIC_TEST", "SYNTHETIC_TEST"),
            ("CONFIRMED_ONLY", "CONFIRMED_ONLY_QUERY_NOT_ATTESTATION"),
        ):
            with self.subTest(klass=klass), patch(
                "research_wp_r0.aql_core_research_query_seam_v1.custody_range",
                return_value={"availability_class": klass},
            ):
                self.assertEqual(query_custody(self.library, request())["evidence_class"], expected)


if __name__ == "__main__":
    unittest.main()
