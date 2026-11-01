"""
Audit C1 Remediation Tests — Issue #215 / Audit #134 comment #6556235030
=========================================================================
Blocker C1: run_manifest_with_preflight_guard() accepted any caller-supplied
PreflightReport(overall=PASS, head_sha=...) without verifying that the SHA
corresponds to the actual git HEAD in repo_root.  A forged report could be
constructed without ever calling run_preflight(repo_root), bypassing the
environmental gate.

Fix: _verify_preflight_sha_matches_repo() re-runs git rev-parse HEAD in
repo_root and compares against preflight.head_sha. Mismatch or unreadable
repo → all entries BLOCKED with PREFLIGHT_SHA_MISMATCH_OR_FORGED or
PREFLIGHT_SHA_UNVERIFIABLE. Applied in both dry_run and execute modes.

FAIL→PASS cycle:
  RED on 992b5fc (pre-fix): test_c1_forged_preflight_dry_run_is_blocked → FAIL
  GREEN after fix: all 6 tests PASS

Run:
    PYTHONPATH=/home/claude/super-kumo-v8 \\
    pytest tools/dev_repro_offline/tests/test_audit_c_remediation.py -v
"""
from __future__ import annotations

import hashlib
import subprocess
import os
from pathlib import Path

import pytest

from tools.dev_repro_offline.preflight import (
    PreflightReport, CheckResult, CheckStatus, run_preflight,
)
from tools.dev_repro_offline.manifest import (
    ManifestEntry, ManifestEntryStatus, TestManifest,
)
from tools.dev_repro_offline.runner import (
    RunStatus, run_manifest_with_preflight_guard,
)

# ── helpers ───────────────────────────────────────────────────────────────────

VALID_FULL_SHA = "a" * 40    # plausible 40-char hex SHA


def _forged_preflight(sha: str = VALID_FULL_SHA) -> PreflightReport:
    """Build a completely forged PASS preflight without running run_preflight()."""
    return PreflightReport(
        overall=CheckStatus.PASS,
        checks=[CheckResult("FORGED", "crafted", CheckStatus.PASS, "forged")],
        head_sha=sha,
        branch="main",
    )


def _unpinned_entry(eid: str = "C1-TEST") -> ManifestEntry:
    return ManifestEntry(
        entry_id=eid,
        label="Audit C1 test entry",
        command_template="pytest {module} -v",
        module_path="tools/dev_repro_offline/tests/",
        expected_sha="",
        owner_issue="#215",
        status=ManifestEntryStatus.EXPECTED,
    )


def _manifest_one() -> TestManifest:
    m = TestManifest()
    m.entries.append(_unpinned_entry())
    return m


# ── C1 defect tests (RED on 992b5fc, GREEN after fix) ─────────────────────────


class TestAuditC1ForgedPreflight:

    def test_c1_forged_preflight_dry_run_is_blocked(self, tmp_path):
        """
        C1 PRIMARY DEFECT — RED on 992b5fc, GREEN after fix.

        A completely forged PreflightReport(overall=PASS) is accepted by
        run_manifest_with_preflight_guard() without any SHA re-verification.

        repo_root=tmp_path is NOT a git repository, so git rev-parse HEAD will
        fail → PREFLIGHT_SHA_UNVERIFIABLE.  After fix, result must be BLOCKED.
        Before fix: returns DRY_RUN (forged preflight silently accepted).
        """
        forged = _forged_preflight(sha=VALID_FULL_SHA)
        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=str(tmp_path),
            preflight=forged, dry_run=True,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"C1: forged preflight (non-git repo_root) produced {result.status!r}. "
            "Must be BLOCKED with PREFLIGHT_SHA_UNVERIFIABLE. "
            f"notes={result.notes!r}"
        )
        assert "PREFLIGHT_SHA_UNVERIFIABLE" in result.notes or \
               "PREFLIGHT_SHA_MISMATCH_OR_FORGED" in result.notes, (
            f"C1: expected PREFLIGHT_SHA_UNVERIFIABLE in notes, got: {result.notes!r}"
        )

    def test_c1_forged_sha_different_from_real_head_is_blocked(self, tmp_path):
        """
        C1: A forged preflight with VALID_FULL_SHA but pointing at an actual git
        repo where the HEAD is different must be BLOCKED with
        PREFLIGHT_SHA_MISMATCH_OR_FORGED.

        We use the actual repo at cwd (super-kumo-v8) as repo_root — its real
        HEAD will differ from VALID_FULL_SHA ('a' * 40).
        """
        repo_root = os.getcwd()  # the actual super-kumo-v8 repo
        forged = _forged_preflight(sha=VALID_FULL_SHA)  # 'a' * 40 ≠ real HEAD

        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=repo_root,
            preflight=forged, dry_run=True,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"C1: forged SHA != real HEAD produced {result.status!r}. "
            "Must be BLOCKED with PREFLIGHT_SHA_MISMATCH_OR_FORGED. "
            f"notes={result.notes!r}"
        )
        assert "PREFLIGHT_SHA_MISMATCH_OR_FORGED" in result.notes, (
            f"C1: expected PREFLIGHT_SHA_MISMATCH_OR_FORGED in notes, got: {result.notes!r}"
        )

    def test_c1_execute_mode_forged_preflight_is_blocked(self, tmp_path):
        """
        C1: Forged preflight in execute mode (dry_run=False) must also be BLOCKED
        before any subprocess is launched.

        repo_root=tmp_path is not a git repo → git rev-parse HEAD fails →
        PREFLIGHT_SHA_UNVERIFIABLE → BLOCKED before reaching B3/B1/B2 chain.
        """
        forged = _forged_preflight(sha=VALID_FULL_SHA)
        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=str(tmp_path),
            preflight=forged, dry_run=False,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"C1: forged preflight in execute mode produced {result.status!r}. "
            "Must be BLOCKED. "
            f"notes={result.notes!r}"
        )


