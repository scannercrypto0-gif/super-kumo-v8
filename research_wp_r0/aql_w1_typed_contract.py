"""W1 typed F1 predecision / F3 effect boundary (research-only).

Original P0 lacks an immutable F1 predecision receipt. This module never
backfills it or upgrades reconstructed observations to PIT evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping
from .aql_w1_opportunity_outcomes import EvidenceError, RetrospectiveSnapshot, digest

F1_SCHEMA = "aql.w1.f1-predecision-selection.v1"
F3_SCHEMA = "aql.w1.f3-final-effect.v1"
F1_STATES = frozenset({"NO_SIGNAL", "WATCH", "ARMED", "EXPIRED", "UNKNOWN", "BLOCKED"})
F3_STATES = frozenset({"NO_SIGNAL", "REJECTED", "TRIGGERED", "NO_FILL", "EXPIRED", "UNKNOWN", "BLOCKED"})
EVIDENCE_CLASSES = frozenset({"RECORDED_F1_PREDECISION", "RECONSTRUCTED_RETROSPECTIVE_NON_PIT"})

def _required(value, field):
    if not isinstance(value, str) or not value:
        raise EvidenceError("missing " + field)

@dataclass(frozen=True)
class F1SelectionV1:
    """Immutable typed F1 input; requires a separately evidenced source receipt."""
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str
    run_manifest_sha256: str
    decision_cutoff_ms: int
    decision_ms: int
    prefix_start_ms: int
    prefix_end_exclusive_ms: int
    prefix_bar_checksums_sha256: str
    input_disposition: str
    strategy_id: str
    dataset_version: int
    feature_policy_version: str
    gap_inventory_sha256: str
    correction_lineage_sha256: str
    f1_signal_state: str
    f1_reason_code: str | None
    direction: str | None
    predecision_eligibility: str
    eligibility_evidence_ref: str | None
    source_version: str
    source_bytes_sha256: str
    selection_policy_version: str
    correction_generation: str
    evidence_class: str
    receipt_sha256: str | None
    schema: str = F1_SCHEMA

    def __post_init__(self):
        if self.schema != F1_SCHEMA or self.f1_signal_state not in F1_STATES:
            raise EvidenceError("invalid F1 schema/state")
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise EvidenceError("invalid F1 evidence class")
        if self.direction not in (None, "LONG", "SHORT"):
            raise EvidenceError("invalid F1 direction")
        if self.predecision_eligibility not in ("YES", "NO", "NOT_ESTABLISHED"):
            raise EvidenceError("invalid eligibility")
        if self.predecision_eligibility == "YES" and (
            not self.eligibility_evidence_ref or self.evidence_class != "RECORDED_F1_PREDECISION"
        ):
            raise EvidenceError("eligible without original predecision evidence")
        if self.evidence_class == "RECORDED_F1_PREDECISION" and not self.receipt_sha256:
            raise EvidenceError("recorded F1 requires durable receipt hash")
        if self.decision_ms < self.decision_cutoff_ms or self.prefix_end_exclusive_ms > self.decision_cutoff_ms:
            raise EvidenceError("invalid predecision timing")
        for field in ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256",
                      "run_manifest_sha256", "prefix_bar_checksums_sha256", "strategy_id",
                      "feature_policy_version", "gap_inventory_sha256", "correction_lineage_sha256",
                      "source_version", "source_bytes_sha256", "selection_policy_version",
                      "correction_generation"):
            _required(getattr(self, field), field)

    @property
    def selection_sha256(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class F3EffectV1:
    """Downstream final F3 disposition; never an F1 signal."""
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str
    effect_disposition: str
    f3_reason_code: str | None
    f1_selection_sha256: str | None
    consumer_receipt_sha256: str
    source_version: str
    execution_class: str
    schema: str = F3_SCHEMA

    def __post_init__(self):
        if self.schema != F3_SCHEMA or self.effect_disposition not in F3_STATES:
            raise EvidenceError("invalid F3 schema/disposition")
        if self.execution_class not in ("MODELED_NON_EXECUTABLE", "OBSERVED_EXECUTION"):
            raise EvidenceError("invalid execution class")
        for field in ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256",
                      "consumer_receipt_sha256", "source_version"):
            _required(getattr(self, field), field)


def reconcile_typed(envelopes: list[Mapping], selections: list[F1SelectionV1]) -> tuple[RetrospectiveSnapshot, ...]:
    """Strict C2→F1 join; original P0 descriptive F3 path stays separate."""
    if len(envelopes) != len(selections):
        raise EvidenceError("NOT_RECORDED_IN_P0: missing F1 selection source")
    keyed = {}
    for s in selections:
        if not isinstance(s, F1SelectionV1):
            raise EvidenceError("F3 effect or untyped selection cannot substitute F1")
        key = (s.trial_id, s.opportunity_id, s.producer_event_id)
        if key in keyed:
            raise EvidenceError("duplicate F1 selection")
        keyed[key] = s
    snapshots, seen = [], set()
    comparable = ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256",
                  "decision_cutoff_ms", "decision_ms", "prefix_start_ms", "prefix_end_exclusive_ms",
                  "prefix_bar_checksums_sha256", "input_disposition", "strategy_id", "dataset_version",
                  "feature_policy_version", "gap_inventory_sha256", "correction_lineage_sha256")
    for e in envelopes:
        key = (e["trial_id"], e["opportunity_id"], e["producer_event_id"])
        if key in seen or key not in keyed:
            raise EvidenceError("unmatched/duplicate C2 identity")
        seen.add(key)
        s = keyed[key]
        if any(e.get(field) != getattr(s, field) for field in comparable):
            raise EvidenceError("C2/F1 provenance mismatch")
        if e.get("run_manifest_sha256") != s.run_manifest_sha256:
            raise EvidenceError("manifest SHA mismatch")
        ctx = digest({"selection_sha256": s.selection_sha256,
                      "source_version": s.source_version,
                      "source_bytes_sha256": s.source_bytes_sha256,
                      "policy_version": s.selection_policy_version,
                      "correction_generation": s.correction_generation})
        snapshots.append(RetrospectiveSnapshot(
            trial_id=s.trial_id, manifest_sha256=s.run_manifest_sha256,
            opportunity_id=s.opportunity_id, producer_event_id=s.producer_event_id,
            envelope_sha256=s.envelope_sha256, decision_cutoff_ms=s.decision_cutoff_ms,
            decision_ms=s.decision_ms, signal_state=s.f1_signal_state,
            reason_code=s.f1_reason_code, direction=s.direction,
            eligibility=s.predecision_eligibility, eligibility_evidence=s.eligibility_evidence_ref,
            context_digest=ctx, evidence_class="RETROSPECTIVE_NON_PIT"))
    if len(seen) != len(keyed):
        raise EvidenceError("orphan F1 selection")
    return tuple(snapshots)
