"""WP-R0: isolated, synthetic-only research integrity primitives (Python stdlib).

This module does NOT connect to providers, operational traders, or databases.
All times are timezone-aware UTC. No state here grants trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
import random
from typing import Any, Iterable, Mapping


def utc(value: datetime) -> datetime:
    """Reject naive timestamps, normalize to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required")
    return value.astimezone(timezone.utc)


def digest(value: Any) -> str:
    """Canonical digest for JSON-compatible, semantically stable content."""
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(serialized.encode("utf-8")).hexdigest()


class EvidenceState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


class Availability(str, Enum):
    VERIFIED = "VERIFIED"
    MODELED = "MODELED"
    UNVERIFIED = "UNVERIFIED"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class TemporalFact:
    fact_id: str
    event_at: datetime
    available_at: datetime | None
    verified_receipt: bool
    source_version: str
    final_at: datetime | None = None
    is_final_bar: bool = False

    def __post_init__(self) -> None:
        if not self.fact_id or not self.source_version:
            raise ValueError("Fact identity and source version required")
        utc(self.event_at)
        if self.available_at is not None:
            utc(self.available_at)
        if self.final_at is not None:
            utc(self.final_at)
        if self.verified_receipt and self.available_at is None:
            raise ValueError("Verified receipt requires available_at")
        if self.is_final_bar and self.final_at is None:
            raise ValueError("Final bars must provide final_at")


@dataclass(frozen=True)
class VisibilityDecision:
    classification: Availability
    allowed_for_live_equivalent: bool
    reason: str


def classify_visibility(
    fact: TemporalFact,
    decision_at: datetime,
    *,
    allow_modeled_replay: bool = False,
) -> VisibilityDecision:
    """Conservative time eligibility; modeled replay is never live-equivalent."""
    cutoff = utc(decision_at)
    if fact.is_final_bar and fact.final_at is not None and utc(fact.final_at) > cutoff:
        return VisibilityDecision(Availability.INELIGIBLE, False, "BAR_NOT_FINAL_AT_DECISION")
    if utc(fact.event_at) > cutoff:
        return VisibilityDecision(Availability.INELIGIBLE, False, "EVENT_IN_FUTURE")
    if fact.available_at is None:
        return VisibilityDecision(Availability.UNVERIFIED, False, "RECEIPT_NOT_PROVEN")
    if utc(fact.available_at) > cutoff:
        return VisibilityDecision(Availability.INELIGIBLE, False, "AVAILABLE_AFTER_DECISION")
    if fact.verified_receipt:
        return VisibilityDecision(Availability.VERIFIED, True, "VERIFIED_AT_CUTOFF")
    if allow_modeled_replay:
        return VisibilityDecision(Availability.MODELED, False, "MODELED_REPLAY_ONLY")
    return VisibilityDecision(Availability.UNVERIFIED, False, "AVAILABILITY_UNVERIFIED")


@dataclass(frozen=True)
class FrozenProtocol:
    hypothesis_id: str
    dataset_digest: str
    primary_metric: str
    eligible_population: str
    comparator: str
    split_plan: str
    cost_policy: str
    trial_family_id: str
    label_horizon: str

    def __post_init__(self) -> None:
        if not all(vars(self).values()):
            raise ValueError("Every frozen protocol field is required")

    @property
    def protocol_digest(self) -> str:
        return digest(vars(self))


@dataclass(frozen=True)
class RunManifest:
    protocol_digest: str
    fixture_digest: str
    code_version: str
    config_digest: str
    environment_version: str
    seed: int


def deterministic_run(manifest: RunManifest, values: Iterable[float]) -> str:
    """Digest deterministic normalized output, not wall-clock metadata."""
    observations = [float(v) for v in values]
    if any(not math.isfinite(v) for v in observations):
        raise ValueError("Non-finite observations are forbidden")
    rng = random.Random(manifest.seed)
    sample = [observations[rng.randrange(len(observations))] for _ in observations] if observations else []
    return digest({
        "manifest": vars(manifest),
        "sample": sample,
        "mean": math.fsum(sample) / len(sample) if sample else None,
    })


@dataclass(frozen=True)
class EvidenceRevision:
    artifact_id: str
    revision: int
    state: EvidenceState
    reason: str