# ── C1 positive / regression tests ────────────────────────────────────────────


class TestAuditC1Positive:

    def test_c1_real_preflight_matching_sha_is_not_blocked(self, tmp_path):
        """
        C1 POSITIVE: a real run_preflight(repo_root) on an actual git repo
        produces a PreflightReport whose head_sha matches the real HEAD.
        run_manifest_with_preflight_guard() must NOT block this case.

        We use the actual repo as repo_root. run_preflight may return WARN
        (dirty worktree, .gitattributes missing) so we test in dry_run=True
        mode where WARN does not block. The key invariant: no C1 block.
        """
        repo_root = os.getcwd()  # actual super-kumo-v8 repo
        real_preflight = run_preflight(repo_root=repo_root)

        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=repo_root,
            preflight=real_preflight, dry_run=True,
        )
        result = report.results[0]
        # Must NOT be blocked with a C1 note — any other status is acceptable
        c1_blocked = (
            result.status == RunStatus.BLOCKED and (
                "PREFLIGHT_SHA_UNVERIFIABLE" in (result.notes or "")
                or "PREFLIGHT_SHA_MISMATCH_OR_FORGED" in (result.notes or "")
            )
        )
        assert not c1_blocked, (
            f"C1 POSITIVE: real preflight from run_preflight() was C1-blocked. "
            f"status={result.status!r} notes={result.notes!r}"
        )

    def test_c1_b3_regression_warn_still_blocks_execute(self, tmp_path):
        """
        REGRESSION (B3): After adding C1 check, B3 (WARN blocks execute) must
        still work.  We need a PreflightReport with actual matching SHA but
        overall=WARN to test B3 still fires after C1 passes.
        """
        repo_root = os.getcwd()
        # Get the real HEAD SHA
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=repo_root,
        )
        real_sha = r.stdout.strip()

        # Build a preflight with matching SHA but WARN overall
        warn_preflight = PreflightReport(
            overall=CheckStatus.WARN,
            checks=[CheckResult("LINE-ENDINGS", "test", CheckStatus.WARN, "warn")],
            head_sha=real_sha,   # matches real HEAD — C1 passes
            branch="feat/test",
        )

        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=repo_root,
            preflight=warn_preflight, dry_run=False,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"B3 REGRESSION: WARN preflight in execute mode produced {result.status!r}. "
            "Must still be BLOCKED after C1 fix. "
            f"notes={result.notes!r}"
        )
        assert "PREFLIGHT_WARN_GATE" in result.notes, (
            f"B3 REGRESSION: expected PREFLIGHT_WARN_GATE in notes, got: {result.notes!r}"
        )

    def test_c1_does_not_block_non_git_repo_dry_run_with_forged_empty_sha(self, tmp_path):
        """
        C1 edge case: a PreflightReport with empty head_sha on a non-git repo_root
        must also be BLOCKED (empty SHA cannot match git rev-parse HEAD output).
        """
        forged = _forged_preflight(sha="")  # empty head_sha
        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=str(tmp_path),
            preflight=forged, dry_run=True,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"C1 edge: empty head_sha on non-git repo produced {result.status!r}. "
            "Must be BLOCKED. "
            f"notes={result.notes!r}"
        )
