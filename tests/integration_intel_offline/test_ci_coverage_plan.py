"""Stage 6 — CI/test coverage plan tests."""
import pytest
from tools.integration_intel_offline.ci_coverage_plan import (
    analyze_pr_coverage, analyze_snapshot_coverage,
)


def verified_entry(level="W1"):
    return {"status": "VERIFIED", "level": level}


class TestAnalyzePrCoverage:
    def test_no_evidence_is_gap(self):
        r = analyze_pr_coverage(1, ["src/foo.py"], [])
        assert r["coverage_label"] == "COVERAGE_GAP"

    def test_pending_evidence_is_gap(self):
        r = analyze_pr_coverage(1, ["src/foo.py"], [{"status": "PENDING", "level": "W1"}])
        assert r["coverage_label"] == "COVERAGE_GAP"

    def test_verified_no_independent_is_adequate(self):
        r = analyze_pr_coverage(1, ["src/foo.py"], [verified_entry("W1")])
        assert r["coverage_label"] == "COVERAGE_ADEQUATE"
        assert r["has_independent_audit"] is False

    def test_verified_independent_audit_adequate(self):
        r = analyze_pr_coverage(1, ["src/foo.py"], [verified_entry("INDEPENDENT_AUDIT")])
        assert r["coverage_label"] == "COVERAGE_ADEQUATE"
        assert r["has_independent_audit"] is True

    def test_workflow_concern_without_evidence(self):
        r = analyze_pr_coverage(1, [".github/workflows/ci.yml"], [])
        assert r["coverage_label"] == "WORKFLOW_CONCERN"

    def test_workflow_no_concern_with_evidence(self):
        r = analyze_pr_coverage(1, [".github/workflows/ci.yml"], [verified_entry()])
        # has verified evidence → adequate (not workflow concern)
        assert r["coverage_label"] == "COVERAGE_ADEQUATE"

    def test_protected_path_concern(self):
        r = analyze_pr_coverage(1, ["src/aql/foo.py"], [])
        assert r["coverage_label"] == "PROTECTED_PATH_CONCERN"

    def test_proposed_tests_capped(self):
        paths = [f"src/module_{i}.py" for i in range(10)]
        r = analyze_pr_coverage(1, paths, [])
        assert len(r["proposed_test_commands"]) <= 5

    def test_classification_label(self):
        r = analyze_pr_coverage(1, ["src/foo.py"], [])
        assert "NOT_A_TEST_EXECUTION" in r["classification"]


class TestAnalyzeSnapshotCoverage:
    def test_two_prs(self):
        prs = [
            {"number": 1, "changed_paths": ["src/a.py"]},
            {"number": 2, "changed_paths": ["src/b.py"]},
        ]
        evidence = {1: [verified_entry()], 2: []}
        results = analyze_snapshot_coverage(prs, evidence)
        assert len(results) == 2
        labels = {r["pr_number"]: r["coverage_label"] for r in results}
        assert labels[1] == "COVERAGE_ADEQUATE"
        assert labels[2] == "COVERAGE_GAP"
