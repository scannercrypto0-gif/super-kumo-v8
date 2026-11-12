"""Focused offline negative and positive controls for anti-redo."""
import importlib.util
import pathlib
import tempfile
import unittest
import json

spec = importlib.util.spec_from_file_location("gate", pathlib.Path(__file__).with_name("anti_redo_gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = "a" * 40
CID = "FACTORY.ATTEMPT"

def record(proof="UNKNOWN", disposition="INVENTORY_REQUIRED"):
    return {
        "task": "Review existing writer", "capability_ids": [CID], "main_sha": SHA,
        "head_pins": {CID: SHA}, "lookups": ["PR #78"], "crosswalk": "Existing writer reused",
        "owner": "PM", "owner_handoff": "Owner handoff", "later_decisions": ["Owner B"],
        "changed_seam": "No changed seam", "proof": proof, "tests_reused": [],
        "new_tests": [], "authority": "Review only", "rollback": "Withdraw task",
        "overlap_review": "Source inspected", "disposition": disposition,
    }

class GateTests(unittest.TestCase):
    def check(self, r):
        return gate.validate(r, {CID}, SHA, {CID: SHA})

    def test_unknown_requires_inventory(self):
        self.assertEqual(self.check(record()), [])

    def test_duplicate_blocked(self):
        self.assertEqual(self.check(record("DUPLICATE_OVERLAP", "BLOCKED_DUPLICATE_RISK")), [])

    def test_proof_mismatch_rejected(self):
        self.assertIn("proof/disposition mismatch", self.check(record("DUPLICATE_OVERLAP", "PROCEED_TO_APPROVAL")))

    def test_missing_capability_rejected(self):
        r = record()
        r["capability_ids"] = ["UNKNOWN.ID"]
        self.assertTrue(any("unknown capability" in x for x in self.check(r)))

    def test_stale_pin_rejected(self):
        r = record()
        r["head_pins"][CID] = "b" * 40
        self.assertTrue(any("stale head pin" in x for x in self.check(r)))

    def test_stale_main_rejected(self):
        r = record()
        r["main_sha"] = "b" * 40
        self.assertIn("stale main SHA", self.check(r))

    def test_reused_test_requires_exact_verification(self):
        r = record()
        r["tests_reused"] = ["CI-40101207446"]
        self.assertTrue(any("test/fixture/runner" in x for x in self.check(r)))

    def test_real_gap_requires_human_signoffs(self):
        r = record("REAL_GAP", "PROCEED_TO_APPROVAL")
        self.assertTrue(any("human signoffs" in x for x in self.check(r)))
        r["pm_approval_reference"] = "Issue #205"
        r["component_review_reference"] = "Factory owner"
        self.assertEqual(self.check(r), [])

    def test_invalid_override_rejected(self):
        r = record()
        r["override"] = {"pm": "PM", "component_owner": "Factory", "reason": "Different contract", "expires_utc": "never", "pinned_revision": SHA}
        self.assertTrue(any("override expiry" in x for x in self.check(r)))

    def test_code_change_without_record_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            base = root / "docs/pm/anti-redo"
            base.mkdir(parents=True)
            (base / "capabilities.json").write_text(json.dumps({"main_sha": SHA, "entries": [{"id": CID, "head": SHA}]}))
            (base / "coverage-manifest.json").write_text(json.dumps({"main_sha": SHA}))
            import subprocess
            import sys
            result = subprocess.run([sys.executable, str(pathlib.Path(gate.__file__)), "--root", temp, "--changed", "src/new_writer.py"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without a pre-assignment record", result.stderr)

if __name__ == "__main__":
    unittest.main()
