"""P2 Core immutable, retrospective-only historical opportunity producer.

No exchange I/O, orders, fills, outcome inspection, or holdout opening.
TEST_ONLY demo fixtures are never market evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Iterable

BAR_MS = 900_000
EMBARGO_MIN_MS = 72 * 60 * 60 * 1000
STATES = frozenset({"NO_SIGNAL", "REJECTED", "TRIGGERED", "UNKNOWN"})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_CLASS = "RETROSPECTIVE_NON_PIT"


class ContractError(ValueError):
    """A provenance, timing, identity, or frozen-protocol invariant failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _hash(obj: object) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _sha(value: str) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _id(value: str) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class HistoricalBarV1:
    open_ms: int
    close_ms: int
    content_sha256: str
    finalized: bool = True
    available_at_ms: int | None = None
    availability_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require(type(self.open_ms) is int and self.open_ms >= 0
                 and self.open_ms % BAR_MS == 0, "BAD_BAR_OPEN")
        _require(type(self.close_ms) is int and self.close_ms == self.open_ms + BAR_MS - 1,
                 "BAD_NATIVE_INTERVAL")
        _require(_sha(self.content_sha256), "BAD_BAR_HASH")
        _require(type(self.finalized) is bool, "BAD_FINALITY")
        _require(self.available_at_ms is None or
                 (type(self.available_at_ms) is int and self.available_at_ms >= self.close_ms),
                 "BAD_AVAILABILITY")
        _require((self.available_at_ms is None) ==
                 (self.availability_evidence_ref is None), "UNSUPPORTED_KNOWN_AT")
        if self.availability_evidence_ref is not None:
            _require(_id(self.availability_evidence_ref), "EMPTY_AVAILABILITY_PROOF")


@dataclass(frozen=True)
class HistoricalSourceV1:
    source_id: str
    exchange: str
    market: str
    symbol: str
    source_package_sha256: str
    manifest_sha256: str
    normalized_sha256: str
    correction_generation: str
    interval_ms: int = BAR_MS
    evidence_class: str = EVIDENCE_CLASS

    def __post_init__(self) -> None:
        for name in ("source_id", "exchange", "market", "symbol", "correction_generation"):
            _require(_id(getattr(self, name)), "MISSING_" + name.upper())
        for name in ("source_package_sha256", "manifest_sha256", "normalized_sha256"):
            _require(_sha(getattr(self, name)), "BAD_" + name.upper())
        _require(self.interval_ms == BAR_MS, "UNSUPPORTED_INTERVAL")
        _require(self.evidence_class == EVIDENCE_CLASS, "NO_HISTORICAL_PIT_UPGRADE")


def validate_bars(source: HistoricalSourceV1,
                  bars: Iterable[HistoricalBarV1]) -> tuple[HistoricalBarV1, ...]:
    """Fail closed on duplicates, gaps, unfinalized bars, and unselected corrections."""
    _require(isinstance(source, HistoricalSourceV1), "BAD_SOURCE")
    rows = tuple(bars)
    _require(bool(rows), "EMPTY_SOURCE")
    for i, bar in enumerate(rows):
        _require(isinstance(bar, HistoricalBarV1), "UNTYPED_BAR")
        _require(bar.finalized, "UNFINALIZED_BAR")
        if i:
            _require(bar.open_ms > rows[i - 1].open_ms, "DUPLICATE_OR_UNSORTED_BAR")
            _require(bar.open_ms == rows[i - 1].open_ms + BAR_MS, "SOURCE_GAP")
    return rows


@dataclass(frozen=True)
class FrozenTrialV1:
    trial_id: str
    hypothesis_sha256: str
    base_definition_sha256: str
    shadow_definition_sha256: str
    preregistration_sha256: str
    train_end_exclusive_ms: int
    holdout_start_ms: int
    holdout_end_exclusive_ms: int
    embargo_ms: int = EMBARGO_MIN_MS
    protocol_sha256: str = ""

    @classmethod
    def seal(cls, *, trial_id: str, hypothesis_sha256: str,
             base_definition_sha256: str, shadow_definition_sha256: str,
             preregistration_sha256: str, train_end_exclusive_ms: int,
             holdout_start_ms: int, holdout_end_exclusive_ms: int,
             embargo_ms: int = EMBARGO_MIN_MS) -> "FrozenTrialV1":
        data = dict(trial_id=trial_id, hypothesis_sha256=hypothesis_sha256,
                    base_definition_sha256=base_definition_sha256,
                    shadow_definition_sha256=shadow_definition_sha256,
                    preregistration_sha256=preregistration_sha256,
                    train_end_exclusive_ms=train_end_exclusive_ms,
                    holdout_start_ms=holdout_start_ms,
                    holdout_end_exclusive_ms=holdout_end_exclusive_ms,
                    embargo_ms=embargo_ms)
        return cls(**data, protocol_sha256=_hash(data))

    def __post_init__(self) -> None:
        _require(_id(self.trial_id), "MISSING_TRIAL")
        for name in ("hypothesis_sha256", "base_definition_sha256",
                     "shadow_definition_sha256", "preregistration_sha256"):
            _require(_sha(getattr(self, name)), "BAD_" + name.upper())
        _require(self.base_definition_sha256 != self.shadow_definition_sha256,
                 "SHADOW_NOT_A_DISTINCT_PREDECLARED_CANDIDATE")
        _require(type(self.embargo_ms) is int and self.embargo_ms >= EMBARGO_MIN_MS,
                 "EMBARGO_TOO_SHORT")
        _require(all(type(x) is int and x >= 0 for x in (
            self.train_end_exclusive_ms, self.holdout_start_ms,
            self.holdout_end_exclusive_ms)), "INVALID_TEMPORAL_FOLD")
        _require(self.train_end_exclusive_ms + self.embargo_ms <= self.holdout_start_ms
                 < self.holdout_end_exclusive_ms, "TRAIN_HOLDOUT_OVERLAP")
        data = {k: v for k, v in asdict(self).items() if k != "protocol_sha256"}
        _require(_sha(self.protocol_sha256) and self.protocol_sha256 == _hash(data),
                 "UNSEALED_OR_MUTATED_PROTOCOL")


