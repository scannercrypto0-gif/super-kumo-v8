"""WP-R3: opportunity-level accounting and cluster sensitivity (stdlib only).

This is a frozen-policy, synthetic-only evaluation aid, NOT execution logic.
A confirmed NO_FILL can have zero *realized exposure return* only under the
explicit frozen zero-exposure/no-order-cost convention. Its missed opportunity
is not zero, nor is its hypothetical execution return known. Missing and
ambiguous outcomes cannot be silently converted to zero.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Sequence

from research_wp_r0.evaluation import OpportunityPair, Resolution


@dataclass(frozen=True)
class FrozenAccountingPolicy:
    policy_id: str
    confirmed_no_fill_zero_exposure: bool
    no_fill_has_no_fees: bool
    minimum_clusters: int = 5

    def __post_init__(self) -> None:
        if not self.policy_id or self.minimum_clusters < 2:
            raise ValueError("A versioned policy and minimum >=2 clusters are required")


@dataclass(frozen=True)
class ClusteredPair:
    pair: OpportunityPair
    market_shock_id: str
    sector_id: str

    def __post_init__(self) -> None:
        if not self.market_shock_id or not self.sector_id:
            raise ValueError("Known market-shock and sector identifiers required")
        if self.pair.baseline.group_id != self.market_shock_id:
            raise ValueError("Market-shock cluster must match immutable paired group")


@dataclass(frozen=True)
class ClusterInterval:
    axis: str
    estimate: float
    lower: float
    upper: float
    independent_groups: int
    observations: int
    resamples: int


@dataclass(frozen=True)
class OpportunityAssessment:
    denominator: int
    complete_pairs: int
    unknown_pairs: int
    ambiguous_pairs: int
    baseline_no_fills: int
    candidate_no_fills: int
    baseline_executed: int
    candidate_executed: int
    realized_policy_net_lift: float | None
    market_interval: ClusterInterval | None
    sector_interval: ClusterInterval | None
    sensitivity_lower: float | None
    sensitivity_upper: float | None
    status: str
    screening_positive: bool
    warnings: tuple[str, ...]


def _accounted_value(outcome, policy: FrozenAccountingPolicy) -> float | None:
    if outcome.resolution == Resolution.KNOWN:
        return outcome.known_net
    if (outcome.resolution == Resolution.NO_FILL
            and policy.confirmed_no_fill_zero_exposure
            and policy.no_fill_has_no_fees):
        return 0.0
    return None


def _cluster_resample(
    effects: Sequence[float],
    keys: Sequence[str],
    *,
    axis: str,
    replicates: int,
    seed: int,
    confidence: float,
) -> ClusterInterval:
    """Resample whole clusters; opportunity-weighted ratio of sum to count.

    Clusters may have unequal sizes. Uses percentile CI as a sensitivity
    diagnostic; does not ensure nominal coverage with few clusters or
    overlapping/cross-classified dependence.
    """
    groups: dict[str, list[float]] = {}
    for value, key in zip(effects, keys):
        groups.setdefault(key, []).append(value)
    labels = sorted(groups)
    if len(labels) < 2:
        raise ValueError("At least two independently labeled clusters required")
    rng = random.Random(seed)
    means = []
    for _ in range(replicates):
        sampled = [labels[rng.randrange(len(labels))] for _ in labels]
        total = math.fsum(math.fsum(groups[label]) for label in sampled)
        count = sum(len(groups[label]) for label in sampled)
        means.append(total / count)
    means.sort()

    def quantile(q: float) -> float:
        pos = (len(means) - 1) * q
        floor = int(pos)
        ceil = min(floor + 1, len(means) - 1)
        return means[floor] + (pos - floor) * (means[ceil] - means[floor])

    tail = (1 - confidence) / 2
    return ClusterInterval(
        axis, math.fsum(effects) / len(effects),
        quantile(tail), quantile(1 - tail), len(labels), len(effects), replicates
    )


def evaluate_opportunity_clusters(
    rows: Sequence[ClusteredPair],
    *,
    policy: FrozenAccountingPolicy,
    replicates: int,
    seed: int,
    confidence: float = 0.95,
    minimum_effect: float = 0.0,
) -> OpportunityAssessment:
    """Provide only a conservative *research screening*, never a promotion.

    Runs two separate whole-cluster resamples: by market shock/time window and
    by sector. The envelope is a *sensitivity range*, NOT a formal simultaneous
    or two-way clustered confidence interval. Sector correlations across shocks,
    opportunity selection and model-search selection require further validation.
    """
    if not rows or not isinstance(replicates, int) or replicates < 100:
        raise ValueError("Need rows and >=100 fixed bootstrap replicates")
    if not 0 < confidence < 1 or not math.isfinite(minimum_effect):
        raise ValueError("Invalid confidence/economic effect")
    if len({row.pair.baseline.opportunity_id for row in rows}) != len(rows):
        raise ValueError("Duplicate opportunity would inflate denominator")

    baseline_nofill = candidate_nofill = base_exec = cand_exec = 0
    unknown = ambiguous = 0
    effects: list[float] = []
    markets: list[str] = []
    sectors: list[str] = []
    for row in rows:
        b, c = row.pair.baseline, row.pair.candidate
        baseline_nofill += int(b.resolution == Resolution.NO_FILL)
        candidate_nofill += int(c.resolution == Resolution.NO_FILL)
        base_exec += int(b.resolution == Resolution.KNOWN)
        cand_exec += int(c.resolution == Resolution.KNOWN)
        if b.resolution == Resolution.MISSING or c.resolution == Resolution.MISSING:
            unknown += 1
        elif b.resolution == Resolution.AMBIGUOUS or c.resolution == Resolution.AMBIGUOUS:
            ambiguous += 1
        b_net = _accounted_value(b, policy)
        c_net = _accounted_value(c, policy)
        if b_net is not None and c_net is not None:
            effects.append(c_net - b_net)
            markets.append(row.market_shock_id)
            sectors.append(row.sector_id)

    warnings = (
        "No-fill zero represents confirmed zero *realized exposure* under the frozen policy; missed upside and execution propensity remain unestimated.",
        "Intervals are axis-wise cluster sensitivity, not formal simultaneous/multiway coverage.",
        "Cluster identifiers require point-in-time provenance; small/uneven clusters and outcome selection may bias inference.",
        "Screening never authorizes strategy promotion or operational trader changes.",
    )
    if not effects:
        return OpportunityAssessment(
            len(rows), 0, unknown, ambiguous, baseline_nofill, candidate_nofill,
            base_exec, cand_exec, None, None, None, None, None,
            "INSUFFICIENT_EVIDENCE", False, warnings,
        )

    estimate = math.fsum(effects) / len(effects)
    market_groups, sector_groups = len(set(markets)), len(set(sectors))
    incomplete = len(effects) != len(rows)
    insufficient = (market_groups < policy.minimum_clusters
                    or sector_groups < policy.minimum_clusters)
    # No misleading narrow CI from one or too few group samples.
    if insufficient:
        return OpportunityAssessment(
            len(rows), len(effects), unknown, ambiguous, baseline_nofill,
            candidate_nofill, base_exec, cand_exec, estimate, None, None,
            None, None, "INSUFFICIENT_CLUSTER_DIVERSITY", False, warnings,
        )
    market_ci = _cluster_resample(
        effects, markets, axis="MARKET_SHOCK",
        replicates=replicates, seed=seed, confidence=confidence
    )
    sector_ci = _cluster_resample(
        effects, sectors, axis="SECTOR",
        replicates=replicates, seed=seed + 1, confidence=confidence
    )
    lower = min(market_ci.lower, sector_ci.lower)
    upper = max(market_ci.upper, sector_ci.upper)
    # This is a screening threshold, not a significance or causal proof.
    screening = (not incomplete and lower > minimum_effect
                 and policy.confirmed_no_fill_zero_exposure
                 and policy.no_fill_has_no_fees)
    return OpportunityAssessment(
        len(rows), len(effects), unknown, ambiguous, baseline_nofill,
        candidate_nofill, base_exec, cand_exec, estimate,
        market_ci, sector_ci, lower, upper,
        "INCOMPLETE_COVERAGE" if incomplete else "EXPLORATORY_CLUSTER_SCREEN",
        screening, warnings,
    )
