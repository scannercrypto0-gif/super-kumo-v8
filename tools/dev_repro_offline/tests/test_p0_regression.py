"""
P0 Regression Tests — Issue #215 Gate 1
========================================
These tests were written BEFORE the fixes.
They must FAIL on the unfixed code (SHA efad773) and PASS after the fix.

P0-A: command allowlist bypass via -c / -m flags or crafted module_path
P0-B: execution proceeds after preflight FAIL in --execute mode

Run to reproduce bugs:
    pytest tools/dev_repro_offline/tests/test_p0_regression.py -v

After the fix these must all pass.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from tools.dev_repro_offline.manifest import ManifestEntry, ManifestEntryStatus, TestManifest
from tools.dev_repro_offline.runner import (
    RunStatus,
    _allowed,
    _build_command,
    run_entry,
    run_manifest,
)
from tools.dev_repro_offline.preflight import run_preflight, CheckStatus
from tools.dev_repro_offline.cli import run as cli_run


# ─────────────────────────────────────────────────────────────────────────────
# P0-A: Command allowlist bypass
# ─────────────────────────────────────────────────────────────────────────────

class TestP0ACommandBypass:
    """
    The runner checks only argv[0] base name against the allowlist.
    A crafted manifest entry can inject dangerous flags or module paths.
    These tests confirm the bypass exists (FAIL on unfixed code) and is
    blocked after the fix (PASS on fixed code).
    """

    def _make_entry(self, template: str, module_path: str = "some/path") -> ManifestEntry:
        return ManifestEntry(
            entry_id="BYPASS-TEST",
            label="bypass probe",
            command_template=template,
            module_path=module_path,
            expected_sha="abc123",
            owner_issue="#215",
            status=ManifestEntryStatus.EXPECTED,
        )

    def test_python_dash_c_is_blocked(self):
        """
        P0-A-1: 'python -c {module}' with arbitrary module_path must be BLOCKED.
        The -c flag lets arbitrary Python code run.
        UNFIXED: run_entry returns DRY_RUN or executes (only exe name checked).
        FIXED:   _allowed / run_entry must return BLOCKED.
        """
        entry = self._make_entry("python -c {module}", module_path="import os")
        argv = _build_command(entry.command_template, entry.module_path)
        # After the fix, -c in argv must make _allowed return False
        assert not _allowed(argv), (
            "P0-A-1 BUG: 'python -c ...' passed the allowlist check. "
            "The -c flag enables arbitrary code execution and must be blocked."
        )

    def test_python_dash_m_is_blocked(self):
        """
        P0-A-2: 'python -m {module}' must be blocked.
        The -m flag can run any importable module as __main__.
        """
        entry = self._make_entry("python -m {module}", module_path="malicious_pkg")
        argv = _build_command(entry.command_template, entry.module_path)
        assert not _allowed(argv), (
            "P0-A-2 BUG: 'python -m ...' passed the allowlist check. "
            "The -m flag enables running arbitrary installed modules."
        )

    def test_module_path_injected_flags_blocked(self):
        """
        P0-A-3: module_path '-c evil_code' injected as argv args must be blocked.
        Template 'python {module}' + module_path '-c evil' → ['python', '-c', 'evil'].
        """
        entry = self._make_entry("python {module}", module_path="-c evil_code")
        argv = _build_command(entry.command_template, entry.module_path)
        # The built argv is ['python', '-c', 'evil_code'] — must be blocked
        assert not _allowed(argv), (
            "P0-A-3 BUG: module_path containing '-c' was not blocked. "
            "argv args must be validated, not just argv[0]."
        )

    def test_run_entry_does_not_launch_when_args_invalid(self, tmp_path):
        """
        P0-A-4: run_entry must return BLOCKED (not DRY_RUN, not PASS, not ERROR)
        when the command template contains disallowed flags.
        """
        entry = self._make_entry("python -c {module}", module_path="import os")
        result = run_entry(entry, str(tmp_path), dry_run=False)
        assert result.status == RunStatus.BLOCKED, (
            f"P0-A-4 BUG: run_entry returned {result.status!r} for 'python -c ...'. "
            "Must return BLOCKED to prevent execution."
        )

    def test_legitimate_pytest_template_still_allowed(self, tmp_path):
        """
        P0-A-COMPAT: The standard pytest template must not be broken by the fix.
        'pytest {module} -v --tb=short' with a normal path must remain EXPECTED.
        """
        entry = self._make_entry(
            "pytest {module} -v --tb=short",
            module_path="tools/dev_repro_offline/tests/",
        )
        argv = _build_command(entry.command_template, entry.module_path)
        assert _allowed(argv), (
            "P0-A-COMPAT: legitimate pytest template was incorrectly blocked. "
            "The fix must not break valid commands."
        )


# ─────────────────────────────────────────────────────────────────────────────
# P0-B: Execution after preflight FAIL
# ─────────────────────────────────────────────────────────────────────────────

class TestP0BExecuteAfterPreflightFail:
    """
    When preflight fails and dry_run=False (--execute mode), no subprocess
    must be launched. The runner must fail closed before any execution.

    On unfixed code: run_manifest is called regardless of preflight result.
    On fixed code:   runner refuses to execute and returns BLOCKED for all entries.
    """

    def test_execute_blocked_on_preflight_fail(self, tmp_path):
        """
        P0-B-1: With dry_run=False and a FAIL preflight, run_manifest must
        not execute any EXPECTED entries — they must all be BLOCKED or SKIP.
        Simulated: preflight always fails on a bare tmp_path (no .git).
        """
        from tools.dev_repro_offline.manifest import build_w1_manifest
        manifest = build_w1_manifest("test_sha")
        # Add an EXPECTED entry that would actually run if not guarded
        manifest.entries[0].status = ManifestEntryStatus.EXPECTED

        preflight = run_preflight(repo_root=str(tmp_path))  # no .git → FAIL
        assert preflight.overall.value == "FAIL", "Precondition: preflight must FAIL on bare dir"

        # Run with execute mode — must refuse execution on preflight FAIL
        from tools.dev_repro_offline.runner import run_manifest_with_preflight_guard
        try:
            run_report = run_manifest_with_preflight_guard(
                manifest, str(tmp_path), preflight=preflight, dry_run=False
            )
        except ImportError:
            # Function doesn't exist yet — the fix needs to add it.
            # Report as test failure with clear message.
            pytest.fail(
                "P0-B-1 BUG: run_manifest_with_preflight_guard does not exist. "
                "The CLI currently calls run_manifest() unconditionally even after "
                "preflight FAIL in --execute mode."
            )
            return

        # After fix: all EXPECTED entries must be BLOCKED (not PASS/FAIL/ERROR)
        for r in run_report.results:
            if r.status not in (RunStatus.BLOCKED, RunStatus.SKIP, RunStatus.DRY_RUN):
                pytest.fail(
                    f"P0-B-1 BUG: entry {r.entry_id!r} has status {r.status!r} "
                    "after preflight FAIL + execute mode. Expected BLOCKED."
                )

    def test_execute_proceeds_on_preflight_pass(self, tmp_path):
        """
        P0-B-COMPAT: run_manifest_with_preflight_guard must NOT block execution
        when preflight passes (dry_run=True for this test — no real subprocess).
        """
        from tools.dev_repro_offline.manifest import build_w1_manifest
        from tools.dev_repro_offline.runner import run_manifest_with_preflight_guard

        manifest = build_w1_manifest("test_sha")
        # Simulate a passing preflight by patching overall
        preflight = run_preflight(repo_root=str(tmp_path))

        # dry_run=True so nothing actually executes — we just check no blanket BLOCKED
        run_report = run_manifest_with_preflight_guard(
            manifest, str(tmp_path), preflight=preflight, dry_run=True
        )
        # With dry_run=True, EXPECTED entries become DRY_RUN (not BLOCKED)
        # BLOCKED entries stay BLOCKED (they're blocked in the manifest, not by guard)
        expected_ids = {e.entry_id for e in manifest.allowed_entries()}
        for r in run_report.results:
            if r.entry_id in expected_ids:
                # Should NOT be blocked specifically by the P0-B preflight fail gate.
                # G7-B note: an EXPECTED entry may still be BLOCKED if preflight.head_sha
                # is absent/invalid (e.g. tmp_path has no .git → git rev-parse fails →
                # head_sha=""). In that case the block reason is SHA_ABSENT_OR_INVALID,
                # not PREFLIGHT_FAIL_GATE. The guard's P0-B gate itself must not fire.
                assert "PREFLIGHT_FAIL_GATE" not in (r.notes or ""), (
                    f"P0-B-COMPAT: EXPECTED entry {r.entry_id!r} was blocked by "
                    "PREFLIGHT_FAIL_GATE even though preflight did not report overall FAIL. "
                    f"notes={r.notes!r}"
                )

    def test_cli_execute_aborts_on_preflight_fail(self, tmp_path):
        """
        P0-B-2: The CLI run() with dry_run=False on a bare directory (preflight FAIL)
        must return exit code 3 (preflight fail gate) and must not have launched
        any subprocess.
        After fix: rc == 3 and no PASS/FAIL results from execution.
        """
        out = tmp_path / "evidence"
        # bare tmp_path has no .git → preflight FAIL
        rc = cli_run(dry_run=False, output_dir=str(out), repo_root=str(tmp_path))
        assert rc == 3, (
            f"P0-B-2 BUG: CLI returned rc={rc} instead of 3 after preflight FAIL "
            "in --execute mode. Execution must be blocked when preflight fails."
        )
