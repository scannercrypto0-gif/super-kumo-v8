"""
Phase 5 — Research Candidate Packaging
========================================
Produces DiscoveryCandidatePackageV1 for each accepted candidate.

All packages carry hard NOT_* flags (enforced in DiscoveryCandidatePackageV1):
  evaluation_status    = NOT_EVALUATED
  scientific_acceptance = NOT_OBTAINED
  execution_status     = NOT_AUTHORIZED
  publishable          = False
  delivery_authorized  = False
  holdout_status       = SEALED_UNOPENED
  factory_routing      = NOT_CONNECTED

The packager records every attempt (including failures) in the ledger before
emitting any candidate package.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from research_wp_r0.strategy_definition import StrategyDefinition

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1,
    NominationEvidenceV1,
    CandidateStatus,
    _canonical,
    _digest,
)
from tools.strategy_discoverer_offline.families import FamilyDefinition
from tools.strategy_discoverer_offline.hypotheses import SearchPlan
from tools.strategy_discoverer_offline.ledger import DiscovererLedger, AttemptState
from tools.strategy_discoverer_offline.generator import GenerationResult


# ---------------------------------------------------------------------------
# Packaging result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PackagingResult:
    """
    Result of packaging all candidates from one GenerationResult.

    packages                : tuple of accepted DiscoveryCandidatePackageV1
    attempt_count           : total attempts (unique_definition_count from generation)
    submitted_count         : len(packages)
    rejected_count          : attempts that failed packaging validation
    ledger_head             : ledger.head_digest() after all attempts recorded
    packaging_manifest_digest: sha256 of canonical packaging manifest
    """
    packages: tuple
    attempt_count: int
    submitted_count: int
    rejected_count: int
    ledger_head: str
    packaging_manifest_digest: str


# ---------------------------------------------------------------------------
# Packager
# ---------------------------------------------------------------------------

class CandidatePackager:
    """
    Packages accepted candidates into DiscoveryCandidatePackageV1 objects.

    Every candidate is registered in the ledger before packaging begins.
    Failures are recorded as INVALID or FAILED states.
    Successfully packaged candidates are recorded as COMPLETE.

    Usage
    -----
    packager = CandidatePackager(ledger, search_plan, family)
    result = packager.package_generation(generation_result, evidence, source_manifest_sha256)
    """

    def __init__(
        self,
        ledger: DiscovererLedger,
        search_plan: SearchPlan,
        family: FamilyDefinition,
    ):
        self._ledger = ledger
        self._search_plan = search_plan
        self._family = family

    def package_generation(
        self,
        gen_result: GenerationResult,
        evidence: NominationEvidenceV1,
        source_manifest_sha256: str,
    ) -> PackagingResult:
        """
        Package all candidates from a GenerationResult.

        Records EVERY attempt in the ledger before emitting any package.
        Returns PackagingResult with full census.
        """
        # Validate source_manifest_sha256 format
        if (not isinstance(source_manifest_sha256, str)
                or len(source_manifest_sha256) != 64
                or not all(c in "0123456789abcdef" for c in source_manifest_sha256)):
            raise ValueError("source_manifest_sha256 must be 64-char lowercase hex SHA-256")

        packages = []
        rejected_count = 0
        attempt_count = gen_result.submitted_count

        for (strategy_def, candidate_id) in gen_result.candidates:
            attempt_id = f"{candidate_id}-{uuid.uuid4().hex[:8]}"

            # STEP 1: Register attempt in ledger BEFORE packaging
            try:
                self._ledger.register(
                    attempt_id=attempt_id,
                    candidate_id=candidate_id,
                    family_id=self._family.family_id,
                    strategy_digest=strategy_def.digest,
                    search_plan_digest=self._search_plan.plan_digest,
                    nomination_digest=evidence.nomination_digest,
                    reason="registered for packaging",
                )
                self._ledger.transition(attempt_id, AttemptState.PENDING,
                                        reason="packaging started")
            except Exception as e:
                # Ledger failure is a hard blocker — do not proceed silently
                raise RuntimeError(
                    f"Ledger registration failure for candidate {candidate_id!r}: {e}"
                ) from e

            # STEP 2: Validate candidate
            try:
                package = self._build_package(
                    strategy_def=strategy_def,
                    candidate_id=candidate_id,
                    evidence=evidence,
                    source_manifest_sha256=source_manifest_sha256,
                )
            except Exception as e:
                # Record failure in ledger
                self._ledger.transition(attempt_id, AttemptState.FAILED,
                                        reason=f"packaging failed: {e}")
                rejected_count += 1
                continue

            # STEP 3: Record successful completion in ledger
            self._ledger.transition(attempt_id, AttemptState.COMPLETE,
                                    reason="packaged successfully")
            packages.append(package)

        # Build packaging manifest for audit
        manifest = {
            "search_plan_id": self._search_plan.search_plan_id,
            "plan_digest": self._search_plan.plan_digest,
            "family_id": self._family.family_id,
            "family_digest": self._family.family_digest,
            "nomination_digest": evidence.nomination_digest,
            "source_manifest_sha256": source_manifest_sha256,
            "generation_manifest_digest": gen_result.generation_manifest_digest,
            "attempt_count": attempt_count,
            "submitted_count": len(packages),
            "rejected_count": rejected_count,
            "ledger_head": self._ledger.head_digest(),
            "package_digests": sorted(p.package_digest for p in packages),
        }
        packaging_manifest_digest = _digest(manifest)

        return PackagingResult(
            packages=tuple(packages),
            attempt_count=attempt_count,
            submitted_count=len(packages),
            rejected_count=rejected_count,
            ledger_head=self._ledger.head_digest(),
            packaging_manifest_digest=packaging_manifest_digest,
        )

    def _build_package(
        self,
        strategy_def: StrategyDefinition,
        candidate_id: str,
        evidence: NominationEvidenceV1,
        source_manifest_sha256: str,
    ) -> DiscoveryCandidatePackageV1:
        """Build one DiscoveryCandidatePackageV1 from a validated strategy."""
        counterhypothesis_id = f"{candidate_id}-null"

        return DiscoveryCandidatePackageV1.build(
            schema_version="aql.discoverer.candidate.v1",
            candidate_id=candidate_id,
            family_id=self._family.family_id,
            family_version=self._family.version,
            strategy_definition_digest=strategy_def.digest,
            strategy_spec=strategy_def.to_dict(),
            nomination_evidence_digest=evidence.nomination_digest,
            source_manifest_sha256=source_manifest_sha256,
            rule_grammar_version="aql.strategy-definition.grammar.v1",
            search_plan_digest=self._search_plan.plan_digest,
            counterhypothesis_id=counterhypothesis_id,
            attempt_ledger_head=self._ledger.head_digest(),
            status=CandidateStatus.PROPOSED_RESEARCH_ONLY.value,
        )
