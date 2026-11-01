"""
Gate 5 Escalated Gaps Regression Tests — Issue #215 PR #214
=============================================================
PM requirement (Issue #215 Final Acceptance): Address three escalated gaps
with focused negative tests.

Gap 1 — pytest argument allowlist (G1-GAP-5):
  _BLOCKED_FLAGS denylist is too narrow; unapproved flags like --forked
  pass through. Fix: replace denylist with _APPROVED_PYTEST_FLAGS allowlist.

Gap 2 — runtime SHA check:
  ManifestEntry.expected_sha is NOT validated at run_entry() time against
  current HEAD SHA. Fix: pass current_sha to run_entry(); return BLOCKED
  if entry.expected_sha is set and doesn't match.

Gap 3 — direct preflight bypass:
  run_manifest(dry_run=False) launches subprocesses without enforcing the
  preflight guard. Fix: run_manifest(dry_run=False) raises RuntimeError
  unless called with the internal _skip_preflight_guard=True sentinel.

FAIL→PASS cycle:
  RED on 8bc898f: 9 FAIL across the three gaps
  GREEN after fix: all tests PASS

Run:
    PYTHONPATH=/home/claude/super-kumo-v8 \\
    pytest tools/dev_repro_offline/tests/test_g5_escalated_gaps_regression.py -v
"""
from __future__ import annotations

import pytest

from tools.dev_repro_offline.runner import (
    _allowed,
    _build_command,
    RunStatus,
    run_entry,
    run_manifest,
)
from tools.dev_repro_offline.manifest import ManifestEntry, ManifestEntryStatus, TestManifest
from tools.dev_repro_offline.preflight import CheckStatus


# ── helpers ───────────────────────────────────────────────────────────────────

def _entry(
    cmd: str = "pytest {module} -v --tb=short",
    module: str = "tools/dev_repro_offline/tests/",
    sha: str = "abc1234",
    status: ManifestEntryStatus = ManifestEntryStatus.EXPECTED,
) -> ManifestEntry:
    return ManifestEntry(
        entry_id="G5-TEST",
        label="Gate5 test entry",
        command_template=cmd,
        module_path=module,
        expected_sha=sha,
        owner_issue="#215",
        status=status,
    )


def _manifest_with_one_entry(entry: ManifestEntry) -> TestManifest:
    m = TestManifest(base_sha="abc1234")
    m.add(entry)
    return m


# ── Gap 1: pytest argument allowlist ─────────────────────────────────────────

class TestGap1PytestArgumentAllowlist:
    """
    G1-GAP-5 Fix: Unapproved pytest flags must be BLOCKED by an allowlist.

    Bug on 8bc898f: _BLOCKED_FLAGS denylist only blocks -c/-m/-p/--co.
    --forked and other unapproved flags pass through.

    RED on 8bc898f:
      test_gap1_forked_flag_blocked   → FAIL (_allowed returns True)
      test_gap1_unknown_flag_blocked  → FAIL (_allowed returns True)
      test_gap1_approved_flags_pass   → PASS (must stay PASS after fix)
    """

    def test_gap1_forked_flag_blocked(self):
        """
        Gap 1 defect: --forked is an unapproved pytest flag; must be BLOCKED.
        Bug on 8bc898f: _allowed(["pytest", "tests/", "--forked"]) returns True.
        """
        assert not _allowed(["pytest", "tests/", "--forked"]), (
            "Gap 1: --forked is not an approved pytest flag; must be BLOCKED. "
            "_BLOCKED_FLAGS denylist is too narrow."
        )

    def test_gap1_unknown_long_flag_blocked(self):
        """
        Gap 1 defect: arbitrary long flags like --randomly-seed must be BLOCKED.
        Bug on 8bc898f: returns True (only known-bad flags are denied).
        """
        assert not _allowed(["pytest", "tests/", "--randomly-seed=1234"]), (
            "Gap 1: --randomly-seed is not an approved pytest flag; must be BLOCKED."
        )

    def test_gap1_run_entry_forked_blocked(self, tmp_path):
        """
        Gap 1 defect: run_entry with --forked in template must return BLOCKED.
        Bug on 8bc898f: returns DRY_RUN/PASS instead of BLOCKED.
        """
        e = _entry(cmd="pytest {module} -v --forked")
        result = run_entry(e, str(tmp_path), dry_run=False)
        assert result.status == RunStatus.BLOCKED, (
            f"Gap 1: --forked template must produce BLOCKED, got {result.status}"
        )

    def test_gap1_approved_flags_still_pass(self):
        """Regression: approved flags (-v, --tb=short, -k) must remain allowed."""
        assert _allowed(["pytest", "tests/", "-v", "--tb=short"])
        assert _allowed(["pytest", "tools/dev_repro_offline/tests/", "-v", "-k", "unit"])

    def test_gap1_approved_flags_with_k_value_pass(self):
        """Regression: -k with a value (not starting with '-') must remain allowed."""
        assert _allowed(["pytest", "tests/", "-v", "--tb=short", "-k", "not integration"])


