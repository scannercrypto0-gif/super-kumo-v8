"""Official Binance H2 provenance: synthetic-only publisher ZIP + checksum tests."""
from __future__ import annotations
import hashlib
import hmac
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from tools.atlas_h2_owner_local_one_shot_v1 import digest
from tools.atlas_h2_binance_public_lane_v1 import (
    ROOT, LANE_SCHEMA, LICENSE_SCHEMA, TERMS_URL,
    Blocked, checksum_parse, filename_for_month, verify_public_month,
    run_public_batch, safe_zip, technical_intake, verified_license,
)


class OfficialBinanceLane(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "intake"
        self.private.mkdir()
        self.output = self.root / "output"
        self.output.mkdir()
        self.month = "2024-03"
        self.filename = filename_for_month(self.month)
        self.begin = 1709251200000
        self.grid = self._grid(31 * 96)
        self.zip = self._zip(self.grid)
        self.sha = hashlib.sha256(self.zip).hexdigest()
        self.checksum = (self.sha + "  " + self.filename + "\n").encode()

    def _grid(self, count):
        return b"".join(
            (str(self.begin + i * 900000) +
             ",1,2,0.5,1.5,30,1709252099999,20,5,4,5,0\n").encode()
            for i in range(count)
        )

    def _zip(self, data):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(self.filename[:-4] + ".csv", data)
        return buf.getvalue()

    def fetch(self, uri, size):
        if uri == ROOT + self.filename:
            return self.zip
        if uri == ROOT + self.filename + ".CHECKSUM":
            return self.checksum
        raise AssertionError("UNEXPECTED_OFFICIAL_URL")

    def _intake(self):
        rows = [
            {"bar_open_ms": self.begin + i * 900000,
             "bar_close_ms": self.begin + (i + 1) * 900000 - 1}
            for i in range(31 * 96)
        ]
        native = {
            "schema": "aql.core.historical-price-custody-query.v1",
            "status": "OK", "coverage": "COMPLETE",
            "dataset_id": "BINANCE-SPOT-BTCUSDT-15M-2024-03",
            "version": 1, "source_bytes_sha256": self.sha,
            "manifest_integrity_sha256": "b"*64,
            "decision_cutoff_ms": 1711929600000,
            "required_bar_count": len(rows),
            "available_bar_count": len(rows),
            "missing_bar_opens": [], "bars": rows,
        }
        native["price_query_sha256"] = digest(native)
        (self.private / "core245-native-receipt.json").write_text(
            json.dumps(native))
        (self.private / "manual-third-ast.json").write_text("{}")
        sha = lambda name: hashlib.sha256(
            (self.private / name).read_bytes()).hexdigest()
        tech = {
            "schema": LANE_SCHEMA, "owner_authorization_ref": "#205/6718325330",
            "one_time_scope_authorized": True,
            "warehouse_root": str(self.root/"original-warehouse"),
            "vault_root": str(self.root/"original-vault"),
            "local_source_zip": str(self.root/"original-zip"),
            "dataset_id": "BINANCE-SPOT-BTCUSDT-15M-2024-03",
            "version": 1, "month": self.month,
            "start_ms": self.begin, "end_exclusive_ms": 1711929600000,
            "decision_cutoff_ms": 1711929600000,
            "source_bytes_sha256": self.sha,
            "manifest_integrity_sha256": "b"*64,
            "native_receipt_file_sha256": sha("core245-native-receipt.json"),
            "strategy_file_sha256": sha("manual-third-ast.json"),
            "strategy_definition_sha256": "c"*64,
            "strategy_id": "h_manual_test",
            "factory_code_sha256": "d"*64,
            "experiment_id": "RESEARCH-H-GENERIC-SYNTHETIC",
        }
        (self.private/"technical-intake.json").write_text(json.dumps(tech))
        (self.private/"historical-license-evidence.json").write_text("{}")
        (self.private/"historical-terms.txt").write_text("synthetic 2024 terms: TEST ONLY")
        (self.private/"historical-license-evidence.mac").write_text("invalid")
        return tech

    def test_valid_public_zip_and_checksum_bound_to_exact_filename(self):
        p = verify_public_month(self.month, fetcher=self.fetch)
        self.assertEqual(p["zip_bytes_sha256"], self.sha)
        self.assertEqual(p["publisher_checksum_sha256"], self.sha)
        self.assertEqual(p["bar_count"], 2976)
        self.assertEqual(p["publisher_cryptographic_signature"], "NOT_PRESENT")

    def test_partial_month_even_valid_checksum_is_rejected(self):
        self.zip = self._zip(self._grid(4))
        self.checksum = (hashlib.sha256(self.zip).hexdigest()
                         + "  " + self.filename).encode()
        with self.assertRaisesRegex(Blocked, "OFFICIAL_NOT_COMPLETE_CALENDAR_MONTH"):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_tampered_zip_is_rejected(self):
        self.zip = self.zip + b"alter"
        with self.assertRaisesRegex(Blocked, "OFFICIAL_ZIP_CHECKSUM_MISMATCH"):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_tampered_checksum_is_rejected(self):
        self.checksum = (("e"*64) + "  " + self.filename).encode()
        with self.assertRaisesRegex(Blocked, "OFFICIAL_ZIP_CHECKSUM_MISMATCH"):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_cross_month_checksum_cannot_substitute(self):
        self.checksum = (self.sha + "  BTCUSDT-15m-2024-04.zip").encode()
        with self.assertRaisesRegex(Blocked, "OFFICIAL_CHECKSUM_CONTENT_MISMATCH"):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_fake_traversal_checksum_fails(self):
        self.checksum = (self.sha + "  ../" + self.filename).encode()
        with self.assertRaises(Blocked):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_sparse_csv_is_rejected(self):
        sparse = self._grid(1) + (
            str(self.begin + 3 * 900000) +
            ",1,2,0.5,1.5,30,1709252099999,20,5,4,5,0\n").encode()
        self.zip = self._zip(sparse)
        self.checksum = (hashlib.sha256(self.zip).hexdigest()
                         + "  " + self.filename).encode()
        with self.assertRaisesRegex(Blocked, "OFFICIAL_KLINE_GAP_OR_DUPLICATE"):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_invalid_zip_member_refused(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as z:
            z.writestr("../bad.csv", self.grid)
        self.zip = raw.getvalue()
        self.checksum = (hashlib.sha256(self.zip).hexdigest()
                         + "  " + self.filename).encode()
        with self.assertRaisesRegex(Blocked, "OFFICIAL_ZIP_MEMBER_UNSAFE"):
            verify_public_month(self.month, fetcher=self.fetch)

    def test_wrong_month_is_rejected_without_network(self):
        with self.assertRaisesRegex(Blocked, "OFFICIAL_MONTH_FORMAT"):
            filename_for_month("../../etc")

    def test_real_e_is_never_read_when_technical_index_absent(self):
        with patch("pathlib.Path.read_bytes",
                   side_effect=AssertionError("private IO should not run")):
            r = run_public_batch(self.private, self.output, fetcher=self.fetch)
        self.assertEqual(r["status"], "BLOCKED")
        self.assertEqual(r["source_read_status"], "NOT_ATTEMPTED")
        self.assertIn("MISSING_PUBLIC_LANE_EVIDENCE:", r["reasons"][0])

    def test_public_archive_proof_does_not_bypass_legal(self):
        tech = self._intake()
        report = run_public_batch(self.private, self.output, fetcher=self.fetch)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("WAIT_LICENSE_REVIEWER_KEY", report["reasons"])
        self.assertEqual(report["details"]["official_zip_sha256"], self.sha)
        self.assertFalse(report["source_read"])
        self.assertNotIn("local_source_zip", str(report))

    def test_legal_self_declaration_is_not_independent_verification(self):
        doc = {
            "schema": LICENSE_SCHEMA,
            "issuer": "BINANCE_DATASET_RIGHTS_AUTHORITY",
            "terms_url": TERMS_URL, "terms_sha256": "a"*64,
            "applies_to_download_year": 2024, "download_year": 2024,
            "intended_use": "PERSONAL_NONCOMMERCIAL_RESEARCH",
            "permitted_use": "PERSONAL_NONCOMMERCIAL_RESEARCH",
            "status": "INDEPENDENTLY_VERIFIED", "issued_at_utc": "2024-05-01",
            "signed_by": "EXTERNAL_COUNTERSIGNER",
            "signature_ref": "verified-external:sample",
        }
        # A string saying "verified" never authenticates itself.
        self.assertEqual(len(verified_license(doc, 2024)), 64)
        self._intake()
        (self.private/"historical-license-evidence.json").write_text(
            json.dumps(doc))
        blocked = run_public_batch(self.private, self.output, fetcher=self.fetch)
        self.assertEqual(blocked["reasons"], ["WAIT_LICENSE_REVIEWER_KEY"])

    def _synthetic_signed_rights(self):
        self._intake()
        source = self.root / "original-zip"
        source.mkdir()
        archive = source / self.filename
        archive.write_bytes(self.zip)
        technical_path = self.private / "technical-intake.json"
        technical = json.loads(technical_path.read_text())
        technical["local_source_zip"] = str(archive)
        technical_path.write_text(json.dumps(technical))
        license_doc = {
            "schema": LICENSE_SCHEMA,
            "issuer": "BINANCE_DATASET_RIGHTS_AUTHORITY",
            "terms_url": TERMS_URL,
            "terms_sha256": hashlib.sha256((self.private/"historical-terms.txt").read_bytes()).hexdigest(),
            "applies_to_download_year": 2024, "download_year": 2024,
            "intended_use": "PERSONAL_NONCOMMERCIAL_RESEARCH",
            "permitted_use": "PERSONAL_NONCOMMERCIAL_RESEARCH",
            "status": "INDEPENDENTLY_VERIFIED", "issued_at_utc": "2024-06-01",
            "signed_by": "EXTERNAL_SYNTHETIC_REVIEWER",
            "signature_ref": "verified-external:synthetic-test-only",
        }
        raw = json.dumps(license_doc).encode()
        (self.private/"historical-license-evidence.json").write_bytes(raw)
        reviewer = self.root/"independent-reviewer.key"
        reviewer.write_bytes(b"r"*32)
        owner = self.root/"owner.key"
        owner.write_bytes(b"o"*32)
        (self.private/"historical-license-evidence.mac").write_text(
            hmac.new(b"r"*32, raw, hashlib.sha256).hexdigest())
        return reviewer, owner, archive

    def test_signed_external_license_and_source_match_reaches_existing_operator(self):
        reviewer, owner, archive = self._synthetic_signed_rights()
        with patch("tools.atlas_h2_binance_public_lane_v1.execute",
                   return_value={"status":"EXPERIMENT_ENGINEERING_PASS",
                                 "sha256":"f"*64,"reason":"SYNTHETIC_MOCK"}) as worker:
            report = run_public_batch(
                self.private, self.output, fetcher=self.fetch,
                reviewer_key=reviewer, owner_key=owner,
                git_repo=self.root/"isolated-repo", confirm_one_run=True)
        self.assertEqual(report["status"], "PASS_ENGINEERING_ONLY")
        self.assertEqual(worker.call_count, 1)
        self.assertTrue((self.private/"h2-public-lane-one-use-claim.json").exists())
        # Calling again cannot consume the same one-run owner permission.
        with patch("tools.atlas_h2_binance_public_lane_v1.execute",
                   side_effect=AssertionError("ONE_RUN_REPLAY")):
            retry = run_public_batch(
                self.private, self.output, fetcher=self.fetch,
                reviewer_key=reviewer, owner_key=owner,
                git_repo=self.root/"other-output", confirm_one_run=True)
        self.assertEqual(retry["reasons"], ["ONE_RUN_ALREADY_RESERVED"])

    def test_owner_archive_content_mismatch_blocks_without_operator(self):
        reviewer, owner, archive = self._synthetic_signed_rights()
        archive.write_bytes(self.zip + b"owner-original-drift")
        with patch("tools.atlas_h2_binance_public_lane_v1.execute",
                   side_effect=AssertionError("NOT_AUTHORIZED")):
            report = run_public_batch(
                self.private, self.output, fetcher=self.fetch,
                reviewer_key=reviewer, owner_key=owner,
                git_repo=self.root/"isolated-repo", confirm_one_run=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(
            report["reasons"],
            ["OWNER_ORIGINAL_ZIP_DIFFERS_FROM_OFFICIAL_PUBLISHER"])
        self.assertFalse((self.private/"h2-public-lane-one-use-claim.json").exists())

    def test_license_terms_tampering_blocked_before_original_zip_read(self):
        reviewer, owner, archive = self._synthetic_signed_rights()
        (self.private/"historical-terms.txt").write_text("tampered")
        with patch("tools.atlas_h2_binance_public_lane_v1.execute",
                   side_effect=AssertionError("NOT_AUTHORIZED")):
            report = run_public_batch(
                self.private, self.output, fetcher=self.fetch,
                reviewer_key=reviewer, owner_key=owner,
                git_repo=self.root/"isolated-repo", confirm_one_run=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reasons"],
                         ["WAIT_HISTORICAL_TERMS_BYTES_AND_SHA"])
        self.assertFalse((self.private/"h2-public-lane-one-use-claim.json").exists())

    def test_local_zip_drift_never_calls_operator(self):
        self._intake()
        # Even if technical metadata is untrusted, absent independent reviewer
        # license must fail before accessing original ZIP.
        with patch("tools.atlas_h2_binance_public_lane_v1.execute",
                   side_effect=AssertionError("NO_LOCAL_SOURCE")):
            report = run_public_batch(
                self.private, self.output, fetcher=self.fetch)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["source_read"])

    def test_unknown_native_and_ast_are_required(self):
        self._intake()
        (self.private/"manual-third-ast.json").unlink()
        r = run_public_batch(self.private, self.output, fetcher=self.fetch)
        self.assertIn("MISSING_PUBLIC_LANE_EVIDENCE:", r["reasons"][0])

    def test_parent_digest_drift_blocks_before_private_source(self):
        self._intake()
        (self.private/"manual-third-ast.json").write_text('{"different":1}')
        r = run_public_batch(self.private, self.output, fetcher=self.fetch)
        self.assertEqual(r["reasons"], ["PRIVATE_EVIDENCE_HASH_DRIFT"])


if __name__ == "__main__":
    unittest.main()
