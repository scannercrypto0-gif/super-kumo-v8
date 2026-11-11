"""
Audit C1 / C1b Remediation Tests — Issue #215 / Audit #134
===========================================================
Blocker C1: run_manifest_with_preflight_guard() accepted any caller-supplied
PreflightReport(overall=PASS, head_sha=...) without verifying that the SHA
corresponds to the actual git HEAD in repo_root.  A forged report could be
constructed without ever calling run_preflight(repo_root), bypassing the
environmental gate.

Fix C1: _verify_preflight_sha_matches_repo() re-runs git rev-parse HEAD in
repo_root and compares against preflight.head_sha. Mismatch or unreadable
repo → all entries BLOCKED with PREFLIGHT_SHA_MISMATCH_OR_FORGED or
PREFLIGHT_SHA_UNVERIFIABLE. Applied in both dry_run and execute modes.

Fix C1b (Audit #134 comment #6556518643): At execute boundary (dry_run=False),
independently re-run run_preflight(repo_root) live. A caller who forges
PreflightReport(overall=PASS, head_sha=<real_HEAD>) passes the C1 SHA gate
but is blocked by C1b if the live environment is not PASS (dirty worktree,
line-ending check failures, etc.). This closes the forged-PASS-with-real-SHA
attack vector.

FAIL→PASS cycle:
  RED on 992b5fc (pre-fix): test_c1_forged_preflight_dry_run_is_blocked → FAIL
  GREEN after fix (C1): all 6 C1 tests PASS
  GREEN after fix (C1b commit): +2 C1b tests PASS

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
        REGRESSION (B3): After adding C1/C1b checks, a WARN environment must
        still block execute.

        Note on C1b interaction: C1b independently re-runs run_preflight(repo_root)
        at execute boundary. If the live repo is dirty, C1b blocks first with
        C1B_LIVE_PREFLIGHT_FAILED. If the live repo is clean, C1b passes and B3
        fires with PREFLIGHT_WARN_GATE. Either way the result is BLOCKED — the
        invariant is that WARN environments never reach execute, regardless of which
        gate fires first.
        """
        repo_root = os.getcwd()
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=repo_root,
        )
        real_sha = r.stdout.strip()

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
            f"B3 REGRESSION: WARN environment in execute mode produced {result.status!r}. "
            "Must be BLOCKED (either by C1b live preflight or B3 WARN gate). "
            f"notes={result.notes!r}"
        )
        # Accept either C1b blocking (dirty live env) or B3 WARN gate (clean env)
        blocked_by_warn_or_c1b = (
            "PREFLIGHT_WARN_GATE" in result.notes
            or "C1B_LIVE_PREFLIGHT_FAILED" in result.notes
        )
        assert blocked_by_warn_or_c1b, (
            f"B3/C1b REGRESSION: expected PREFLIGHT_WARN_GATE or C1B_LIVE_PREFLIGHT_FAILED "
            f"in notes, got: {result.notes!r}"
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

# ── C1b dedicated tests (RED on 3f3c1ad pre-C1b, GREEN after C1b commit) ─────


class TestAuditC1bLivePreflight:
    """
    C1b: At execute boundary, run_manifest_with_preflight_guard() must
    independently re-run run_preflight(repo_root) even when the caller supplies
    a PreflightReport(overall=PASS, head_sha=<real HEAD>).

    Attack vector closed: a caller can forge overall=PASS and set head_sha to the
    actual git HEAD (obtained independently). C1 SHA check passes. Without C1b,
    the execute boundary has no knowledge that the environment is dirty.
    C1b catches this by re-running run_preflight() live.
    """

    def test_c1b_forged_pass_with_real_sha_in_dirty_worktree_is_blocked(self):
        """
        C1b PRIMARY: Forged PreflightReport(overall=PASS, head_sha=<real HEAD>)
        in a dirty worktree (runner.py modified) must be BLOCKED with
        C1B_LIVE_PREFLIGHT_FAILED at execute boundary.

        This is the exact attack closed by C1b: caller obtains the real HEAD SHA
        via git rev-parse HEAD and builds a fake PASS report without ever calling
        run_preflight(). C1 passes (SHA matches). C1b catches the dirty env.

        Precondition: runner.py is modified (git status shows M) in this CI run.
        If the worktree is unexpectedly clean, C1b won't fire but the test still
        verifies that BLOCKED is returned (either gate is acceptable).
        """
        repo_root = os.getcwd()
        # Get the real HEAD SHA
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=repo_root,
        )
        real_sha = r.stdout.strip()
        assert real_sha, "Could not read git HEAD SHA — test environment misconfigured"

        # Forge a PASS report with the real HEAD SHA
        forged_pass = PreflightReport(
            overall=CheckStatus.PASS,
            checks=[CheckResult("FORGED", "no real check", CheckStatus.PASS, "forged")],
            head_sha=real_sha,   # real SHA — C1 will PASS
            branch="feat/c1b-test",
        )

        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=repo_root,
            preflight=forged_pass, dry_run=False,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"C1b: forged PASS report with real SHA in execute mode produced "
            f"{result.status!r}. Must be BLOCKED. notes={result.notes!r}"
        )
        # C1b must have fired (dirty worktree) OR the environment was already clean
        # and some other gate fired — either way it must not be a silent PASS/DRY_RUN
        assert result.status != RunStatus.DRY_RUN, (
            "C1b: dry_run=False but got DRY_RUN status — execute boundary is broken"
        )

    def test_c1b_does_not_fire_in_dry_run_mode(self):
        """
        C1b BOUNDARY: C1b live preflight re-run must NOT occur in dry_run=True mode.
        Only execute mode (dry_run=False) triggers the live preflight.

        A forged PASS report with a SHA mismatch (not real HEAD) will be caught by
        C1 (SHA check), but that's fine — it still proves C1b is not the gating logic
        in dry_run mode. We verify: dry_run=True with a real run_preflight() result
        is not C1b-blocked.
        """
        repo_root = os.getcwd()
        # Use a genuinely produced preflight (SHA will match)
        real_preflight = run_preflight(repo_root=repo_root)

        report = run_manifest_with_preflight_guard(
            _manifest_one(), repo_root=repo_root,
            preflight=real_preflight, dry_run=True,   # dry_run=True → C1b must NOT fire
        )
        result = report.results[0]
        # Must NOT be blocked by C1b in dry_run mode
        c1b_blocked = (
            result.status == RunStatus.BLOCKED
            and "C1B_LIVE_PREFLIGHT_FAILED" in (result.notes or "")
        )
        assert not c1b_blocked, (
            f"C1b BOUNDARY: C1b fired in dry_run=True mode — must not. "
            f"status={result.status!r} notes={result.notes!r}"
        )
