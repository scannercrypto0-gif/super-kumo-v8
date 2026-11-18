"""Focused byte-level original Binance 15m ZIP acquisition gate tests.

Generated archives here are adversarial fixtures, NOT real issuer provenance.
"""
import hashlib
import io
import zipfile
import unittest

from research_wp_r0.aql_w1_external_raw_source_gate import inspect_original_raw_archive
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError

BAR = 900000
START = 1704067200000
NAME = "BTCUSDT-15m-2024-01-01.csv"


def archive(count=96, *, alter_index=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        rows = []
        for i in range(count):
            o = START + i*BAR
            row = [o, "100", "110", "95", "105", "12", o+BAR-1,
                   "12", "1", "2", "3", "0"]
            if alter_index is not None and i == alter_index:
                row[0] = o + 1
            rows.append(",".join(map(str,row)))
        z.writestr(NAME, ("\n".join(rows)+"\n").encode())
    return buffer.getvalue()


def check(raw, *, expected=None, issuer=None, manifest=None,
          custody=None, clock=None, count=96):
    digest = expected or hashlib.sha256(raw or b"").hexdigest()
    return inspect_original_raw_archive(
        raw, source_id="binance-vision:spot:BTCUSDT:15m:2024-01-01",
        expected_archive_sha256=digest, expected_member=NAME,
        expected_first_open_ms=START, expected_15m_bars=count,
        issuer_receipt_bytes=issuer,
        independently_retained_manifest_bytes=manifest,
        expected_manifest_sha256=hashlib.sha256(manifest).hexdigest()
        if manifest else None,
        verify_external_custody=custody,
        verify_independent_clock=clock)


class ExternalRawSourceTests(unittest.TestCase):
    def test_original_bytes_integrity_is_not_external_authority(self):
        raw = archive()
        result = check(raw)
        self.assertEqual(result["observed_archive_sha256"],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["integrity_status"], "ORIGINAL_BYTES_HASH_AND_GRID_MATCH")
        self.assertEqual(result["observed_15m_bars"], 96)
        self.assertEqual(result["external_evidence_status"], "BLOCKED_EXTERNAL_EVIDENCE")
        self.assertIn("INDEPENDENT_MANIFEST_BYTES_NOT_SUPPLIED", result["blockers"])
        self.assertFalse(result["independently_anchored"])

    def test_no_original_archive_stays_blocked(self):
        result = check(None, expected="a"*64)
        self.assertEqual(result["integrity_status"], "NOT_VERIFIED")
        self.assertIn("ORIGINAL_RAW_ZIP_BYTES_NOT_SUPPLIED", result["blockers"])

    def test_original_bytes_tampered_rejected(self):
        raw = archive()
        changed = raw+b"FORGED"
        result = check(changed, expected=hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["integrity_status"], "HASH_MISMATCH")
        self.assertFalse(result["independently_anchored"])

    def test_grid_discontinuity_rejected(self):
        with self.assertRaises(EvidenceError):
            check(archive(alter_index=10))

    def test_three_day_horizon_requires_288_bars(self):
        with self.assertRaises(EvidenceError):
            check(archive(), count=288)

    def test_missing_custodian_witness_stays_blocked(self):
        raw = archive()
        result = check(raw, issuer=b"fixture-receipt", manifest=b"fixture-manifest",
                       clock=lambda issuer, source: True)
        self.assertIn("EXTERNAL_CUSTODIAN_WITNESS_MISSING", result["blockers"])
        self.assertFalse(result["independently_anchored"])

    def test_synthetic_callbacks_do_not_count_as_audited_authority(self):
        raw = archive()
        result = check(raw, issuer=b"fixture-receipt", manifest=b"fixture-manifest",
                       custody=lambda *args: True, clock=lambda *args: True)
        self.assertEqual(result["external_evidence_status"],
                         "HOST_WITNESS_CALLBACK_AFFIRMED_NOT_AUDITED")
        self.assertTrue(result["independently_anchored"])
        self.assertNotEqual(result["external_evidence_status"], "VERIFIED_OPERATIONAL_PIT")

    def test_denied_clock_fails_closed(self):
        raw = archive()
        result = check(raw, issuer=b"fixture-receipt", manifest=b"fixture-manifest",
                       custody=lambda *args: True, clock=lambda *args: False)
        self.assertEqual(result["external_evidence_status"], "BLOCKED_EXTERNAL_EVIDENCE")
        self.assertFalse(result["independently_anchored"])


if __name__ == "__main__":
    unittest.main()
