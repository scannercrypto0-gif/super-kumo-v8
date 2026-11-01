"""W1 Factory read-only research projection; never constructs fills or positions.

Market outcomes are retrospective excursions, not executable orders or PnL.
This module deliberately does not import the paper/position ledger.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json

from research_wp_r0.aql_w1_opportunity_outcomes import (
    EvidenceError, HORIZONS, RetrospectiveSnapshot, canonical,
)

STATES = frozenset(("NO_SIGNAL", "WATCH", "ARMED", "EXPIRED", "UNKNOWN", "BLOCKED"))
ELIGIBILITY = frozenset(("YES", "NO", "NOT_ESTABLISHED"))


def _hash(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchSelectionV1:
    opportunity_identity: str
    snapshot_id: str
    source_signal_state: str
    source_reason_code: str | None
    entry_eligibility: str
    eligibility_evidence: str | None
    cohort: str
    evidence_class: str = "RETROSPECTIVE_NON_PIT"

    @classmethod
    def from_snapshot(cls, snapshot: RetrospectiveSnapshot):
        if snapshot.signal_state not in STATES:
            raise EvidenceError("unknown original signal state")
        if snapshot.eligibility not in ELIGIBILITY:
            raise EvidenceError("unknown eligibility")
        if snapshot.evidence_class != "RETROSPECTIVE_NON_PIT":
            raise EvidenceError("PIT and retrospective evidence cannot be mixed")
        if snapshot.eligibility == "YES" and not snapshot.eligibility_evidence:
            raise EvidenceError("eligible without predecision evidence")
        # F1 predecision cohorts; F3 dispositions must never be inferred here.
        if snapshot.eligibility != "YES":
            cohort = "NOT_ESTABLISHED_OR_INELIGIBLE"
        elif snapshot.signal_state == "ARMED":
            cohort = "F1_ARMED_PREDECISION_ONLY"
        else:
            cohort = "F1_NON_ARMED_DENOMINATOR_ONLY"
        return cls(snapshot.opportunity_identity, snapshot.snapshot_id,
                   snapshot.signal_state, snapshot.reason_code,
                   snapshot.eligibility, snapshot.eligibility_evidence, cohort)


def project(snapshots, outcomes, *, expected_total=None, f3_effects=None):
    """Validate exact snapshot identity and horizon generations; no missing rows silently dropped.

    The latest correction generation is NOT guessed. A caller must explicitly
    select one immutable outcome version per snapshot/horizon.
    """
    snapshots = tuple(snapshots)
    if expected_total is not None and len(snapshots) != expected_total:
        raise EvidenceError("scheduled denominator mismatch")
    selections = {}
    for s in snapshots:
        selection = ResearchSelectionV1.from_snapshot(s)
        if selection.opportunity_identity in selections:
            raise EvidenceError("duplicate opportunity identity")
        selections[selection.opportunity_identity] = selection
    selected = {}
    for o in outcomes:
        key = (o["opportunity_identity"], o["horizon_ms"])
        selection = selections.get(o["opportunity_identity"])
        if selection is None:
            raise EvidenceError("orphan market outcome")
        if o["snapshot_id"] != selection.snapshot_id:
            raise EvidenceError("outcome snapshot mismatch")
        if o["horizon_ms"] not in HORIZONS:
            raise EvidenceError("invalid outcome horizon")
        if o.get("reference_kind") != "OPEN_AT_CUTOFF_NON_EXECUTABLE":
            raise EvidenceError("executable reference forbidden")
        if o.get("execution_status") != "NOT_OBSERVED":
            raise EvidenceError("paper execution mixed into research")
        if o.get("evaluation_version_id") != o.get("outcome_id"):
            raise EvidenceError("outcome generation mismatch")
        identity = {k: o[k] for k in (
            "opportunity_identity", "snapshot_id", "horizon_ms",
            "source_version", "policy_version", "correction_generation")}
        if _hash(identity) != o["outcome_id"]:
            raise EvidenceError("outcome identity tampered")
        if key in selected:
            raise EvidenceError("multiple generations: explicit version selection required")
        if o["status"] == "EVALUATED":
            if o.get("window_quality") != "COMPLETE_FINALIZED":
                raise EvidenceError("incomplete evaluated market window")
            if o.get("excursion_metrics_status") != "EVALUATED":
                raise EvidenceError("missing evaluated excursion status")
            if not all(isinstance(o.get(k), (int, float)) and
                       0 <= o[k] < float("inf") for k in ("mfe", "mae")):
                raise EvidenceError("invalid MFE/MAE")
        selected[key] = dict(o)
    # Optional typed F3 effects are a separate final-disposition stream.
    by_effect = Counter()
    if f3_effects is not None:
        from research_wp_r0.aql_w1_typed_contract import F3EffectV1
        expected_keys = {(s.trial_id, s.opportunity_id, s.producer_event_id,
                          s.envelope_sha256) for s in snapshots}
        seen_effects = set()
        for effect in f3_effects:
            if not isinstance(effect, F3EffectV1):
                raise EvidenceError("untyped F3 effect")
            key = (effect.trial_id, effect.opportunity_id, effect.producer_event_id,
                   effect.envelope_sha256)
            if key not in expected_keys or key in seen_effects:
                raise EvidenceError("orphan or duplicate F3 effect")
            seen_effects.add(key)
            by_effect[effect.effect_disposition] += 1
        if seen_effects != expected_keys:
            raise EvidenceError("F3 denominator mismatch")
    by_state = Counter(s.source_signal_state for s in selections.values())
    by_cohort = Counter(s.cohort for s in selections.values())
    by_status = Counter(o["status"] for o in selected.values())
    report = {
        "schema": "AQL-W1-FACTORY-RESEARCH-REPORT-v1",
        "evidence_class": "RETROSPECTIVE_NON_PIT",
        "scheduled_total": len(selections),
        "source_states": dict(sorted(by_state.items())),
        "f3_final_effects": dict(sorted(by_effect.items())) if f3_effects is not None else None,
        "eligible_rejected_cohort": "NOT_ESTABLISHED",
        "cohorts": dict(sorted(by_cohort.items())),
        "outcomes_by_status": dict(sorted(by_status.items())),
        "outcome_count": len(selected),
        "primary_checkpoint_ms": 86_400_000,
        "primary_metric": "MFE_WITH_MAE_COUNTERMETRIC_DESCRIPTIVE_ONLY",
        "research_only": True,
        "no_fill_or_pnl_inference": True,
    }
    report["report_sha256"] = _hash(report)
    return report
