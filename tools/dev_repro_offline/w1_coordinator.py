"""
Stage 7 — W1 Evidence Coordinator
Labels Core (12/12) and Factory (7/7) results separately.
Proves that separate results at different SHAs ≠ integrated 19/19.
Never claims combined/integrated W1 verification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .manifest import ManifestEntryStatus
from .runner import RunReport, RunStatus


class W1Component(str, Enum):
    CORE    = "CORE"
    FACTORY = "FACTORY"
    REPRO   = "REPRO_SELF"


@dataclass
class W1ComponentResult:
    component: W1Component
    entry_id: str
    status: RunStatus
    expected_sha: str
    actual_sha: str
    is_verified_at_expected_sha: bool
    notes: str = ""


@dataclass
class W1CoordinatorReport:
    """
    Summary of W1 component results.

    CRITICAL INVARIANT:
      - Core (12/12) passes were recorded at SHA 6f8d64f — not current HEAD.
      - Factory (7/7) passes were recorded at SHA 57c8d35 — not current HEAD.
      - These are NOT an integrated verification.  Separate ≠ 19/19 integrated.
    """
    core_result:    Optional[W1ComponentResult] = None
    factory_result: Optional[W1ComponentResult] = None
    repro_result:   Optional[W1ComponentResult] = None
    current_head:   str = ""
    integrated_claim: bool = False   # ALWAYS False — invariant enforced below

    def __post_init__(self):
        # Enforce invariant: this coordinator never asserts integration
        object.__setattr__(self, "integrated_claim", False)

    def summary(self) -> str:
        lines = [
            "W1 COORDINATOR REPORT",
            f"Current HEAD: {self.current_head}",
        ]
        for label, result in [
            ("CORE   ", self.core_result),
            ("FACTORY", self.factory_result),
            ("REPRO  ", self.repro_result),
        ]:
            if result is None:
                lines.append(f"  {label}: NOT RECORDED")
            else:
                verified = "YES" if result.is_verified_at_expected_sha else "NO"
                lines.append(
                    f"  {label}: {result.status.value}"
                    f" | expected_sha={result.expected_sha}"
                    f" | verified_at_that_sha={verified}"
                    f" | {result.notes}"
                )
        lines.append(
            "INTEGRATED (19/19): NOT VERIFIED"
            " — separate component results at different SHAs ≠ integrated."
        )
        return "\n".join(lines)


# Known SHAs (mirrors manifest.py)
_CORE_W1_SHA    = "6f8d64f"
_FACTORY_W1_SHA = "57c8d35"


def build_w1_coordinator_report(
    run_report: RunReport,
    current_head: str,
) -> W1CoordinatorReport:
    """
    Inspect a RunReport and label each W1 component separately.
    Never declares integrated W1 verification.
    """
    by_id = {r.entry_id: r for r in run_report.results}

    def _make(
        component: W1Component,
        entry_id: str,
        expected_sha: str,
        owner_note: str,
    ) -> W1ComponentResult:
        run = by_id.get(entry_id)
        if run is None:
            return W1ComponentResult(
                component=component,
                entry_id=entry_id,
                status=RunStatus.BLOCKED,
                expected_sha=expected_sha,
                actual_sha=current_head,
                is_verified_at_expected_sha=False,
                notes=f"Entry not in run report. {owner_note}",
            )
        # Verified only if ran at the expected SHA
        verified = (
            run.status == RunStatus.PASS
            and current_head.startswith(expected_sha)
        )
        return W1ComponentResult(
            component=component,
            entry_id=entry_id,
            status=run.status,
            expected_sha=expected_sha,
            actual_sha=current_head,
            is_verified_at_expected_sha=verified,
            notes=owner_note + (
                f" Owner-recorded passes at SHA {expected_sha}."
                if not verified else
                f" Independently verified at SHA {expected_sha}."
            ),
        )

    core = _make(
        W1Component.CORE, "CORE-W1-UNIT", _CORE_W1_SHA,
        "Core W1 — 12/12 owner-run passes."
    )
    factory = _make(
        W1Component.FACTORY, "FACTORY-W1-UNIT", _FACTORY_W1_SHA,
        "Factory W1 — 7/7 owner-run passes. Stacks on unmerged Core PR."
    )

    repro_run = by_id.get("REPRO-SELF-001")
    repro = W1ComponentResult(
        component=W1Component.REPRO,
        entry_id="REPRO-SELF-001",
        status=repro_run.status if repro_run else RunStatus.BLOCKED,
        expected_sha=current_head,
        actual_sha=current_head,
        is_verified_at_expected_sha=(
            repro_run.status == RunStatus.PASS if repro_run else False
        ),
        notes="dev_repro_offline self-tests.",
    )

    return W1CoordinatorReport(
        core_result=core,
        factory_result=factory,
        repro_result=repro,
        current_head=current_head,
    )
