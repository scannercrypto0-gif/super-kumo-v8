"""
Phase 1 — Contract Freeze
=========================
Versioned, immutable contracts for Strategy Discoverer V1.

Key design decisions
--------------------
* NominationEvidenceV1   — read-only evidence envelope received from Scanner.
                           While PR #227 carries unresolved P0 issues every
                           upstream input is quarantined as UNKNOWN/DEFERRED.
* EvidenceClass          — no LIVE_PIT designation in Discoverer V1.
* DiscoveryCandidatePackageV1 — all output fields carry hard NOT_* guards.

Nothing in this file imports from unmerged PRs (#46, #222, #226, #227, #228).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers (deterministic, no external deps)
# ---------------------------------------------------------------------------

def _canonical(value: object) -> bytes:
    """Deterministic JSON serialisation — identical to strategy_definition.canonical."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


# ---------------------------------------------------------------------------
# Evidence class enum — defines what we know about the nomination's provenance
# ---------------------------------------------------------------------------

class EvidenceClass(str, Enum):
    """Classification of the epistemic quality of a nomination's data provenance.

    No LIVE_PIT designation exists in Discoverer V1.  Any claim of live PIT
    from an upstream adapter must be downgraded to UNKNOWN_UNVERIFIED until
    an independent source verifier confirms it.
    """
    TEST_ONLY_SYNTHETIC          = "TEST_ONLY_SYNTHETIC"
    RETROSPECTIVE_NON_PIT_VERIFIED = "RETROSPECTIVE_NON_PIT_VERIFIED"
    UNKNOWN_UNVERIFIED           = "UNKNOWN_UNVERIFIED"


class SourceAvailability(str, Enum):
    """Availability status of the underlying source bars."""
    CONFIRMED_FINAL   = "CONFIRMED_FINAL"
    WARMUP_INCOMPLETE = "WARMUP_INCOMPLETE"
    COVERAGE_PARTIAL  = "COVERAGE_PARTIAL"
    UNKNOWN           = "UNKNOWN"
    MISSING           = "MISSING"


class ScannerQuarantineStatus(str, Enum):
    """
    Status assigned by the scanner_adapter to a raw upstream nomination.

    While PR #227 carries unresolved P0 deficiencies ALL nominations from
    a real Scanner run must be classified UNKNOWN/DEFERRED and must never
    be promoted to research-eligible status.
    """
    UNKNOWN_DEFERRED     = "UNKNOWN_DEFERRED"   # default while #227 P0 open
    TEST_ONLY_SYNTHETIC  = "TEST_ONLY_SYNTHETIC" # fixture data, no real claims
    REJECTED_BAD_SCHEMA  = "REJECTED_BAD_SCHEMA"
    REJECTED_PIT_FAILURE = "REJECTED_PIT_FAILURE"
    REJECTED_CENSUS_FAIL = "REJECTED_CENSUS_FAIL"
    REJECTED_HASH_MISMATCH = "REJECTED_HASH_MISMATCH"


