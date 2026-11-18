"""WP-R1: honest, synthetic-first, standard-library quantitative test helpers.

Do not infer trading alpha from the statistical interfaces alone. All research
protocols must freeze family scope, selection history and primary metric.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from statistics import mean
from typing import Sequence


def _probability(p: float) -> float:
    p = float(p)
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("Expected finite p-value in [0, 1]")
    return p


def bonferroni(p_values: Sequence[float]) -> tuple[float, ...]:
    """Family-wise adjustment: all attempted hypotheses belong in input."""
    p = tuple(_probability(x) for x in p_values)
    if not p:
        raise ValueError("A predeclared trial family cannot be empty")
    return tuple(min(1., x * len(p)) for x in p)


def holm(p_values: Sequence[float]) -> tuple[float, ...]:
    """Holm step-down FWER correction; valid under arbitrary dependence
    for individually valid marginal p-values.
    """
    p = tuple(_probability(x) for x in p_values)
    n = len(p)
    if n == 0:
        raise ValueError("A predeclared trial family cannot be empty")
    ranks = sorted(range(n), key=lambda i: (p[i], i))
    adjusted = [0.] * n
    current = 0.
    for rank, original_index in enumerate(ranks):
        current = max(current, min(1., (n - rank) * p[original_index]))
        adjusted[original_index] = current
    return tuple(adjusted)


def _finite_vector(values: Sequence[float], *, minimum: int = 1) -> tuple[float, ...]:
    out = tuple(float(v) for v in values)
    if len(out) < minimum or any(not math.isfinite(v) for v in out):
        raise ValueError("Expected sufficient finite observations")
    return out


@dataclass(frozen=True)
class BootstrapInterval:
    effect: float
    lower: float
    upper: float
    replicates: int
    block_length: int
    observations: int


def paired_moving_block_interval(
    baseline_net: Sequence[float],
    candidate_net: Sequence[float],
    *,
    block_length: int,
    replicates: int,
    seed: int,
    confidence: float = 0.95,
) -> BootstrapInterval:
    """Paired circular moving-block percentile bootstrap on ordered outcomes.

    The two sequences MUST be aligned by ex-ante eligible opportunity.
    Blocks approximate temporal dependence, not cross-asset market-factor
    clustering. No causal or confirmatory guarantee from this function.
    """
    left = _finite_vector(baseline_net, minimum=2)
    right = _finite_vector(candidate_net, minimum=2)
    n = len(left)
    if len(right) != n:
        raise ValueError("Paired samples require identical denominators")
    if not isinstance(block_length, int) or not 1 <= block_length < n:
        raise ValueError("Block length must be smaller than sample size; a full circular block produces a degenerate interval")
    # Conservative safety floor, not a guarantee of valid bootstrap coverage.
    if n < 3 * block_length:
        raise ValueError("At least three nominal block lengths required; interval would be poorly supported")
    if not isinstance(replicates, int) or replicates < 100:
        raise ValueError("At least 100 bootstrap replicates required")
    if not 0 < confidence < 1:
        raise ValueError("Invalid confidence level")
    diff = tuple(b - a for a, b in zip(left, right))
    rng = random.Random(seed)
    draws = []
    for _ in range(replicates):
        resample = []
        while len(resample) < n:
            start = rng.randrange(n)
            resample.extend(diff[(start + offset) % n] for offset in range(block_length))
        draws.append(math.fsum(resample[:n]) / n)
    draws.sort()

    def quantile(q: float) -> float:
        position = (len(draws) - 1) * q
        lo = int(position)
        hi = min(lo + 1, len(draws) - 1)
        return draws[lo] + (position - lo) * (draws[hi] - draws[lo])

    tail = (1 - confidence) / 2
    return BootstrapInterval(
        effect=math.fsum(diff) / n,
        lower=quantile(tail),
        upper=quantile(1 - tail),
        replicates=replicates,
        block_length=block_length,
        observations=n,
    )


@dataclass(frozen=True)
class LabelWindow:
    """Time-ordered point-in-time observation and its forward-label maturity."""
    observation_at: datetime
    label_end_at: datetime

    def __post_init__(self) -> None:
        for time in (self.observation_at, self.label_end_at):
            if time.tzinfo is None or time.utcoffset() is None:
                raise ValueError("Time-zone-aware observations required")
        if self.label_end_at < self.observation_at:
            raise ValueError("Forward label cannot mature before observation")


@dataclass(frozen=True)
class WalkForwardFold:
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]


def purged_forward_folds(
    windows: Sequence[LabelWindow], *,
    minimum_training: int,
    test_size: int,
    embargo: timedelta = timedelta(0),
) -> tuple[WalkForwardFold, ...]:
    """Forward-only blocked test windows; training labels must mature <=
    first test decision minus embargo. Excludes later training observations.
    """
    if minimum_training < 1 or test_size < 1 or embargo < timedelta(0):
        raise ValueError("Invalid fold settings")
    if not windows:
        raise ValueError("No label windows")
    times = [w.observation_at.astimezone(timezone.utc) for w in windows]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("Observations must be strictly chronological")
    folds = []
    for start in range(minimum_training, len(windows), test_size):
        test = tuple(range(start, min(len(windows), start + test_size)))
        cutoff = times[start] - embargo
        train = tuple(
            i for i in range(start)
            if windows[i].label_end_at.astimezone(timezone.utc) <= cutoff
        )
        if len(train) < minimum_training:
            continue
        folds.append(WalkForwardFold(train, test))
    return tuple(folds)


@dataclass(frozen=True)
class NullAudit:
    """Idealized correlated-Gaussian toy model; NOT valid calibrated p-values."""
    replicates: int
    candidates: int
    factor_loading: float
    selected_family_rate: float
    monte_carlo_standard_error: float


def synthetic_correlated_null_audit(
    *,
    seed: int,
    replicates: int,
    candidates: int,
    factor_loading: float,
    family_alpha: float = 0.05,
) -> NullAudit:
    """Explore effect of correlated candidate *valid* null p-values.

    One-factor normals -> two-sided normal-tail p-values. Intended for
    testing family-level correction code under candidate dependence, not
    simulating serially dependent market returns or financial strategy alpha.
    """
    if not (isinstance(replicates, int) and replicates >= 100):
        raise ValueError("At least 100 null replicates required")
    if not (isinstance(candidates, int) and candidates >= 1):
        raise ValueError("Need at least one candidate")
    if not math.isfinite(factor_loading) or not 0 <= factor_loading <= 1:
        raise ValueError("Factor loading must be between 0 and 1")
    if not 0 < family_alpha < 1:
        raise ValueError("Invalid family alpha")
    rng = random.Random(seed)
    false_families = 0
    residual = math.sqrt(1 - factor_loading ** 2)
    for _ in range(replicates):
        common = rng.gauss(0., 1.)
        p_values = []
        for _ in range(candidates):
            z = factor_loading * common + residual * rng.gauss(0., 1.)
            # erfc(|z| / sqrt(2)) = valid two-sided Gaussian null p-value
            p_values.append(math.erfc(abs(z) / math.sqrt(2)))
        false_families += min(holm(p_values)) <= family_alpha
    rate = false_families / replicates
    return NullAudit(replicates, candidates, factor_loading, rate,
                     math.sqrt(rate * (1 - rate) / replicates))
