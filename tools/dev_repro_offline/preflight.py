"""
Stage 4 — Non-Mutating Preflight
Checks git state, line endings, required files, and interpreter.
NEVER switches branches, resets, installs packages, or makes any write.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class CheckStatus(str, Enum):
    PASS    = "PASS"
    FAIL    = "FAIL"
    WARN    = "WARN"
    SKIP    = "SKIP"


@dataclass
class CheckResult:
    check_id: str
    description: str
    status: CheckStatus
    detail: str = ""
    remediation: str = ""


@dataclass
class PreflightReport:
    overall: CheckStatus
    checks: list[CheckResult] = field(default_factory=list)
    head_sha: str = ""
    branch: str = ""

    def passed(self) -> bool:
        return self.overall == CheckStatus.PASS

    def summary(self) -> str:
        counts = {s: 0 for s in CheckStatus}
        for c in self.checks:
            counts[c.status] += 1
        parts = [f"{k.value}={v}" for k, v in counts.items() if v]
        return "PREFLIGHT " + self.overall.value + " | " + " ".join(parts)


# ── helpers ──────────────────────────────────────────────────────────────────

def _git(args: list[str], cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git"] + args, capture_output=True, text=True, timeout=10, cwd=cwd
        )
        return r.returncode, r.stdout.strip()
    except Exception as exc:
        return -1, str(exc)


def _check_clean_worktree(root: str) -> CheckResult:
    rc, out = _git(["status", "--porcelain"], root)
    if rc != 0:
        return CheckResult(
            "GIT-CLEAN", "Worktree is clean", CheckStatus.FAIL,
            detail=f"git status failed: {out}",
            remediation="Ensure git is installed and the repository is valid.",
        )
    dirty = [l for l in out.splitlines() if not l.startswith("??")]
    if dirty:
        return CheckResult(
            "GIT-CLEAN", "Worktree is clean", CheckStatus.FAIL,
            detail=f"Uncommitted changes: {len(dirty)} file(s)",
            remediation="Commit or stash changes before running verification.",
        )
    return CheckResult("GIT-CLEAN", "Worktree is clean", CheckStatus.PASS,
                       detail="No uncommitted changes.")


def _check_head_sha(root: str, expected_sha: Optional[str]) -> CheckResult:
    rc, sha = _git(["rev-parse", "HEAD"], root)
    if rc != 0:
        return CheckResult(
            "GIT-SHA", "HEAD SHA readable", CheckStatus.FAIL,
            detail=sha, remediation="Check repository integrity.",
        )
    if expected_sha and not sha.startswith(expected_sha):
        return CheckResult(
            "GIT-SHA", "HEAD SHA matches expected", CheckStatus.FAIL,
            detail=f"Expected prefix={expected_sha} actual={sha}",
            remediation=(
                "The repository is at a different commit than expected. "
                "Do NOT checkout/reset. Record this discrepancy."
            ),
        )
    msg = f"HEAD={sha}" + (f" (matches expected prefix {expected_sha})" if expected_sha else "")
    return CheckResult("GIT-SHA", "HEAD SHA readable", CheckStatus.PASS, detail=msg)


def _check_line_endings(root: str) -> CheckResult:
    """Warn if .gitattributes is absent (may cause platform line-ending issues)."""
    ga = Path(root) / ".gitattributes"
    if ga.exists():
        return CheckResult(
            "LINE-ENDINGS", ".gitattributes present", CheckStatus.PASS,
            detail=str(ga),
        )
    return CheckResult(
        "LINE-ENDINGS", ".gitattributes present", CheckStatus.WARN,
        detail=".gitattributes not found; line-ending behaviour is platform-defined.",
        remediation="Add .gitattributes with `* text=auto` for cross-platform safety.",
    )


def _check_python_version(min_major: int = 3, min_minor: int = 9) -> CheckResult:
    ver = sys.version_info
    ok = (ver.major, ver.minor) >= (min_major, min_minor)
    detail = f"Python {ver.major}.{ver.minor}.{ver.micro}"
    if ok:
        return CheckResult("PYTHON-VER", "Python version adequate", CheckStatus.PASS,
                           detail=detail)
    return CheckResult(
        "PYTHON-VER", "Python version adequate", CheckStatus.FAIL,
        detail=detail + f" < {min_major}.{min_minor}",
        remediation=f"Install Python >= {min_major}.{min_minor}.",
    )


def _check_pytest_importable() -> CheckResult:
    try:
        import pytest
        return CheckResult("PYTEST-IMPORT", "pytest importable", CheckStatus.PASS,
                           detail=f"pytest {pytest.__version__}")
    except ImportError:
        return CheckResult(
            "PYTEST-IMPORT", "pytest importable", CheckStatus.FAIL,
            detail="pytest not importable",
            remediation="pip install pytest",
        )


def _check_no_protected_import() -> CheckResult:
    """Verify no protected namespace is importable via sys.modules (not in this process)."""
    protected = ["src.aql", "research_wp_r0"]
    found = [p for p in protected if p in sys.modules]
    if found:
        return CheckResult(
            "NAMESPACE-ISOLATION", "Protected namespaces not in sys.modules",
            CheckStatus.FAIL,
            detail=f"Loaded: {found}",
            remediation="Do not import protected production modules in this toolkit.",
        )
    return CheckResult(
        "NAMESPACE-ISOLATION", "Protected namespaces not in sys.modules",
        CheckStatus.PASS, detail="None of the protected prefixes found in sys.modules.",
    )


def _check_required_paths(root: str, paths: list[str]) -> list[CheckResult]:
    results = []
    for p in paths:
        full = Path(root) / p
        if full.exists():
            results.append(CheckResult(
                f"PATH-{p.replace('/','_').upper()}", f"Required path exists: {p}",
                CheckStatus.PASS, detail=str(full),
            ))
        else:
            results.append(CheckResult(
                f"PATH-{p.replace('/','_').upper()}", f"Required path exists: {p}",
                CheckStatus.FAIL,
                detail=f"Not found: {full}",
                remediation=f"Ensure {p} exists before running tests.",
            ))
    return results


# ── public API ───────────────────────────────────────────────────────────────

def run_preflight(
    repo_root: Optional[str] = None,
    expected_sha: Optional[str] = None,
    required_paths: Optional[list[str]] = None,
) -> PreflightReport:
    """
    Run all non-mutating preflight checks.
    Never switches branches, checks out, resets, or modifies anything.
    """
    root = str(Path(repo_root).resolve()) if repo_root else os.getcwd()
    checks: list[CheckResult] = []

    _, head_sha = _git(["rev-parse", "HEAD"], root)
    _, branch   = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)

    checks.append(_check_clean_worktree(root))
    checks.append(_check_head_sha(root, expected_sha))
    checks.append(_check_line_endings(root))
    checks.append(_check_python_version())
    checks.append(_check_pytest_importable())
    checks.append(_check_no_protected_import())

    for r in _check_required_paths(root, required_paths or []):
        checks.append(r)

    # Overall: FAIL if any FAIL; WARN if any WARN; else PASS
    statuses = {c.status for c in checks}
    if CheckStatus.FAIL in statuses:
        overall = CheckStatus.FAIL
    elif CheckStatus.WARN in statuses:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    return PreflightReport(
        overall=overall,
        checks=checks,
        head_sha=head_sha,
        branch=branch,
    )
