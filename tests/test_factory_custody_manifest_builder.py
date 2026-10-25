"""Manifest generation tests use synthetic files only."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.custody_manifest_builder import build_custody_manifest
from research_wp_r0.custody_anchor_verifier import verify_custody_bundle


class CustodyManifestBuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "bundle"
        self.root.mkdir()
        (self.root / "sample.txt").write_bytes(b"synthetic research")
        self.anchor = Path(self.tmp.name) / "external-anchor.sha256"

    def test_builder_verifier_roundtrip_and_no_custody_claim(self):
        result = build_custody_manifest(self.root)
        self.anchor.write_text(result["manifest_sha256"], encoding="ascii")
        verified = verify_custody_bundle(self.root, self.anchor)
        self.assertTrue(verified["content_verified"])
        self.assertFalse(verified["independent_custody_verified"])
        self.assertEqual(verified["file_count"], 1)

    def test_deterministic_across_equivalent_bundles(self):
        first = build_custody_manifest(self.root)
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        (other / "sample.txt").write_bytes(b"synthetic research")
        second = build_custody_manifest(other)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_nested_file_roundtrip(self):
        nested = self.root / "market"
        nested.mkdir()
        (nested / "bar.csv").write_bytes(b"synthetic,bar\\n")
        result = build_custody_manifest(self.root)
        self.anchor.write_text(result["manifest_sha256"], encoding="ascii")
        self.assertEqual(verify_custody_bundle(self.root, self.anchor)["file_count"], 2)

    def test_never_overwrites_manifest(self):
        build_custody_manifest(self.root)
        with self.assertRaises(FileExistsError):
            build_custody_manifest(self.root)

    def test_empty_bundle_rejected(self):
        (self.root / "sample.txt").unlink()
        with self.assertRaises(ValueError):
            build_custody_manifest(self.root)

    def test_symlink_directory_rejected_when_supported(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        try:
            (self.root / "linked").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            build_custody_manifest(self.root)

    def test_modified_evidence_detected_by_verifier(self):
        result = build_custody_manifest(self.root)
        self.anchor.write_text(result["manifest_sha256"], encoding="ascii")
        (self.root / "sample.txt").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            verify_custody_bundle(self.root, self.anchor)


if __name__ == "__main__":
    unittest.main()
