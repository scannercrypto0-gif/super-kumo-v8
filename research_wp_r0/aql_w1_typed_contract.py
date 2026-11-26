"""Typed contracts for W1 Factory research streams.

F3EffectV1: immutable typed record for a single F3 final-disposition effect.
Used by aql_w1_factory_research_consumer.project() to validate that F3 effects
are a separate stream from F1 and are properly identity-bound to snapshots.

RESEARCH ONLY — evidence_class = "RETROSPECTIVE_NON_PIT".
No executable fills, no PIT timestamps, no real custody.
"""
from __future__ import annotations

from dataclasses import dataclass


# Valid final dispositions for an F3 effect (maps to signal_state).
# Matches describe_original_p0_f3_effects validation.
_VALID_DISPOSITIONS = frozenset({"NO_SIGNAL", "REJECTED", "TRIGGERED"})

# Valid execution class labels for research context.
_VALID_EXECUTION_CLASSES = frozenset({
    "MODELED_NON_EXECUTABLE",
    "NOT_APPLICABLE",
})


@dataclass(frozen=True)
class F3EffectV1:
    """Single F3 final-disposition record — typed, immutable, identity-bound.

    Fields
    ------
    trial_id          : str   — binds to RetrospectiveSnapshot.trial_id
    opportunity_id    : str   — binds to RetrospectiveSnapshot.opportunity_id
    producer_event_id : str   — binds to RetrospectiveSnapshot.producer_event_id
    envelope_sha256   : str   — binds to RetrospectiveSnapshot.envelope_sha256
    effect_disposition: str   — final F3 state: NO_SIGNAL | REJECTED | TRIGGERED
    reason_code       : str | None — why the disposition occurred
    direction         : str | None — LONG / SHORT / None (not inferred from price)
    receipt_id        : str   — identity of the durable F3 receipt
    archive_version   : str   — archive provenance label
    execution_class   : str   — must be MODELED_NON_EXECUTABLE or NOT_APPLICABLE
    """

    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str
    effect_disposition: str
    reason_code: str | None
    direction: str | None
    receipt_id: str
    archive_version: str
    execution_class: str

    def __post_init__(self) -> None:
        if not isinstance(self.trial_id, str) or not self.trial_id:
            raise ValueError("F3EffectV1: trial_id must be a non-empty str")
        if not isinstance(self.opportunity_id, str) or not self.opportunity_id:
            raise ValueError("F3EffectV1: opportunity_id must be a non-empty str")
        if not isinstance(self.producer_event_id, str) or not self.producer_event_id:
            raise ValueError("F3EffectV1: producer_event_id must be a non-empty str")
        if not isinstance(self.envelope_sha256, str) or not self.envelope_sha256:
            raise ValueError("F3EffectV1: envelope_sha256 must be a non-empty str")
        if self.effect_disposition not in _VALID_DISPOSITIONS:
            raise ValueError(
                f"F3EffectV1: effect_disposition must be one of {sorted(_VALID_DISPOSITIONS)}, "
                f"got {self.effect_disposition!r}"
            )
        if self.direction is not None and self.direction not in ("LONG", "SHORT"):
            raise ValueError(
                f"F3EffectV1: direction must be LONG, SHORT or None, got {self.direction!r}"
            )
        if self.execution_class not in _VALID_EXECUTION_CLASSES:
            raise ValueError(
                f"F3EffectV1: execution_class must be one of {sorted(_VALID_EXECUTION_CLASSES)}, "
                f"got {self.execution_class!r}"
            )
