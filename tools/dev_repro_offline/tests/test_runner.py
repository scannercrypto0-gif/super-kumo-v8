"""Tests for Stage 5 — Allowlist-Gated Subprocess Runner."""
from tools.dev_repro_offline.manifest import ManifestEntry, ManifestEntryStatus, TestManifest
from tools.dev_repro_offline.runner import (
    run_entry, run_manifest, RunStatus, _allowed, _build_command,
)


def _entry(
    eid="T1",
    cmd="pytest {module} -v",
    module="tools/dev_repro_offline/tests/",
    status=ManifestEntryStatus.EXPECTED,
    sha="",          # G7-B: default to unpinned — unit tests here test non-SHA behaviour
) -> ManifestEntry:
    return ManifestEntry(
        entry_id=eid, label=eid, command_template=cmd,
        module_path=module, expected_sha=sha, owner_issue="#212", status=status,
    )


def test_build_command_substitution():
    argv = _build_command("pytest {module} -v", "tests/foo/")
    assert argv == ["pytest", "tests/foo/", "-v"]


def test_allowed_pytest():
    assert _allowed(["pytest", "tests/"])

def test_allowed_pytest_with_flags():
    assert _allowed(["pytest", "tests/", "-v", "--tb=short"])

def test_allowed_python_plain_path():
    # Gate 1 fix (G1-GAP-1, Issue #215): python removed from _ALLOWED_EXECUTABLES.
    # The manifest never uses python commands; allowing python permitted arbitrary
    # file execution. python <path> — even with no flags — is now BLOCKED.
    assert not _allowed(["python", "some/script.py"])

def test_not_allowed_python_dash_m():
    # P0-A fix: python -m <module> must be BLOCKED (arbitrary module execution)
    assert not _allowed(["python", "-m", "pytest"])

def test_not_allowed_python_dash_c():
    # P0-A fix: python -c <code> must be BLOCKED (arbitrary inline code)
    assert not _allowed(["python", "-c", "import os"])

def test_not_allowed_shell():
    assert not _allowed(["bash", "-c", "rm -rf /"])

def test_not_allowed_curl():
    assert not _allowed(["curl", "http://example.com"])


def test_dry_run_default(tmp_path):
    e = _entry()
    result = run_entry(e, str(tmp_path), dry_run=True)
    assert result.status == RunStatus.DRY_RUN


def test_blocked_entry_not_run(tmp_path):
    e = _entry(status=ManifestEntryStatus.BLOCKED)
    result = run_entry(e, str(tmp_path), dry_run=False)
    assert result.status == RunStatus.BLOCKED


def test_skip_entry_not_run(tmp_path):
    e = _entry(status=ManifestEntryStatus.SKIP)
    result = run_entry(e, str(tmp_path), dry_run=False)
    assert result.status == RunStatus.SKIP


def test_disallowed_executable_blocked(tmp_path):
    e = _entry(cmd="curl http://example.com {module}")
    result = run_entry(e, str(tmp_path), dry_run=False)
    assert result.status == RunStatus.BLOCKED


def test_run_manifest_dry_run_all_dry(tmp_path):
    m = TestManifest()
    m.add(_entry("E1"))
    m.add(_entry("B1", status=ManifestEntryStatus.BLOCKED))
    report = run_manifest(m, str(tmp_path), dry_run=True)
    statuses = {r.status for r in report.results}
    # E1 → DRY_RUN, B1 → BLOCKED
    assert RunStatus.DRY_RUN in statuses
    assert RunStatus.BLOCKED in statuses
    # Nothing actually executed
    assert RunStatus.PASS not in statuses
    assert RunStatus.FAIL not in statuses


def test_run_manifest_summary_contains_mode(tmp_path):
    m = TestManifest()
    m.add(_entry())
    report = run_manifest(m, str(tmp_path), dry_run=True)
    assert "DRY_RUN" in report.summary()
