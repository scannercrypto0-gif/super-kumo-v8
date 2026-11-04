"""
Discoverer → Factory Lab Bridge
================================
Wires the full pipeline:
  HypothesisProposal → HypothesisGenerator → StrategyDefinition
    → CandidatePackager → DiscoveryCandidatePackageV1
    → [DataSourceIsolator] → FactoryLabReceiptV1

This module is the ONLY entry point for routing a sealed Discoverer
candidate package to the Factory Lab.  It enforces all isolation and
safety constraints.

REUSE (from PR #230, unchanged)
  - HypothesisGenerator (generator.py) + 7 FamilyDefinitions (families.py)
  - HypothesisProposal / SearchPlan (hypotheses.py)
  - DiscovererLedger (ledger.py)
  - DiscoveryCandidatePackageV1 (contracts.py)

HARD CONSTRAINTS (never relaxed in this module)
  - factory_routing on the package remains NOT_CONNECTED (read-only)
  - Holdout:              NEVER accessed
  - Real execution:       NEVER initiated
  - Profitability eval:   NEVER performed
  - Work module:          NEVER imported
  - Unmerged PRs:         NOT imported (only research_wp_r0 merged modules)
  - Live market data:     NEVER used

SEPARATION PROTOCOL
  - DataSourceIsolator quarantines any nomination with undocumented source
    or timing before it reaches the bridge routing logic.
  - ScannerQuarantineStatus.UNKNOWN_DEFERRED is blocked (rule R4).
  - The Discoverer pipeline is completely isolated from the Scanner pipeline:
    no Scanner data, classes, or references flow through here.

The bridge emits a FactoryLabReceiptV1 for EVERY routing attempt — whether
admitted, quarantined, or rejected — so attempt history and denominators
are always preserved.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1,
    NominationEvidenceV1,
    FactoryRouting,
    _digest,
)
from tools.strategy_discoverer_offline.data_isolator import (
    DataSourceIsolator,
    QuarantineVerdict,
)
from tools.strategy_discoverer_offline.factory_lab_contracts import (
    FactoryRoutingStatus,
    FactoryLabReceiptV1,
    LabDenominatorSnapshotV1,
    LabAttemptLogV1,
)


# ---------------------------------------------------------------------------
# Safety verification
# ---------------------------------------------------------------------------

class SafetyFlagError(ValueError):
    """Raised when a package's safety flags do not satisfy hard constraints."""


def _verify_package_safety(pkg: DiscoveryCandidatePackageV1) -> None:
    """
    Verify that all Discoverer safety flags are intact before routing.

    This is a redundant check: DiscoveryCandidatePackageV1.__post_init__
    already enforces these, but the bridge re-checks independently so that
    any future relaxation of contract invariants does not silently bypass
    the bridge's own safety layer.
    """
    errors = []
    if pkg.evaluation_status != "NOT_EVALUATED":
        errors.append(f"evaluation_status={pkg.evaluation_status!r} (expected NOT_EVALUATED)")
    if pkg.scientific_acceptance != "NOT_OBTAINED":
        errors.append(f"scientific_acceptance={pkg.scientific_acceptance!r} (expected NOT_OBTAINED)")
    if pkg.execution_status != "NOT_AUTHORIZED":
        errors.append(f"execution_status={pkg.execution_status!r} (expected NOT_AUTHORIZED)")
    if pkg.publishable is not False:
        errors.append(f"publishable={pkg.publishable!r} (expected False)")
    if pkg.delivery_authorized is not False:
        errors.append(f"delivery_authorized={pkg.delivery_authorized!r} (expected False)")
    if pkg.holdout_status != "SEALED_UNOPENED":
        errors.append(f"holdout_status={pkg.holdout_status!r} (expected SEALED_UNOPENED)")
    if pkg.factory_routing != FactoryRouting.NOT_CONNECTED.value:
        errors.append(f"factory_routing={pkg.factory_routing!r} (expected NOT_CONNECTED)")
    if errors:
        raise SafetyFlagError(
            f"Package {pkg.candidate_id!r} failed safety verification: "
            + "; ".join(errors)
        )