class EvidenceGraph:
    """Version-specific DAG; append-only evidence state revisions."""

    def __init__(self) -> None:
        self._children: dict[str, set[str]] = {}
        self._revisions: dict[str, list[EvidenceRevision]] = {}

    def add_artifact(self, artifact_id: str, parents: Iterable[str] = ()) -> None:
        if not artifact_id or artifact_id in self._children:
            raise ValueError("Artifact already exists or has no ID")
        parents = tuple(parents)
        if artifact_id in parents or any(p not in self._children for p in parents):
            raise ValueError("Parents must exist and not include self")
        self._children[artifact_id] = set()
        self._revisions[artifact_id] = [
            EvidenceRevision(artifact_id, 1, EvidenceState.UNVERIFIED, "NEW_ARTIFACT")
        ]
        for parent in parents:
            self._children[parent].add(artifact_id)

    def descendants(self, artifact_id: str) -> frozenset[str]:
        if artifact_id not in self._children:
            raise KeyError(artifact_id)
        result: set[str] = set()
        pending = list(self._children[artifact_id])
        while pending:
            item = pending.pop()
            if item not in result:
                result.add(item)
                pending.extend(self._children[item])
        return frozenset(result)

    def revise(self, artifact_id: str, state: EvidenceState, reason: str) -> EvidenceRevision:
        if artifact_id not in self._revisions or not reason:
            raise ValueError("Known artifact and reason required")
        history = self._revisions[artifact_id]
        revision = EvidenceRevision(artifact_id, len(history) + 1, state, reason)
        history.append(revision)
        return revision

    def history(self, artifact_id: str) -> tuple[EvidenceRevision, ...]:
        return tuple(self._revisions[artifact_id])

    def invalidate_source(self, source_id: str, reason: str) -> frozenset[str]:
        affected = self.descendants(source_id) | {source_id}
        for artifact in sorted(affected):
            self.revise(artifact, EvidenceState.INVALID, "UPSTREAM_CORRECTION:" + reason)
        return frozenset(affected)


class HoldoutCustody:
    """Access logging; tuning after holdout exposure invalidates 'untouched'."""
    def __init__(self) -> None:
        self._opened: set[str] = set()
        self._tainted: set[str] = set()
        self.audit: list[tuple[str, str]] = []

    def open(self, experiment_id: str) -> None:
        self._opened.add(experiment_id)
        self.audit.append((experiment_id, "HOLDOUT_OPENED"))

    def tune(self, experiment_id: str) -> None:
        if experiment_id in self._opened:
            self._tainted.add(experiment_id)
        self.audit.append((experiment_id, "TUNED_AFTER_HOLDOUT" if experiment_id in self._tainted else "TUNED"))

    def untouched(self, experiment_id: str) -> bool:
        return experiment_id not in self._tainted


class ExperimentRegistry:
    """Atomic logical publication and complete trial accounting in memory."""
    def __init__(self) -> None:
        self.protocols: dict[str, FrozenProtocol] = {}
        self.trials: dict[str, list[tuple[str, str]]] = {}
        self.results: dict[str, str] = {}

    def register(self, experiment_id: str, protocol: FrozenProtocol) -> None:
        if not experiment_id or experiment_id in self.protocols:
            raise ValueError("Experiment must have a unique ID")
        self.protocols[experiment_id] = protocol
        self.trials[experiment_id] = []

    def log_trial(self, experiment_id: str, candidate: str, outcome: str) -> None:
        if experiment_id in self.results:
            raise ValueError("Published experiment is immutable")
        self.trials[experiment_id].append((candidate, outcome))

    def publish(self, experiment_id: str, result_digest: str, *, complete: bool) -> None:
        if not complete or not result_digest:
            raise ValueError("Partial/failed runs cannot publish complete evidence")
        if experiment_id in self.results:
            if self.results[experiment_id] == result_digest:
                return  # Idempotent retry of the exact same logical output
            raise ValueError("Conflicting publication")
        self.results[experiment_id] = result_digest


class ResearchAuthority:
    ALLOWED = frozenset({"read_market_versions", "write_research_experiment", "propose_candidate"})

    @classmethod
    def authorize(cls, action: str) -> bool:
        if action not in cls.ALLOWED:
            raise PermissionError("Research role cannot perform: " + action)
        return True


@dataclass(frozen=True)
class NullSearchReport:
    replicates: int
    candidates_per_replicate: int
    family_false_positive_rate: float
    standard_error: float


def simulate_null_search(*, seed: int, replicates: int, candidates: int, family_alpha: float = 0.05) -> NullSearchReport:
    """Synthetic independent Uniform(0,1) null p-values; Bonferroni family guard.

    This checks selection bookkeeping under an ideal null, NOT empirical
    performance with dependent price samples or real trading outcomes.
    """
    if replicates < 1 or candidates < 1 or not 0 < family_alpha < 1:
        raise ValueError("Invalid search design")
    rng = random.Random(seed)
    false_families = 0
    for _ in range(replicates):
        p_values = [rng.random() for _ in range(candidates)]
        false_families += min(p_values) <= family_alpha / candidates
    rate = false_families / replicates
    return NullSearchReport(replicates, candidates, rate, math.sqrt(rate * (1 - rate) / replicates))