@dataclass(frozen=True)
class P2HistoricalOpportunityV1:
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    source_id: str
    source_package_sha256: str
    feature_prefix_sha256: str
    policy_sha256: str
    decision_cutoff_ms: int
    decision_ms: int
    disposition: str
    direction: str | None
    direction_evidence_ref: str | None
    regime: str | None
    regime_source_sha256: str | None
    reason_code: str | None = None
    evidence_class: str = EVIDENCE_CLASS

    def __post_init__(self) -> None:
        for name in ("trial_id", "opportunity_id", "producer_event_id", "source_id"):
            _require(_id(getattr(self, name)), "MISSING_" + name.upper())
        for name in ("source_package_sha256", "feature_prefix_sha256", "policy_sha256"):
            _require(_sha(getattr(self, name)), "BAD_" + name.upper())
        _require(type(self.decision_cutoff_ms) is int and self.decision_cutoff_ms >= 0
                 and self.decision_cutoff_ms % BAR_MS == 0, "BAD_CUTOFF_GRID")
        _require(type(self.decision_ms) is int and self.decision_ms >= self.decision_cutoff_ms,
                 "DECISION_BEFORE_CUTOFF")
        _require(self.disposition in STATES, "BAD_DISPOSITION")
        _require(self.direction in ("LONG", "SHORT", None), "BAD_DIRECTION")
        _require((self.direction is None) == (self.direction_evidence_ref is None),
                 "DIRECTION_WITHOUT_ORIGINAL_EVIDENCE")
        if self.direction_evidence_ref is not None:
            _require(_id(self.direction_evidence_ref), "EMPTY_DIRECTION_PROOF")
        _require((self.regime is None) == (self.regime_source_sha256 is None),
                 "REGIME_WITHOUT_SOURCE")
        if self.regime is not None:
            _require(_id(self.regime) and _sha(self.regime_source_sha256), "INVALID_REGIME")
        _require(self.evidence_class == EVIDENCE_CLASS, "NO_PIT_UPGRADE")


def schedule_pair(trial: FrozenTrialV1, source: HistoricalSourceV1,
                  bars: Iterable[HistoricalBarV1],
                  opportunities: Iterable[P2HistoricalOpportunityV1],
                  *, permit_holdout: bool = False) -> dict:
    """Frozen two-arm *schedule*, not strategy decisions or actual outcomes.

    This development-only entrypoint cannot open a holdout, even by toggling a flag.
    """
    _require(permit_holdout is False, "HOLDOUT_LOCKED")
    valid_bars = validate_bars(source, bars)
    by_close = {b.close_ms + 1: i for i, b in enumerate(valid_bars)}
    opportunities = tuple(opportunities)
    _require(bool(opportunities), "EMPTY_OPPORTUNITY_DENOMINATOR")
    seen = set()
    pairs = []
    for item in opportunities:
        _require(isinstance(item, P2HistoricalOpportunityV1), "UNTYPED_OPPORTUNITY")
        _require(item.trial_id == trial.trial_id and item.source_id == source.source_id
                 and item.source_package_sha256 == source.source_package_sha256,
                 "CROSS_TRIAL_OR_SOURCE")
        _require(item.decision_cutoff_ms < trial.train_end_exclusive_ms,
                 "HOLDOUT_OR_EMBARGO_OPPORTUNITY")
        _require(item.decision_cutoff_ms in by_close, "CUTOFF_NOT_NATIVE_BAR_CLOSE")
        _require(item.decision_ms < trial.train_end_exclusive_ms,
                 "DECISION_AFTER_TRAIN_CUTOFF")
        _require(item.opportunity_id not in seen, "DUPLICATE_OPPORTUNITY")
        seen.add(item.opportunity_id)
        prefix = valid_bars[:by_close[item.decision_cutoff_ms] + 1]
        _require(all(b.available_at_ms is None or
                     b.available_at_ms <= item.decision_cutoff_ms for b in prefix),
                 "KNOWN_AFTER_CUTOFF")
        # Actual C2 source-specific feature-prefix digest must be independently
        # provided by the upstream producer; don't invent it from future bars.
        pair_id = _hash(dict(protocol_sha256=trial.protocol_sha256,
                             trial_id=trial.trial_id,
                             opportunity_id=item.opportunity_id))
        base = dict(arm="BASE", definition_sha256=trial.base_definition_sha256)
        shadow = dict(arm="SHADOW", definition_sha256=trial.shadow_definition_sha256)
        pairs.append(dict(pair_id=pair_id, opportunity=asdict(item),
                          arms=[base, shadow]))
    result = dict(schema="aql.p2.core.paired-schedule.v1", test_only=False,
                  evidence_class=EVIDENCE_CLASS, source=asdict(source),
                  source_bar_count=len(valid_bars), protocol=asdict(trial),
                  scheduled_total=len(pairs), pairs=pairs,
                  outcome_evaluation="NOT_PERFORMED",
                  execution_status="NOT_OBSERVED", holdout_status="SEALED_UNOPENED")
    result["artifact_sha256"] = _hash(result)
    return result
