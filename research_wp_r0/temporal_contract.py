"""WP-R5: fail-closed, frozen temporal comparability contract (stdlib only).

A validator for supplied provenance, NOT a source of independent proof that
timestamps are truthful. Historical provider arrival/receipt and universe
completeness must be audited separately. No permission to promote a strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Sequence

from research_wp_r0.evaluation import OpportunityPair


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime with a valid offset is required")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TemporalOpportunity:
    opportunity_id: str
    decision_at: datetime
    baseline_feature_available_at: datetime
    candidate_feature_available_at: datetime
    baseline_horizon_end_at: datetime
    candidate_horizon_end_at: datetime
    baseline_label_available_at: datetime
    candidate_label_available_at: datetime
    opportunity_group_id: str

    def __post_init__(self) -> None:
        if not self.opportunity_id or not self.opportunity_group_id:
            raise ValueError("Opportunity and group identity required")
        decision = _utc(self.decision_at)
        for value in (self.baseline_feature_available_at, self.candidate_feature_available_at,
                      self.baseline_horizon_end_at, self.candidate_horizon_end_at,
                      self.baseline_label_available_at, self.candidate_label_available_at):
            _utc(value)
        if (_utc(self.baseline_feature_available_at) > decision
                or _utc(self.candidate_feature_available_at) > decision):
            raise ValueError("Feature only received after the decision: potential lookahead")
        base_end = _utc(self.baseline_horizon_end_at)
        cand_end = _utc(self.candidate_horizon_end_at)
        if base_end != cand_end or base_end <= decision:
            raise ValueError("Both versions must have the same forward-label maturity")
        if (_utc(self.baseline_label_available_at) < base_end
                or _utc(self.candidate_label_available_at) < cand_end):
            raise ValueError("Label cannot be available before its outcome horizon closes")


@dataclass(frozen=True)
class FrozenTemporalManifest:
    """Logical custody record for a fixed, ordered, same-horizon universe.

    `source_version` and `protocol_digest` are supplied provenance references;
    validator checks their presence and deterministic digest, NOT authenticity.
    """
    protocol_digest: str
    source_version: str
    horizon_name: str
    ordered: tuple[TemporalOpportunity, ...]
    horizon_seconds: int = 3600

    def __post_init__(self) -> None:
        if not self.protocol_digest or not self.source_version or not self.horizon_name:
            raise ValueError("Frozen protocol, source version and horizon required")
        if not isinstance(self.ordered, (list, tuple)) or not all(
            isinstance(item, TemporalOpportunity) for item in self.ordered
        ):
            raise ValueError("Frozen temporal universe must contain TemporalOpportunity objects")
        object.__setattr__(self, "ordered", tuple(self.ordered))
        if not self.ordered:
            raise ValueError("Empty opportunity universe")
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ValueError("Frozen horizon duration must be positive integer seconds")
        ids = set()
        previous = None
        for event in self.ordered:
            if event.opportunity_id in ids:
                raise ValueError("Duplicate opportunity identity")
            ids.add(event.opportunity_id)
            t = _utc(event.decision_at)
            if int((_utc(event.baseline_horizon_end_at) - t).total_seconds()) != self.horizon_seconds or (_utc(event.baseline_horizon_end_at) - t).total_seconds() != self.horizon_seconds:
                raise ValueError("Opportunity horizon differs from frozen study horizon")
            if previous is not None and t <= previous:
                raise ValueError("Decision times must be strictly increasing in manifest order")
            previous = t

    @property
    def digest(self) -> str:
        def stamp(dt: datetime) -> str:
            return _utc(dt).isoformat()
        payload = {
            "protocol_digest": self.protocol_digest,
            "source_version": self.source_version,
            "horizon_name": self.horizon_name,
            "horizon_seconds": self.horizon_seconds,
            "ordered": [
                {
                    "opportunity_id": o.opportunity_id,
                    "group": o.opportunity_group_id,
                    "decision_at": stamp(o.decision_at),
                    "baseline_feature_available_at": stamp(o.baseline_feature_available_at),
                    "candidate_feature_available_at": stamp(o.candidate_feature_available_at),
                    "baseline_horizon_end_at": stamp(o.baseline_horizon_end_at),
                    "candidate_horizon_end_at": stamp(o.candidate_horizon_end_at),
                    "baseline_label_available_at": stamp(o.baseline_label_available_at),
                    "candidate_label_available_at": stamp(o.candidate_label_available_at),
                }
                for o in self.ordered
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def validate_temporal_pairs(
    pairs: Sequence[OpportunityPair],
    manifest: FrozenTemporalManifest,
) -> str:
    """Reject unknown/extra/reordered opportunities and group identity drift.

    Dataset version and provenance cannot be independently established from
    caller-supplied data. Exact ordered coverage is intentional: no silent
    dropped no-fills, unselected entries, or missing opportunities.
    """
    if len(pairs) != len(manifest.ordered):
        raise ValueError("Pair denominator differs from frozen opportunity universe")
    for row, frozen in zip(pairs, manifest.ordered):
        if row.baseline.opportunity_id != frozen.opportunity_id:
            raise ValueError("Opportunity order/identity differs from frozen manifest")
        if row.baseline.group_id != frozen.opportunity_group_id:
            raise ValueError("Market group differs from frozen manifest")
    return manifest.digest
