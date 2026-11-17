"""G4 — Multi-profile screening pipeline.

Lifecycle: DISCOVERED → SCREENED → QUALIFIED → NOMINATED
Terminal:  REJECTED | EXPIRED | UNKNOWN

Two scoring profiles are supported:
  INTRADAY — weight groups: strong_close(20), internal_path(20),
             momentum_timing(20), volume(20), mtf_structure(15), liquidity(5)
  SWING    — weight groups: market_structure(35), strong_close(15),
             internal_path(15), higher_context(15), momentum_volume(15), liquidity(5)

Score computation:
  Each weight group has feature contributions mapped in PROFILE_WEIGHTS.
  group_score = sum of (feature_value * contribution_weight) for available features
               / sum of expected contribution_weights for that group
  profile_score = sum(group_score * group_weight) / 100
  Final score rounded to 0.01 via ROUND_HALF_EVEN (matches ZS reference contract).

If any HARD_REQUIRED feature is SCORE_UNAVAILABLE → stage stays SCREENED (not QUALIFIED).
If ≥ SOFT_COVERAGE_THRESHOLD features are OK → QUALIFIED, else SCREENED.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Sequence

from .contracts import (
    _utc, STAGE_DISCOVERED, STAGE_SCREENED, STAGE_QUALIFIED,
    STAGE_NOMINATED, STAGE_REJECTED, TERMINAL_STAGES,
)
from .features import MTFFeatureSnapshot, STATUS_OK

# ── Profile definitions ────────────────────────────────────────────────────────

PROFILE_INTRADAY = "INTRADAY"
PROFILE_SWING = "SWING"
SUPPORTED_PROFILES = frozenset({PROFILE_INTRADAY, PROFILE_SWING})

# Group weights (must sum to 100 per profile)
GROUP_WEIGHTS: dict[str, dict[str, int]] = {
    PROFILE_INTRADAY: {
        "strong_close":     20,
        "internal_path":    20,
        "momentum_timing":  20,
        "volume":           20,
        "mtf_structure":    15,
        "liquidity":         5,
    },
    PROFILE_SWING: {
        "market_structure": 35,
        "strong_close":     15,
        "internal_path":    15,
        "higher_context":   15,
        "momentum_volume":  15,
        "liquidity":         5,
    },
}

# Feature → (group, contribution_weight within group)
# contribution_weight is relative within the group; groups are normalised internally.
FEATURE_GROUP_MAP: dict[str, dict[str, tuple[str, int]]] = {
    PROFILE_INTRADAY: {
        # strong_close (20)
        "oc_5m":            ("strong_close",    60),
        "oc_30m":           ("strong_close",    40),
        # internal_path (20)
        "range_pos_5m":     ("internal_path",   50),
        "range_pos_30m":    ("internal_path",   50),  # may be absent
        # momentum_timing (20)
        "c2c_1bar_5m":      ("momentum_timing", 50),
        "c2c_1bar_30m":     ("momentum_timing", 50),
        # volume (20)
        "rvol_quote_5m":    ("volume",          60),
        "rvol_quote_30m":   ("volume",          40),
        # mtf_structure (15)
        "trend_slope_1h":   ("mtf_structure",   50),
        "trend_slope_4h":   ("mtf_structure",   50),
        # liquidity (5)
        "spread_bps":       ("liquidity",       100),
    },
    PROFILE_SWING: {
        # market_structure (35)
        "range_pos_1d":     ("market_structure", 50),
        "trend_slope_1d":   ("market_structure", 50),
        # strong_close (15)
        "oc_1h":            ("strong_close",     60),
        "oc_4h":            ("strong_close",     40),
        # internal_path (15)
        "range_pos_1h":     ("internal_path",    50),
        "range_pos_4h":     ("internal_path",    50),
        # higher_context (15)
        "trend_slope_4h":   ("higher_context",   60),
        "c2c_1bar_1d":      ("higher_context",   40),
        # momentum_volume (15)
        "rvol_quote_1h":    ("momentum_volume",  60),
        "c2c_1bar_4h":      ("momentum_volume",  40),
        # liquidity (5)
        "spread_bps":       ("liquidity",        100),
    },
}

# Features required for QUALIFIED (unavailability blocks advancement)
HARD_REQUIRED: dict[str, frozenset[str]] = {
    PROFILE_INTRADAY: frozenset({"oc_5m", "rvol_quote_5m", "c2c_1bar_5m"}),
    PROFILE_SWING:    frozenset({"oc_1h", "rvol_quote_1h", "range_pos_1d"}),
}

# Minimum fraction of all profile features that must be OK to advance to QUALIFIED
SOFT_COVERAGE_THRESHOLD = Decimal("0.50")

# Minimum score to advance to NOMINATED
NOMINATION_THRESHOLD: dict[str, Decimal] = {
    PROFILE_INTRADAY: Decimal("60.00"),
    PROFILE_SWING:    Decimal("55.00"),
}

_HUNDRED = Decimal("100")
_ZERO = Decimal("0")
_SCORE_PRECISION = Decimal("0.01")


# ── Scoring ────────────────────────────────────────────────────────────────────

def _normalise_feature(name: str, value: Decimal, profile: str) -> Decimal:
    """Normalise a feature value into [0, 100] range for group scoring.

    Normalisation rules (profile-specific):
      OC / C2C momentum  → clamp to [-5%, +5%] → scale to [0, 100]
      RVOL               → clamp to [0, 3] → scale to [0, 100]
      range_pos          → already [0, 100]
      trend_slope        → clamp to [-2%, +2%] → scale to [0, 100]
      spread_bps (inverted: lower is better) → clamp [0, 30] → 100*(30-v)/30
    """
    if "oc_" in name or "c2c_" in name:
        clipped = max(Decimal("-5"), min(Decimal("5"), value))
        return (clipped + 5) * 10  # [0, 100]
    if "rvol_" in name:
        clipped = max(_ZERO, min(Decimal("3"), value))
        return clipped / 3 * 100
    if "range_pos_" in name:
        return max(_ZERO, min(_HUNDRED, value))
    if "trend_slope_" in name:
        clipped = max(Decimal("-2"), min(Decimal("2"), value))
        return (clipped + 2) * 25  # [0, 100]
    if "spread_bps" in name:
        clipped = max(_ZERO, min(Decimal("30"), value))
        return (_HUNDRED - clipped / 30 * 100)
    # fallback: clamp to [0, 100]
    return max(_ZERO, min(_HUNDRED, value))


def compute_score(
    snapshot: MTFFeatureSnapshot,
    profile: str,
) -> tuple[Decimal | None, str, list[str]]:
    """Compute a profile score from the MTF feature snapshot.

    Returns (score_decimal, score_status, reason_codes)
    score_status: "SCORED" | "SCORE_UNAVAILABLE"
    """
    if profile not in SUPPORTED_PROFILES:
        return None, "SCORE_UNAVAILABLE", [f"UNKNOWN_PROFILE:{profile}"]

    feature_map: dict[str, Decimal] = {}
    for cell in snapshot.features:
        if cell.is_ok and cell.value is not None:
            feature_map[cell.name] = Decimal(cell.value)

    feature_group_map = FEATURE_GROUP_MAP[profile]
    group_weights = GROUP_WEIGHTS[profile]
    hard_required = HARD_REQUIRED[profile]
    reasons: list[str] = []

    # Check hard required features
    for feat in hard_required:
        if feat not in feature_map:
            reasons.append(f"HARD_REQUIRED_MISSING:{feat}")

    if reasons:
        return None, "SCORE_UNAVAILABLE", reasons

    # Build group scores
    group_accum: dict[str, tuple[Decimal, Decimal]] = {}  # group → (weighted_sum, weight_sum)
    for feat_name, (group, contrib) in feature_group_map.items():
        if feat_name in feature_map:
            norm = _normalise_feature(feat_name, feature_map[feat_name], profile)
            if group not in group_accum:
                group_accum[group] = (_ZERO, _ZERO)
            ws, wt = group_accum[group]
            group_accum[group] = (ws + norm * contrib, wt + contrib)

    # Compute profile score
    total_score = _ZERO
    for group_name, group_weight in group_weights.items():
        if group_name in group_accum:
            ws, wt = group_accum[group_name]
            if wt > 0:
                g_score = ws / wt  # [0, 100]
            else:
                g_score = _ZERO
        else:
            g_score = _ZERO  # all features unavailable for this group
        total_score += g_score * group_weight / 100

    score = total_score.quantize(_SCORE_PRECISION, rounding=ROUND_HALF_EVEN)
    return score, "SCORED", reasons


# ── Candidate model ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScanCandidate:
    symbol: str
    profile: str
    stage: str
    score: Decimal | None
    score_status: str
    reasons: tuple[str, ...]
    coverage_ratio: Decimal
    cutoff_at: datetime

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "profile": self.profile,
            "stage": self.stage,
            "score": str(self.score) if self.score is not None else None,
            "score_status": self.score_status,
            "reasons": list(self.reasons),
            "coverage_ratio": str(self.coverage_ratio),
            "cutoff_at": self.cutoff_at.isoformat(),
        }


# ── Pipeline ───────────────────────────────────────────────────────────────────

def screen_candidate(
    snapshot: MTFFeatureSnapshot,
    profile: str,
) -> ScanCandidate:
    """Run the full screening → qualification → nomination pipeline for one candidate.

    Returns a ScanCandidate at the highest stage it qualifies for.
    """
    cutoff_at = snapshot.cutoff_at
    reasons: list[str] = []

    if profile not in SUPPORTED_PROFILES:
        return ScanCandidate(
            symbol=snapshot.symbol,
            profile=profile,
            stage=STAGE_REJECTED,
            score=None,
            score_status="SCORE_UNAVAILABLE",
            reasons=("UNKNOWN_PROFILE",),
            coverage_ratio=_ZERO,
            cutoff_at=cutoff_at,
        )

    coverage_ratio = snapshot.coverage_ratio
    hard_required = HARD_REQUIRED[profile]

    # SCREENED: check hard required availability
    missing_hard = [f for f in hard_required
                    if all(c.name != f or not c.is_ok for c in snapshot.features)]
    if missing_hard:
        reasons.extend(f"HARD_REQUIRED_MISSING:{f}" for f in missing_hard)
        return ScanCandidate(
            symbol=snapshot.symbol,
            profile=profile,
            stage=STAGE_SCREENED,
            score=None,
            score_status="SCORE_UNAVAILABLE",
            reasons=tuple(reasons),
            coverage_ratio=coverage_ratio,
            cutoff_at=cutoff_at,
        )

    # QUALIFIED: check soft coverage threshold
    if coverage_ratio < SOFT_COVERAGE_THRESHOLD:
        reasons.append(
            f"COVERAGE_BELOW_THRESHOLD:{coverage_ratio}")
        return ScanCandidate(
            symbol=snapshot.symbol,
            profile=profile,
            stage=STAGE_SCREENED,
            score=None,
            score_status="SCORE_UNAVAILABLE",
            reasons=tuple(reasons),
            coverage_ratio=coverage_ratio,
            cutoff_at=cutoff_at,
        )

    # Compute score
    score, score_status, score_reasons = compute_score(snapshot, profile)
    reasons.extend(score_reasons)

    if score_status != "SCORED" or score is None:
        return ScanCandidate(
            symbol=snapshot.symbol,
            profile=profile,
            stage=STAGE_QUALIFIED,
            score=None,
            score_status=score_status,
            reasons=tuple(reasons),
            coverage_ratio=coverage_ratio,
            cutoff_at=cutoff_at,
        )

    # NOMINATED: score meets threshold
    threshold = NOMINATION_THRESHOLD[profile]
    stage = STAGE_NOMINATED if score >= threshold else STAGE_QUALIFIED
    if stage == STAGE_QUALIFIED:
        reasons.append(f"SCORE_BELOW_THRESHOLD:{score}<{threshold}")

    return ScanCandidate(
        symbol=snapshot.symbol,
        profile=profile,
        stage=stage,
        score=score,
        score_status=score_status,
        reasons=tuple(reasons),
        coverage_ratio=coverage_ratio,
        cutoff_at=cutoff_at,
    )


def screen_all_profiles(
    snapshot: MTFFeatureSnapshot,
    profiles: Sequence[str] | None = None,
) -> dict[str, ScanCandidate]:
    """Screen one symbol across all (or selected) profiles.

    Returns {profile_id: ScanCandidate}.
    """
    if profiles is None:
        profiles = list(SUPPORTED_PROFILES)
    return {profile: screen_candidate(snapshot, profile) for profile in profiles}
