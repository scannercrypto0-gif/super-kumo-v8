"""
Gate 1 Argv Grammar Regression Tests — Issue #215 Gate 1 (PR #214)
====================================================================
Proves full argv grammar: _allowed() must reject forbidden inputs and
zero subprocess launches occur on any forbidden argv.

FAIL→PASS cycle:
  RED  (SHA 6406d66): G1-GAP-1 through G1-GAP-5 all FAIL
         (_allowed() returns True for inputs that must be blocked)
  GREEN (post-fix SHA): all tests PASS

Confirmed BUGS on 6406d66:
  G1-GAP-1: python/python3 accepted — arbitrary file execution risk
  G1-GAP-2: pytest allows path traversal (../../) in module position
  G1-GAP-3: pytest allows absolute paths (/ prefix) in module position
  G1-GAP-4: pytest allows module_path flag injection (--flag as module)
  G1-GAP-5: pytest --forked (unapproved flag) passes because only
             -p/--co/-c/-m are in _BLOCKED_FLAGS

Run:
    cd <repo_root> && pytest tools/dev_repro_offline/tests/test_g1_argv_regression.py -v
"""
from __future__ import annotations

import pytest

from tools.dev_repro_offline.runner import _allowed, _build_command, RunStatus, run_entry
from tools.dev_repro_offline.manifest import ManifestEntry, ManifestEntryStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    cmd: str = "pytest {module} -v --tb=short",
    module: str = "tools/dev_repro_offline/tests/",
    status: ManifestEntryStatus = ManifestEntryStatus.EXPECTED,
) -> ManifestEntry:
    return ManifestEntry(
        entry_id="G1-TEST",
        label="Gate1 test entry",
        command_template=cmd,
        module_path=module,
        expected_sha="6406d66",
        owner_issue="#215",
        status=status,
    )


# ---------------------------------------------------------------------------
# ALREADY CORRECT (GREEN on both pre- and post-fix): verify baseline stays
# ---------------------------------------------------------------------------

class TestG1BaselineAlreadyBlocked:
    """These must be blocked on BOTH pre- and post-fix SHAs."""

    def test_g1_baseline_bash_blocked(self):
        """bash must not be in allowed executables."""
        assert not _allowed(["bash", "-c", "rm -rf /"])

    def test_g1_baseline_curl_blocked(self):
        """curl must not be in allowed executables."""
        assert not _allowed(["curl", "http://example.com"])

    def test_g1_baseline_python_dash_m_blocked(self):
        """python -m is an existing block (arbitrary module execution)."""
        assert not _allowed(["python", "-m", "pytest"])

    def test_g1_baseline_python_dash_c_blocked(self):
        """python -c is an existing block (arbitrary inline code)."""
        assert not _allowed(["python", "-c", "import os; os.system('id')"])

    def test_g1_baseline_pytest_dash_p_blocked(self):
        """pytest -p (plugin injection) must be blocked."""
        assert not _allowed(["pytest", "-p", "evil_plugin", "tests/"])

    def test_g1_baseline_empty_argv_blocked(self):
        """Empty argv must be blocked."""
        assert not _allowed([])

    def test_g1_baseline_pytest_allowed(self):
        """Legitimate pytest invocation must still be allowed after fix."""
        assert _allowed(["pytest", "tools/dev_repro_offline/tests/", "-v", "--tb=short"])

    def test_g1_baseline_pytest_tests_root_allowed(self):
        """pytest tests/ (approved root) must still be allowed after fix."""
        assert _allowed(["pytest", "tests/", "-v", "--tb=short"])


# ---------------------------------------------------------------------------
# G1-GAP-1: python/python3 arbitrary file — BUG: currently PASSES, must FAIL
# ---------------------------------------------------------------------------

