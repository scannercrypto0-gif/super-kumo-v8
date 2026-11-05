"""
Data Source Isolator — Undocumented Source / Timing Quarantine
==============================================================
Enforces that only fully documented, verified data enters the Factory Lab pipeline.

Quarantine rules (all fail-closed):
  R1 — UNKNOWN_UNVERIFIED evidence class → QUARANTINED_UNDOCUMENTED_SRC
  R2 — UNKNOWN or MISSING source availability → QUARANTINED_UNDOCUMENTED_TIME
  R3 — cutoff_ms == 0 (sentinel / placeholder) → QUARANTINED_UNDOCUMENTED_TIME
  R4 — ScannerQuarantineStatus.UNKNOWN_DEFERRED → QUARANTINED_SCANNER_P0
  R5 — source_dataset_version < 1 → QUARANTINED_UNDOCUMENTED_SRC
  R6 — source_dataset_id empty / missing → QUARANTINED_UNDOCUMENTED_SRC

Rules are evaluated in order; the first match wins.  Admitted nominations
are assigned QuarantineVerdict.ADMITTED.

This module imports ONLY from the discoverer contracts package.
No imports from Scanner, Work, Holdout, or any unmerged PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from tools.strategy_discoverer_offline.contracts import (
    NominationEvidenceV1,
    EvidenceClass,
    SourceAvailability,
    ScannerQuarantineStatus,
)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class QuarantineVerdict(str, Enum):
    ADMITTED                      = "ADMITTED"
    QUARANTINED_UNDOCUMENTED_SRC  = "QUARANTINED_UNDOCUMENTED_SRC"
    QUARANTINED_UNDOCUMENTED_TIME = "QUARANTINED_UNDOCUMENTED_TIME"
    QUARANTINED_SCANNER_P0        = "QUARANTINED_SCANNER_P0"
    QUARANTINED_EVIDENCE_UNKNOWN  = "QUARANTINED_EVIDENCE_UNKNOWN"


@dataclass(frozen=True)
class IsolationResult:
    """
    Result of isolating a single NominationEvidenceV1.

    verdict         : QuarantineVerdict
    rule_id         : rule that triggered quarantine (None if ADMITTED)
    reason          : human-readable explanation
    evidence_class  : EvidenceClass from the nomination
    source_avail    : SourceAvailability from the nomination
    scanner_status  : ScannerQuarantineStatus from the nomination
    """
    verdict: str
    rule_id: Optional[str]
    reason: str
    evidence_class: str
    source_avail: str
    scanner_status: str

    @property
    def admitted(self) -> bool:
        return self.verdict == QuarantineVerdict.ADMITTED.value

    @property
    def quarantined(self) -> bool:
        return not self.admitted


# ---------------------------------------------------------------------------
# Isolation rules
# ---------------------------------------------------------------------------

_RULES: list = []


def _rule(rule_id: str):
    """Decorator: register a rule function."""
    def decorator(fn):
        _RULES.append((rule_id, fn))
        return fn
    return decorator


@_rule("R1")
def _r1_unknown_evidence(ev: NominationEvidenceV1) -> Optional[tuple]:
    """UNKNOWN_UNVERIFIED evidence class — undocumented source."""
    if ev.evidence_class == EvidenceClass.UNKNOWN_UNVERIFIED.value:
        return (
            QuarantineVerdict.QUARANTINED_EVIDENCE_UNKNOWN,
            "evidence_class=UNKNOWN_UNVERIFIED: source provenance not documented",
        )
    return None


@_rule("R2")
def _r2_unavailable_source(ev: NominationEvidenceV1) -> Optional[tuple]:
    """UNKNOWN or MISSING source availability — undocumented timing."""
    if ev.source_availability in (
        SourceAvailability.UNKNOWN.value,
        SourceAvailability.MISSING.value,
    ):
        return (
            QuarantineVerdict.QUARANTINED_UNDOCUMENTED_TIME,
            f"source_availability={ev.source_availability}: bar availability not documented",
        )
    return None


@_rule("R3")
def _r3_zero_cutoff(ev: NominationEvidenceV1) -> Optional[tuple]:
    """cutoff_ms == 0 is a placeholder / sentinel — timing undocumented."""
    if ev.cutoff_ms == 0:
        return (
            QuarantineVerdict.QUARANTINED_UNDOCUMENTED_TIME,
            "cutoff_ms=0: decision cutoff is a placeholder, timing undocumented",
        )
    return None


@_rule("R4")
def _r4_scanner_p0(ev: NominationEvidenceV1) -> Optional[tuple]:
    """UNKNOWN_DEFERRED scanner status while P0 issues unresolved."""
    if ev.quarantine_status == ScannerQuarantineStatus.UNKNOWN_DEFERRED.value:
        return (
            QuarantineVerdict.QUARANTINED_SCANNER_P0,
            "quarantine_status=UNKNOWN_DEFERRED: Scanner P0 issues not resolved",
        )
    return None


@_rule("R5")
def _r5_bad_dataset_version(ev: NominationEvidenceV1) -> Optional[tuple]:
    """source_dataset_version < 1 — dataset version undocumented."""
    if ev.source_dataset_version < 1:
        return (
            QuarantineVerdict.QUARANTINED_UNDOCUMENTED_SRC,
            f"source_dataset_version={ev.source_dataset_version}: must be ≥ 1",
        )
    return None


@_rule("R6")
def _r6_empty_dataset_id(ev: NominationEvidenceV1) -> Optional[tuple]:
    """source_dataset_id empty — dataset identity undocumented."""
    if not ev.source_dataset_id or not ev.source_dataset_id.strip():
        return (
            QuarantineVerdict.QUARANTINED_UNDOCUMENTED_SRC,
            "source_dataset_id is empty: dataset identity not documented",
        )
    return None


# ---------------------------------------------------------------------------
# DataSourceIsolator
# ---------------------------------------------------------------------------

class DataSourceIsolator:
    """
    Enforces data-provenance isolation for Discoverer → Factory Lab routing.

    Usage
    -----
    isolator = DataSourceIsolator()
    result = isolator.evaluate(evidence)
    if result.admitted:
        # proceed to bridge
    else:
        # quarantine the nomination
    """

    def evaluate(self, evidence: NominationEvidenceV1) -> IsolationResult:
        """
        Evaluate a NominationEvidenceV1 against all isolation rules.

        Rules are applied in order R1–R6.  First match wins.
        Returns ADMITTED only if all rules pass.
        """
        if not isinstance(evidence, NominationEvidenceV1):
            raise TypeError(f"Expected NominationEvidenceV1, got {type(evidence)}")

        for rule_id, rule_fn in _RULES:
            outcome = rule_fn(evidence)
            if outcome is not None:
                verdict, reason = outcome
                return IsolationResult(
                    verdict=verdict.value,
                    rule_id=rule_id,
                    reason=reason,
                    evidence_class=evidence.evidence_class,
                    source_avail=evidence.source_availability,
                    scanner_status=evidence.quarantine_status,
                )

        return IsolationResult(
            verdict=QuarantineVerdict.ADMITTED.value,
            rule_id=None,
            reason="All isolation rules passed",
            evidence_class=evidence.evidence_class,
            source_avail=evidence.source_availability,
            scanner_status=evidence.quarantine_status,
        )

    def evaluate_batch(
        self, evidences: list
    ) -> tuple:
        """
        Evaluate a batch of NominationEvidenceV1 objects.

        Returns (admitted: list[NominationEvidenceV1],
                 quarantined: list[IsolationResult])
        """
        admitted, quarantined = [], []
        for ev in evidences:
            result = self.evaluate(ev)
            if result.admitted:
                admitted.append(ev)
            else:
                quarantined.append(result)
        return admitted, quarantined
