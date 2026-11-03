"""
Phase 2 — Scanner Admission & Quarantine Adapter
=================================================
Strict read-only boundary between the raw Scanner output and the Discoverer.

Design principles
-----------------
* NEVER import from unmerged PR #227 scanner source.
* NEVER trust any upstream boolean (e.g. "nominated=True") without
  independent verification of source/PIT/census.
* While PR #227 carries unresolved P0 issues ALL real nominations are
  classified as UNKNOWN/DEFERRED, never as eligible research candidates.
* Synthetic TEST_ONLY fixtures may be admitted with class TEST_ONLY_SYNTHETIC.
* Fail closed: any schema error, hash mismatch, or policy violation raises or
  emits a REJECTED quarantine status — never silently swallowed.

This adapter defines its own envelope schema independently of PR #227; it
describes WHAT a future corrected Scanner should supply.  The adapter will
need a versioned re-review once PR #227 P0 issues are resolved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from tools.strategy_discoverer_offline.contracts import (
    NominationEvidenceV1,
    EvidenceClass,
    SourceAvailability,
    ScannerQuarantineStatus,
    _canonical,
    _digest,
)


# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

# Version of the adapter's own input schema.  Must be matched exactly.
ADAPTER_SCHEMA_VERSION = "aql.scanner-adapter.input.v1"

# While PR #227 carries P0 issues, treat all non-synthetic scanner input
# as UNKNOWN/DEFERRED regardless of what the upstream envelope claims.
_SCANNER_P0_UNRESOLVED = True  # Set to False only after explicit owner/PM approval


# ---------------------------------------------------------------------------
# Raw input schema (what the adapter expects from the upstream Scanner)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawScannerEnvelope:
    """
    Minimal validated snapshot of what the Scanner should supply.

    This is NOT a trusted object — it is only used to extract and hash fields
    before the adapter quarantines the content.  No field here confers
    research authority.

    The field set is designed to match the PROPOSED corrected Scanner contract
    (after P0 fixes), not the current PR #227 state.  While P0 is unresolved
    the adapter always emits UNKNOWN/DEFERRED regardless.
    """
    schema_version: str
    scanner_contract_version: str
    scanner_source_commit: str
    scan_run_id: str
    market: str
    symbol: str
    timeframe: str
    profile: str
    cutoff_ms: int
    source_dataset_id: str
    source_dataset_version: int
    source_raw_sha256: str
    source_manifest_sha256: str
    universe_snapshot_sha256: str
    full_universe_denominator: int
    eligible_selected: int
    ineligible: int
    unscanned: int
    screened_rejected: int
    unknown: int
    nominated: int
    failed_attempts: int
    omission_reason_codes: list
    independent_verifier_receipt_sha256: str
    envelope_payload_bytes: bytes   # raw bytes of the envelope (for digest)
    receipt_payload_bytes: bytes    # raw bytes of the receipt (for digest)

    def envelope_sha256(self) -> str:
        return hashlib.sha256(self.envelope_payload_bytes).hexdigest()

    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.receipt_payload_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Admission result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdmissionResult:
    """
    Result of processing a raw upstream envelope through the quarantine adapter.

    evidence    : NominationEvidenceV1 if admission succeeded (even as UNKNOWN);
                  None if schema validation itself failed.
    quarantine  : final ScannerQuarantineStatus assigned
    reason      : human-readable reason string
    """
    evidence: Optional[NominationEvidenceV1]
    quarantine: str   # ScannerQuarantineStatus.value
    reason: str


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class ScannerQuarantineAdapter:
    """
    Strict read-only quarantine boundary.

    Usage
    -----
    adapter = ScannerQuarantineAdapter()
    result = adapter.admit(raw_envelope)
    # result.quarantine will be UNKNOWN_DEFERRED while #227 P0 open
    # result.quarantine will be TEST_ONLY_SYNTHETIC for synthetic fixtures

    Synthetic fixtures
    ------------------
    Use admit_synthetic_fixture() instead of admit() for TEST_ONLY data.
    Synthetic fixtures bypass real-Scanner schema checks and always carry
    EvidenceClass.TEST_ONLY_SYNTHETIC.
    """

    def admit(self, raw: RawScannerEnvelope) -> AdmissionResult:
        """
        Process a real upstream Scanner envelope through the quarantine boundary.

        Returns AdmissionResult.  While _SCANNER_P0_UNRESOLVED is True the
        quarantine status will always be UNKNOWN_DEFERRED regardless of what
        the envelope claims.

        Schema errors produce REJECTED_BAD_SCHEMA with evidence=None.
        """
        # Schema version check
        if raw.schema_version != ADAPTER_SCHEMA_VERSION:
            return AdmissionResult(
                evidence=None,
                quarantine=ScannerQuarantineStatus.REJECTED_BAD_SCHEMA.value,
                reason=f"schema_version mismatch: got {raw.schema_version!r}",
            )

        # Basic sanity: cutoff must be non-negative int
        if not isinstance(raw.cutoff_ms, int) or raw.cutoff_ms < 0:
            return AdmissionResult(
                evidence=None,
                quarantine=ScannerQuarantineStatus.REJECTED_BAD_SCHEMA.value,
                reason="cutoff_ms invalid",
            )

        # SHA-256 field format check (independent verifier receipt)
        iv_sha = raw.independent_verifier_receipt_sha256
        if not isinstance(iv_sha, str) or len(iv_sha) != 64 or not all(
                c in "0123456789abcdef" for c in iv_sha):
            return AdmissionResult(
                evidence=None,
                quarantine=ScannerQuarantineStatus.REJECTED_HASH_MISMATCH.value,
                reason="independent_verifier_receipt_sha256 format invalid",
            )

        # Census sanity
        if raw.nominated > raw.eligible_selected:
            return AdmissionResult(
                evidence=None,
                quarantine=ScannerQuarantineStatus.REJECTED_CENSUS_FAIL.value,
                reason="nominated exceeds eligible_selected",
            )
        if raw.eligible_selected > raw.full_universe_denominator:
            return AdmissionResult(
                evidence=None,
                quarantine=ScannerQuarantineStatus.REJECTED_CENSUS_FAIL.value,
                reason="eligible_selected exceeds full_universe_denominator",
            )

        # Determine quarantine status and evidence class
        if _SCANNER_P0_UNRESOLVED:
            quarantine = ScannerQuarantineStatus.UNKNOWN_DEFERRED.value
            evidence_class = EvidenceClass.UNKNOWN_UNVERIFIED.value
        else:
            # C-04 fix: dead code replaced with explicit guard.
            # This path must NOT be activated silently. P0 remediation requires
            # a dedicated policy review, new evidence-class definitions, and
            # explicit owner approval before quarantine can be lifted.
            raise NotImplementedError(
                "P0 remediation path is not yet implemented. "
                "Set _SCANNER_P0_UNRESOLVED=False only after explicit owner "
                "approval and a dedicated policy review. "
                "AQL ref: scanner_adapter.py C-04"
            )

        evidence = NominationEvidenceV1.build(
            schema_version="aql.discoverer.nomination-evidence.v1",
            evidence_class=evidence_class,
            quarantine_status=quarantine,
            scanner_contract_version=raw.scanner_contract_version,
            scanner_source_commit=raw.scanner_source_commit,
            scanner_envelope_sha256=raw.envelope_sha256(),
            scanner_receipt_sha256=raw.receipt_sha256(),
            source_dataset_id=raw.source_dataset_id,
            source_dataset_version=raw.source_dataset_version,
            source_raw_sha256=raw.source_raw_sha256,
            source_manifest_sha256=raw.source_manifest_sha256,
            universe_snapshot_sha256=raw.universe_snapshot_sha256,
            scan_run_id=raw.scan_run_id,
            market=raw.market,
            symbol=raw.symbol,
            timeframe=raw.timeframe,
            profile=raw.profile,
            cutoff_ms=raw.cutoff_ms,
            source_availability=SourceAvailability.UNKNOWN.value,
            full_universe_denominator=raw.full_universe_denominator,
            eligible_selected=raw.eligible_selected,
            ineligible=raw.ineligible,
            unscanned=raw.unscanned,
            screened_rejected=raw.screened_rejected,
            unknown=raw.unknown,
            nominated=raw.nominated,
            failed_attempts=raw.failed_attempts,
            omission_reason_codes=tuple(raw.omission_reason_codes),
            independent_verifier_receipt_sha256=raw.independent_verifier_receipt_sha256,
        )

        return AdmissionResult(
            evidence=evidence,
            quarantine=quarantine,
            reason="P0 unresolved — all real nominations quarantined as UNKNOWN/DEFERRED",
        )

    def admit_synthetic_fixture(self, spec: dict) -> NominationEvidenceV1:
        """
        Admit a TEST_ONLY synthetic fixture.

        Accepts either a full NominationEvidenceV1 spec (all required fields
        except schema_version, evidence_class, quarantine_status, nomination_digest
        which are forced), OR a simplified fixture spec using short names:

          receipt_id              → scan_run_id
          dataset_id              → source_dataset_id
          dataset_manifest_sha256 → source_manifest_sha256
          decision_cutoff_ms      → cutoff_ms
          census_eligible_count   → eligible_selected (and full_universe_denominator
                                    if that is also absent)
          census_omission_count   → ineligible
          census_omission_codes   → omission_reason_codes

        Informational simplified keys with no NominationEvidenceV1 equivalent
        are silently dropped: available_at_ms, bar_count, warmup_bars.

        Missing required NominationEvidenceV1 fields receive safe TEST_ONLY
        defaults so minimal fixture specs remain concise.

        Returns NominationEvidenceV1 with evidence_class=TEST_ONLY_SYNTHETIC and
        quarantine_status=TEST_ONLY_SYNTHETIC.  Raises ValueError on schema errors.
        """
        spec = dict(spec)

        # Translate simplified spec keys → NominationEvidenceV1 field names.
        # If both the short and long key are present, the long key wins.
        _FIELD_MAP = {
            "receipt_id": "scan_run_id",
            "dataset_id": "source_dataset_id",
            "dataset_manifest_sha256": "source_manifest_sha256",
            "decision_cutoff_ms": "cutoff_ms",
            "census_eligible_count": "eligible_selected",
            "census_omission_count": "ineligible",
            "census_omission_codes": "omission_reason_codes",
        }
        for short, full in _FIELD_MAP.items():
            if short in spec:
                if full not in spec:
                    spec[full] = spec.pop(short)
                else:
                    spec.pop(short)  # long form already present; discard short

        # Drop informational-only keys that have no NominationEvidenceV1 field.
        for key in ("available_at_ms", "bar_count", "warmup_bars"):
            spec.pop(key, None)

        # If full_universe_denominator absent, mirror eligible_selected.
        if "full_universe_denominator" not in spec and "eligible_selected" in spec:
            spec["full_universe_denominator"] = spec["eligible_selected"]

        # Supply safe TEST_ONLY defaults for any remaining required fields.
        spec.setdefault("scanner_contract_version", "TEST_ONLY.0.1.0")
        spec.setdefault("scanner_source_commit", "0" * 40)
        spec.setdefault("scanner_envelope_sha256", "0" * 64)
        spec.setdefault("scanner_receipt_sha256", "0" * 64)
        spec.setdefault("source_dataset_version", 1)
        spec.setdefault("source_raw_sha256", "0" * 64)
        spec.setdefault("universe_snapshot_sha256", "0" * 64)
        spec.setdefault("profile", "default")
        spec.setdefault(
            "source_availability", SourceAvailability.CONFIRMED_FINAL.value
        )
        spec.setdefault("unscanned", 0)
        spec.setdefault("screened_rejected", 0)
        spec.setdefault("unknown", 0)
        spec.setdefault("nominated", 1)
        spec.setdefault("failed_attempts", 0)
        spec.setdefault("independent_verifier_receipt_sha256", "0" * 64)

        # Force required identity fields.
        spec["schema_version"] = "aql.discoverer.nomination-evidence.v1"
        spec["evidence_class"] = EvidenceClass.TEST_ONLY_SYNTHETIC.value
        spec["quarantine_status"] = ScannerQuarantineStatus.TEST_ONLY_SYNTHETIC.value
        spec["omission_reason_codes"] = tuple(spec.get("omission_reason_codes", ()))

        # Remove nomination_digest if accidentally included.
        spec.pop("nomination_digest", None)

        return NominationEvidenceV1.build(**spec)


# ---------------------------------------------------------------------------
# Policy guard — called by generator to prevent promotion of quarantined items
# ---------------------------------------------------------------------------

def assert_eligible_for_research(evidence: NominationEvidenceV1) -> None:
    """
    Raise if the evidence record is not eligible for research candidate generation.

    Currently only TEST_ONLY_SYNTHETIC evidence is ever eligible while #227 P0
    issues remain open.  This function is the single enforcement point.

    Raises
    ------
    ValueError if the evidence is not eligible.
    """
    if evidence.quarantine_status == ScannerQuarantineStatus.TEST_ONLY_SYNTHETIC.value:
        return  # OK for test-only use
    raise ValueError(
        f"Evidence is not eligible for research candidate generation: "
        f"quarantine_status={evidence.quarantine_status!r}, "
        f"evidence_class={evidence.evidence_class!r}. "
        f"Scanner PR #227 P0 issues must be resolved and independently reviewed "
        f"before real nominations can be admitted."
    )
