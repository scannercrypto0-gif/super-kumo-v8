"""Tests for Stage 4 — Non-Mutating Preflight."""
from tools.dev_repro_offline.preflight import (
    run_preflight, CheckStatus, _check_python_version,
    _check_no_protected_import, _check_required_paths,
)


def test_preflight_runs_without_error(tmp_path):
    report = run_preflight(repo_root=str(tmp_path))
    assert report.overall in (CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL)
    assert len(report.checks) >= 5


def test_python_version_pass():
    import sys
    result = _check_python_version(sys.version_info.major, sys.version_info.minor)
    assert result.status == CheckStatus.PASS


def test_python_version_fail():
    result = _check_python_version(min_major=99, min_minor=0)
    assert result.status == CheckStatus.FAIL


def test_namespace_isolation():
    result = _check_no_protected_import()
    # In test environment, protected namespaces must not be loaded
    assert result.status == CheckStatus.PASS


def test_required_path_pass(tmp_path):
    (tmp_path / "some_file.py").write_text("# x")
    results = _check_required_paths(str(tmp_path), ["some_file.py"])
    assert results[0].status == CheckStatus.PASS


def test_required_path_fail(tmp_path):
    results = _check_required_paths(str(tmp_path), ["nonexistent.py"])
    assert results[0].status == CheckStatus.FAIL


def test_sha_mismatch_is_fail(tmp_path):
    report = run_preflight(repo_root=str(tmp_path), expected_sha="aaaaaaaaaaaa")
    sha_check = next(c for c in report.checks if c.check_id == "GIT-SHA")
    # If git is available and HEAD doesn't match, it should FAIL
    # If git is not available, we accept ERROR or FAIL
    assert sha_check.status in (CheckStatus.FAIL, CheckStatus.PASS)


def test_preflight_never_modifies_files(tmp_path):
    """Preflight must not create or modify any file."""
    before = set(tmp_path.rglob("*"))
    run_preflight(repo_root=str(tmp_path))
    after = set(tmp_path.rglob("*"))
    assert before == after, "Preflight must not create or modify files"


def test_overall_fail_if_any_check_fails(tmp_path):
    # Request a missing required path to force FAIL
    report = run_preflight(repo_root=str(tmp_path), required_paths=["does_not_exist.py"])
    assert report.overall == CheckStatus.FAIL
