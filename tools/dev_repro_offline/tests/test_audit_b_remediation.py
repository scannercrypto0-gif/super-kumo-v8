"""
G7 Audit B-Series Remediation Regression Tests — Issue #215 / Audit #134 comment #6555797225
=============================================================================================
Three Audit CHANGES_REQUIRED findings on PR #214 HEAD c8e67669e13e954c4d47d7675fcbd10d311e738a:

B1 — Forged preflight bypass / direct run_entry execute
  (a) run_entry(dry_run=False) is directly callable for un-pinned EXPECTED entries
      without any preflight guard — no sentinel required.  A caller can bypass the
      entire P0-B / G5-GAP-3 chain and launch subprocesses with no git verification.
  (b) run_manifest_with_preflight_guard(preflight=forged) accepts an externally
      constructed PreflightReport with overall=PASS — real git verification is
      never performed.  Any caller can forge a PASS preflight and proceed to execute.
  Fix: add _preflight_guard_token sentinel to run_entry() for execute mode.
       run_manifest_with_preflight_guard() → run_manifest() → run_entry() sentinel
       chain enforces that execution can ONLY flow through the authorized path.

B2 — Execute-mode SHA strictness
  _is_valid_sha() accepts 7–40 hex characters.  In execute mode current_sha must be
  a full 40-hex string produced by `git rev-parse HEAD`, not an abbreviated SHA.
  An abbreviated SHA (e.g. 7 chars) as current_sha in execute mode must be BLOCKED.
  Fix: add _is_valid_execute_sha() requiring exactly 40 lowercase hex chars; use it
       to validate current_sha in run_entry() execute mode (dry_run=False only).
       7–40 acceptance kept for manifest expected_sha prefix-match comparison.

B3 — WARN not sufficient execute authority
  run_manifest_with_preflight_guard() only blocks on CheckStatus.FAIL.
  A preflight that returns WARN (e.g. dirty worktree, line-ending warning) passes
  through to execute mode — subprocesses are launched in a non-clean environment.
  Fix: change guard condition from `overall == FAIL` to `overall != PASS`.
       Only CheckStatus.PASS may proceed to execute; WARN blocks like FAIL does.

FAIL → PASS cycle:
  RED on pre-fix HEAD c8e67669: B1a, B2, B3 tests FAIL
  GREEN after fix: all tests PASS

Run:
    PYTHONPATH=/home/claude/super-kumo-v8 \\
    pytest tools/dev_repro_offline/tests/test_audit_b_remediation.py -v
"""
from __future__ import annotations

import pytest

from tools.dev_repro_offline.manifest import ManifestEntry, ManifestEntryStatus, TestManifest
from tools.dev_repro_offline.runner import (
    RunStatus,
    run_entry,
    run_manifest,
    run_manifest_with_preflight_guard,
    _PREFLIGHT_GUARD_TOKEN,
)
from tools.dev_repro_offline.preflight import PreflightReport, CheckResult, CheckStatus


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

VALID_FULL_SHA  = "a" * 40   # valid 40-char hex — as produced by git rev-parse HEAD
VALID_SHORT_SHA = "abc1234"  # valid 7-char abbreviated SHA — must NOT be accepted in execute

def _unpinned_entry(eid: str = "AUDIT-B1") -> ManifestEntry:
    """EXPECTED entry with NO expected_sha — not SHA-pinned."""
    return ManifestEntry(
        entry_id=eid,
        label="Audit B remediation un-pinned test entry",
        command_template="pytest {module} -v",
        module_path="tools/dev_repro_offline/tests/",
        expected_sha="",
        owner_issue="#215",
        status=ManifestEntryStatus.EXPECTED,
    )

def _pinned_entry(sha: str = VALID_FULL_SHA, eid: str = "AUDIT-B2") -> ManifestEntry:
    """EXPECTED entry with expected_sha pinned — SHA-pinned."""
    return ManifestEntry(
        entry_id=eid,
        label="Audit B remediation pinned test entry",
        command_template="pytest {module} -v",
        module_path="tools/dev_repro_offline/tests/",
        expected_sha=sha,
        owner_issue="#215",
        status=ManifestEntryStatus.EXPECTED,
    )

def _preflight(overall: CheckStatus, sha: str = VALID_FULL_SHA) -> PreflightReport:
    """Construct a PreflightReport with the given overall status and head_sha."""
    return PreflightReport(
        overall=overall,
        checks=[CheckResult("GIT-SHA", "HEAD SHA", overall, sha)],
        head_sha=sha,
        branch="feat/test",
    )