# ---------------------------------------------------------------------------
# NominationEvidenceV1 — frozen evidence envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NominationEvidenceV1:
    """
    Canonical, strict evidence record for a single nomination.

    All byte-level fields are hex-encoded SHA-256 digests supplied by the
    adapter; they are never computed here from mutable dicts.  The adapter
    is responsible for fail-closed validation before constructing this object.

    Fields
    ------
    schema_version          : always "aql.discoverer.nomination-evidence.v1"
    evidence_class          : EvidenceClass enum value
    quarantine_status       : ScannerQuarantineStatus assigned by adapter
    scanner_contract_version: semantic version of the Scanner contract in use
    scanner_source_commit   : git SHA of the Scanner implementation reviewed
    scanner_envelope_sha256 : SHA-256 of the raw upstream envelope bytes
    scanner_receipt_sha256  : SHA-256 of the Scanner's own receipt/claim bytes
    source_dataset_id       : dataset identifier as known to the custody system
    source_dataset_version  : integer dataset version (≥1)
    source_raw_sha256       : SHA-256 of the raw source data bytes
    source_manifest_sha256  : SHA-256 of the dataset manifest
    universe_snapshot_sha256: SHA-256 of the universe/membership snapshot
    scan_run_id             : Scanner run identifier string
    market                  : e.g. "BINANCE_SPOT"
    symbol                  : e.g. "BTCUSDT"
    timeframe               : e.g. "1h"
    profile                 : Scanner profile name used
    cutoff_ms               : decision cutoff in milliseconds UTC (≥0)
    source_availability     : SourceAvailability enum value
    full_universe_denominator: total universe size at scan time
    eligible_selected       : subset submitted for scanning
    ineligible              : count deemed ineligible before scanning
    unscanned               : count in eligible set but not completed
    screened_rejected       : count explicitly screened out
    unknown                 : count with unknown/error outcome
    nominated               : count passing nomination criteria
    failed_attempts         : count of failed scan attempts
    omission_reason_codes   : tuple of string codes explaining any gaps
    independent_verifier_receipt_sha256: receipt from a SEPARATE trusted verifier
                              (not self-attested by the Scanner)
    nomination_digest       : SHA-256 of canonical serialisation of this record
    """

    schema_version: str
    evidence_class: str                 # EvidenceClass.value
    quarantine_status: str              # ScannerQuarantineStatus.value
    scanner_contract_version: str
    scanner_source_commit: str
    scanner_envelope_sha256: str
    scanner_receipt_sha256: str
    source_dataset_id: str
    source_dataset_version: int
    source_raw_sha256: str
    source_manifest_sha256: str
    universe_snapshot_sha256: str
    scan_run_id: str
    market: str
    symbol: str
    timeframe: str
    profile: str
    cutoff_ms: int
    source_availability: str            # SourceAvailability.value
    full_universe_denominator: int
    eligible_selected: int
    ineligible: int
    unscanned: int
    screened_rejected: int
    unknown: int
    nominated: int
    failed_attempts: int
    omission_reason_codes: tuple        # tuple of strings
    independent_verifier_receipt_sha256: str
    nomination_digest: str              # sha256 of canonical(all other fields)

    # ------------------------------------------------------------------
    # Validation guards
    # ------------------------------------------------------------------

    def __post_init__(self):
        # Schema version guard
        if self.schema_version != "aql.discoverer.nomination-evidence.v1":
            raise ValueError(f"Unexpected schema_version: {self.schema_version!r}")

        # Enum membership
        EvidenceClass(self.evidence_class)
        ScannerQuarantineStatus(self.quarantine_status)
        SourceAvailability(self.source_availability)

        # Cutoff must be non-negative integer
        if not isinstance(self.cutoff_ms, int) or self.cutoff_ms < 0:
            raise ValueError("cutoff_ms must be non-negative integer")

        # Version
        if not isinstance(self.source_dataset_version, int) or self.source_dataset_version < 1:
            raise ValueError("source_dataset_version must be positive integer")

        # Census: counts must be non-negative integers
        for attr in ("full_universe_denominator", "eligible_selected", "ineligible",
                     "unscanned", "screened_rejected", "unknown", "nominated",
                     "failed_attempts"):
            v = getattr(self, attr)
            if not isinstance(v, int) or v < 0:
                raise ValueError(f"{attr} must be non-negative integer, got {v!r}")

        # Nominated must be a subset of eligible_selected
        if self.nominated > self.eligible_selected:
            raise ValueError("nominated cannot exceed eligible_selected")

        # Eligible_selected must fit within full universe
        if self.eligible_selected > self.full_universe_denominator:
            raise ValueError("eligible_selected cannot exceed full_universe_denominator")

        # SHA-256 hex fields: 64 hex characters
        for attr in ("scanner_envelope_sha256", "scanner_receipt_sha256",
                     "source_raw_sha256", "source_manifest_sha256",
                     "universe_snapshot_sha256",
                     "independent_verifier_receipt_sha256", "nomination_digest"):
            v = getattr(self, attr)
            if not isinstance(v, str) or len(v) != 64 or not all(
                    c in "0123456789abcdef" for c in v):
                raise ValueError(f"{attr} must be 64-char lowercase hex SHA-256")

        # Verify nomination_digest commitment
        expected = _digest(self._fields_for_digest())
        if self.nomination_digest != expected:
            raise ValueError(
                f"nomination_digest mismatch: stored={self.nomination_digest} "
                f"computed={expected}"
            )

        # Omission reason codes: tuple of non-empty strings
        if not isinstance(self.omission_reason_codes, tuple):
            raise ValueError("omission_reason_codes must be a tuple")
        for code in self.omission_reason_codes:
            if not isinstance(code, str) or not code:
                raise ValueError("Each omission_reason_code must be a non-empty string")

    def _fields_for_digest(self) -> dict:
        """Return dict of all fields except nomination_digest for digest computation."""
        return {
            "schema_version": self.schema_version,
            "evidence_class": self.evidence_class,
            "quarantine_status": self.quarantine_status,
            "scanner_contract_version": self.scanner_contract_version,
            "scanner_source_commit": self.scanner_source_commit,
            "scanner_envelope_sha256": self.scanner_envelope_sha256,
            "scanner_receipt_sha256": self.scanner_receipt_sha256,
            "source_dataset_id": self.source_dataset_id,
            "source_dataset_version": self.source_dataset_version,
            "source_raw_sha256": self.source_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "universe_snapshot_sha256": self.universe_snapshot_sha256,
            "scan_run_id": self.scan_run_id,
            "market": self.market,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "profile": self.profile,
            "cutoff_ms": self.cutoff_ms,
            "source_availability": self.source_availability,
            "full_universe_denominator": self.full_universe_denominator,
            "eligible_selected": self.eligible_selected,
            "ineligible": self.ineligible,
            "unscanned": self.unscanned,
            "screened_rejected": self.screened_rejected,
            "unknown": self.unknown,
            "nominated": self.nominated,
            "failed_attempts": self.failed_attempts,
            "omission_reason_codes": list(self.omission_reason_codes),
            "independent_verifier_receipt_sha256": self.independent_verifier_receipt_sha256,
        }

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["nomination_digest"] = self.nomination_digest
        return d

    @classmethod
    def build(cls, **kwargs) -> "NominationEvidenceV1":
        """
        Convenience constructor: computes nomination_digest from all other fields.
        Caller must NOT pass nomination_digest — it is computed here.
        """
        if "nomination_digest" in kwargs:
            raise ValueError(
                "Do not pass nomination_digest to NominationEvidenceV1.build(); "
                "it is computed from the other fields."
            )
        # Compute digest over the fields that will be stored
        fields_for_digest = {
            k: (list(v) if k == "omission_reason_codes" else v)
            for k, v in kwargs.items()
        }
        nomination_digest = _digest(fields_for_digest)
        return cls(**kwargs, nomination_digest=nomination_digest)

    @classmethod
    def from_dict(cls, d: dict) -> "NominationEvidenceV1":
        data = dict(d)
        data["omission_reason_codes"] = tuple(data.get("omission_reason_codes", []))
        return cls(**data)


