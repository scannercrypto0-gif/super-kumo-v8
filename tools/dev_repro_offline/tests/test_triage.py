"""Tests for Stage 9 — Offline Failure Triage."""
from tools.dev_repro_offline.runner import RunResult, RunStatus
from tools.dev_repro_offline.triage import (
    triage_result, triage_report, TriageCategory,
    RunReport,
)


def _result(status, stdout="", stderr="", notes="", entry_id="T1") -> RunResult:
    return RunResult(
        entry_id=entry_id, status=status,
        command=["pytest", "tests/"],
        stdout_excerpt=stdout, stderr_excerpt=stderr, notes=notes,
    )


def test_blocked_categorised_as_blocked():
    r = _result(RunStatus.BLOCKED, notes="BLOCKED: SHA mismatch")
    t = triage_result(r)
    assert t.category == TriageCategory.BLOCKED


def test_import_error_detected():
    r = _result(RunStatus.FAIL, stderr="ModuleNotFoundError: No module named 'foo'")
    t = triage_result(r)
    assert t.category == TriageCategory.IMPORT_ERROR


def test_assertion_fail_detected():
    r = _result(RunStatus.FAIL, stdout="E   AssertionError: expected 1 got 2")
    t = triage_result(r)
    assert t.category == TriageCategory.ASSERTION_FAIL


def test_fixture_missing_detected():
    r = _result(RunStatus.FAIL, stderr="FileNotFoundError: fixture not found")
    t = triage_result(r)
    assert t.category == TriageCategory.FIXTURE_MISSING


def test_timeout_categorised():
    r = _result(RunStatus.TIMEOUT, notes="Timed out after 120s")
    t = triage_result(r)
    assert t.category == TriageCategory.TIMEOUT


def test_namespace_leak_highest_priority():
    # Even if there's also an assertion error, namespace leak takes priority
    r = _result(RunStatus.FAIL,
                stdout="AssertionError\nsrc.aql imported",
                stderr="E   assert False")
    t = triage_result(r)
    assert t.category == TriageCategory.NAMESPACE_LEAK


def test_unknown_for_empty_output():
    r = _result(RunStatus.FAIL, stdout="", stderr="")
    t = triage_result(r)
    assert t.category == TriageCategory.UNKNOWN


def test_triage_report_skips_pass():
    rr = RunReport(dry_run=False, results=[
        _result(RunStatus.PASS, entry_id="P1"),
        _result(RunStatus.FAIL, stderr="ImportError", entry_id="F1"),
    ])
    tr = triage_report(rr)
    assert len(tr.entries) == 1
    assert tr.entries[0].entry_id == "F1"


def test_summary_not_empty_on_failures():
    rr = RunReport(dry_run=False, results=[
        _result(RunStatus.BLOCKED, notes="blocked", entry_id="B1"),
    ])
    tr = triage_report(rr)
    assert tr.summary().startswith("TRIAGE")