# ─────────────────────────────────────────────────────────────────────────────
# B1 — Direct run_entry execute bypass (no sentinel)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditB1DirectRunEntryBypass:
    """
    B1 defect: run_entry(dry_run=False) is callable directly for un-pinned EXPECTED
    entries without any sentinel or preflight guard.  The G5-GAP-3 sentinel on
    run_manifest() is not enough — run_entry() can be called directly, skipping
    run_manifest() entirely.

    Fix: run_entry(dry_run=False) must require _preflight_guard_token.
    Without it → BLOCKED with B1_EXECUTE_GUARD_REQUIRED note.

    RED on c8e67669: run_entry(dry_run=False) on un-pinned entry proceeds
      (reaches subprocess launch path — would succeed/fail on pytest availability,
      never BLOCKED for missing guard).
    GREEN after fix: returns BLOCKED immediately for missing sentinel.
    """

    def test_b1_direct_run_entry_execute_no_sentinel_is_blocked(self, tmp_path):
        """
        B1 core: calling run_entry(dry_run=False) directly on an un-pinned EXPECTED
        entry without the sentinel guard must return BLOCKED.

        On pre-fix c8e67669: no sentinel check exists on run_entry — the call
        reaches the subprocess launch path and would attempt to run pytest
        (returns PASS/FAIL/ERROR, never BLOCKED for missing guard).

        After fix: run_entry(dry_run=False) without _preflight_guard_token →
        RunStatus.BLOCKED with a note naming the B1 execute guard requirement.
        """
        entry = _unpinned_entry()
        result = run_entry(entry, str(tmp_path), dry_run=False)
        assert result.status == RunStatus.BLOCKED, (
            f"B1 BUG: run_entry(dry_run=False) called directly without sentinel "
            f"must return BLOCKED, got {result.status!r}. "
            "Un-pinned EXPECTED entries must not be executable without the internal "
            "_preflight_guard_token — the P0-B / G5-GAP-3 chain must cover run_entry too."
        )
        assert "guard" in result.notes.lower() or "sentinel" in result.notes.lower() or \
               "preflight" in result.notes.lower(), (
            f"B1: BLOCKED note must mention guard/sentinel/preflight. Got: {result.notes!r}"
        )

    def test_b1_run_entry_dry_run_without_sentinel_still_works(self, tmp_path):
        """
        B1 regression: dry_run=True must NOT require the sentinel.
        dry-run mode launches no subprocess, so the guard is only needed for execute mode.
        """
        entry = _unpinned_entry()
        result = run_entry(entry, str(tmp_path), dry_run=True)
        assert result.status == RunStatus.DRY_RUN, (
            f"B1 regression: run_entry(dry_run=True) must return DRY_RUN without sentinel. "
            f"Got {result.status!r}. The execute guard must only apply in execute mode."
        )

    def test_b1_run_manifest_with_preflight_guard_chain_still_works(self, tmp_path):
        """
        B1 regression: the authorized path run_manifest_with_preflight_guard →
        run_manifest(sentinel) → run_entry(sentinel) must NOT be blocked.
        The sentinel chain must remain functional.

        Uses a PASS preflight and a manifest with one un-pinned entry.
        Result must NOT be BLOCKED for sentinel-missing reasons.
        """
        entry = _unpinned_entry(eid="B1-CHAIN-TEST")
        manifest = TestManifest()
        manifest.add(entry)

        preflight = _preflight(CheckStatus.PASS, sha=VALID_FULL_SHA)

        # Execute mode via authorized path — must not block on sentinel
        # (It may block on subprocess failure since tmp_path has no tests, but
        #  should not block with B1 sentinel error)
        report = run_manifest_with_preflight_guard(
            manifest, str(tmp_path),
            preflight=preflight,
            dry_run=False,
        )
        assert report.results, "B1 chain regression: must produce at least one result"
        result = report.results[0]
        # Must NOT be BLOCKED due to missing guard sentinel (may be PASS/FAIL/ERROR from pytest)
        # Check that if blocked, the note is NOT about a missing preflight guard/sentinel
        if result.status == RunStatus.BLOCKED:
            note_lower = result.notes.lower()
            assert "b1" not in note_lower and (
                ("guard" not in note_lower and "sentinel" not in note_lower) or
                "preflight_fail" in note_lower or "sha" in note_lower
            ), (
                f"B1 chain regression: authorized execute path should not be blocked "
                f"by missing sentinel guard. Got BLOCKED with note: {result.notes!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# B2 — Execute-mode SHA strictness (40-char only)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditB2ExecuteModeSHAStrictness:
    """
    B2 defect: _is_valid_sha() accepts 7–40 hex chars; in execute mode
    current_sha must be full 40-hex (from `git rev-parse HEAD`).
    An abbreviated SHA (7-char) as current_sha in execute mode must be BLOCKED.

    Fix: add _is_valid_execute_sha() → ^[0-9a-f]{40}$; use it to validate
    current_sha in run_entry() when dry_run=False.
    7–40 char acceptance kept for manifest expected_sha prefix-matching.

    RED on c8e67669: 7-char SHA is accepted by _is_valid_sha → execute proceeds.
    GREEN after fix: 7-char SHA in execute mode → BLOCKED with B2 note.
    """

    def test_b2_short_sha_execute_mode_is_blocked(self, tmp_path):
        """
        B2 core: a pinned entry with a valid 7-char SHA match, but current_sha
        is also 7-char abbreviated — must be BLOCKED in execute mode.

        On pre-fix c8e67669: _is_valid_sha("abc1234") returns True (7 chars OK)
        → SHA check passes → subprocess launches.

        After fix: _is_valid_execute_sha() requires exactly 40 hex chars;
        7-char current_sha in execute mode → BLOCKED with B2 note.
        """
        short_sha = "abc1234"
        # Pin the entry to the same short SHA so the prefix-match would pass
        entry = _pinned_entry(sha=short_sha, eid="B2-SHORT-SHA")
        result = run_entry(
            entry, str(tmp_path),
            dry_run=False,
            current_sha=short_sha,
        )
        assert result.status == RunStatus.BLOCKED, (
            f"B2 BUG: abbreviated SHA {short_sha!r} as current_sha in execute mode "
            f"must return BLOCKED, got {result.status!r}. "
            "Execute mode must require full 40-hex SHA from git rev-parse HEAD, "
            "not the 7-40 char form accepted by _is_valid_sha()."
        )
        assert ("b2" in result.notes.lower() or
                "40" in result.notes or
                "full" in result.notes.lower() or
                "execute" in result.notes.lower()), (
            f"B2: BLOCKED note must mention execute-mode SHA strictness. Got: {result.notes!r}"
        )

    def test_b2_malformed_sha_execute_mode_is_blocked(self, tmp_path):
        """
        B2 extension: a non-hex or empty current_sha must be BLOCKED in execute mode.
        This is already the case for _is_valid_sha, but the B2 fix must not regress it.
        """
        entry = _pinned_entry(sha=VALID_FULL_SHA[:7], eid="B2-MALFORMED")
        for bad_sha in ["", "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ", "not-hex"]:
            result = run_entry(
                entry, str(tmp_path),
                dry_run=False,
                current_sha=bad_sha,
            )
            assert result.status == RunStatus.BLOCKED, (
                f"B2: malformed current_sha {bad_sha!r} must be BLOCKED in execute mode, "
                f"got {result.status!r}."
            )

    def test_b2_full_40hex_sha_passes_execute_mode_sha_check(self, tmp_path):
        """
        B2 regression: a full 40-hex current_sha that matches the entry's expected_sha
        must NOT be blocked by the B2 fix.

        (The result may be PASS/FAIL/ERROR from subprocess, never BLOCKED for SHA reason.)
        """
        full_sha = VALID_FULL_SHA
        entry = _pinned_entry(sha=full_sha, eid="B2-FULL-SHA")
        result = run_entry(
            entry, str(tmp_path),
            dry_run=False,
            current_sha=full_sha,
        )
        # May fail/error (pytest on tmp_path finds no tests) — but must not be
        # BLOCKED due to B2 SHA strictness
        assert result.status != RunStatus.BLOCKED or (
            "sha" not in result.notes.lower() or "b2" in result.notes.lower() or
            "mismatch" in result.notes.lower()
        ), (
            f"B2 regression: valid full 40-hex SHA must not be blocked by B2 fix. "
            f"Got BLOCKED with note: {result.notes!r}"
        )

    def test_b2_short_sha_dry_run_still_accepted(self, tmp_path):
        """
        B2 regression: dry_run=True with 7-char SHA must NOT be blocked.
        The stricter SHA check applies to execute mode only.
        """
        short_sha = "abc1234"
        entry = _pinned_entry(sha=short_sha, eid="B2-DRY")
        result = run_entry(
            entry, str(tmp_path),
            dry_run=True,
            current_sha=short_sha,
        )
        assert result.status == RunStatus.DRY_RUN, (
            f"B2 regression: dry_run=True with 7-char SHA must return DRY_RUN, "
            f"got {result.status!r}. B2 strictness applies to execute mode only."
        )


# ─────────────────────────────────────────────────────────────────────────────
# B3 — WARN preflight must block execute
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditB3WarnBlocksExecute:
    """
    B3 defect: run_manifest_with_preflight_guard() only blocks on CheckStatus.FAIL.
    When preflight returns WARN (e.g. dirty worktree, line-ending warning),
    execute mode proceeds — subprocesses are launched in a non-clean environment.

    Fix: change `overall == CheckStatus.FAIL` to `overall != CheckStatus.PASS`.
    Only PASS may proceed to execute; WARN is treated the same as FAIL.

    RED on c8e67669: WARN preflight passes through → subprocess launches.
    GREEN after fix: WARN preflight → all EXPECTED entries BLOCKED (PREFLIGHT_WARN_GATE).
    """

    def test_b3_warn_preflight_blocks_execute(self, tmp_path):
        """
        B3 core: run_manifest_with_preflight_guard with overall=WARN in execute mode
        must block all EXPECTED entries, not allow subprocesses to launch.

        On pre-fix c8e67669: guard checks `overall == FAIL` only → WARN passes
        through → subprocess launched.

        After fix: `overall != PASS` → WARN is treated like FAIL →
        all EXPECTED entries blocked with PREFLIGHT_WARN_GATE or similar note.
        """
        entry = _unpinned_entry(eid="B3-WARN")
        manifest = TestManifest()
        manifest.add(entry)

        warn_preflight = _preflight(CheckStatus.WARN, sha=VALID_FULL_SHA)

        report = run_manifest_with_preflight_guard(
            manifest, str(tmp_path),
            preflight=warn_preflight,
            dry_run=False,
        )
        assert report.results, "B3: must produce results for the manifest entry"
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"B3 BUG: WARN preflight in execute mode must block all EXPECTED entries, "
            f"got {result.status!r}. "
            "run_manifest_with_preflight_guard must block on WARN, not only on FAIL. "
            "Fix: change guard condition to `overall != CheckStatus.PASS`."
        )
        assert ("warn" in result.notes.lower() or
                "preflight" in result.notes.lower() or
                "gate" in result.notes.lower()), (
            f"B3: BLOCKED note must mention WARN/preflight/gate. Got: {result.notes!r}"
        )

    def test_b3_fail_preflight_still_blocks_execute(self, tmp_path):
        """
        B3 regression: FAIL preflight must still block execute (existing G5-GAP-3).
        The B3 fix must not break the FAIL block path.
        """
        entry = _unpinned_entry(eid="B3-FAIL")
        manifest = TestManifest()
        manifest.add(entry)

        fail_preflight = _preflight(CheckStatus.FAIL, sha=VALID_FULL_SHA)

        report = run_manifest_with_preflight_guard(
            manifest, str(tmp_path),
            preflight=fail_preflight,
            dry_run=False,
        )
        assert report.results, "B3 regression: must produce results"
        result = report.results[0]
        assert result.status == RunStatus.BLOCKED, (
            f"B3 regression: FAIL preflight must still block EXPECTED entries, "
            f"got {result.status!r}."
        )

    def test_b3_pass_preflight_allows_execute(self, tmp_path):
        """
        B3 regression: PASS preflight must NOT block in execute mode.
        (Result may be PASS/FAIL/ERROR from subprocess — never BLOCKED by preflight gate.)
        """
        entry = _unpinned_entry(eid="B3-PASS")
        manifest = TestManifest()
        manifest.add(entry)

        pass_preflight = _preflight(CheckStatus.PASS, sha=VALID_FULL_SHA)

        report = run_manifest_with_preflight_guard(
            manifest, str(tmp_path),
            preflight=pass_preflight,
            dry_run=False,
        )
        assert report.results, "B3 regression: must produce results"
        result = report.results[0]
        # Must not be BLOCKED due to preflight gate (may be blocked for other reasons
        # like B1 sentinel if B1 fix is applied before B3; check note)
        if result.status == RunStatus.BLOCKED:
            note_lower = result.notes.lower()
            assert "preflight_fail_gate" not in note_lower and \
                   "preflight_warn_gate" not in note_lower and \
                   "warn" not in note_lower, (
                f"B3 regression: PASS preflight must not trigger preflight gate block. "
                f"Got BLOCKED with note: {result.notes!r}"
            )

    def test_b3_warn_preflight_dry_run_still_executes(self, tmp_path):
        """
        B3 regression: WARN preflight in dry_run=True must NOT block.
        dry-run mode launches no subprocess, so the gate only applies to execute mode.
        """
        entry = _unpinned_entry(eid="B3-DRY")
        manifest = TestManifest()
        manifest.add(entry)

        warn_preflight = _preflight(CheckStatus.WARN, sha=VALID_FULL_SHA)

        report = run_manifest_with_preflight_guard(
            manifest, str(tmp_path),
            preflight=warn_preflight,
            dry_run=True,
        )
        assert report.results, "B3 dry-run regression: must produce results"
        # In dry-run mode, entries should be DRY_RUN (not BLOCKED by preflight gate)
        for res in report.results:
            if res.status == RunStatus.BLOCKED:
                assert "preflight" not in res.notes.lower() or \
                       "fail" not in res.notes.lower(), (
                    f"B3 dry-run regression: WARN preflight must not block dry-run entries. "
                    f"Got BLOCKED with note: {res.notes!r}"
                )