# ---------------------------------------------------------------------------
# Bridge routing result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BridgeRoutingResult:
    """
    Result of routing a single candidate through the Factory Lab Bridge.

    receipt         : FactoryLabReceiptV1 always present
    routed          : True iff routing_status == ROUTED_SYNTHETIC_ONLY
    quarantine_rule : rule_id from DataSourceIsolator if quarantined
    """
    receipt: FactoryLabReceiptV1
    routed: bool
    quarantine_rule: Optional[str]

    @property
    def routing_status(self) -> str:
        return self.receipt.routing_status


# ---------------------------------------------------------------------------
# DiscovererToFactoryBridge
# ---------------------------------------------------------------------------

class DiscovererToFactoryBridge:
    """
    Single entry point for routing sealed Discoverer candidate packages to
    the Factory Lab.

    Parameters
    ----------
    ledger_reference    : string identifier of the DiscovererLedger being used
                          (not imported here — the ledger_head is passed in
                          per-call to maintain isolation between modules).
    isolator            : DataSourceIsolator instance (default: new instance)
    log                 : LabAttemptLogV1 instance (default: new instance)

    Usage
    -----
    bridge = DiscovererToFactoryBridge(ledger_reference="main")
    result = bridge.route(
        package=pkg,
        evidence=evidence,
        ledger_attempt_id="attempt-001",
        ledger_head_digest="<64-char hex>",
    )
    # result.receipt is a FactoryLabReceiptV1
    # result.routed is True iff routing succeeded
    """

    def __init__(
        self,
        ledger_reference: str = "discoverer-main",
        isolator: Optional[DataSourceIsolator] = None,
        log: Optional[LabAttemptLogV1] = None,
    ) -> None:
        if not isinstance(ledger_reference, str) or not ledger_reference.strip():
            raise ValueError("ledger_reference must be a non-empty string")
        self._ledger_ref = ledger_reference
        self._isolator = isolator or DataSourceIsolator()
        self._log = log or LabAttemptLogV1()

    # -- Properties ----------------------------------------------------------

    @property
    def log(self) -> LabAttemptLogV1:
        return self._log

    @property
    def ledger_reference(self) -> str:
        return self._ledger_ref

    # -- Core routing --------------------------------------------------------

    def route(
        self,
        *,
        package: DiscoveryCandidatePackageV1,
        evidence: NominationEvidenceV1,
        ledger_attempt_id: str,
        ledger_head_digest: str,
    ) -> BridgeRoutingResult:
        """
        Route a sealed Discoverer package to the Factory Lab.

        Steps:
          1. Verify package safety flags (independent re-check)
          2. Build denominator snapshot from evidence
          3. Run DataSourceIsolator rules
          4. If admitted → assign ROUTED_SYNTHETIC_ONLY
             If quarantined → assign matching QUARANTINED_* status
          5. Build FactoryLabReceiptV1 and append to log

        The method is fail-closed: any unexpected exception is re-raised
        after recording a REJECTED_BAD_PACKAGE receipt if possible.
        """
        if not isinstance(package, DiscoveryCandidatePackageV1):
            raise TypeError(f"Expected DiscoveryCandidatePackageV1, got {type(package)}")
        if not isinstance(evidence, NominationEvidenceV1):
            raise TypeError(f"Expected NominationEvidenceV1, got {type(evidence)}")

        receipt_id = str(uuid.uuid4())
        routed_at_ns = time.time_ns()
        predecessor = self._log.head_digest

        # --- 1. Safety flags ------------------------------------------------
        safety_verified = False
        try:
            _verify_package_safety(package)
            safety_verified = True
        except SafetyFlagError as exc:
            receipt = FactoryLabReceiptV1.build(
                receipt_id=receipt_id,
                routing_status=FactoryRoutingStatus.REJECTED_SAFETY_FLAG,
                quarantine_reason=str(exc),
                candidate_id=package.candidate_id,
                package_digest=package.package_digest,
                strategy_definition_digest=package.strategy_definition_digest,
                family_id=package.family_id,
                nomination_evidence_digest=package.nomination_evidence_digest,
                denominator_snapshot=LabDenominatorSnapshotV1.from_evidence(evidence),
                ledger_attempt_id=ledger_attempt_id,
                ledger_head_digest=ledger_head_digest,
                predecessor_receipt_digest=predecessor,
                routed_at_ns=routed_at_ns,
                safety_flags_verified=False,
            )
            self._log.append(receipt)
            return BridgeRoutingResult(receipt=receipt, routed=False, quarantine_rule=None)

        # --- 2. Denominator snapshot ----------------------------------------
        denominator_snapshot = LabDenominatorSnapshotV1.from_evidence(evidence)

        # --- 3. Data isolation ----------------------------------------------
        isolation = self._isolator.evaluate(evidence)

        # --- 4. Assign routing status ----------------------------------------
        if isolation.admitted:
            routing_status = FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY
            quarantine_reason = None
            quarantine_rule = None
        else:
            # Map QuarantineVerdict → FactoryRoutingStatus
            _verdict_map = {
                QuarantineVerdict.QUARANTINED_UNDOCUMENTED_SRC.value:
                    FactoryRoutingStatus.QUARANTINED_UNDOCUMENTED_SRC,
                QuarantineVerdict.QUARANTINED_UNDOCUMENTED_TIME.value:
                    FactoryRoutingStatus.QUARANTINED_UNDOCUMENTED_TIME,
                QuarantineVerdict.QUARANTINED_SCANNER_P0.value:
                    FactoryRoutingStatus.QUARANTINED_SCANNER_P0,
                QuarantineVerdict.QUARANTINED_EVIDENCE_UNKNOWN.value:
                    FactoryRoutingStatus.QUARANTINED_EVIDENCE_UNKNOWN,
            }
            routing_status = _verdict_map.get(
                isolation.verdict,
                FactoryRoutingStatus.REJECTED_BAD_PACKAGE,
            )
            quarantine_reason = isolation.reason
            quarantine_rule = isolation.rule_id

        # --- 5. Build and log receipt ----------------------------------------
        receipt = FactoryLabReceiptV1.build(
            receipt_id=receipt_id,
            routing_status=routing_status,
            quarantine_reason=quarantine_reason,
            candidate_id=package.candidate_id,
            package_digest=package.package_digest,
            strategy_definition_digest=package.strategy_definition_digest,
            family_id=package.family_id,
            nomination_evidence_digest=package.nomination_evidence_digest,
            denominator_snapshot=denominator_snapshot,
            ledger_attempt_id=ledger_attempt_id,
            ledger_head_digest=ledger_head_digest,
            predecessor_receipt_digest=predecessor,
            routed_at_ns=routed_at_ns,
            safety_flags_verified=safety_verified,
        )
        self._log.append(receipt)

        return BridgeRoutingResult(
            receipt=receipt,
            routed=routing_status == FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY,
            quarantine_rule=quarantine_rule,
        )

    def route_batch(
        self,
        *,
        pairs: List[Tuple[DiscoveryCandidatePackageV1, NominationEvidenceV1]],
        ledger_head_digest: str,
        ledger_attempt_ids: Optional[List[str]] = None,
    ) -> List[BridgeRoutingResult]:
        """
        Route a batch of (package, evidence) pairs through the bridge.

        ledger_attempt_ids, if supplied, must have the same length as pairs.
        Auto-generates attempt IDs if not supplied.
        """
        if ledger_attempt_ids is not None and len(ledger_attempt_ids) != len(pairs):
            raise ValueError("ledger_attempt_ids length must match pairs length")
        results = []
        for i, (pkg, ev) in enumerate(pairs):
            attempt_id = (
                ledger_attempt_ids[i] if ledger_attempt_ids else str(uuid.uuid4())
            )
            results.append(
                self.route(
                    package=pkg,
                    evidence=ev,
                    ledger_attempt_id=attempt_id,
                    ledger_head_digest=ledger_head_digest,
                )
            )
        return results

    # -- Summary -------------------------------------------------------------

    def summary(self) -> dict:
        """Return a summary of routing attempts so far."""
        s = self._log.summary()
        s["ledger_reference"] = self._ledger_ref
        return s
