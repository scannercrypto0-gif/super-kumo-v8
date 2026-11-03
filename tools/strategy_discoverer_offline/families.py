"""
Phase 3a — Family Registry
===========================
Frozen declarative family grid definitions.

Each FamilyDefinition declares:
  - family_id, version, description
  - indicator axes (each axis = indicator_id + parameter ranges)
  - entry / exit / regime / timing fields
  - max_candidates budget (≤ 256 per candidate_grid contract)

Families are FROZEN at discovery time — no runtime mutation.

Available families (V1)
-----------------------
F001  MomentumCrossover   — EMA fast/slow crossover, RSI filter
F002  BBandsMeanReversion — BBANDS entry at deviation extremes
F003  TrendADX            — ADX trend strength with EMA direction
F004  MACDSignal          — MACD histogram sign flip
F005  StochReversal       — Stochastic %K/%D crossover at extremes
F006  ROCThreshold        — Rate of Change momentum threshold
F007  OBVVolumeLead       — OBV divergence from price

All use only indicators registered in IndicatorRegistryV2 (merged PR #68).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


# ---------------------------------------------------------------------------
# Family definition dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterAxis:
    """A single parameter axis in a Cartesian grid."""
    name: str           # parameter name as registered in IndicatorRegistryV2
    values: tuple       # frozen tuple of allowed parameter values

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("ParameterAxis name must be a non-empty string")
        if not isinstance(self.values, tuple) or len(self.values) == 0:
            raise ValueError("ParameterAxis values must be a non-empty tuple")
        for v in self.values:
            if not isinstance(v, (int, float)):
                raise ValueError(f"Parameter value must be numeric, got {v!r}")


@dataclass(frozen=True)
class IndicatorAxis:
    """Configuration for one indicator slot in the family grid."""
    indicator_id: str
    parameter_axes: tuple   # tuple of ParameterAxis

    def __post_init__(self):
        if not self.indicator_id:
            raise ValueError("indicator_id must be non-empty")
        if not isinstance(self.parameter_axes, tuple):
            raise ValueError("parameter_axes must be a tuple")


@dataclass(frozen=True)
class FamilyDefinition:
    """
    Frozen family definition.

    family_id       : unique identifier, [A-Za-z][A-Za-z0-9_.-]{0,63}
    version         : semantic version string
    description     : human-readable description
    indicator_axes  : tuple of IndicatorAxis defining the Cartesian grid
    entry_rule_template : description of entry rule structure
    exit_rule_template  : description of exit rule structure
    timing          : one of CONFIRMED_CLOSE | NEXT_ELIGIBLE_OPEN
    max_candidates  : per-run candidate budget (≤ 256)
    counterhypothesis_template : description of null hypothesis structure
    family_digest   : sha256 of canonical(family definition fields)
    """
    family_id: str
    version: str
    description: str
    indicator_axes: tuple           # tuple of IndicatorAxis
    entry_rule_template: str
    exit_rule_template: str
    timing: str
    max_candidates: int
    counterhypothesis_template: str
    family_digest: str

    def __post_init__(self):
        import re
        if not re.match(r'^[A-Za-z][A-Za-z0-9_.\-]{0,63}$', self.family_id):
            raise ValueError(f"Invalid family_id: {self.family_id!r}")
        if self.timing not in ("CONFIRMED_CLOSE", "NEXT_ELIGIBLE_OPEN"):
            raise ValueError(f"Invalid timing: {self.timing!r}")
        if not isinstance(self.max_candidates, int) or not 1 <= self.max_candidates <= 256:
            raise ValueError(f"max_candidates must be 1–256, got {self.max_candidates}")
        if not isinstance(self.indicator_axes, tuple):
            raise ValueError("indicator_axes must be a tuple")
        # Verify digest
        expected = _digest(self._fields_for_digest())
        if self.family_digest != expected:
            raise ValueError(
                f"family_digest mismatch for {self.family_id}: "
                f"stored={self.family_digest} computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "family_id": self.family_id,
            "version": self.version,
            "description": self.description,
            "indicator_axes": [
                {
                    "indicator_id": ax.indicator_id,
                    "parameter_axes": [
                        {"name": p.name, "values": list(p.values)}
                        for p in ax.parameter_axes
                    ],
                }
                for ax in self.indicator_axes
            ],
            "entry_rule_template": self.entry_rule_template,
            "exit_rule_template": self.exit_rule_template,
            "timing": self.timing,
            "max_candidates": self.max_candidates,
            "counterhypothesis_template": self.counterhypothesis_template,
        }

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["family_digest"] = self.family_digest
        return d

    @classmethod
    def build(cls, **kwargs) -> "FamilyDefinition":
        if "family_digest" in kwargs:
            raise ValueError("Do not pass family_digest; it is computed.")
        # Canonicalize tuples
        indicator_axes_raw = kwargs.get("indicator_axes", ())
        kwargs["indicator_axes"] = tuple(indicator_axes_raw)
        fields_for_digest = {
            "family_id": kwargs["family_id"],
            "version": kwargs["version"],
            "description": kwargs["description"],
            "indicator_axes": [
                {
                    "indicator_id": ax.indicator_id,
                    "parameter_axes": [
                        {"name": p.name, "values": list(p.values)}
                        for p in ax.parameter_axes
                    ],
                }
                for ax in kwargs["indicator_axes"]
            ],
            "entry_rule_template": kwargs["entry_rule_template"],
            "exit_rule_template": kwargs["exit_rule_template"],
            "timing": kwargs["timing"],
            "max_candidates": kwargs["max_candidates"],
            "counterhypothesis_template": kwargs["counterhypothesis_template"],
        }
        family_digest = _digest(fields_for_digest)
        return cls(**kwargs, family_digest=family_digest)


# ---------------------------------------------------------------------------
# Helper: build a ParameterAxis
# ---------------------------------------------------------------------------

def _ax(name: str, *values) -> ParameterAxis:
    return ParameterAxis(name=name, values=tuple(values))


def _ind(indicator_id: str, *axes: ParameterAxis) -> IndicatorAxis:
    return IndicatorAxis(indicator_id=indicator_id, parameter_axes=tuple(axes))


# ---------------------------------------------------------------------------
# V1 Family Registry — 7 families
# ---------------------------------------------------------------------------

F001_MOMENTUM_CROSSOVER = FamilyDefinition.build(
    family_id="F001",
    version="1.0",
    description=(
        "EMA fast/slow crossover with RSI filter. "
        "Entry when fast EMA crosses above/below slow EMA and RSI confirms "
        "momentum direction."
    ),
    indicator_axes=(
        _ind("EMA_v1", _ax("period", 9, 12, 21)),
        _ind("EMA_v1", _ax("period", 26, 50, 100)),
        _ind("RSI_v1", _ax("period", 14, 21)),
    ),
    entry_rule_template=(
        "EMA(fast) crosses EMA(slow) AND RSI(period) > threshold_long "
        "OR EMA(fast) crosses below EMA(slow) AND RSI(period) < threshold_short"
    ),
    exit_rule_template=(
        "EMA(fast) crosses back through EMA(slow) OR RSI(period) reaches extreme"
    ),
    timing="CONFIRMED_CLOSE",
    max_candidates=54,   # 3 x 3 x 2 x 3 (threshold variants) = 54
    counterhypothesis_template=(
        "Random crossover signal at same eligible universe and frequency; "
        "no EMA or RSI filter applied"
    ),
)

F002_BBANDS_MEAN_REVERSION = FamilyDefinition.build(
    family_id="F002",
    version="1.0",
    description=(
        "Bollinger Bands mean reversion. "
        "Entry when price touches outer band (deviation threshold), "
        "exit at middle band or opposite touch."
    ),
    indicator_axes=(
        _ind("BBANDS_v2", _ax("period", 10, 20, 30), _ax("deviations", 1.5, 2.0, 2.5)),
    ),
    entry_rule_template=(
        "Close <= BBANDS(lower) AND recent trend neutral OR "
        "Close >= BBANDS(upper) AND recent trend neutral"
    ),
    exit_rule_template="Close crosses BBANDS(middle)",
    timing="CONFIRMED_CLOSE",
    max_candidates=9,   # 3 x 3
    counterhypothesis_template=(
        "Random entry at same bar frequency, no BBANDS filter; "
        "contrarian signal with random direction"
    ),
)

F003_TREND_ADX = FamilyDefinition.build(
    family_id="F003",
    version="1.0",
    description=(
        "ADX trend strength with EMA direction filter. "
        "Entry when ADX > threshold indicating strong trend and EMA slope confirms."
    ),
    indicator_axes=(
        _ind("ADX_v2", _ax("period", 10, 14, 20)),
        _ind("EMA_v1", _ax("period", 20, 50)),
    ),
    entry_rule_template=(
        "ADX(period) > adx_threshold AND EMA(period) slope positive (long) "
        "OR ADX(period) > adx_threshold AND EMA(period) slope negative (short)"
    ),
    exit_rule_template="ADX(period) < exit_threshold OR EMA(period) slope reversal",
    timing="CONFIRMED_CLOSE",
    max_candidates=24,   # 3 x 2 x 4 (threshold variants)
    counterhypothesis_template=(
        "No ADX filter; EMA direction only with random entry timing"
    ),
)

F004_MACD_SIGNAL = FamilyDefinition.build(
    family_id="F004",
    version="1.0",
    description=(
        "MACD histogram sign flip. "
        "Entry on MACD histogram zero-line crossing."
    ),
    indicator_axes=(
        _ind("MACD_v2",
             _ax("fast", 9, 12),
             _ax("slow", 26, 50),
             _ax("signal", 9, 12)),
    ),
    entry_rule_template=(
        "MACD(histogram) changes sign from negative to positive (long) "
        "OR from positive to negative (short)"
    ),
    exit_rule_template="MACD(histogram) changes sign again OR magnitude threshold",
    timing="CONFIRMED_CLOSE",
    max_candidates=8,   # 2 fast x 2 slow x 2 signal (only valid fast < slow)
    counterhypothesis_template="Random entry at same frequency; no MACD filter",
)

F005_STOCH_REVERSAL = FamilyDefinition.build(
    family_id="F005",
    version="1.0",
    description=(
        "Stochastic %K/%D crossover at overbought/oversold extremes. "
        "Entry when %K crosses %D while in extreme zone."
    ),
    indicator_axes=(
        _ind("STOCH_v2", _ax("period", 5, 14, 21), _ax("smooth", 3, 5)),
    ),
    entry_rule_template=(
        "STOCH(%K) crosses above STOCH(%D) while %K < 20 (long) "
        "OR STOCH(%K) crosses below STOCH(%D) while %K > 80 (short)"
    ),
    exit_rule_template="STOCH(%K) exits extreme zone or crosses %D in reverse",
    timing="NEXT_ELIGIBLE_OPEN",
    max_candidates=12,  # 3 x 2 x 2 (long/short)
    counterhypothesis_template=(
        "Random entry in same extreme zone, no crossover filter"
    ),
)

F006_ROC_THRESHOLD = FamilyDefinition.build(
    family_id="F006",
    version="1.0",
    description=(
        "Rate of Change momentum threshold. "
        "Entry when ROC exceeds positive/negative threshold."
    ),
    indicator_axes=(
        _ind("ROC_v2", _ax("period", 5, 10, 20, 50)),
    ),
    entry_rule_template=(
        "ROC(period) > positive_threshold (long momentum) "
        "OR ROC(period) < negative_threshold (short momentum)"
    ),
    exit_rule_template="ROC(period) reverts toward zero or threshold_exit",
    timing="CONFIRMED_CLOSE",
    max_candidates=16,  # 4 periods x 4 threshold variants
    counterhypothesis_template="Random momentum signal at same frequency, no ROC filter",
)

F007_OBV_VOLUME_LEAD = FamilyDefinition.build(
    family_id="F007",
    version="1.0",
    description=(
        "OBV divergence from price. "
        "Entry when OBV trend diverges from price trend, "
        "signaling potential reversal."
    ),
    indicator_axes=(
        _ind("OBV_v2"),                          # no parameters
        _ind("EMA_v1", _ax("period", 10, 20)),  # for smoothing OBV / price trend
    ),
    entry_rule_template=(
        "OBV(smoothed) makes new high while price does not (bullish divergence) "
        "OR OBV(smoothed) makes new low while price does not (bearish divergence)"
    ),
    exit_rule_template="Price confirms OBV signal or lookback window expires",
    timing="CONFIRMED_CLOSE",
    max_candidates=12,  # 2 EMA periods x 6 lookback/threshold variants
    counterhypothesis_template="Random entry at same divergence frequency; no OBV filter",
)


# ---------------------------------------------------------------------------
# Family registry
# ---------------------------------------------------------------------------

FAMILY_REGISTRY: Dict[str, FamilyDefinition] = {
    f.family_id: f for f in (
        F001_MOMENTUM_CROSSOVER,
        F002_BBANDS_MEAN_REVERSION,
        F003_TREND_ADX,
        F004_MACD_SIGNAL,
        F005_STOCH_REVERSAL,
        F006_ROC_THRESHOLD,
        F007_OBV_VOLUME_LEAD,
    )
}


def get_family(family_id: str) -> FamilyDefinition:
    if family_id not in FAMILY_REGISTRY:
        raise ValueError(f"Unknown family_id: {family_id!r}. "
                         f"Available: {sorted(FAMILY_REGISTRY)}")
    return FAMILY_REGISTRY[family_id]


def list_families() -> List[str]:
    return sorted(FAMILY_REGISTRY.keys())


def family_registry_digest() -> str:
    """Canonical digest of the entire frozen registry."""
    registry_repr = {
        fid: fdef.family_digest
        for fid, fdef in sorted(FAMILY_REGISTRY.items())
    }
    return _digest(registry_repr)