class TestG1Gap1PythonArbitraryFile:
    """
    G1-GAP-1 BUG: python and python3 are in _ALLOWED_EXECUTABLES.
    The manifest never uses python/python3 commands — only pytest.
    Allowing them permits arbitrary file execution: `python /etc/cron.py`.
    Fix: remove python/python3 from _ALLOWED_EXECUTABLES.

    RED on 6406d66: _allowed(["python", "arbitrary.py"]) returns True
    GREEN after fix: returns False
    """

    def test_g1_python_arbitrary_path_blocked(self):
        """python <any_file> must be blocked — python not in approved executables."""
        assert not _allowed(["python", "arbitrary_path.py"])

    def test_g1_python3_arbitrary_path_blocked(self):
        """python3 <any_file> must be blocked."""
        assert not _allowed(["python3", "arbitrary_path.py"])

    def test_g1_python_absolute_path_blocked(self):
        """python /tmp/evil.py must be blocked."""
        assert not _allowed(["python", "/tmp/evil.py"])

    def test_g1_python3_absolute_path_blocked(self):
        """python3 /etc/cron.d/evil.py must be blocked."""
        assert not _allowed(["python3", "/etc/cron.d/evil.py"])

    def test_g1_python_no_flags_still_blocked(self):
        """Even python <path> with no flags must be blocked (exe not in allowlist)."""
        assert not _allowed(["python", "tests/unit/test_foo.py"])

    def test_g1_run_entry_python_cmd_blocked(self, tmp_path):
        """run_entry with python command_template must return BLOCKED, not launch."""
        e = _entry(cmd="python {module}", module="tools/dev_repro_offline/tests/")
        result = run_entry(e, str(tmp_path), dry_run=False)
        assert result.status == RunStatus.BLOCKED, (
            f"Expected BLOCKED, got {result.status}: {result.notes}"
        )


# ---------------------------------------------------------------------------
# G1-GAP-2: pytest path traversal — BUG: currently PASSES, must FAIL
# ---------------------------------------------------------------------------

class TestG1Gap2PytestPathTraversal:
    """
    G1-GAP-2 BUG: _allowed() does not check for path traversal sequences
    in the module_path position of pytest argv.
    `pytest ../../etc/passwd` currently passes the guard.
    Fix: reject any argv element that contains '../' or starts with absolute path.

    RED on 6406d66: _allowed(["pytest", "../../etc/"]) returns True
    GREEN after fix: returns False
    """

    def test_g1_pytest_dotdot_traversal_blocked(self):
        """pytest ../../ path traversal must be blocked."""
        assert not _allowed(["pytest", "../../etc/passwd"])

    def test_g1_pytest_dotdot_in_subpath_blocked(self):
        """pytest with ../ anywhere in the module path must be blocked."""
        assert not _allowed(["pytest", "tools/../../../etc/"])

    def test_g1_pytest_absolute_path_blocked(self):
        """pytest /absolute/path must be blocked."""
        assert not _allowed(["pytest", "/tmp/evil_tests/"])

    def test_g1_pytest_home_tilde_blocked(self):
        """pytest ~/evil must be blocked."""
        assert not _allowed(["pytest", "~/evil_tests/"])

    def test_g1_run_entry_traversal_blocked(self, tmp_path):
        """run_entry with traversal module_path must return BLOCKED."""
        e = _entry(cmd="pytest {module} -v", module="../../etc/")
        result = run_entry(e, str(tmp_path), dry_run=False)
        assert result.status == RunStatus.BLOCKED, (
            f"Expected BLOCKED, got {result.status}: {result.notes}"
        )


# ---------------------------------------------------------------------------
# G1-GAP-4: pytest module_path flag injection — BUG: currently PASSES
# ---------------------------------------------------------------------------

class TestG1Gap4PytestModuleFlagInjection:
    """
    G1-GAP-4 BUG: When module_path begins with '--', it appears as argv[1]
    in "pytest {module} -v --tb=short". _allowed() only blocks flags in
    _BLOCKED_FLAGS, not arbitrary unknown flags injected as module_path.
    Fix: reject any pytest argv element in the module position that
    starts with '-' (flag injection via module substitution).

    RED on 6406d66: _allowed(["pytest", "--forked", "-v"]) returns True
    GREEN after fix: returns False
    """

    def test_g1_pytest_flag_injected_as_module_blocked(self):
        """module_path='--forked' expands to pytest --forked -v → must be BLOCKED."""
        argv = _build_command("pytest {module} -v --tb=short", "--forked")
        # argv = ["pytest", "--forked", "-v", "--tb=short"]
        assert not _allowed(argv), f"Expected blocked, got allowed: {argv}"

    def test_g1_pytest_double_flag_injection_blocked(self):
        """module_path='--collect-only' → must be BLOCKED."""
        argv = _build_command("pytest {module} -v", "--collect-only")
        assert not _allowed(argv)

    def test_g1_pytest_single_dash_flag_injection_blocked(self):
        """module_path='-x' → pytest -x -v → must be BLOCKED (flag as module)."""
        argv = _build_command("pytest {module} -v", "-x")
        assert not _allowed(argv)

    def test_g1_run_entry_flag_injection_blocked(self, tmp_path):
        """run_entry where module_path='--forked' must return BLOCKED."""
        e = _entry(cmd="pytest {module} -v --tb=short", module="--forked")
        result = run_entry(e, str(tmp_path), dry_run=False)
        assert result.status == RunStatus.BLOCKED, (
            f"Expected BLOCKED, got {result.status}: {result.notes}"
        )


