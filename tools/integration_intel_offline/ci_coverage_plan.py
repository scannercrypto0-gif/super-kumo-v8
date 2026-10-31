"""Stage 6 — CI/test coverage plan generator.

Read-only analysis: proposes a targeted test matrix for each PR in the snapshot.
Does NOT run tests, rewrite workflows, or touch protected paths.
Emits COVERAGE_GAP when a PR lacks recorded acceptance evidence.
Emits WORKFLOW_CONCERN when PR changes .github/workflows/ without test evidence.
Never issues a merge recommendation.
"""
from __future__ import annotations
from typing import Literal

CoverageLabel = Literal[
    "COVERAGE_ADEQUATE",
    "COVERAGE_GAP",
    "WORKFLOW_CONCERN",
    "PROTECTED_PATH_CONCERN",
    "UNKNOWN",
]

_WORKFLOW_PREFIXES = (".github/workflows/", ".github/actions/")
_TEST_PREFIXES = ("tests/", "test_", "_test.py")


def _touches_workflows(paths: list[str]) -> bool:
    return any(p.startswith(wp) for p in paths for wp in _WORKFLOW_PREFIXES)


def _touches_tests(paths: list[str]) -> bool:
    return any(
        p.startswith("tests/") or p.endswith("_test.py") or "/test_" in p
        for p in paths
    )


def _touches_protected(paths: list[str]) -> bool:
    from tools.integration_intel_offline.denylist import classify_path
    return any(classify_path(p).status == "PROTECTED" for p in paths)


def analyze_pr_coverage(
    pr_number: int,
    changed_paths: list[str],
    evidence_entries: list[dict],
) -> dict:
    """Return coverage assessment for a single PR.

    evidence_entries: list of EvidenceEntry.to_dict() dicts for this PR.
    """
    has_verified = any(e["status"] == "VERIFIED" for e in evidence_entries)
    has_independent = any(
        e["status"] == "VERIFIED" and e["level"] == "INDEPENDENT_AUDIT"
        for e in evidence_entries
    )
    workflow_concern = _touches_workflows(changed_paths) and not has_verified
    protected_concern = _touches_protected(changed_paths)
    touches_tests = _touches_tests(changed_paths)

    if protected_concern and not has_verified:
        label: CoverageLabel = "PROTECTED_PATH_CONCERN"
        notes = (
            f"PR #{pr_number} touches protected paths without verified acceptance evidence. "
            "Owner authorization required before any review action."
        )
    elif workflow_concern:
        label = "WORKFLOW_CONCERN"
        notes = (
            f"PR #{pr_number} modifies CI/workflow files. "
            "No verified test evidence found — risk of silent CI breakage."
        )
    elif not has_verified:
        label = "COVERAGE_GAP"
        notes = (
            f"PR #{pr_number} has no verified acceptance evidence recorded. "
            "Recommend: run unit tests, record result, re-analyze."
        )
    elif not has_independent:
        label = "COVERAGE_ADEQUATE"
        notes = (
            f"PR #{pr_number} has verified evidence (level: self-attested). "
            "Independent audit pending — recommend before final review."
        )
    else:
        label = "COVERAGE_ADEQUATE"
        notes = f"PR #{pr_number} has verified independent audit evidence."

    proposed_tests: list[str] = []
    if not touches_tests:
        proposed_tests.append(f"pytest tests/ -x -q  # no test files changed in PR #{pr_number}")
    for path in changed_paths:
        if path.endswith(".py") and not path.startswith("tests/"):
            test_guess = "tests/" + path.replace("tools/", "").replace(".py", "_test.py")
            proposed_tests.append(f"pytest {test_guess} -x -q  # targeted")

    return {
        "pr_number": pr_number,
        "coverage_label": label,
        "has_verified_evidence": has_verified,
        "has_independent_audit": has_independent,
        "touches_workflow_files": _touches_workflows(changed_paths),
        "touches_protected_paths": protected_concern,
        "proposed_test_commands": proposed_tests[:5],  # cap at 5
        "notes": notes,
        "classification": "COVERAGE_ANALYSIS_ONLY__NOT_A_TEST_EXECUTION",
    }


def analyze_snapshot_coverage(
    prs_with_paths: list[dict],
    evidence_by_pr: dict[int, list[dict]],
) -> list[dict]:
    """Coverage analysis for all PRs in snapshot.

    prs_with_paths: list of {number, changed_paths}
    evidence_by_pr: {pr_number: [EvidenceEntry.to_dict(), ...]}
    """
    return [
        analyze_pr_coverage(
            pr["number"],
            pr.get("changed_paths", []),
            evidence_by_pr.get(pr["number"], []),
        )
        for pr in prs_with_paths
    ]
