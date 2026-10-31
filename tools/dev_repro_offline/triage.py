"""
Stage 9 — Offline Failure Triage
Categorises run failures without auto-editing code.
Ambiguous causes → UNKNOWN (never fabricated).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .runner import RunReport, RunResult, RunStatus


class TriageCategory(str, Enum):
    IMPORT_ERROR    = "IMPORT_ERROR"      # ModuleNotFoundError / ImportError
    ASSERTION_FAIL  = "ASSERTION_FAIL"    # AssertionError in test output
    FIXTURE_MISSING = "FIXTURE_MISSING"   # FileNotFoundError / fixture path
    TIMEOUT         = "TIMEOUT"           # run exceeded time limit
    NAMESPACE_LEAK  = "NAMESPACE_LEAK"    # protected namespace in output
    PLATFORM_ISSUE  = "PLATFORM_ISSUE"    # OS-specific failure hint
    BLOCKED         = "BLOCKED"           # entry was BLOCKED — not a failure
    UNKNOWN         = "UNKNOWN"           # cannot determine cause


@dataclass
class TriageEntry:
    entry_id: str
    run_status: RunStatus
    category: TriageCategory
    evidence: str = ""           # excerpt from stdout/stderr used
    remediation_hint: str = ""


@dataclass
class TriageReport:
    entries: list[TriageEntry] = field(default_factory=list)

    def has_unknown(self) -> bool:
        return any(e.category == TriageCategory.UNKNOWN for e in self.entries)

    def summary(self) -> str:
        counts: dict[TriageCategory, int] = {}
        for e in self.entries:
            counts[e.category] = counts.get(e.category, 0) + 1
        parts = [f"{k.value}={v}" for k, v in sorted(counts.items(), key=lambda x: x[0])]
        return "TRIAGE " + " ".join(parts) if parts else "TRIAGE (empty)"


# ── keyword heuristics ────────────────────────────────────────────────────────

_IMPORT_KEYWORDS   = ("ModuleNotFoundError", "ImportError", "No module named")
_ASSERT_KEYWORDS   = ("AssertionError", "assert ", "FAILED", "E   assert")
_FIXTURE_KEYWORDS  = ("FileNotFoundError", "No such file", "fixture")
_PLATFORM_KEYWORDS = ("WinError", "PermissionError", "permission denied",
                      "CRLF", "line ending")
_NAMESPACE_KEYWORDS = ("src.aql", "research_wp_r0")


def _scan(text: str, keywords: tuple[str, ...]) -> Optional[str]:
    for kw in keywords:
        if kw in text:
            # return first matching line as evidence
            for line in text.splitlines():
                if kw in line:
                    return line[:200]
    return None


def triage_result(result: RunResult) -> TriageEntry:
    if result.status == RunStatus.BLOCKED:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.BLOCKED,
            evidence=result.notes[:200],
            remediation_hint=(
                "This entry is BLOCKED because its expected SHA is not the current HEAD."
            ),
        )

    if result.status in (RunStatus.PASS, RunStatus.DRY_RUN, RunStatus.SKIP):
        # Nothing to triage
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.UNKNOWN,
            evidence="(no failure — status is " + result.status.value + ")",
        )

    if result.status == RunStatus.TIMEOUT:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.TIMEOUT,
            evidence=result.notes,
            remediation_hint="Increase timeout or investigate infinite loop.",
        )

    combined = (result.stdout_excerpt or "") + "\n" + (result.stderr_excerpt or "")

    # Check namespace leak first (highest severity)
    ev = _scan(combined, _NAMESPACE_KEYWORDS)
    if ev:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.NAMESPACE_LEAK,
            evidence=ev,
            remediation_hint=(
                "A protected namespace (src.aql / research_wp_r0) appeared in output. "
                "Ensure no protected import leaked into the test environment."
            ),
        )

    ev = _scan(combined, _IMPORT_KEYWORDS)
    if ev:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.IMPORT_ERROR,
            evidence=ev,
            remediation_hint="Install missing package or fix import path.",
        )

    ev = _scan(combined, _FIXTURE_KEYWORDS)
    if ev:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.FIXTURE_MISSING,
            evidence=ev,
            remediation_hint="Check that fixture files exist under tools/dev_repro_offline/tests/.",
        )

    ev = _scan(combined, _PLATFORM_KEYWORDS)
    if ev:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.PLATFORM_ISSUE,
            evidence=ev,
            remediation_hint="Platform-specific issue; check OS and line-ending settings.",
        )

    ev = _scan(combined, _ASSERT_KEYWORDS)
    if ev:
        return TriageEntry(
            entry_id=result.entry_id,
            run_status=result.status,
            category=TriageCategory.ASSERTION_FAIL,
            evidence=ev,
            remediation_hint="A test assertion failed. Review the failing test for details.",
        )

    # Cannot categorise
    return TriageEntry(
        entry_id=result.entry_id,
        run_status=result.status,
        category=TriageCategory.UNKNOWN,
        evidence=(combined[:300] if combined.strip() else "(no output)"),
        remediation_hint=(
            "Cannot determine cause automatically. "
            "Review full output manually. Do NOT auto-edit code."
        ),
    )


def triage_report(run_report: RunReport) -> TriageReport:
    """Triage all failed/blocked results in a RunReport."""
    entries = []
    for result in run_report.results:
        if result.status not in (RunStatus.PASS, RunStatus.DRY_RUN, RunStatus.SKIP):
            entries.append(triage_result(result))
    return TriageReport(entries=entries)