# ---------------------------------------------------------------------------
# G1-GAP-5: unapproved pytest flags — confirm scope + NOT_REPRODUCED note
# ---------------------------------------------------------------------------

class TestG1Gap5UnapprovedPytestFlags:
    """
    G1-GAP-5: pytest currently accepts any non-BLOCKED flag.
    The manifest only uses approved flags: -v, --tb=short, -k 'filter'.
    The PM requires: 'no arbitrary pytest flags'.

    NOTE: '--forked' appears in existing test_runner.py as 'allowed'
    because the original design only blocks code-execution flags.
    The gap is that _BLOCKED_FLAGS is too narrow.

    Resolution in this gate: document as NOT_REPRODUCED at the subprocess
    level (the template is trusted; module_path injection is the real
    attack surface, covered in GAP-4). The PM gap is acknowledged but
    fixing arbitrary pytest flag rejection requires approved-flag allowlisting
    which is a scope extension. ESCALATED for PM decision.
    """

    def test_g1_pytest_forked_is_blocked(self):
        """
        Gate 5 / G5-GAP-1 fix: --forked is no longer allowed.
        The old denylist (_BLOCKED_FLAGS) was replaced with an approved-flags
        allowlist (_APPROVED_PYTEST_FLAGS) that does not include --forked.
        RED on 8bc898f: this assertion was assert True (documenting the gap).
        GREEN after Gate 5 fix: --forked returns False.
        """
        assert not _allowed(["pytest", "tools/dev_repro_offline/tests/", "--forked"]), (
            "G5-GAP-1: --forked must be BLOCKED by the approved-flags allowlist."
        )


# ---------------------------------------------------------------------------
# Zero subprocess launch verification
# ---------------------------------------------------------------------------

class TestG1ZeroSubprocessOnForbidden:
    """
    Verify that run_entry returns BLOCKED (not PASS/FAIL/ERROR) for all
    forbidden inputs — confirming zero subprocess launches.
    """

    def test_g1_no_subprocess_on_python_cmd(self, tmp_path):
        """python command_template → BLOCKED before subprocess."""
        e = _entry(cmd="python {module}", module="tests/")
        r = run_entry(e, str(tmp_path), dry_run=False)
        assert r.status == RunStatus.BLOCKED
        assert r.returncode is None, "returncode must be None — no process ran"

    def test_g1_no_subprocess_on_traversal(self, tmp_path):
        """Path traversal module_path → BLOCKED before subprocess."""
        e = _entry(cmd="pytest {module} -v", module="../../etc/")
        r = run_entry(e, str(tmp_path), dry_run=False)
        assert r.status == RunStatus.BLOCKED
        assert r.returncode is None

    def test_g1_no_subprocess_on_flag_injection(self, tmp_path):
        """Flag-injected module_path → BLOCKED before subprocess."""
        e = _entry(cmd="pytest {module} -v", module="--forked")
        r = run_entry(e, str(tmp_path), dry_run=False)
        assert r.status == RunStatus.BLOCKED
        assert r.returncode is None


# ---------------------------------------------------------------------------
# NOT_TESTED: run_manifest direct-call bypass
# ---------------------------------------------------------------------------
#
# run_manifest(dry_run=False) does NOT enforce the preflight guard.
# A caller that bypasses run_manifest_with_preflight_guard() can launch
# subprocesses even when preflight has failed (SHA mismatch, dirty env).
#
# NOT_TESTED in this gate because:
# - run_manifest() is an internal function with documented "do not call directly"
#   warning in its docstring.
# - Testing the bypass requires a live subprocess execution with a valid pytest
#   path, which is out of scope for this security-focused gate.
# - The proper fix is to either: (a) enforce preflight in run_manifest() itself,
#   or (b) remove run_manifest() from the public API and rename with _ prefix.
# ESCALATED for PM decision.
#
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# NOT_TESTED: SHA mismatch gate at entry level
# ---------------------------------------------------------------------------
#
# ManifestEntry.expected_sha is recorded per-entry but NOT validated against
# current HEAD at run_entry() time. CORE-W1-UNIT and FACTORY-W1-UNIT are
# manually set to status=BLOCKED to handle this, but the SHA check is not
# programmatic — it relies on the manifest builder hardcoding the BLOCKED
# status.
#
# A fix would be: in run_entry(), compare entry.expected_sha against a
# passed current_sha argument and return BLOCKED if mismatch.
# This requires an API change and is outside the authorized scope of Gate 1.
# ESCALATED for PM decision.
#
# ---------------------------------------------------------------------------
