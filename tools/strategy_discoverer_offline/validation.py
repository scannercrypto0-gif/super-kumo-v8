"""
Phase 6 — Scientific Validation Readiness Protocol
=====================================================
Versioned, pre-declared validation protocol.

IMPORTANT: This module declares WHAT will be done when evaluation is
authorized.  It does NOT run any evaluation, access historical data,
score candidates, or touch the holdout set.

Governance requirements before any evaluation is authorized
-----------------------------------------------------------
1. All P0 Scanner issues (PR #227) must be independently reviewed and accepted.
2. Strategy Discoverer Draft PR must be reviewed and approved.
3. Owner must grant explicit evaluation authorization.
4. This protocol must be frozen and registered BEFORE any data access.
5. The holdout set remains SEALED until separate explicit authorization.

This protocol freezes the following before any authorized evaluation:
  - Comparator slate (random and simple baselines)
  - Evaluation metrics and statistical tests
  - Multiple-testing correction approach
  - Walk-forward partition rules
  - Embargo / purge window
  - Holdout governance

References
----------
* White (2000) Reality Check: https://doi.org/10.1111/1468-0262.00152
* Sullivan, Timmermann & White (1999): https://doi.org/10.1111/0022-1082.00163
* Bailey et al. (2014) Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659
* Liu, Tsyvinski & Wu (2022) Crypto factors: https://doi.org/10.1111/jofi.13119
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


# ---------------------------------------------------------------------------
# Protocol status
# ---------------------------------------------------------------------------

class ProtocolStatus(str, Enum):
    DRAFT          = "DRAFT"           # not yet frozen
    FROZEN         = "FROZEN"          # locked; no changes allowed
    EVALUATION_NOT_AUTHORIZED = "EVALUATION_NOT_AUTHORIZED"


# ---------------------------------------------------------------------------
# Comparator slate
# ---------------------------------------------------------------------------

COMPARATOR_SLATE_V1 = [
    {
        "id": "RANDOM_BASELINE",
        "description": (
            "Random entry/exit conditioned on same eligible universe and time; "
            "same k candidates as the strategy family."
        ),
    },
    {
        "id": "PREVALENCE_MATCHED_RANDOM",
        "description": (
            "Random signal matching the empirical nomination rate of each strategy, "
            "applied at same frequency."
        ),
    },
    {
        "id": "VOLUME_ONLY",
        "description": (
            "Entry based solely on 24h quote-volume rank; no technical signal."
        ),
    },
    {
        "id": "SIMPLE_MOMENTUM",
        "description": (
            "1-bar lookback return sign; no indicator or filter."
        ),
    },
    {
        "id": "RVOL_ONLY",
        "description": (
            "Relative volume (RVOL) threshold only; no price signal."
        ),
    },
    {
        "id": "MIN_SPREAD_LIQUIDITY",
        "description": (
            "Select lowest bid-ask spread and highest volume; no direction signal."
        ),
    },
    {
        "id": "MOMENTUM_PLUS_LIQUIDITY",
        "description": (
            "Simple momentum combined with volume; no other filters."
        ),
    },
]


# ---------------------------------------------------------------------------
# Predeclared metrics (not yet computed)
# ---------------------------------------------------------------------------

PREDECLARED_METRICS_V1 = [
    "precision_at_k",
    "recall_at_k",
    "opportunity_coverage_rate",
    "censor_rate",
    "lift_vs_unconditional",
    "lift_vs_same_eligibility_prevalence",
    "pr_auc",           # only where well-formed labels and correct base rates exist
    "calibration_brier_score",   # only if score treated as probability
    "turnover_rate",
    "symbol_concentration",
    "false_positive_rate",
    "regime_strata_breakdown",
    "volatility_strata_breakdown",
    "liquidity_strata_breakdown",
    "cost_latency_breakeven_spread",
    "missingness_failure_rate",
]


# ---------------------------------------------------------------------------
# Partition and embargo rules (predeclared)
# ---------------------------------------------------------------------------

PARTITION_RULES_V1 = {
    "type": "chronological_walkforward",
    "description": (
        "Strictly non-overlapping chronological partitions. "
        "Development/validation period precedes prospective untouched test tranche. "
        "No random row split."
    ),
    "embargo_policy": (
        "Purge overlapping label/feature windows with embargo sized at least "
        "maximum_lookback + outcome_exposure as applicable."
    ),
    "normalization_policy": (
        "Fit normalizations and thresholds strictly within training partition. "
        "No information leakage from validation or test periods."
    ),
    "group_policy": (
        "Source/delist-aware groups. "
        "Cluster/block uncertainty accounted for in bootstrap."
    ),
    "holdout_policy": (
        "Hidden holdout sealed until new authorization. "
        "No peeking, no adaptive decisions based on holdout performance."
    ),
}


# ---------------------------------------------------------------------------
# Multiple-testing correction (predeclared)
# ---------------------------------------------------------------------------

MULTIPLICITY_PLAN_V1 = {
    "approach": "block_bootstrap_by_time_and_symbol_cluster",
    "methods": ["Holm_stepdown", "White_Reality_Check", "bootstrap_confidence_intervals"],
    "search_multiplicity_scope": (
        "All candidates across all families, all profiles, all threshold variants, "
        "all parameter grid points. Search duplication, ablations, profile tuning, "
        "repeated peeks, and negative controls all counted."
    ),
    "minimum_effective_independent_events": "to be determined from actual partition size",
    "references": [
        "White (2000) doi:10.1111/1468-0262.00152",
        "Sullivan, Timmermann, White (1999) doi:10.1111/0022-1082.00163",
        "Bailey et al. (2014) https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659",
    ],
}


# ---------------------------------------------------------------------------
# Validation protocol (frozen record)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationProtocolV1:
    """
    Frozen pre-declared validation protocol.

    Must be registered BEFORE any evaluation data is accessed.
    protocol_status must be EVALUATION_NOT_AUTHORIZED for all V1 runs.

    Fields
    ------
    schema_version      : "aql.discoverer.validation-protocol.v1"
    protocol_id         : unique protocol identifier
    family_registry_digest : digest of FAMILY_REGISTRY at freeze time
    search_plan_digest  : digest of the associated SearchPlan
    comparator_slate    : frozen list of comparator descriptions
    predeclared_metrics : frozen list of metric names
    partition_rules     : partition/embargo/holdout policy dict
    multiplicity_plan   : multiple-testing correction plan dict
    protocol_status     : always EVALUATION_NOT_AUTHORIZED in V1
    holdout_sealed      : always True in V1
    evaluation_gates    : ordered list of gates that must pass before evaluation
    protocol_digest     : sha256 of canonical(all other fields)
    """
    schema_version: str
    protocol_id: str
    family_registry_digest: str
    search_plan_digest: str
    comparator_slate: tuple
    predeclared_metrics: tuple
    partition_rules: dict
    multiplicity_plan: dict
    protocol_status: str
    holdout_sealed: bool
    evaluation_gates: tuple
    protocol_digest: str

    def __post_init__(self):
        if self.schema_version != "aql.discoverer.validation-protocol.v1":
            raise ValueError(f"Bad schema_version: {self.schema_version!r}")
        if self.protocol_status != ProtocolStatus.EVALUATION_NOT_AUTHORIZED.value:
            raise ValueError(
                "protocol_status must be EVALUATION_NOT_AUTHORIZED in Discoverer V1"
            )
        if self.holdout_sealed is not True:
            raise ValueError("holdout_sealed must be True in Discoverer V1")
        expected = _digest(self._fields_for_digest())
        if self.protocol_digest != expected:
            raise ValueError(
                f"protocol_digest mismatch: stored={self.protocol_digest} "
                f"computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "family_registry_digest": self.family_registry_digest,
            "search_plan_digest": self.search_plan_digest,
            "comparator_slate": list(self.comparator_slate),
            "predeclared_metrics": list(self.predeclared_metrics),
            "partition_rules": self.partition_rules,
            "multiplicity_plan": self.multiplicity_plan,
            "protocol_status": self.protocol_status,
            "holdout_sealed": self.holdout_sealed,
            "evaluation_gates": list(self.evaluation_gates),
        }

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["protocol_digest"] = self.protocol_digest
        return d

    @classmethod
    def build(cls, *, protocol_id: str, family_registry_digest: str,
              search_plan_digest: str) -> "ValidationProtocolV1":
        """Build the V1 validation protocol with all predeclared fields."""
        evaluation_gates = (
            "GATE_A: P0 identity/PIT fail-closed, complete run census, "
            "receipt integrity, 3.11-3.13 CI green",
            "GATE_B: Authorized real custody read-only replay with immutable receipts, "
            "full missingness/accounting coverage, separate source verification",
            "GATE_C: Locked comparator evaluation with uncertainty report, no holdout",
            "GATE_D: Untouched OOS claim only after separate explicit owner permission "
            "and prereg — not through this review",
        )
        kwargs = dict(
            schema_version="aql.discoverer.validation-protocol.v1",
            protocol_id=protocol_id,
            family_registry_digest=family_registry_digest,
            search_plan_digest=search_plan_digest,
            comparator_slate=tuple(
                json.dumps(c, sort_keys=True) for c in COMPARATOR_SLATE_V1
            ),
            predeclared_metrics=tuple(PREDECLARED_METRICS_V1),
            partition_rules=PARTITION_RULES_V1,
            multiplicity_plan=MULTIPLICITY_PLAN_V1,
            protocol_status=ProtocolStatus.EVALUATION_NOT_AUTHORIZED.value,
            holdout_sealed=True,
            evaluation_gates=evaluation_gates,
        )
        protocol_digest = _digest({
            **kwargs,
            "comparator_slate": list(kwargs["comparator_slate"]),
            "predeclared_metrics": list(kwargs["predeclared_metrics"]),
            "evaluation_gates": list(kwargs["evaluation_gates"]),
        })
        return cls(**kwargs, protocol_digest=protocol_digest)
