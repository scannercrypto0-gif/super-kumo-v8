"""WP-R6: synthetic-only frozen search ledger and holdout custody contract.

Memory-local logical guards, not tamperproof logging or a validated statistical
test. Only independent external provenance can establish true OOS custody.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Sequence

from research_wp_r0.statistics import holm


def utc_stamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamps required")
    return value.astimezone(timezone.utc).isoformat()


def fingerprint(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class FrozenSearchFamily:
    family_id: str
    protocol_digest: str
    temporal_manifest_digest: str
    dataset_version: str
    metric_name: str
    metric_direction: str
    candidate_ids: tuple[str, ...]
    alpha: float
    declared_at: datetime

    def __post_init__(self) -> None:
        fields = (self.family_id, self.protocol_digest, self.temporal_manifest_digest,
                  self.dataset_version, self.metric_name)
        if not all(fields):
            raise ValueError("Every research scope/provenance reference is required")
        if self.metric_direction not in ("MAXIMIZE", "MINIMIZE"):
            raise ValueError("Metric direction required")
        if not self.candidate_ids or not all(self.candidate_ids):
            raise ValueError("A complete, nonempty candidate family must be predeclared")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("Candidate identities must be unique")
        if not isinstance(self.alpha, (float, int)) or not math.isfinite(self.alpha) or not 0 < self.alpha < 1:
            raise ValueError("Invalid family alpha")
        utc_stamp(self.declared_at)

    @property
    def digest(self) -> str:
        return fingerprint({
            "family_id": self.family_id,
            "protocol": self.protocol_digest,
            "temporal_manifest": self.temporal_manifest_digest,
            "dataset_version": self.dataset_version,
            "metric": self.metric_name,
            "direction": self.metric_direction,
            "candidate_ids": self.candidate_ids,
            "alpha": self.alpha,
            "declared_at": utc_stamp(self.declared_at),
        })


class AttemptState(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class Attempt:
    candidate_id: str
    state: AttemptState
    result_digest: str
    recorded_at: datetime
    marginal_p_value: float | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.result_digest:
            raise ValueError("Each candidate requires an outcome-evidence digest")
        utc_stamp(self.recorded_at)
        if self.state == AttemptState.COMPLETE:
            if self.marginal_p_value is None or not math.isfinite(self.marginal_p_value) or not 0 <= self.marginal_p_value <= 1:
                raise ValueError("Complete candidate needs a finite, valid-looking marginal p-value")
        elif self.marginal_p_value is not None:
            raise ValueError("Failed/ineligible candidates cannot report a calibrated p-value")


@dataclass(frozen=True)
class HoldoutEvent:
    event_type: str
    at: datetime
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.evidence_digest:
            raise ValueError("Holdout event must carry evidence")
        if self.event_type not in ("OPEN", "TUNE", "REOPEN"):
            raise ValueError("Unknown holdout operation")
        utc_stamp(self.at)


@dataclass(frozen=True)
class ResearchGateReport:
    family_digest: str
    total_declared: int
    complete: int
    failed: int
    ineligible: int
    missing: int
    selected_candidate: str | None
    adjusted_p_values: tuple[tuple[str, float], ...]
    holdout_tainted: bool
    status: str
    confirmatory_eligible: bool
    warnings: tuple[str, ...]


class TrialFamilyLedger:
    """Append-only *within one in-memory instance*. Restart is NOT durable.

    Every declared candidate must receive a final attempted result, including
    failures. No retroactive candidate registration or selection after holdout.
    """

    def __init__(self, family: FrozenSearchFamily) -> None:
        self.family = family
        self._attempts: dict[str, Attempt] = {}
        self._selected: str | None = None
        self._selection_at: datetime | None = None
        self._holdout: list[HoldoutEvent] = []
        self._sealed = False

    def record_attempt(self, attempt: Attempt) -> None:
        if self._sealed or self._selected is not None or self._holdout:
            raise ValueError("Cannot tune/add results after selection or holdout exposure")
        if attempt.candidate_id not in self.family.candidate_ids:
            raise ValueError("Undeclared candidate would conceal multiplicity")
        if attempt.candidate_id in self._attempts:
            raise ValueError("Trial revision requires a new explicitly declared family")
        if utc_stamp(attempt.recorded_at) < utc_stamp(self.family.declared_at):
            raise ValueError("Cannot register an attempt before family declaration")
        self._attempts[attempt.candidate_id] = attempt

    def select(self, candidate_id: str, *, at: datetime) -> None:
        if self._selected is not None or self._holdout or self._sealed:
            raise ValueError("Candidate can only be selected once before holdout")
        if len(self._attempts) != len(self.family.candidate_ids):
            raise ValueError("Entire trial family must be accounted for")
        if candidate_id not in self._attempts or self._attempts[candidate_id].state != AttemptState.COMPLETE:
            raise ValueError("Only a completed candidate may be selected")
        selected_at = utc_stamp(at)
        if selected_at < max(utc_stamp(a.recorded_at) for a in self._attempts.values()):
            raise ValueError("Selection cannot predate finished trials")
        self._selected, self._selection_at = candidate_id, at
        self._sealed = True

    def holdout_event(self, event: HoldoutEvent) -> None:
        if self._selected is None:
            raise ValueError("Holdout access requires a frozen, complete selected family")
        if utc_stamp(event.at) < utc_stamp(self._selection_at):
            raise ValueError("Holdout access cannot predate selection")
        if self._holdout and utc_stamp(event.at) < utc_stamp(self._holdout[-1].at):
            raise ValueError("Holdout event chronology cannot be reversed")
        if event.event_type == "OPEN" and self._holdout:
            raise ValueError("Second OPEN must be recorded explicitly as REOPEN")
        if event.event_type != "OPEN" and not self._holdout:
            raise ValueError("First holdout event must be OPEN")
        self._holdout.append(event)

    def report(self) -> ResearchGateReport:
        ordered = [self._attempts.get(i) for i in self.family.candidate_ids]
        complete = sum(x is not None and x.state == AttemptState.COMPLETE for x in ordered)
        failed = sum(x is not None and x.state == AttemptState.FAILED for x in ordered)
        ineligible = sum(x is not None and x.state == AttemptState.INELIGIBLE for x in ordered)
        missing = len(self.family.candidate_ids) - complete - failed - ineligible
        # Conservatively treat all declared attempts as the trial denominator:
        # failed/missing candidates are p=1, never silently removed from count.
        p_values = [x.marginal_p_value if x is not None and x.state == AttemptState.COMPLETE else 1.0
                    for x in ordered]
        corrected = tuple(zip(self.family.candidate_ids, holm(p_values)))
        tainted = any(e.event_type in ("TUNE", "REOPEN") for e in self._holdout)
        if missing:
            status = "INCOMPLETE_TRIAL_FAMILY"
        elif self._selected is None:
            status = "AWAITING_PRE_HOLDOUT_SELECTION"
        elif not self._holdout:
            status = "FROZEN_HOLDOUT_UNOPENED"
        elif tainted:
            status = "HOLDOUT_CONTAMINATED"
        else:
            status = "EXPLORATORY_HOLDOUT_OPENED"
        return ResearchGateReport(
            self.family.digest, len(ordered), complete, failed, ineligible,
            missing, self._selected, corrected, tainted,
            status, False,
            (
                "UNADJUSTED_FOR_SEARCH_BEYOND_DECLARED_FAMILY: no proof that earlier explorations were included.",
                "Holm needs independently validated marginal p-values; numeric correction alone does not establish calibration.",
                "Memory-only audit is not tamperproof and cannot verify true holdout access or data provenance.",
                "No result grants statistical confirmation, candidate promotion or G0/G1 operational authority.",
            ),
        )
