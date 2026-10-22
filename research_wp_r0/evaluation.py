"""WP-R2: synthetic, opportunity-level paired research evaluation.

Scope is strictly offline research; never writes trader state or simulates missing
fills. An observation's frozen event identity, horizon and comparability are
prerequisites for pairing. This is not an execution engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

from research_wp_r0.statistics import BootstrapInterval, paired_moving_block_interval


class Resolution(str, Enum):
    KNOWN = "KNOWN"
    NO_FILL = "NO_FILL"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"


@dataclass(frozen=True)
class OpportunityOutcome:
    opportunity_id: str
    group_id: str
    """Group may identify a common market shock; used for disclosure only."""
    resolution: Resolution
    gross_return: float | None = None
    execution_cost: float | None = None
    bound_low: float | None = None
    bound_high: float | None = None

    def __post_init__(self) -> None:
        if not self.opportunity_id or not self.group_id:
            raise ValueError("Opportunity and group identities are required")
        numeric = (self.gross_return, self.execution_cost, self.bound_low, self.bound_high)
        if any(x is not None and not math.isfinite(x) for x in numeric):
            raise ValueError("Values must be finite")
        if self.resolution == Resolution.KNOWN:
            if self.gross_return is None or self.execution_cost is None:
                raise ValueError("Known fills require gross return and costs")
            if self.execution_cost < 0 or self.bound_low is not None or self.bound_high is not None:
                raise ValueError("Invalid known fill")
        elif self.resolution == Resolution.NO_FILL:
            if any(x is not None for x in numeric):
                raise ValueError("No-fill has no modeled executed PnL")
        elif self.resolution == Resolution.AMBIGUOUS:
            if self.bound_low is None or self.bound_high is None or self.bound_low > self.bound_high:
                raise ValueError("Ambiguous outcome needs ordered net-return bounds")
            if self.gross_return is not None or self.execution_cost is not None:
                raise ValueError("Do not assert known fill alongside ambiguous bounds")
        else:
            if any(x is not None for x in numeric):
                raise ValueError("Missing evidence cannot assert return/bounds")

    @property
    def known_net(self) -> float | None:
        if self.resolution == Resolution.KNOWN:
            return self.gross_return - self.execution_cost
        return None


@dataclass(frozen=True)
class OpportunityPair:
    baseline: OpportunityOutcome
    candidate: OpportunityOutcome

    def __post_init__(self) -> None:
        if self.baseline.opportunity_id != self.candidate.opportunity_id:
            raise ValueError("A pair must represent the same opportunity")
        if self.baseline.group_id != self.candidate.group_id:
            raise ValueError("Paired evidence must preserve correlated-event group identity")


@dataclass(frozen=True)
class EvaluationReport:
    opportunities: int
    baseline_known: int
    candidate_known: int
    baseline_no_fill: int
    candidate_no_fill: int
    ambiguous_pairs: int
    missing_pairs: int
    fully_known_pairs: int
    observed_group_count: int
    paired_net_lift: float | None
    lift_interval: BootstrapInterval | None
    evidence_status: str
    decision: str
    notes: tuple[str, ...]


def evaluate_paired(
    pairs: Sequence[OpportunityPair],
    *,
    block_length: int,
    replicates: int,
    seed: int,
    minimum_paired: int,
    minimum_effect: float = 0.0,
) -> EvaluationReport:
    """Assess research improvement only on fully resolved executed PnL pairs.

    The complete opportunity denominator is retained. No-fill, missing and
    ambiguous outcomes cannot be coded as zero or best/worst realized profit.
    This does *not* estimate intent-to-trade opportunity-level return when
    no-fill exists; it explicitly reports conditional-on-both-known lift only.
    """
    if not pairs or minimum_paired < 2 or not math.isfinite(minimum_effect):
        raise ValueError("Invalid evaluation design")
    ids = [p.baseline.opportunity_id for p in pairs]
    if len(ids) != len(set(ids)):
        raise ValueError("Repeated opportunities could inflate evidence")
    baseline = []
    candidate = []
    baseline_known = candidate_known = 0
    baseline_no_fill = candidate_no_fill = 0
    ambiguous = missing = 0
    groups = set()
    for pair in pairs:
        b, c = pair.baseline, pair.candidate
        groups.add(b.group_id)
        baseline_known += b.resolution == Resolution.KNOWN
        candidate_known += c.resolution == Resolution.KNOWN
        baseline_no_fill += b.resolution == Resolution.NO_FILL
        candidate_no_fill += c.resolution == Resolution.NO_FILL
        ambiguous += (b.resolution == Resolution.AMBIGUOUS or
                      c.resolution == Resolution.AMBIGUOUS)
        missing += (b.resolution == Resolution.MISSING or
                    c.resolution == Resolution.MISSING)
        if b.known_net is not None and c.known_net is not None:
            baseline.append(b.known_net)
            candidate.append(c.known_net)
    n = len(baseline)
    notes = [
        "Paired effect conditional on both strategies having known executed outcomes.",
        "Shared market group correlations are disclosed, not modeled by circular time-block resampling.",
        "Costs and returns must be supplied on the same frozen notional/denominator.",
    ]
    if n < minimum_paired:
        return EvaluationReport(
            len(pairs), baseline_known, candidate_known, baseline_no_fill,
            candidate_no_fill, ambiguous, missing, n, len(groups),
            None, None, "INSUFFICIENT_EVIDENCE", "NO_PROMOTION",
            tuple(notes + ["Too few resolved paired opportunities."]),
        )
    interval = paired_moving_block_interval(
        baseline, candidate, block_length=block_length,
        replicates=replicates, seed=seed,
    )
    # A pointwise CI on selectively observed executions does not prove
    # whole-opportunity benefit, particularly when fills/unknowns differ.
    outstanding = n != len(pairs)
    evidence_status = "INCOMPLETE_COVERAGE" if outstanding else "EXPLORATORY"
    decision = "FURTHER_INDEPENDENT_VALIDATION"
    if interval.upper <= minimum_effect:
        decision = "DO_NOT_NOMINATE"
    elif interval.lower > minimum_effect and not outstanding:
        decision = "HISTORICAL_CANDIDATE_ONLY"
    if outstanding:
        notes.append("Unresolved/no-fill opportunities prevent unconditional improvement claims.")
    return EvaluationReport(
        len(pairs), baseline_known, candidate_known, baseline_no_fill,
        candidate_no_fill, ambiguous, missing, n, len(groups),
        interval.effect, interval, evidence_status, decision, tuple(notes),
    )
