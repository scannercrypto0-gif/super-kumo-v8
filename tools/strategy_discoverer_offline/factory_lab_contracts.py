"""
Factory Lab Contracts — Discoverer → Lab Receipt Layer
=======================================================
Immutable receipts and denominator snapshots produced by DiscovererToFactoryBridge.

Design
------
* DiscoveryCandidatePackageV1.factory_routing remains "NOT_CONNECTED" (Discoverer's sealed output).
* The Bridge is a one-way gate: it reads the sealed package and emits a separate
  FactoryLabReceiptV1 — Lab's signed acknowledgement.
* LabDenominatorSnapshotV1 captures universe counts from NominationEvidenceV1 at
  routing time so denominators survive independent audit without touching the package.
* LabAttemptLogV1 is a lightweight append-only log of all routing attempts (accepted,
  quarantined, rejected) with hash-chaining for tamper detection.

SAFETY CONSTRAINTS (never relaxed in this layer):
  - Holdout:              NEVER accessed
  - Real execution:       NEVER initiated
  - Profitability eval:   NEVER performed
  - Live / Work data:     NEVER imported
  - Unmerged PRs:         NOT imported
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers (identical to contracts.py to avoid cross-module coupling)
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
# FactoryRoutingStatus — outcome of a single routing attempt
# ---------------------------------------------------------------------------

class FactoryRoutingStatus(str, Enum):
    """Outcome assigned by the bridge for each candidate routing attempt."""
    ROUTED_SYNTHETIC_ONLY         = "ROUTED_SYNTHETIC_ONLY"
    QUARANTINED_UNDOCUMENTED_SRC  = "QUARANTINED_UNDOCUMENTED_SRC"
    QUARANTINED_UNDOCUMENTED_TIME = "QUARANTINED_UNDOCUMENTED_TIME"
    QUARANTINED_SCANNER_P0        = "QUARANTINED_SCANNER_P0"
    QUARANTINED_EVIDENCE_UNKNOWN  = "QUARANTINED_EVIDENCE_UNKNOWN"
    REJECTED_SAFETY_FLAG          = "REJECTED_SAFETY_FLAG"
    REJECTED_PROVENANCE_MISMATCH  = "REJECTED_PROVENANCE_MISMATCH"
    REJECTED_BAD_PACKAGE          = "REJECTED_BAD_PACKAGE"


# ---------------------------------------------------------------------------
# LabDenominatorSnapshotV1 — universe counts captured at routing time
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabDenominatorSnapshotV1:
    """
    Universe denominator snapshot extracted from NominationEvidenceV1 at
    the moment of routing.  Stored in the receipt so denominators survive
    independent audit.

    Fields are taken verbatim from NominationEvidenceV1; no inference or
    computation is performed.

    schema_version          : "aql.lab.denominator-snapshot.v1"
    full_universe_denominator: total universe at scan time
    eligible_selected       : subset submitted for scanning
    ineligible              : count deemed ineligible before scanning
    unscanned               : count in eligible set but not completed
    screened_rejected       : count explicitly screened out
    unknown                 : count with unknown disposition
    nominated               : count that passed all gates (subset of eligible_selected)
    source_dataset_id       : source dataset identifier
    source_dataset_version  : integer version of the dataset
    snapshot_digest         : sha256 of canonical({all fields except snapshot_digest})
    """
    schema_version: str
    full_universe_denominator: int
    eligible_selected: int
    ineligible: int
    unscanned: int
    screened_rejected: int
    unknown: int
    nominated: int
    source_dataset_id: str
    source_dataset_version: int
    snapshot_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "aql.lab.denominator-snapshot.v1":
            raise ValueError(f"Bad schema_version: {self.schema_version!r}")
        for attr in ("full_universe_denominator", "eligible_selected", "ineligible",
                     "unscanned", "screened_rejected", "unknown", "nominated",
                     "source_dataset_version"):
            v = getattr(self, attr)
            if not isinstance(v, int) or v < 0:
                raise ValueError(f"{attr} must be a non-negative int")
        if self.nominated > self.eligible_selected:
            raise ValueError("nominated cannot exceed eligible_selected")
        if self.eligible_selected > self.full_universe_denominator:
            raise ValueError("eligible_selected cannot exceed full_universe_denominator")
        _assert_sha256(self.snapshot_digest, "snapshot_digest")
        expected = _digest(self._fields_for_digest())
        if self.snapshot_digest != expected:
            raise ValueError(
                f"snapshot_digest mismatch: stored={self.snapshot_digest} "
                f"computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "full_universe_denominator": self.full_universe_denominator,
            "eligible_selected": self.eligible_selected,
            "ineligible": self.ineligible,
            "unscanned": self.unscanned,
            "screened_rejected": self.screened_rejected,
            "unknown": self.unknown,
            "nominated": self.nominated,
            "source_dataset_id": self.source_dataset_id,
            "source_dataset_version": self.source_dataset_version,
        }

    @classmethod
    def from_evidence(cls, ev) -> "LabDenominatorSnapshotV1":
        """Build from a NominationEvidenceV1 instance."""
        fields = {
            "schema_version": "aql.lab.denominator-snapshot.v1",
            "full_universe_denominator": ev.full_universe_denominator,
            "eligible_selected": ev.eligible_selected,
            "ineligible": ev.ineligible,
            "unscanned": ev.unscanned,
            "screened_rejected": ev.screened_rejected,
            "unknown": ev.unknown,
            "nominated": ev.nominated,
            "source_dataset_id": ev.source_dataset_id,
            "source_dataset_version": ev.source_dataset_version,
        }
        fields["snapshot_digest"] = _digest(fields)
        return cls(**fields)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "full_universe_denominator": self.full_universe_denominator,
            "eligible_selected": self.eligible_selected,
            "ineligible": self.ineligible,
            "unscanned": self.unscanned,
            "screened_rejected": self.screened_rejected,
            "unknown": self.unknown,
            "nominated": self.nominated,
            "source_dataset_id": self.source_dataset_id,
            "source_dataset_version": self.source_dataset_version,
            "snapshot_digest": self.snapshot_digest,
        }


# ---------------------------------------------------------------------------
# FactoryLabReceiptV1 — immutable Lab receipt for one routing attempt
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FactoryLabReceiptV1:
    """
    Immutable receipt issued by DiscovererToFactoryBridge for each
    routing attempt.

    The receipt references the original candidate package by digest but does
    NOT embed or modify it.  factory_routing on the package stays NOT_CONNECTED
    — this receipt is the bridge's separate record of the routing event.

    schema_version          : "aql.lab.receipt.v1"
    receipt_id              : unique receipt identifier
    routing_status          : FactoryRoutingStatus value
    quarantine_reason       : human-readable reason when quarantined/rejected
    candidate_id            : from DiscoveryCandidatePackageV1
    package_digest          : sha256 of the DiscoveryCandidatePackageV1 payload
    strategy_definition_digest: sha256 of the StrategyDefinition payload
    family_id               : strategy family identifier
    nomination_evidence_digest: sha256 of the NominationEvidenceV1
    denominator_snapshot    : LabDenominatorSnapshotV1 (universe counts)
    ledger_attempt_id       : attempt_id in DiscovererLedger (cross-reference)
    ledger_head_digest      : DiscovererLedger head digest at time of routing
    predecessor_receipt_digest: sha256 of previous receipt (or 64 zeros for first)
    routed_at_ns            : wall-clock nanoseconds (observational only)
    safety_flags_verified   : True iff all package safety flags were verified
    holdout_accessed        : MUST be False
    real_execution_initiated: MUST be False
    work_module_imported    : MUST be False
    receipt_digest          : sha256 of canonical(all fields except receipt_digest)
    """

    SCHEMA_VERSION = "aql.lab.receipt.v1"
    _NULL_DIGEST = "0" * 64

    schema_version: str
    receipt_id: str
    routing_status: str
    quarantine_reason: Optional[str]
    candidate_id: str
    package_digest: str
    strategy_definition_digest: str
    family_id: str
    nomination_evidence_digest: str
    denominator_snapshot: LabDenominatorSnapshotV1
    ledger_attempt_id: str
    ledger_head_digest: str
    predecessor_receipt_digest: str
    routed_at_ns: int
    safety_flags_verified: bool
    holdout_accessed: bool           # MUST be False
    real_execution_initiated: bool   # MUST be False
    work_module_imported: bool       # MUST be False
    receipt_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(f"Bad schema_version: {self.schema_version!r}")

        FactoryRoutingStatus(self.routing_status)   # validate enum

        # Hard safety guards — NEVER relaxed
        if self.holdout_accessed is not False:
            raise ValueError("holdout_accessed must be False")
        if self.real_execution_initiated is not False:
            raise ValueError("real_execution_initiated must be False")
        if self.work_module_imported is not False:
            raise ValueError("work_module_imported must be False")

        # SHA fields
        for attr in ("package_digest", "strategy_definition_digest",
                     "nomination_evidence_digest", "ledger_head_digest",
                     "predecessor_receipt_digest", "receipt_digest"):
            _assert_sha256(getattr(self, attr), attr)

        if self.routed_at_ns < 0:
            raise ValueError("routed_at_ns must be non-negative")
        if not isinstance(self.denominator_snapshot, LabDenominatorSnapshotV1):
            raise ValueError("denominator_snapshot must be LabDenominatorSnapshotV1")

        # Verify receipt_digest
        expected = _digest(self._fields_for_digest())
        if self.receipt_digest != expected:
            raise ValueError(
                f"receipt_digest mismatch for {self.receipt_id}: "
                f"stored={self.receipt_digest} computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "routing_status": self.routing_status,
            "quarantine_reason": self.quarantine_reason,
            "candidate_id": self.candidate_id,
            "package_digest": self.package_digest,
            "strategy_definition_digest": self.strategy_definition_digest,
            "family_id": self.family_id,
            "nomination_evidence_digest": self.nomination_evidence_digest,
            "denominator_snapshot_digest": self.denominator_snapshot.snapshot_digest,
            "ledger_attempt_id": self.ledger_attempt_id,
            "ledger_head_digest": self.ledger_head_digest,
            "predecessor_receipt_digest": self.predecessor_receipt_digest,
            "routed_at_ns": self.routed_at_ns,
            "safety_flags_verified": self.safety_flags_verified,
            "holdout_accessed": self.holdout_accessed,
            "real_execution_initiated": self.real_execution_initiated,
            "work_module_imported": self.work_module_imported,
        }

    def to_dict(self) -> dict:
        d = dict(self._fields_for_digest())
        d["denominator_snapshot"] = self.denominator_snapshot.to_dict()
        d["receipt_digest"] = self.receipt_digest
        return d

    @classmethod
    def build(
        cls,
        *,
        receipt_id: str,
        routing_status: FactoryRoutingStatus,
        quarantine_reason: Optional[str],
        candidate_id: str,
        package_digest: str,
        strategy_definition_digest: str,
        family_id: str,
        nomination_evidence_digest: str,
        denominator_snapshot: LabDenominatorSnapshotV1,
        ledger_attempt_id: str,
        ledger_head_digest: str,
        predecessor_receipt_digest: str,
        routed_at_ns: int,
        safety_flags_verified: bool,
    ) -> "FactoryLabReceiptV1":
        """Factory: computes receipt_digest automatically."""
        kwargs = dict(
            schema_version=cls.SCHEMA_VERSION,
            receipt_id=receipt_id,
            routing_status=routing_status.value,
            quarantine_reason=quarantine_reason,
            candidate_id=candidate_id,
            package_digest=package_digest,
            strategy_definition_digest=strategy_definition_digest,
            family_id=family_id,
            nomination_evidence_digest=nomination_evidence_digest,
            denominator_snapshot=denominator_snapshot,
            ledger_attempt_id=ledger_attempt_id,
            ledger_head_digest=ledger_head_digest,
            predecessor_receipt_digest=predecessor_receipt_digest,
            routed_at_ns=routed_at_ns,
            safety_flags_verified=safety_flags_verified,
            holdout_accessed=False,
            real_execution_initiated=False,
            work_module_imported=False,
        )
        # Compute receipt_digest over the stable fields
        digest_input = {
            "schema_version": kwargs["schema_version"],
            "receipt_id": receipt_id,
            "routing_status": routing_status.value,
            "quarantine_reason": quarantine_reason,
            "candidate_id": candidate_id,
            "package_digest": package_digest,
            "strategy_definition_digest": strategy_definition_digest,
            "family_id": family_id,
            "nomination_evidence_digest": nomination_evidence_digest,
            "denominator_snapshot_digest": denominator_snapshot.snapshot_digest,
            "ledger_attempt_id": ledger_attempt_id,
            "ledger_head_digest": ledger_head_digest,
            "predecessor_receipt_digest": predecessor_receipt_digest,
            "routed_at_ns": routed_at_ns,
            "safety_flags_verified": safety_flags_verified,
            "holdout_accessed": False,
            "real_execution_initiated": False,
            "work_module_imported": False,
        }
        kwargs["receipt_digest"] = _digest(digest_input)
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# LabAttemptLogV1 — append-only log of all routing attempts
# ---------------------------------------------------------------------------

@dataclass
class LabAttemptLogV1:
    """
    Lightweight append-only log of Factory Lab routing attempts.

    Hash-chained for tamper detection: each receipt's predecessor_receipt_digest
    must equal the previous receipt's receipt_digest.

    max_entries             : maximum number of receipts (default 10_000)
    receipts                : ordered list of FactoryLabReceiptV1
    """

    max_entries: int = 10_000
    _receipts: List[FactoryLabReceiptV1] = field(default_factory=list)

    def append(self, receipt: FactoryLabReceiptV1) -> None:
        """Append a receipt, verifying chain linkage."""
        if not isinstance(receipt, FactoryLabReceiptV1):
            raise TypeError("Expected FactoryLabReceiptV1")
        if len(self._receipts) >= self.max_entries:
            raise OverflowError(
                f"LabAttemptLogV1 max_entries={self.max_entries} reached"
            )
        expected_predecessor = (
            self._receipts[-1].receipt_digest
            if self._receipts
            else FactoryLabReceiptV1._NULL_DIGEST
        )
        if receipt.predecessor_receipt_digest != expected_predecessor:
            raise ValueError(
                f"Chain broken: expected predecessor_receipt_digest="
                f"{expected_predecessor} got {receipt.predecessor_receipt_digest}"
            )
        self._receipts.append(receipt)

    @property
    def head_digest(self) -> str:
        """SHA-256 of the most recent receipt, or null digest if empty."""
        return (
            self._receipts[-1].receipt_digest
            if self._receipts
            else FactoryLabReceiptV1._NULL_DIGEST
        )

    @property
    def receipts(self) -> tuple:
        return tuple(self._receipts)

    def __len__(self) -> int:
        return len(self._receipts)

    # Counts by status
    def count_by_status(self, status: FactoryRoutingStatus) -> int:
        return sum(1 for r in self._receipts if r.routing_status == status.value)

    @property
    def routed_count(self) -> int:
        return self.count_by_status(FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY)

    @property
    def quarantined_count(self) -> int:
        return sum(
            self.count_by_status(s)
            for s in FactoryRoutingStatus
            if s.value.startswith("QUARANTINED_")
        )

    @property
    def rejected_count(self) -> int:
        return sum(
            self.count_by_status(s)
            for s in FactoryRoutingStatus
            if s.value.startswith("REJECTED_")
        )

    def summary(self) -> dict:
        return {
            "total": len(self._receipts),
            "routed": self.routed_count,
            "quarantined": self.quarantined_count,
            "rejected": self.rejected_count,
            "head_digest": self.head_digest,
        }
