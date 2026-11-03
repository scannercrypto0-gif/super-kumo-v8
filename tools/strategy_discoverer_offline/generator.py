"""
Phase 3c — Hypothesis & Candidate Generator
=============================================
Generates StrategyDefinition candidates from family grids.

Uses ONLY:
  research_wp_r0.strategy_definition.StrategyDefinition  (PR #69, MERGED)
  research_wp_r0.strategy_definition.candidate_grid      (PR #69, MERGED)
  research_wp_r0.indicator_library_v2.IndicatorRegistryV2 (PR #68, MERGED)

Does NOT import from:
  - Any unmerged PR (#46, #222, #226, #227, #228)
  - Factory, Scanner, Work, Core, or live data sources

Candidates are produced as StrategyDefinition objects via candidate_grid().
Each candidate is cross-checked for uniqueness by digest before acceptance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Dict, Optional

from research_wp_r0.strategy_definition import (
    StrategyDefinition,
    candidate_grid,
)
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

from tools.strategy_discoverer_offline.contracts import (
    NominationEvidenceV1,
)
from tools.strategy_discoverer_offline.scanner_adapter import assert_eligible_for_research
from tools.strategy_discoverer_offline.families import FamilyDefinition
from tools.strategy_discoverer_offline.hypotheses import HypothesisProposal, SearchPlan


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


# Default registry — IndicatorRegistryV2 extends V1 with OHLCV indicators
_DEFAULT_REGISTRY = IndicatorRegistryV2()

# Maximum candidates per generator run (hard limit from StrategyDefinition contract)
MAX_CANDIDATES_PER_RUN = 256

# Grammar version (identifies the boolean AST grammar in use)
RULE_GRAMMAR_VERSION = "aql.strategy-definition.grammar.v1"


# ---------------------------------------------------------------------------
# Spec-building helpers
# ---------------------------------------------------------------------------

# The ONLY valid timing dict for V1 (StrategyDefinition rejects anything else)
_TIMING = {
    "decision": "CONFIRMED_CLOSE",
    "entry_execution": "NEXT_ELIGIBLE_OPEN",
    "ambiguity": "REJECT",
}

# Conservative risk defaults valid for all V1 families (unlevered, research-only)
_DEFAULT_RISK = {
    "unit": "ENTRY_NOTIONAL",
    "max_exposure": 0.01,
    "max_leverage": 1,
    "stop_fraction": 0.02,
    "target_fraction": 0.04,
    "entry_ttl_bars": 3,
    "holding_bars": 20,
}

# Constraint templates — reused across indicators
_INT_C = {"type": "int", "min": 1, "max": 1000}
_SMOOTH_C = {"type": "number", "min": 1.0, "max": 100.0}
_DEV_C = {"type": "number", "min": 0.1, "max": 10.0}


def _ind(name: str, indicator_id: str, version: str,
         parameters: dict, constraints: dict) -> dict:
    """Build a well-formed indicator reference dict."""
    return {
        "name": name,
        "indicator_id": indicator_id,
        "version": version,
        "parameters": dict(parameters),
        "constraints": {k: dict(v) for k, v in constraints.items()},
    }


def _ref(name: str, field: str, lag: int = 0) -> dict:
    """Build an indicator-reference AST leaf node."""
    return {"op": "indicator", "name": name, "field": field, "lag": lag}


def _const(value) -> dict:
    """Build a constant AST node."""
    return {"op": "constant", "value": value}


def _gt(left: dict, right: dict) -> dict:
    return {"op": "gt", "left": left, "right": right}


# ---------------------------------------------------------------------------
# Per-family spec data
#
# Each entry defines:
#   indicators : list of indicator ref dicts (correct name/indicator_id/version/
#                parameters/constraints per StrategyDefinition._reference())
#   entry      : valid boolean AST expression for entry
#   exit       : valid boolean AST expression for exit
#   axes       : dict mapping "ref_name.param_name" -> list of sweep values
#                for candidate_grid()
#
# Rules enforced here:
#   * indicator["name"] must be unique within a family (named refs)
#   * Two EMA_v1 slots in F001 → "ema_fast" / "ema_slow" to avoid collision
#   * EMA_v1 has TWO params: period AND smoothing (both must be declared)
#   * OBV_v2 has NO params (empty dicts)
#   * All axis values must fall within their corresponding constraint bounds
# ---------------------------------------------------------------------------

_FAMILY_SPEC_DATA: dict = {

    # F001: EMA momentum crossover + RSI filter
    "F001": {
        "indicators": [
            _ind("ema_fast", "EMA_v1", "1",
                 {"period": 9, "smoothing": 2.0},
                 {"period": _INT_C, "smoothing": _SMOOTH_C}),
            _ind("ema_slow", "EMA_v1", "1",
                 {"period": 26, "smoothing": 2.0},
                 {"period": _INT_C, "smoothing": _SMOOTH_C}),
            _ind("rsi", "RSI_v1", "1",
                 {"period": 14},
                 {"period": _INT_C}),
        ],
        # Entry:  fast EMA crosses above slow EMA
        "entry": _gt(_ref("ema_fast", "value"), _ref("ema_slow", "value")),
        # Exit:   slow EMA crosses above fast EMA (prior bar)
        "exit":  _gt(_ref("ema_slow", "value", lag=1), _ref("ema_fast", "value", lag=1)),
        "axes": {
            "ema_fast.period": [9, 12, 21],
            "ema_slow.period": [26, 50, 100],
            "rsi.period":      [14, 21],
        },
    },

    # F002: Bollinger Bands mean-reversion
    "F002": {
        "indicators": [
            _ind("bbands", "BBANDS_v2", "2",
                 {"period": 20, "deviations": 2.0},
                 {"period": _INT_C, "deviations": _DEV_C}),
        ],
        "entry": _gt(_ref("bbands", "middle"), _ref("bbands", "lower")),
        "exit":  _gt(_ref("bbands", "upper"), _ref("bbands", "middle")),
        "axes": {
            "bbands.period":     [10, 20, 30],
            "bbands.deviations": [1.5, 2.0, 2.5],
        },
    },

    # F003: ADX trend filter + EMA direction
    "F003": {
        "indicators": [
            _ind("adx", "ADX_v2", "2",
                 {"period": 14},
                 {"period": _INT_C}),
            _ind("ema", "EMA_v1", "1",
                 {"period": 20, "smoothing": 2.0},
                 {"period": _INT_C, "smoothing": _SMOOTH_C}),
        ],
        # Entry:  ADX above 25 (trending market)
        "entry": _gt(_ref("adx", "adx"), _const(25)),
        # Exit:   ADX drops below 20 (trend weakening)
        "exit":  _gt(_const(20), _ref("adx", "adx")),
        "axes": {
            "adx.period": [10, 14, 20],
            "ema.period":  [20, 50],
        },
    },

    # F004: MACD histogram signal
    "F004": {
        "indicators": [
            _ind("macd", "MACD_v2", "2",
                 {"fast": 12, "slow": 26, "signal": 9},
                 {"fast": _INT_C, "slow": _INT_C, "signal": _INT_C}),
        ],
        "entry": _gt(_ref("macd", "histogram"), _const(0)),
        "exit":  _gt(_const(0), _ref("macd", "histogram")),
        "axes": {
            "macd.fast":   [9, 12],
            "macd.slow":   [26, 50],
            "macd.signal": [9, 12],
        },
    },

    # F005: Stochastic reversal
    "F005": {
        "indicators": [
            _ind("stoch", "STOCH_v2", "2",
                 {"period": 14, "smooth": 3},
                 {"period": _INT_C, "smooth": _INT_C}),
        ],
        # Entry: %K crosses above %D
        "entry": _gt(_ref("stoch", "k"), _ref("stoch", "d")),
        # Exit:  %D crosses above %K
        "exit":  _gt(_ref("stoch", "d"), _ref("stoch", "k")),
        "axes": {
            "stoch.period": [5, 14, 21],
            "stoch.smooth": [3, 5],
        },
    },

    # F006: Rate-of-change threshold
    "F006": {
        "indicators": [
            _ind("roc", "ROC_v2", "2",
                 {"period": 10},
                 {"period": _INT_C}),
        ],
        "entry": _gt(_ref("roc", "roc"), _const(1.0)),
        "exit":  _gt(_const(-1.0), _ref("roc", "roc")),
        "axes": {
            "roc.period": [5, 10, 20, 50],
        },
    },

    # F007: OBV volume lead + EMA trend filter
    "F007": {
        "indicators": [
            _ind("obv", "OBV_v2", "2",
                 {},   # OBV_v2 has no parameters
                 {}),
            _ind("ema", "EMA_v1", "1",
                 {"period": 10, "smoothing": 2.0},
                 {"period": _INT_C, "smoothing": _SMOOTH_C}),
        ],
        # Entry: OBV rising (current bar > prior bar)
        "entry": _gt(_ref("obv", "obv", lag=0), _ref("obv", "obv", lag=1)),
        # Exit:  OBV falling
        "exit":  _gt(_ref("obv", "obv", lag=1), _ref("obv", "obv", lag=0)),
        "axes": {
            "ema.period": [10, 20],
        },
    },
}


# ---------------------------------------------------------------------------
# Generation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenerationResult:
    """
    Result of one generator run.

    search_plan_digest      : identifies the search plan that produced this
    candidates              : tuple of (StrategyDefinition, candidate_id) pairs
    attempt_count           : total candidates attempted (including failures)
    unique_definition_count : count with distinct digest
    submitted_count         : count ready for ledger (= unique, no duplicates)
    evaluated_count         : always 0 in Discoverer V1
    duplicate_digests       : frozenset of digests appearing more than once
    generation_manifest_digest : sha256 of canonical generation manifest
    """
    search_plan_digest: str
    candidates: tuple               # tuple of (StrategyDefinition, str candidate_id)
    attempt_count: int
    unique_definition_count: int
    submitted_count: int
    evaluated_count: int
    duplicate_digests: frozenset
    generation_manifest_digest: str

    def __post_init__(self):
        if self.evaluated_count != 0:
            raise ValueError("evaluated_count must always be 0 in Discoverer V1")
        if self.submitted_count > self.unique_definition_count:
            raise ValueError("submitted_count cannot exceed unique_definition_count")
        if self.submitted_count > self.attempt_count:
            raise ValueError("submitted_count cannot exceed attempt_count")


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class HypothesisGenerator:
    """
    Generates StrategyDefinition candidates from a FamilyDefinition grid.

    Usage
    -----
    gen = HypothesisGenerator()
    result = gen.run_family(family, evidence, plan_digest)

    Evidence must pass assert_eligible_for_research() — currently only
    TEST_ONLY_SYNTHETIC evidence is accepted while Scanner PR #227 P0 open.
    """

    def __init__(self, registry: Optional[IndicatorRegistryV2] = None):
        self._registry = registry or _DEFAULT_REGISTRY

    def run_family(
        self,
        family: FamilyDefinition,
        evidence: NominationEvidenceV1,
        search_plan_digest: str,
    ) -> GenerationResult:
        """
        Generate candidates for one family from a validated evidence record.

        Raises ValueError if evidence is not eligible for research.
        Returns GenerationResult with full attempt accounting.
        """
        # Gate: policy guard — must pass before any generation
        assert_eligible_for_research(evidence)

        # Build the base StrategyDefinition for this family
        base_spec = self._build_base_spec(family)
        base_sd = StrategyDefinition(base_spec, registry=self._registry)

        # Build axes for candidate_grid: {"ref_name.param_name": [values]}
        axes = self._build_candidate_grid_axes(family)

        # Generate all candidates via candidate_grid
        max_grid = min(family.max_candidates, MAX_CANDIDATES_PER_RUN)
        if axes:
            all_candidates = candidate_grid(
                base_sd, axes, registry=self._registry, maximum=max_grid
            )
        else:
            # Family with no swept parameters: single base candidate
            all_candidates = (base_sd,)

        # Deduplicate by digest, enforce budget
        seen_digests: Dict[str, str] = {}   # digest -> candidate_id
        duplicate_digests: set = set()
        accepted_candidates: List = []
        attempt_count = 0

        for idx, sd in enumerate(all_candidates):
            if attempt_count >= max_grid:
                break
            attempt_count += 1
            d = sd.digest
            candidate_id = f"{family.family_id}-{idx:04d}"
            if d in seen_digests:
                duplicate_digests.add(d)
                continue
            seen_digests[d] = candidate_id
            accepted_candidates.append((sd, candidate_id))

        unique_definition_count = len(seen_digests)
        submitted_count = len(accepted_candidates)

        # Build generation manifest for audit trail
        manifest = {
            "family_id": family.family_id,
            "family_version": family.version,
            "family_digest": family.family_digest,
            "search_plan_digest": search_plan_digest,
            "evidence_class": evidence.evidence_class,
            "quarantine_status": evidence.quarantine_status,
            "nomination_digest": evidence.nomination_digest,
            "attempt_count": attempt_count,
            "unique_definition_count": unique_definition_count,
            "submitted_count": submitted_count,
            "evaluated_count": 0,
            "duplicate_count": len(duplicate_digests),
            "accepted_digests": sorted(seen_digests.keys()),
        }
        generation_manifest_digest = _digest(manifest)

        return GenerationResult(
            search_plan_digest=search_plan_digest,
            candidates=tuple(accepted_candidates),
            attempt_count=attempt_count,
            unique_definition_count=unique_definition_count,
            submitted_count=submitted_count,
            evaluated_count=0,
            duplicate_digests=frozenset(duplicate_digests),
            generation_manifest_digest=generation_manifest_digest,
        )

    # ------------------------------------------------------------------
    # Per-family spec builders
    # ------------------------------------------------------------------

    def _build_base_spec(self, family: FamilyDefinition) -> dict:
        """
        Return a valid StrategyDefinition spec dict for one family.

        Uses named indicator refs (unique name per slot, even for same
        indicator_id) and correct AST boolean expressions per the V1 grammar.

        Fields: exactly schema_version, strategy_id, strategy_version, scope,
        indicators, entry, exit, timing, risk — no extras.
        """
        fdata = _FAMILY_SPEC_DATA[family.family_id]
        return {
            "schema_version": "1",
            "strategy_id": f"{family.family_id.lower()}-v1",
            "strategy_version": "v1",
            "scope": "RESEARCH_ONLY",
            "indicators": [dict(ind) for ind in fdata["indicators"]],
            "entry": fdata["entry"],
            "exit": fdata["exit"],
            "timing": dict(_TIMING),
            "risk": dict(_DEFAULT_RISK),
        }

    def _build_candidate_grid_axes(self, family: FamilyDefinition) -> dict:
        """
        Return the axes dict for candidate_grid().

        Keys are "ref_name.param_name" matching the named indicator refs in the
        base spec.  Values are lists of sweep values for each parameter.
        """
        return dict(_FAMILY_SPEC_DATA[family.family_id]["axes"])
