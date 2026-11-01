"""
G7-B Regression Tests — Issue #215 comment #6555520562
=======================================================
Defect: preflight's verified HEAD SHA is NOT wired end-to-end through
run_manifest_with_preflight_guard → run_manifest → run_entry.

Current state (HEAD 66bcd27):
  - run_manifest_with_preflight_guard() receives preflight.head_sha but does
    NOT pass it to run_manifest() or run_entry()
  - run_manifest() does NOT accept or propagate a current_sha parameter
  - run_entry() has current_sha: Optional[str] = None; when caller omits it,
    EXPECTED SHA-pinned entries execute with NO SHA verification (opt-out)

G7-B REQUIREMENT (Issue #215 comment #6555520562):
  Wire authorized preflight's actual git HEAD SHA end-to-end through
  run_manifest_with_preflight_guard → run_manifest → run_entry for ALL EXPECTED
  entries. No caller may execute SHA-pinned entries with current_sha=None,
  malformed/empty SHA, or mismatch. Trust boundary: untrusted caller-supplied
  current_sha alone cannot fake authorized preflight.

Tests in class TestG7BSHAWiringDefects are RED on 66bcd27, GREEN after fix.
Tests in class TestG7BRegressionAlreadyCorrect stay GREEN throughout.

Run:
    pytest tools/dev_repro_offline/tests/test_g7b_sha_wiring_regression.py -v
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest

from tools.dev_repro_offline.manifest import (
    ManifestEntry, ManifestEntryStatus, TestManifest,
)
from tools.dev_repro_offline.runner import (
    RunStatus, run_entry, run_manifest, run_manifest_with_preflight_guard,
    _PREFLIGHT_GUARD_TOKEN,
)
from tools.dev_repro_offline.preflight import PreflightReport, CheckStatus


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

VALID_SHA = "a" * 40          # 40-char hex — simulates git rev-parse HEAD output
ALT_SHA   = "b" * 40          # a different valid 40-char SHA

def _pinned_entry(sha: str = VALID_SHA) -> ManifestEntry:
    """Create an EXPECTED entry with expected_sha pinned to sha."""
    return ManifestEntry(
        entry_id="G7B-TEST-PINNED",
        label="G7-B pinned test entry",
        command_template="pytest {module} -v",
        module_path="tools/dev_repro_offline/tests/test_g7b_sha_wiring_regression.py",
        expected_sha=sha,
        owner_issue="#215",
        status=ManifestEntryStatus.EXPECTED,
    )

def _unpinned_entry() -> ManifestEntry:
    """Create an EXPECTED entry with NO expected_sha (not SHA-pinned)."""
    return ManifestEntry(
        entry_id="G7B-TEST-UNPINNED",
        label="G7-B unpinned test entry",
        command_template="pytest {module} -v",
        module_path="tools/dev_repro_offline/tests/test_g7b_sha_wiring_regression.py",
        expected_sha="",
        owner_issue="#215",
        status=ManifestEntryStatus.EXPECTED,
    )

def _passing_preflight(sha: str = VALID_SHA) -> PreflightReport:
    """A PreflightReport that reports PASS with a specific head_sha."""
    from tools.dev_repro_offline.preflight import CheckResult
    return PreflightReport(
        overall=CheckStatus.PASS,
        checks=[CheckResult("GIT-SHA", "HEAD SHA", CheckStatus.PASS, sha)],
        head_sha=sha,
        branch="feat/test",
    )

def _failing_preflight(sha: str = VALID_SHA) -> PreflightReport:
    """A PreflightReport that reports FAIL (dirty worktree etc.)."""
    from tools.dev_repro_offline.preflight import CheckResult
    return PreflightReport(
        overall=CheckStatus.FAIL,
        checks=[CheckResult("GIT-CLEAN", "Worktree is clean", CheckStatus.FAIL, "dirty")],
        head_sha=sha,
        branch="feat/test",
    )


# ─────────────────────────────────────────────────────────────────────────────
# G7-B DEFECT TESTS — RED on 66bcd27, GREEN after fix
# ─────────────────────────────────────────────────────────────────────────────

class TestG7BSHAWiringDefects:

    def test_g7b_pinned_entry_no_sha_is_blocked(self):
        """
        G7-B PRIMARY DEFECT — RED on 66bcd27, GREEN after fix.

        An EXPECTED SHA-pinned entry called via run_entry() with current_sha=None
        (the default) must return BLOCKED before any subprocess.

        Current behaviour: current_sha=None causes the SHA check to be skipped
        entirely ('if current_sha and entry.expected_sha:' → False → skip).
        The entry proceeds to DRY_RUN (or PASS in execute mode) without any
        SHA verification — this is the G7-B opt-out that must be closed.
        """
        entry = _pinned_entry()
        result = run_entry(entry, repo_root="/fake", dry_run=True, current_sha=None)

        assert result.status == RunStatus.BLOCKED, (
            f"G7-B DEFECT: run_entry() returned {result.status!r} for a pinned "
            "EXPECTED entry when current_sha=None. Must return BLOCKED. "
            "SHA-pinned entries must not execute without a verified SHA. "
            f"notes={result.notes!r}"
        )

    def test_g7b_pinned_entry_empty_sha_is_blocked(self):
        """
        G7-B — EXPECTED SHA-pinned entry with current_sha="" must be BLOCKED.
        An empty string is semantically the same as 'no SHA provided'.
        """
        entry = _pinned_entry()
        result = run_entry(entry, repo_root="/fake", dry_run=True, current_sha="")

        assert result.status == RunStatus.BLOCKED, (
            f"G7-B DEFECT: run_entry() returned {result.status!r} for a pinned "
            "EXPECTED entry when current_sha=''. Must return BLOCKED. "
            f"notes={result.notes!r}"
        )

    def test_g7b_pinned_entry_malformed_sha_is_blocked(self):
        """
        G7-B — EXPECTED SHA-pinned entry with non-hex malformed SHA must be BLOCKED.
        A SHA like 'not-a-sha!!!' is not a valid git object identifier.
        """
        entry = _pinned_entry()
        result = run_entry(entry, repo_root="/fake", dry_run=True, current_sha="not-a-sha!!!")

        assert result.status == RunStatus.BLOCKED, (
            f"G7-B DEFECT: run_entry() returned {result.status!r} for a pinned "
            "EXPECTED entry when current_sha='not-a-sha!!!'. Must return BLOCKED. "
            f"notes={result.notes!r}"
        )

    def test_g7b_sha_does_not_flow_from_preflight_guard_to_run_entry(self):
        """
        G7-B WIRING DEFECT — preflight.head_sha is not propagated to run_entry().

        run_manifest_with_preflight_guard() receives a PreflightReport with
        head_sha=VALID_SHA. The manifest has a pinned entry with expected_sha=VALID_SHA.
        In dry_run=True mode the preflight guard currently does NOT pass the SHA
        through, so run_entry() gets current_sha=None → the SHA check is silently
        skipped.

        Fix: preflight.head_sha must flow automatically through run_manifest()
        → run_entry() so the SHA check is performed even in dry_run mode.

        This test verifies the wiring by using a WRONG expected_sha in the entry
        and a CORRECT sha in the preflight. After the fix, the SHA mismatch must
        cause BLOCKED. Before the fix, SHA never reaches run_entry() → DRY_RUN.
        """
        # Entry pinned to ALT_SHA (different from preflight's VALID_SHA)
        entry = _pinned_entry(sha=ALT_SHA)
        manifest = TestManifest()
        manifest.entries.append(entry)

        preflight = _passing_preflight(sha=VALID_SHA)  # VALID_SHA ≠ ALT_SHA

        # dry_run=True — even in dry-run the SHA must be compared after fix
        report = run_manifest_with_preflight_guard(
            manifest, repo_root="/fake",
            preflight=preflight,
            dry_run=True,
        )

        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"G7-B WIRING DEFECT: run_manifest_with_preflight_guard returned "
            f"{result.status!r} for an entry pinned to {ALT_SHA[:8]}... "
            f"when preflight head_sha={VALID_SHA[:8]}... (mismatch). "
            "After the fix, preflight.head_sha must flow to run_entry() and "
            "the SHA mismatch must produce BLOCKED. "
            "Currently the SHA never reaches run_entry() → DRY_RUN returned instead. "
            f"notes={result.notes!r}"
        )

    def test_g7b_run_manifest_does_not_propagate_current_sha_to_run_entry(self):
        """
        G7-B — run_manifest() must accept and propagate current_sha to each run_entry().

        Currently run_manifest() calls run_entry(entry, repo_root, dry_run=dry_run,
        timeout=timeout) with NO current_sha. Fix must add current_sha to the
        run_manifest() signature and thread it through.

        Verified by: passing the wrong SHA explicitly and checking BLOCKED is returned.
        """
        entry = _pinned_entry(sha=VALID_SHA)
        manifest = TestManifest()
        manifest.entries.append(entry)

        # Call run_manifest (dry_run=True — no guard needed) and pass wrong SHA
        # After fix: run_manifest accepts current_sha and passes it to run_entry → BLOCKED
        # Before fix: run_manifest has no current_sha param → run_entry gets None → DRY_RUN
        try:
            report = run_manifest(manifest, repo_root="/fake", dry_run=True,
                                  current_sha=ALT_SHA)  # wrong SHA, mismatch
            result = report.results[0]
            assert result.status == RunStatus.BLOCKED, (
                f"G7-B DEFECT: run_manifest() did not propagate current_sha={ALT_SHA[:8]}... "
                f"to run_entry(). Returned {result.status!r} instead of BLOCKED. "
                "Fix must add current_sha param to run_manifest() and thread it through."
            )
        except TypeError as exc:
            pytest.fail(
                f"G7-B DEFECT: run_manifest() does not accept current_sha parameter "
                f"(TypeError: {exc}). Fix must add current_sha to its signature."
            )


# ─────────────────────────────────────────────────────────────────────────────
# G7-B POSITIVE TEST — matching SHA via preflight guard executes entry
# ─────────────────────────────────────────────────────────────────────────────

class TestG7BSHAPositive:

    def test_g7b_matching_sha_via_preflight_gives_dry_run(self):
        """
        G7-B POSITIVE: entry pinned to VALID_SHA, preflight.head_sha=VALID_SHA,
        dry_run=True → result must be DRY_RUN (not BLOCKED).

        Verifies that the wiring passes SHA correctly AND does not false-positive.
        This test is GREEN on both old and new code for dry_run=True when SHA matches
        — but after the fix the SHA comparison actually happens; before the fix it is
        silently skipped. The pass condition remains DRY_RUN in both cases.
        """
        entry = _pinned_entry(sha=VALID_SHA)
        manifest = TestManifest()
        manifest.entries.append(entry)

        preflight = _passing_preflight(sha=VALID_SHA)

        report = run_manifest_with_preflight_guard(
            manifest, repo_root="/fake",
            preflight=preflight,
            dry_run=True,
        )

        result = report.results[0]
        assert result.status == RunStatus.DRY_RUN, (
            f"G7-B POSITIVE: expected DRY_RUN but got {result.status!r}. "
            f"Entry pinned to {VALID_SHA[:8]}... and preflight has same SHA — should pass. "
            f"notes={result.notes!r}"
        )

    def test_g7b_unpinned_entry_with_no_sha_is_not_blocked(self):
        """
        G7-B POSITIVE: unpinned entries (entry.expected_sha='') must NOT be blocked
        when current_sha=None. The 'no opt-out' rule only applies to SHA-pinned entries.
        """
        entry = _unpinned_entry()
        result = run_entry(entry, repo_root="/fake", dry_run=True, current_sha=None)
        assert result.status == RunStatus.DRY_RUN, (
            f"G7-B POSITIVE: unpinned entry (expected_sha='') got {result.status!r} "
            "with current_sha=None. Must be DRY_RUN — SHA block only for pinned entries."
        )

    def test_g7b_pinned_entry_matching_sha_is_not_blocked(self):
        """
        G7-B POSITIVE: run_entry() with matching current_sha must NOT be BLOCKED.
        """
        entry = _pinned_entry(sha=VALID_SHA)
        result = run_entry(entry, repo_root="/fake", dry_run=True, current_sha=VALID_SHA)
        assert result.status == RunStatus.DRY_RUN, (
            f"G7-B POSITIVE: matching SHA produced {result.status!r}, expected DRY_RUN. "
            f"notes={result.notes!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION — already-correct G5 behaviour must survive
# ─────────────────────────────────────────────────────────────────────────────

class TestG7BRegressionAlreadyCorrect:

    def test_g5gap3_direct_run_manifest_execute_still_raises(self):
        """
        REGRESSION (G5-GAP-3): direct run_manifest(dry_run=False) without guard token
        must still raise RuntimeError.
        """
        entry = _pinned_entry()
        manifest = TestManifest()
        manifest.entries.append(entry)
        with pytest.raises(RuntimeError, match=r"preflight_guard|preflight|P0-B"):
            run_manifest(manifest, repo_root="/fake", dry_run=False)

    def test_g5gap3_run_manifest_dry_run_still_works(self):
        """
        REGRESSION (G5-GAP-3): run_manifest(dry_run=True) must still work without guard.
        The dry_run guard only applies to execute mode.
        """
        entry = _unpinned_entry()
        manifest = TestManifest()
        manifest.entries.append(entry)
        # Should not raise
        report = run_manifest(manifest, repo_root="/fake", dry_run=True)
        assert len(report.results) == 1

    def test_sha_mismatch_still_blocked(self):
        """
        REGRESSION (G5-GAP-2): explicit SHA mismatch must still be BLOCKED.
        """
        entry = _pinned_entry(sha=VALID_SHA)
        result = run_entry(entry, repo_root="/fake", dry_run=True, current_sha=ALT_SHA)
        assert result.status == RunStatus.BLOCKED, (
            f"REGRESSION: SHA mismatch produced {result.status!r}, expected BLOCKED."
        )

    def test_preflight_fail_still_blocks_execute(self):
        """
        REGRESSION (P0-B): failing preflight in execute mode must still block all entries.
        """
        entry = _pinned_entry(sha=VALID_SHA)
        manifest = TestManifest()
        manifest.entries.append(entry)

        preflight = _failing_preflight(sha=VALID_SHA)

        report = run_manifest_with_preflight_guard(
            manifest, repo_root="/fake",
            preflight=preflight,
            dry_run=False,
        )
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"REGRESSION (P0-B): failing preflight in execute mode returned "
            f"{result.status!r}. Must be BLOCKED."
        )
        assert "PREFLIGHT_FAIL_GATE" in result.notes