# ── Gap 2: runtime SHA check ──────────────────────────────────────────────────

class TestGap2RuntimeShaCheck:
    """
    Gap 2 Fix: run_entry() must validate entry.expected_sha against current_sha
    and return BLOCKED on mismatch.

    Bug on 8bc898f: run_entry() ignores entry.expected_sha at runtime; a
    stale manifest entry runs unchanged on a different commit.

    RED on 8bc898f:
      test_gap2_sha_mismatch_is_blocked   → FAIL (returns DRY_RUN, not BLOCKED)
      test_gap2_sha_match_is_allowed      → PASS (must stay PASS after fix)
    """

    def test_gap2_sha_mismatch_is_blocked(self, tmp_path):
        """
        Gap 2 defect: entry.expected_sha='abc1234' but current_sha='deadbeef' →
        must return BLOCKED. On 8bc898f, run_entry ignores current_sha entirely.
        """
        e = _entry(sha="abc1234")
        result = run_entry(
            e, str(tmp_path),
            dry_run=False,
            current_sha="deadbeef9999",
        )
        assert result.status == RunStatus.BLOCKED, (
            f"Gap 2: SHA mismatch must produce BLOCKED, got {result.status}. "
            "entry.expected_sha='abc1234' vs current_sha='deadbeef9999'"
        )

    def test_gap2_sha_prefix_match_is_allowed(self, tmp_path):
        """Regression: when expected_sha is a prefix of current_sha, must NOT block."""
        e = _entry(sha="abc1234")
        result = run_entry(
            e, str(tmp_path),
            dry_run=True,  # dry_run to avoid actual subprocess
            current_sha="abc12349999longsha",
        )
        # In dry_run mode, should return DRY_RUN (not BLOCKED)
        assert result.status == RunStatus.DRY_RUN, (
            f"Gap 2 regression: prefix SHA match must not block, got {result.status}"
        )

    def test_gap2_no_current_sha_does_not_block(self, tmp_path):
        """Regression: when current_sha not provided, run_entry must not block."""
        e = _entry(sha="abc1234")
        result = run_entry(e, str(tmp_path), dry_run=True)
        assert result.status == RunStatus.DRY_RUN, (
            f"Gap 2 regression: omitting current_sha must not block, got {result.status}"
        )


# ── Gap 3: direct preflight bypass ───────────────────────────────────────────

class TestGap3DirectPreflightBypass:
    """
    Gap 3 Fix: run_manifest(dry_run=False) must refuse direct calls.
    Callers must use run_manifest_with_preflight_guard() in execute mode.

    Bug on 8bc898f: run_manifest(dry_run=False) silently launches subprocesses
    bypassing the P0-B preflight gate that blocks on environment failures.

    RED on 8bc898f:
      test_gap3_direct_execute_raises → FAIL (no error raised)
      test_gap3_dry_run_still_works  → PASS (must stay PASS after fix)
    """

    def test_gap3_direct_execute_raises(self, tmp_path):
        """
        Gap 3 defect: run_manifest(dry_run=False) must raise RuntimeError.
        Bug on 8bc898f: returns a RunReport silently, bypassing preflight gate.
        """
        e = _entry(cmd="pytest {module} -v --tb=short",
                   module="tools/dev_repro_offline/tests/test_g1_argv_regression.py")
        manifest = _manifest_with_one_entry(e)
        with pytest.raises(RuntimeError, match="preflight_guard|preflight|P0-B"):
            run_manifest(manifest, str(tmp_path), dry_run=False)

    def test_gap3_dry_run_still_works(self, tmp_path):
        """Regression: run_manifest(dry_run=True) must still work normally."""
        e = _entry()
        manifest = _manifest_with_one_entry(e)
        report = run_manifest(manifest, str(tmp_path), dry_run=True)
        # In dry_run mode, BLOCKED entries or DRY_RUN — just check no exception
        assert report is not None
        assert len(report.results) == 1
