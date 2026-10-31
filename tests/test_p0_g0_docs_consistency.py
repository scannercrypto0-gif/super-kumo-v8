"""Focused consistency assertion for active G0 status docs (Audit #134 / docs #203)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestP0G0DocsConsistency(unittest.TestCase):
    def test_active_readme_and_reusable_startup_prompt(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        start = (ROOT / "00_START_HERE.md").read_text(encoding="utf-8")
        prompt = start.split("## Reusable startup prompt", 1)[1].split(
            "## Proactive documentation and Work handoff", 1
        )[0]
        gov = start.split("## Handoff continuity and completeness — G0-GOV-01", 1)[1].split(
            "## G0 reconciliation source map", 1
        )[0]
        readme_current = readme.split("## Current next step", 1)[1]
        for label, block in (
            ("README status", readme.split("## First read", 1)[0]),
            ("README current next step", readme_current),
            ("START current summary", start.split("## Canonical project identity", 1)[0]),
            ("START reusable prompt", prompt),
            ("START GOV-01 active guidance", gov),
        ):
            with self.subTest(section=label):
                self.assertIn("G0", block)
                self.assertIn("2026-10-22", block)
                self.assertIn("R09", block)
                self.assertNotIn("keep G0 OPEN", block)
                self.assertNotIn("G0 remains OPEN", block)
                self.assertNotIn("G0 and G0-001 remain OPEN", block)
        for label, block in (("README current next step", readme_current),
                             ("START reusable prompt", prompt),
                             ("START GOV-01 active guidance", gov)):
            with self.subTest(gate_separation=label):
                self.assertIn("G1", block)
        self.assertIn("G0 FINAL APPROVED", prompt)
        self.assertIn("G0 FINAL APPROVED", readme_current)
        self.assertIn("G0-GOV-01 rule remains owner-approved provisional", gov)


if __name__ == "__main__":
    unittest.main()
