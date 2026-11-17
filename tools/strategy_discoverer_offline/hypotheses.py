"""
Phase 3b — Hypothesis Definitions
===================================
Bounded, falsifiable proposal + negative control definitions.

A HypothesisProposal links a FamilyDefinition to a specific parameter
configuration and declares:
  - primary hypothesis (the trading rule)
  - counterhypothesis (the paired null/control)
  - declared assumptions (must be pre-specified before any data access)
  - scientific status = PROPOSED_RESEARCH_ONLY (never evaluated here)

Hypotheses are frozen at proposal time.  No runtime mutation.
No historical performance data enters this module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, Any, Optional

from tools.strategy_discoverer_offline.families import FamilyDefinition, get_family


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


# ---------------------------------------------------------------------------
# Hypothesis proposal
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HypothesisProposal:
    """
    Frozen, falsifiable research hypothesis proposal.

    hypothesis_id       : unique identifier, scoped to family
    family_id           : parent FamilyDefinition.family_id
    family_version      : FamilyDefinition.version (must match)
    family_digest       : FamilyDefinition.family_digest (for integrity)
    parameter_config    : dict of declared parameter values for this proposal
    entry_direction     : "LONG" | "SHORT" | "BOTH"
    hypothesis_statement: human-readable falsifiable claim (pre-declared)
    minimum_effect_size : pre-declared minimum economically meaningful effect
    null_hypothesis     : paired null/control description
    counterhypothesis_id: identifier for the paired counterhypothesis
    scientific_status   : always "PROPOSED_RESEARCH_ONLY"
    assumptions         : tuple of pre-declared assumptions (strings)
    hypothesis_digest   : sha256 of canonical(all other fields)
    """
    hypothesis_id: str
    family_id: str
    family_version: str
    family_digest: str
    parameter_config: dict
    entry_direction: str
    hypothesis_statement: str
    minimum_effect_size: str
    null_hypothesis: str
    counterhypothesis_id: str
    scientific_status: str
    assumptions: tuple
    hypothesis_digest: str

    def __post_init__(self):
        if self.entry_direction not in ("LONG", "SHORT", "BOTH"):
            raise ValueError(f"Invalid entry_direction: {self.entry_direction!r}")
        if self.scientific_status != "PROPOSED_RESEARCH_ONLY":
            raise ValueError("scientific_status must be PROPOSED_RESEARCH_ONLY")
        if not isinstance(self.assumptions, tuple):
            raise ValueError("assumptions must be a tuple")
        # Verify digest
        expected = _digest(self._fields_for_digest())
        if self.hypothesis_digest != expected:
            raise ValueError(
                f"hypothesis_digest mismatch for {self.hypothesis_id}: "
                f"stored={self.hypothesis_digest} computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "family_id": self.family_id,
            "family_version": self.family_version,
            "family_digest": self.family_digest,
            "parameter_config": self.parameter_config,
            "entry_direction": self.entry_direction,
            "hypothesis_statement": self.hypothesis_statement,
            "minimum_effect_size": self.minimum_effect_size,
            "null_hypothesis": self.null_hypothesis,
            "counterhypothesis_id": self.counterhypothesis_id,
            "scientific_status": self.scientific_status,
            "assumptions": list(self.assumptions),
        }

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["hypothesis_digest"] = self.hypothesis_digest
        return d

    @classmethod
    def build(cls, *, family: FamilyDefinition, hypothesis_id: str,
              parameter_config: dict, entry_direction: str,
              hypothesis_statement: str, minimum_effect_size: str,
              null_hypothesis: str, counterhypothesis_id: str,
              assumptions: tuple) -> "HypothesisProposal":
        """Build a frozen hypothesis proposal linked to a FamilyDefinition."""
        kwargs = dict(
            hypothesis_id=hypothesis_id,
            family_id=family.family_id,
            family_version=family.version,
            family_digest=family.family_digest,
            parameter_config=dict(parameter_config),
            entry_direction=entry_direction,
            hypothesis_statement=hypothesis_statement,
            minimum_effect_size=minimum_effect_size,
            null_hypothesis=null_hypothesis,
            counterhypothesis_id=counterhypothesis_id,
            scientific_status="PROPOSED_RESEARCH_ONLY",
            assumptions=tuple(assumptions),
        )
        hypothesis_digest = _digest({
            **kwargs,
            "assumptions": list(kwargs["assumptions"]),
        })
        return cls(**kwargs, hypothesis_digest=hypothesis_digest)


# ---------------------------------------------------------------------------
# Canonical hypothesis search plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchPlan:
    """
    Frozen search plan declaring all hypotheses to be explored in one run.

    search_plan_id      : unique identifier
    family_registry_digest : digest of FAMILY_REGISTRY at plan creation time
    hypothesis_ids      : ordered tuple of hypothesis_id strings
    total_candidate_budget : declared maximum candidates across all hypotheses
    plan_digest         : sha256 of canonical(all other fields)
    """
    search_plan_id: str
    family_registry_digest: str
    hypothesis_ids: tuple
    total_candidate_budget: int
    plan_digest: str

    def __post_init__(self):
        if not isinstance(self.hypothesis_ids, tuple) or len(self.hypothesis_ids) == 0:
            raise ValueError("hypothesis_ids must be a non-empty tuple")
        if not isinstance(self.total_candidate_budget, int) or self.total_candidate_budget < 1:
            raise ValueError("total_candidate_budget must be positive integer")
        expected = _digest(self._fields_for_digest())
        if self.plan_digest != expected:
            raise ValueError(
                f"plan_digest mismatch: stored={self.plan_digest} computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "search_plan_id": self.search_plan_id,
            "family_registry_digest": self.family_registry_digest,
            "hypothesis_ids": list(self.hypothesis_ids),
            "total_candidate_budget": self.total_candidate_budget,
        }

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["plan_digest"] = self.plan_digest
        return d

    @classmethod
    def build(cls, *, search_plan_id: str, family_registry_digest: str,
              hypothesis_ids: tuple, total_candidate_budget: int) -> "SearchPlan":
        kwargs = dict(
            search_plan_id=search_plan_id,
            family_registry_digest=family_registry_digest,
            hypothesis_ids=tuple(hypothesis_ids),
            total_candidate_budget=total_candidate_budget,
        )
        plan_digest = _digest({**kwargs, "hypothesis_ids": list(kwargs["hypothesis_ids"])})
        return cls(**kwargs, plan_digest=plan_digest)
