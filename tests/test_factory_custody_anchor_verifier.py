"""Offline custody verifier contract tests. Not proof of protected storage."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.custody_anchor_verifier import verify_custody_bundle


class CustodyAnchorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "bundle"
        self.root.mkdir()
        self.anchor = Path(self.tmp.name) / "anchor.sha256"
        (self.root / "evidence.txt").write_bytes(b"synthetic evidence")
        self.manifest = {"schema": "atlas-custody-v1", "files": [
            {"path": "evidence.txt", "sha256": hashlib.sha256(b"synthetic evidence").hexdigest()}]}
        self.refresh()

    def refresh(self):
        raw = json.dumps(self.manifest, sort_keys=True).encode()
        (self.root / "custody-manifest.json").write_bytes(raw)
        self.anchor.write_text(hashlib.sha256(raw).hexdigest(), encoding="ascii")

    def test_valid_content_not_independent_custody(self):
        result = verify_custody_bundle(self.root, self.anchor)
        self.assertEqual(result["file_count"], 1)
        self.assertTrue(result["content_verified"])
        self.assertFalse(result["independent_custody_verified"])

    def test_tampered_evidence_rejected(self):
        (self.root / "evidence.txt").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            verify_custody_bundle(self.root, self.anchor)

    def test_tampered_manifest_rejected(self):
        (self.root / "custody-manifest.json").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            verify_custody_bundle(self.root, self.anchor)

    def test_traversal_and_duplicates_rejected(self):
        for name in ("../outside", "sub/../evidence.txt", "/absolute"):
            self.manifest["files"][0]["path"] = name
            self.refresh()
            with self.assertRaises(ValueError):
                verify_custody_bundle(self.root, self.anchor)
        self.manifest["files"][0]["path"] = "evidence.txt"
        self.manifest["files"].append(dict(self.manifest["files"][0]))
        self.refresh()
        with self.assertRaises(ValueError):
            verify_custody_bundle(self.root, self.anchor)

    def test_extra_file_and_anchor_inside_bundle_rejected(self):
        (self.root / "unlisted.txt").write_bytes(b"x")
        with self.assertRaises(ValueError):
            verify_custody_bundle(self.root, self.anchor)
        (self.root / "unlisted.txt").unlink()
        inside = self.root / "anchor.sha256"
        inside.write_text(self.anchor.read_text())
        with self.assertRaises(ValueError):
            verify_custody_bundle(self.root, inside)


if __name__ == "__main__":
    unittest.main()