# ---------------------------------------------------------------------------
# DiscoveryCandidatePackageV1 — immutable research candidate output
# ---------------------------------------------------------------------------

class EvaluationStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"


class ScientificAcceptanceStatus(str, Enum):
    NOT_OBTAINED = "NOT_OBTAINED"


class ExecutionStatus(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


class HoldoutStatus(str, Enum):
    SEALED_UNOPENED = "SEALED_UNOPENED"


class FactoryRouting(str, Enum):
    NOT_CONNECTED = "NOT_CONNECTED"


class CandidateStatus(str, Enum):
    PROPOSED_RESEARCH_ONLY = "PROPOSED_RESEARCH_ONLY"
    INVALID                = "INVALID"
    REJECTED               = "REJECTED"
    DEFERRED               = "DEFERRED"


@dataclass(frozen=True)
class DiscoveryCandidatePackageV1:
    """
    Immutable research candidate output package.

    All safety flags are hard-coded constants; any attempt to set them to
    values that would indicate live authority raises ValueError in __post_init__.

    Fields
    ------
    schema_version          : "aql.discoverer.candidate.v1"
    candidate_id            : unique identifier string
    family_id               : family identifier
    family_version          : version string of the family definition
    strategy_definition_digest : sha256 digest of the StrategyDefinition payload
    strategy_spec           : full strategy spec dict (from StrategyDefinition.to_dict())
    nomination_evidence_digest : sha256 of the NominationEvidenceV1.nomination_digest
    source_manifest_sha256  : sha256 of the source/fixture manifest used
    rule_grammar_version    : version of the boolean AST grammar used
    search_plan_digest      : sha256 of the search plan that generated this candidate
    counterhypothesis_id    : paired null/counter hypothesis identifier
    attempt_ledger_head     : sha256 of the last ledger entry at time of packaging
    status                  : CandidateStatus
    evaluation_status       : ALWAYS "NOT_EVALUATED"
    scientific_acceptance   : ALWAYS "NOT_OBTAINED"
    execution_status        : ALWAYS "NOT_AUTHORIZED"
    publishable             : ALWAYS False
    delivery_authorized     : ALWAYS False
    holdout_status          : ALWAYS "SEALED_UNOPENED"
    factory_routing         : ALWAYS "NOT_CONNECTED"
    package_digest          : sha256 of canonical(all other fields)
    """

    schema_version: str
    candidate_id: str
    family_id: str
    family_version: str
    strategy_definition_digest: str
    strategy_spec: dict
    nomination_evidence_digest: str
    source_manifest_sha256: str
    rule_grammar_version: str
    search_plan_digest: str
    counterhypothesis_id: str
    attempt_ledger_head: str
    status: str                         # CandidateStatus.value
    evaluation_status: str              # MUST be NOT_EVALUATED
    scientific_acceptance: str          # MUST be NOT_OBTAINED
    execution_status: str               # MUST be NOT_AUTHORIZED
    publishable: bool                   # MUST be False
    delivery_authorized: bool           # MUST be False
    holdout_status: str                 # MUST be SEALED_UNOPENED
    factory_routing: str                # MUST be NOT_CONNECTED
    package_digest: str

    def __post_init__(self):
        if self.schema_version != "aql.discoverer.candidate.v1":
            raise ValueError(f"Bad schema_version: {self.schema_version!r}")

        CandidateStatus(self.status)

        # Hard safety guards — these can NEVER be overridden
        if self.evaluation_status != EvaluationStatus.NOT_EVALUATED.value:
            raise ValueError("evaluation_status must be NOT_EVALUATED")
        if self.scientific_acceptance != ScientificAcceptanceStatus.NOT_OBTAINED.value:
            raise ValueError("scientific_acceptance must be NOT_OBTAINED")
        if self.execution_status != ExecutionStatus.NOT_AUTHORIZED.value:
            raise ValueError("execution_status must be NOT_AUTHORIZED")
        if self.publishable is not False:
            raise ValueError("publishable must be False")
        if self.delivery_authorized is not False:
            raise ValueError("delivery_authorized must be False")
        if self.holdout_status != HoldoutStatus.SEALED_UNOPENED.value:
            raise ValueError("holdout_status must be SEALED_UNOPENED")
        if self.factory_routing != FactoryRouting.NOT_CONNECTED.value:
            raise ValueError("factory_routing must be NOT_CONNECTED")

        # SHA fields
        for attr in ("strategy_definition_digest", "nomination_evidence_digest",
                     "source_manifest_sha256", "search_plan_digest",
                     "attempt_ledger_head", "package_digest"):
            v = getattr(self, attr)
            if not isinstance(v, str) or len(v) != 64 or not all(
                    c in "0123456789abcdef" for c in v):
                raise ValueError(f"{attr} must be 64-char lowercase hex SHA-256")

        # Verify package_digest
        expected = _digest(self._fields_for_digest())
        if self.package_digest != expected:
            raise ValueError(
                f"package_digest mismatch: stored={self.package_digest} "
                f"computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "family_id": self.family_id,
            "family_version": self.family_version,
            "strategy_definition_digest": self.strategy_definition_digest,
            "strategy_spec": self.strategy_spec,
            "nomination_evidence_digest": self.nomination_evidence_digest,
            "source_manifest_sha256": self.source_manifest_sha256,
            "rule_grammar_version": self.rule_grammar_version,
            "search_plan_digest": self.search_plan_digest,
            "counterhypothesis_id": self.counterhypothesis_id,
            "attempt_ledger_head": self.attempt_ledger_head,
            "status": self.status,
            "evaluation_status": self.evaluation_status,
            "scientific_acceptance": self.scientific_acceptance,
            "execution_status": self.execution_status,
            "publishable": self.publishable,
            "delivery_authorized": self.delivery_authorized,
            "holdout_status": self.holdout_status,
            "factory_routing": self.factory_routing,
        }

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["package_digest"] = self.package_digest
        return d

    @classmethod
    def build(cls, **kwargs) -> "DiscoveryCandidatePackageV1":
        """
        Convenience constructor: forces all safety flags and computes package_digest.
        Caller must not pass the safety-flag fields or package_digest.
        """
        protected = ("evaluation_status", "scientific_acceptance", "execution_status",
                     "publishable", "delivery_authorized", "holdout_status",
                     "factory_routing", "package_digest")
        for p in protected:
            if p in kwargs:
                raise ValueError(f"Field {p!r} is hard-coded; do not pass it to build()")

        kwargs["evaluation_status"] = EvaluationStatus.NOT_EVALUATED.value
        kwargs["scientific_acceptance"] = ScientificAcceptanceStatus.NOT_OBTAINED.value
        kwargs["execution_status"] = ExecutionStatus.NOT_AUTHORIZED.value
        kwargs["publishable"] = False
        kwargs["delivery_authorized"] = False
        kwargs["holdout_status"] = HoldoutStatus.SEALED_UNOPENED.value
        kwargs["factory_routing"] = FactoryRouting.NOT_CONNECTED.value

        # Build a temporary instance fields dict (without package_digest) for hashing
        fields_for_digest = {k: v for k, v in kwargs.items()}
        package_digest = _digest(fields_for_digest)
        return cls(**kwargs, package_digest=package_digest)

    @classmethod
    def from_dict(cls, d: dict) -> "DiscoveryCandidatePackageV1":
        return cls(**d)
