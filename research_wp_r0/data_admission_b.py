"""Factory consumer-only, fail-closed admission of *supplied* observation revisions.

No provider/issuer authentication, Core runtime import, market access, PIT
certification or trading permission. This gate is required BEFORE feeding
any supplied empirical feature into Scanner, indicators or Decision.
"""
from dataclasses import dataclass
import re

_SHA = re.compile(r"[0-9a-f]{64}\\Z")
_STATES = frozenset(("CONFIRMED", "WITHHELD", "IN_DOUBT", "UNKNOWN"))


@dataclass(frozen=True)
class Admission:
    status: str
    reason: str
    version_id: str | None = None
    empirical_eligible: bool = False
    real_pit_accepted: bool = False


def _result(status, reason, version_id=None):
    return Admission(status, reason, version_id)


def admit_revision(record, *, cutoff_ms, expected_manifest_digest,
                   verified_source_timing=False):
    """Inspect a Core-compatible value object or mapping, never promote custody.

    verified_source_timing is an explicitly separate, independently checked
    source-clock assertion from the caller, not inferred from a receipt string.
    Passing it permits *review eligibility* only, NEVER real-PIT acceptance.
    """
    if type(cutoff_ms) is not int or cutoff_ms < 0:
        return _result("REJECT_FOR_EMPIRICAL", "INVALID_CUTOFF")
    if type(expected_manifest_digest) is not str or not _SHA.fullmatch(expected_manifest_digest):
        return _result("REJECT_FOR_EMPIRICAL", "MISSING_PINNED_MANIFEST")
    if type(record) is not dict:
        return _result("REJECT_FOR_EMPIRICAL", "MALFORMED_REVISION")
    version = record.get("version_id")
    if not isinstance(version, str) or not version:
        return _result("UNKNOWN_PENDING_EVIDENCE", "MISSING_VERSION_ID")
    def timestamp(key):
        v = record.get(key)
        return v if type(v) is int and v >= 0 else None
    if record.get("manifest_digest") != expected_manifest_digest:
        return _result("REJECT_FOR_EMPIRICAL", "MANIFEST_MISMATCH", version)
    if record.get("gap_state") not in _STATES or record["gap_state"] != "CONFIRMED":
        return _result("UNKNOWN_PENDING_EVIDENCE", "SPARSE_OR_UNCONFIRMED", version)
    if not isinstance(record.get("payload_digest"), str) or not _SHA.fullmatch(record["payload_digest"]):
        return _result("REJECT_FOR_EMPIRICAL", "INVALID_CONTENT_ID", version)
    close = timestamp("bar_close_ms")
    first = timestamp("first_local_seen_ms")
    committed = timestamp("ingest_committed_ms")
    provider = timestamp("provider_available_ms")
    if close is None or first is None or committed is None:
        return _result("UNKNOWN_PENDING_EVIDENCE", "MISSING_FIRST_KNOWN_OR_COMMIT", version)
    if close > first or first > committed:
        return _result("REJECT_FOR_EMPIRICAL", "INCONSISTENT_CHRONOLOGY", version)
    if first > cutoff_ms or committed > cutoff_ms:
        return _result("REJECT_FOR_EMPIRICAL", "NOT_KNOWN_AT_CUTOFF", version)
    revised = timestamp("revision_first_seen_ms")
    if record.get("supersedes_version_id") is not None:
        if revised is None or revised > cutoff_ms:
            return _result("REJECT_FOR_EMPIRICAL", "LATE_OR_UNPROVEN_CORRECTION", version)
        if revised < first:
            return _result("REJECT_FOR_EMPIRICAL", "REVISION_CHRONOLOGY_INVALID", version)
    if provider is None or provider > cutoff_ms:
        return _result("UNKNOWN_PENDING_EVIDENCE", "PROVIDER_AS_OF_UNVERIFIED", version)
    if not verified_source_timing or not record.get("provider_evidence_ref") or not record.get("clock_evidence_ref"):
        return _result("UNKNOWN_PENDING_EVIDENCE", "SOURCE_TIMING_NOT_INDEPENDENTLY_VERIFIED", version)
    return Admission("ELIGIBLE_FOR_EMPIRICAL_REVIEW", "SOURCE_TIME_REQUIRES_COUNCIL_REVIEW", version,
                     empirical_eligible=True, real_pit_accepted=False)
