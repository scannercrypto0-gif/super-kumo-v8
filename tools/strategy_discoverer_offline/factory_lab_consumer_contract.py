"""
Discoverer → Factory Lab Research Consumer Contract  (Proposed, Read-Only)
==========================================================================
Schema:  aql.discoverer.factory-research-consumer-proposal.v1

PURPOSE
-------
This module defines the **proposed** intake object that the Discoverer
pipeline would hand off to Factory Lab for offline research evaluation.
It maps every sealed Discoverer artefact to Factory Lab's experiment
intake surface, without connecting to or modifying any Factory module.

STATUS: PROPOSED — FACTORY CONSUMER NOT YET CONNECTED
  factory_consumer_connected = False
  evaluation_status          = NOT_EVALUATED

This file is READ-ONLY from the perspective of Factory C (PR #260).
Factory C does not import from this module.  When Factory C implements
its consumer side, it will produce a ``FactoryResearchConsumerReceiptV1``
with ``factory_consumer_connected = True`` and
``evaluation_status ≠ NOT_EVALUATED``.

INPUTS MAPPED
-------------
1. ``DiscoveryCandidatePackageV1``  — sealed candidate (from PR #230)
2. ``FactoryLabReceiptV1``           — bridge routing receipt (this PR)
3. ``NominationEvidenceV1``          — nomination evidence (from PR #230)
4. ``LabAttemptLogV1`` reference     — log census at intake time
5. Ledger reference                  — string cross-reference to DiscovererLedger
6. ``LedgerMembershipProofV1``       — optional; fail-closed NOT_VERIFIED if absent

HARD CONSTRAINTS (never relaxed in this module)
  - Holdout:              NEVER accessed
  - Real execution:       NEVER initiated
  - Profitability eval:   NEVER performed
  - Paper upgrade:        NEVER triggered
  - Work module:          NEVER imported
  - Live market data:     NEVER used
  - Factory C files:      NOT modified

KNOWN LIMITATION — PARTIAL LEDGER BINDING
------------------------------------------
``ledger_attempt_id`` is recorded in ``FactoryLabReceiptV1`` but has no
cryptographic hash sealed inside ``DiscoveryCandidatePackageV1``.  The
bridge can verify that ``package.attempt_ledger_head`` matches the
caller-supplied ledger head (binding check b in route()), but it cannot
prove that ``ledger_attempt_id`` is a real membership entry in the
DiscovererLedger without importing that module (which would violate
isolation).  Therefore:

  ledger_membership_status = NOT_VERIFIED   (fail-closed default)

A future ``LedgerMembershipProofV1`` carrying a signed membership
assertion from the ledger itself could upgrade this to VERIFIED, but that
integration is deferred and outside the scope of this PR.

COORDINATION WITH FACTORY C (PR #260)
--------------------------------------
Factory C's operational path  Scanner → Secretary → Paper  does NOT wait
for Discoverer.  The two pipelines are independent.  This consumer
contract is a **future intake point** that Factory C may choose to
implement.  See coordination comment on PR #260 for details.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers (self-contained — no import from factory_lab_contracts to avoid
# circular coupling)
# ---------------------------------------------------------------------------

def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


_HEX64 = set("0123456789abcdef")


def _assert_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _HEX64:
        raise ValueError(f"{field_name} must be a 64-char lowercase hex SHA-256")


# ---------------------------------------------------------------------------
# LedgerMembershipStatus
# ---------------------------------------------------------------------------

class LedgerMembershipStatus(str, Enum):
    """
    Verification status for ledger_attempt_id membership.

    VERIFIED     : A LedgerMembershipProofV1 was supplied and validated.
    NOT_VERIFIED : No proof supplied or proof failed; fail-closed default.
    """
    VERIFIED     = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"


# ---------------------------------------------------------------------------
# FactoryConsumerConnectionStatus
# ---------------------------------------------------------------------------

class FactoryConsumerConnectionStatus(str, Enum):
    """
    Whether Factory Lab has connected and accepted this intake package.

    FACTORY_CONSUMER_NOT_CONNECTED : Default; set by Discoverer.
    FACTORY_CONSUMER_CONNECTED     : Set by Factory C when it acknowledges.
    """
    FACTORY_CONSUMER_NOT_CONNECTED = "FACTORY_CONSUMER_NOT_CONNECTED"
    FACTORY_CONSUMER_CONNECTED     = "FACTORY_CONSUMER_CONNECTED"


# ---------------------------------------------------------------------------
# ResearchEvaluationStatus
# ---------------------------------------------------------------------------

class ResearchEvaluationStatus(str, Enum):
    """
    Evaluation status assigned by Factory Lab.

    NOT_EVALUATED         : Default; Discoverer has not evaluated the strategy.
    PENDING_LAB_INTAKE    : Factory C acknowledged intake; not yet evaluated.
    EVALUATED_PASS        : Factory evaluation completed; strategy passed.
    EVALUATED_FAIL        : Factory evaluation completed; strategy failed.
    EVALUATION_ERROR      : Factory encountered an error during evaluation.
    """
    NOT_EVALUATED      = "NOT_EVALUATED"
    PENDING_LAB_INTAKE = "PENDING_LAB_INTAKE"
    EVALUATED_PASS     = "EVALUATED_PASS"
    EVALUATED_FAIL     = "EVALUATED_FAIL"
    EVALUATION_ERROR   = "EVALUATION_ERROR"


# ---------------------------------------------------------------------------
# LedgerMembershipProofV1 — optional; fail-closed if absent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LedgerMembershipProofV1:
    """
    Optional proof that ``ledger_attempt_id`` is a real entry in the
    DiscovererLedger at the moment ``ledger_head_digest`` was sealed.

    This is a **proposed structure** only.  The DiscovererLedger module
    (ledger.py from PR #230) is not imported here.  A real implementation
    would require the ledger to sign a membership assertion that includes:
      - ledger_reference   (which ledger)
      - ledger_head_digest (at which head)
      - ledger_attempt_id  (the entry being proved)
      - package_digest     (the candidate sealed at that entry)

    Without this object, ``ledger_membership_status = NOT_VERIFIED``.

    schema_version      : "aql.discoverer.ledger-membership-proof.v1"
    ledger_reference    : string identifier of the DiscovererLedger
    ledger_head_digest  : ledger head when proof was generated (sha256)
    ledger_attempt_id   : the attempt whose membership is proved
    package_digest      : sha256 of DiscoveryCandidatePackageV1 at that entry
    proof_digest        : sha256 of canonical(all fields except proof_digest)

    LIMITATION: This module cannot cryptographically validate the proof
    without importing the ledger.  The receiver (Factory C) is responsible
    for validating proof_digest and the signed assertion when it implements
    this intake.
    """
    SCHEMA_VERSION = "aql.discoverer.ledger-membership-proof.v1"

    schema_version:    str
    ledger_reference:  str
    ledger_head_digest: str
    ledger_attempt_id: str
    package_digest:    str
    proof_digest:      str

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(f"Bad schema_version: {self.schema_version!r}")
        for attr in ("ledger_head_digest", "package_digest", "proof_digest"):
            _assert_sha256(getattr(self, attr), attr)
        if not self.ledger_reference.strip():
            raise ValueError("ledger_reference must be non-empty")
        if not self.ledger_attempt_id.strip():
            raise ValueError("ledger_attempt_id must be non-empty")
        expected = _digest(self._fields_for_digest())
        if self.proof_digest != expected:
            raise ValueError(
                f"proof_digest mismatch: stored={self.proof_digest} "
                f"computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "schema_version":    self.schema_version,
            "ledger_reference":  self.ledger_reference,
            "ledger_head_digest": self.ledger_head_digest,
            "ledger_attempt_id": self.ledger_attempt_id,
            "package_digest":    self.package_digest,
        }

    @classmethod
    def build(
        cls,
        *,
        ledger_reference: str,
        ledger_head_digest: str,
        ledger_attempt_id: str,
        package_digest: str,
    ) -> "LedgerMembershipProofV1":
        """Build a proof object (without real ledger validation)."""
        fields = {
            "schema_version":    cls.SCHEMA_VERSION,
            "ledger_reference":  ledger_reference,
            "ledger_head_digest": ledger_head_digest,
            "ledger_attempt_id": ledger_attempt_id,
            "package_digest":    package_digest,
        }
        proof_digest = _digest(fields)
        return cls(**fields, proof_digest=proof_digest)

    def to_dict(self) -> dict:
        return {
            "schema_version":    self.schema_version,
            "ledger_reference":  self.ledger_reference,
            "ledger_head_digest": self.ledger_head_digest,
            "ledger_attempt_id": self.ledger_attempt_id,
            "package_digest":    self.package_digest,
            "proof_digest":      self.proof_digest,
        }


# ---------------------------------------------------------------------------
# DiscovererResearchIntakeV1 — the proposed intake object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscovererResearchIntakeV1:
    """
    Proposed intake object: maps sealed Discoverer artefacts to Factory
    Lab's research experiment intake.

    This object is produced by the Discoverer pipeline and held as a
    read-only hand-off record.  Factory C, when it implements the consumer
    side, will read ``intake_digest`` and all cross-reference digests to
    confirm it is consuming exactly the artefacts the Discoverer sealed.

    MAPPING TO FACTORY LAB INTAKE
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Discoverer field                   → Factory Lab intake field
    ------------------------------------------------------------------
    candidate_id                       → experiment_id (research run)
    strategy_definition_digest         → strategy_digest (which strategy)
    family_id                          → strategy_family (taxonomy)
    nomination_evidence_digest         → evidence_digest (universe counts)
    receipt_digest                     → routing_provenance_digest
    attempt_log_head_digest            → attempt_census_digest
    ledger_head_digest                 → ledger_state_at_packaging_digest
    ledger_attempt_id                  → ledger_cross_reference (attested)
    ledger_membership_status           → NOT_VERIFIED | VERIFIED
    ------------------------------------------------------------------

    factory_consumer_connected : always False from Discoverer side
    evaluation_status          : always NOT_EVALUATED from Discoverer side

    SCHEMA: "aql.discoverer.factory-research-consumer-proposal.v1"

    Fields
    ------
    schema_version            : "aql.discoverer.factory-research-consumer-proposal.v1"
    candidate_id              : from DiscoveryCandidatePackageV1
    strategy_definition_digest: sha256 of StrategyDefinition (from package)
    family_id                 : strategy family identifier
    nomination_evidence_digest: sha256 of NominationEvidenceV1 (from package)
    package_digest            : sha256 of DiscoveryCandidatePackageV1
    receipt_digest            : sha256 of FactoryLabReceiptV1 (bridge receipt)
    attempt_log_head_digest   : sha256 of LabAttemptLogV1 head at intake time
    ledger_reference          : string identifier of the DiscovererLedger
    ledger_head_digest        : sha256 of ledger head at packaging time
    ledger_attempt_id         : caller-attested ledger cross-reference
    ledger_membership_status  : VERIFIED | NOT_VERIFIED (fail-closed)
    membership_proof_digest   : sha256 of LedgerMembershipProofV1, or null
    factory_consumer_connected: MUST be False (Discoverer side)
    evaluation_status         : MUST be NOT_EVALUATED (Discoverer side)
    holdout_accessed          : MUST be False
    real_execution_initiated  : MUST be False
    work_module_imported      : MUST be False
    created_at_ns             : wall-clock nanoseconds when intake was created
    intake_digest             : sha256 of canonical(all fields except intake_digest)
    """

    SCHEMA_VERSION = "aql.discoverer.factory-research-consumer-proposal.v1"
    _NULL_DIGEST   = "0" * 64

    schema_version:             str
    candidate_id:               str
    strategy_definition_digest: str
    family_id:                  str
    nomination_evidence_digest: str
    package_digest:             str
    receipt_digest:             str
    attempt_log_head_digest:    str
    ledger_reference:           str
    ledger_head_digest:         str
    ledger_attempt_id:          str
    ledger_membership_status:   str    # LedgerMembershipStatus value
    membership_proof_digest:    Optional[str]  # sha256 or None
    factory_consumer_connected: str    # FactoryConsumerConnectionStatus
    evaluation_status:          str    # ResearchEvaluationStatus
    holdout_accessed:           bool   # MUST be False
    real_execution_initiated:   bool   # MUST be False
    work_module_imported:       bool   # MUST be False
    created_at_ns:              int
    intake_digest:              str

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(f"Bad schema_version: {self.schema_version!r}")

        # Validate enum fields
        LedgerMembershipStatus(self.ledger_membership_status)
        FactoryConsumerConnectionStatus(self.factory_consumer_connected)
        ResearchEvaluationStatus(self.evaluation_status)

        # Discoverer-side invariants — these are set by the Discoverer;
        # Factory C sets its own values when it produces a receipt.
        if self.factory_consumer_connected != FactoryConsumerConnectionStatus.FACTORY_CONSUMER_NOT_CONNECTED.value:
            raise ValueError(
                "factory_consumer_connected must be FACTORY_CONSUMER_NOT_CONNECTED "
                "(Discoverer side); Factory C sets its own value in its receipt"
            )
        if self.evaluation_status != ResearchEvaluationStatus.NOT_EVALUATED.value:
            raise ValueError(
                "evaluation_status must be NOT_EVALUATED (Discoverer side); "
                "Factory C sets its own value in its receipt"
            )

        # Hard safety guards
        if self.holdout_accessed is not False:
            raise ValueError("holdout_accessed must be False")
        if self.real_execution_initiated is not False:
            raise ValueError("real_execution_initiated must be False")
        if self.work_module_imported is not False:
            raise ValueError("work_module_imported must be False")

        # SHA fields
        sha_fields = [
            "strategy_definition_digest",
            "nomination_evidence_digest",
            "package_digest",
            "receipt_digest",
            "attempt_log_head_digest",
            "ledger_head_digest",
            "intake_digest",
        ]
        for attr in sha_fields:
            _assert_sha256(getattr(self, attr), attr)

        # membership_proof_digest is optional but must be valid sha256 if present
        if self.membership_proof_digest is not None:
            _assert_sha256(self.membership_proof_digest, "membership_proof_digest")

        # Consistency: if membership_proof_digest is present, status must be VERIFIED
        if (self.membership_proof_digest is not None
                and self.ledger_membership_status != LedgerMembershipStatus.VERIFIED.value):
            raise ValueError(
                "membership_proof_digest is set but ledger_membership_status is not VERIFIED"
            )
        if (self.membership_proof_digest is None
                and self.ledger_membership_status == LedgerMembershipStatus.VERIFIED.value):
            raise ValueError(
                "ledger_membership_status is VERIFIED but membership_proof_digest is None"
            )

        if self.created_at_ns < 0:
            raise ValueError("created_at_ns must be non-negative")

        # Verify intake_digest
        expected = _digest(self._fields_for_digest())
        if self.intake_digest != expected:
            raise ValueError(
                f"intake_digest mismatch: stored={self.intake_digest} "
                f"computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "schema_version":             self.schema_version,
            "candidate_id":               self.candidate_id,
            "strategy_definition_digest": self.strategy_definition_digest,
            "family_id":                  self.family_id,
            "nomination_evidence_digest": self.nomination_evidence_digest,
            "package_digest":             self.package_digest,
            "receipt_digest":             self.receipt_digest,
            "attempt_log_head_digest":    self.attempt_log_head_digest,
            "ledger_reference":           self.ledger_reference,
            "ledger_head_digest":         self.ledger_head_digest,
            "ledger_attempt_id":          self.ledger_attempt_id,
            "ledger_membership_status":   self.ledger_membership_status,
            "membership_proof_digest":    self.membership_proof_digest,
            "factory_consumer_connected": self.factory_consumer_connected,
            "evaluation_status":          self.evaluation_status,
            "holdout_accessed":           self.holdout_accessed,
            "real_execution_initiated":   self.real_execution_initiated,
            "work_module_imported":       self.work_module_imported,
            "created_at_ns":              self.created_at_ns,
        }

    def to_dict(self) -> dict:
        d = dict(self._fields_for_digest())
        d["intake_digest"] = self.intake_digest
        return d

    @classmethod
    def build(
        cls,
        *,
        candidate_id:               str,
        strategy_definition_digest: str,
        family_id:                  str,
        nomination_evidence_digest: str,
        package_digest:             str,
        receipt_digest:             str,
        attempt_log_head_digest:    str,
        ledger_reference:           str,
        ledger_head_digest:         str,
        ledger_attempt_id:          str,
        membership_proof:           Optional[LedgerMembershipProofV1] = None,
    ) -> "DiscovererResearchIntakeV1":
        """
        Build a sealed intake object.

        ``membership_proof``, if supplied, sets ledger_membership_status=VERIFIED
        and records membership_proof_digest.  If absent (default), status is
        NOT_VERIFIED (fail-closed).

        All other Discoverer-side fields are set automatically:
          factory_consumer_connected = FACTORY_CONSUMER_NOT_CONNECTED
          evaluation_status          = NOT_EVALUATED
          holdout_accessed           = False
          real_execution_initiated   = False
          work_module_imported       = False
        """
        if membership_proof is not None:
            membership_status = LedgerMembershipStatus.VERIFIED.value
            proof_digest: Optional[str] = membership_proof.proof_digest
        else:
            membership_status = LedgerMembershipStatus.NOT_VERIFIED.value
            proof_digest = None

        created_at_ns = time.time_ns()

        fields = {
            "schema_version":             cls.SCHEMA_VERSION,
            "candidate_id":               candidate_id,
            "strategy_definition_digest": strategy_definition_digest,
            "family_id":                  family_id,
            "nomination_evidence_digest": nomination_evidence_digest,
            "package_digest":             package_digest,
            "receipt_digest":             receipt_digest,
            "attempt_log_head_digest":    attempt_log_head_digest,
            "ledger_reference":           ledger_reference,
            "ledger_head_digest":         ledger_head_digest,
            "ledger_attempt_id":          ledger_attempt_id,
            "ledger_membership_status":   membership_status,
            "membership_proof_digest":    proof_digest,
            "factory_consumer_connected": FactoryConsumerConnectionStatus.FACTORY_CONSUMER_NOT_CONNECTED.value,
            "evaluation_status":          ResearchEvaluationStatus.NOT_EVALUATED.value,
            "holdout_accessed":           False,
            "real_execution_initiated":   False,
            "work_module_imported":       False,
            "created_at_ns":              created_at_ns,
        }
        fields["intake_digest"] = _digest({k: v for k, v in fields.items()})
        return cls(**fields)


# ---------------------------------------------------------------------------
# build_research_intake() — convenience helper
# ---------------------------------------------------------------------------

def build_research_intake(
    *,
    package,            # DiscoveryCandidatePackageV1
    receipt,            # FactoryLabReceiptV1
    attempt_log_head_digest: str,
    ledger_reference:        str,
    membership_proof:        Optional[LedgerMembershipProofV1] = None,
) -> DiscovererResearchIntakeV1:
    """
    Convenience function: build a ``DiscovererResearchIntakeV1`` from a
    sealed ``DiscoveryCandidatePackageV1`` and its ``FactoryLabReceiptV1``.

    Parameters
    ----------
    package                 : DiscoveryCandidatePackageV1 (from PR #230)
    receipt                 : FactoryLabReceiptV1 (from bridge routing)
    attempt_log_head_digest : LabAttemptLogV1.head_digest at intake time
    ledger_reference        : string identifier of the DiscovererLedger
    membership_proof        : optional LedgerMembershipProofV1; default None

    The receipt's ``routing_status`` must be ROUTED_SYNTHETIC_ONLY.
    Any other status means the candidate was not admitted and cannot
    form a valid research intake.
    """
    if receipt.routing_status != "ROUTED_SYNTHETIC_ONLY":
        raise ValueError(
            f"Cannot build research intake from receipt with "
            f"routing_status={receipt.routing_status!r}; "
            f"only ROUTED_SYNTHETIC_ONLY candidates are eligible"
        )
    # Cross-verify that the receipt references the same package
    if receipt.package_digest != package.package_digest:
        raise ValueError(
            f"Receipt package_digest does not match package: "
            f"receipt={receipt.package_digest[:16]}… "
            f"package={package.package_digest[:16]}…"
        )

    return DiscovererResearchIntakeV1.build(
        candidate_id=package.candidate_id,
        strategy_definition_digest=package.strategy_definition_digest,
        family_id=package.family_id,
        nomination_evidence_digest=package.nomination_evidence_digest,
        package_digest=package.package_digest,
        receipt_digest=receipt.receipt_digest,
        attempt_log_head_digest=attempt_log_head_digest,
        ledger_reference=ledger_reference,
        ledger_head_digest=receipt.ledger_head_digest,
        ledger_attempt_id=receipt.ledger_attempt_id,
        membership_proof=membership_proof,
    )


# ---------------------------------------------------------------------------
# Canonical schema reference (read-only)
# ---------------------------------------------------------------------------

SCHEMA_ID = "aql.discoverer.factory-research-consumer-proposal.v1"

SCHEMA_EXAMPLE = {
    "schema": SCHEMA_ID,
    "status": "PROPOSED — FACTORY CONSUMER NOT CONNECTED",
    "safety_invariants": {
        "factory_consumer_connected": "FACTORY_CONSUMER_NOT_CONNECTED",
        "evaluation_status":          "NOT_EVALUATED",
        "holdout_accessed":           False,
        "real_execution_initiated":   False,
        "work_module_imported":       False,
    },
    "ledger_membership_limitation": (
        "ledger_attempt_id has no cryptographic hash sealed in "
        "DiscoveryCandidatePackageV1.  The bridge verifies "
        "attempt_ledger_head (binding check b) but cannot prove "
        "membership in DiscovererLedger without importing it.  "
        "Default: ledger_membership_status = NOT_VERIFIED (fail-closed).  "
        "A future LedgerMembershipProofV1 integration can upgrade to VERIFIED."
    ),
    "factory_c_coordination": (
        "Factory C (PR #260) operational path Scanner→Secretary→Paper "
        "does NOT wait for Discoverer.  This contract is a future intake "
        "point only.  See PR #260 coordination comment."
    ),
    "intake_fields": {
        "candidate_id":               "<from DiscoveryCandidatePackageV1>",
        "strategy_definition_digest": "<sha256 of StrategyDefinition>",
        "family_id":                  "<strategy family>",
        "nomination_evidence_digest": "<sha256 of NominationEvidenceV1>",
        "package_digest":             "<sha256 of DiscoveryCandidatePackageV1>",
        "receipt_digest":             "<sha256 of FactoryLabReceiptV1>",
        "attempt_log_head_digest":    "<LabAttemptLogV1.head_digest at intake>",
        "ledger_reference":           "<DiscovererLedger identifier>",
        "ledger_head_digest":         "<ledger head at packaging time>",
        "ledger_attempt_id":          "<caller-attested; NOT_VERIFIED by default>",
        "ledger_membership_status":   "NOT_VERIFIED",
        "membership_proof_digest":    None,
        "intake_digest":              "<sha256 of canonical(all above fields)>",
    },
}
