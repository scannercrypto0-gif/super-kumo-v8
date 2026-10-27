"""Offline Core data-proof envelope -> Factory admission boundary, fail closed.

Core PR #137 is still draft. This read-only adapter NEVER creates first-known,
post-COMMIT or provider-availability proofs; no trading/OOS authority.
"""
import hashlib
import json
from .data_admission_b import Admission, admit_revision

def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def review_core_envelope(envelope, *, pinned_digest, cutoff_ms, consumer="factory",
                         minimum_epoch=0):
    """Return one conservative receipt per supplied observation revision.

    Envelope integrity is local only. Successful verification still cannot
    promote Core LOCAL_ONLY_UNATTESTED to real PIT or empirical eligibility.
    """
    if type(envelope) is not dict or type(pinned_digest) is not str:
        return (Admission("REJECT_FOR_EMPIRICAL", "INVALID_CORE_ENVELOPE"),)
    body = {k: v for k, v in envelope.items() if k != "manifest_sha256"}
    if envelope.get("manifest_sha256") != pinned_digest or _hash(body) != pinned_digest:
        return (Admission("REJECT_FOR_EMPIRICAL", "CORE_ENVELOPE_PIN_MISMATCH"),)
    if (body.get("schema") != "core-data-proof-envelope-v1"
            or body.get("consumer") != consumer
            or type(body.get("epoch")) is not int or body["epoch"] < minimum_epoch
            or body.get("provenance_scope") != "LOCAL_ONLY_UNATTESTED"
            or type(body.get("gap_states")) is not dict
            or type(body.get("versions")) is not list):
        return (Admission("REJECT_FOR_EMPIRICAL", "CORE_ENVELOPE_CONTRACT_MISMATCH"),)
    results = []
    for item in body["versions"]:
        if type(item) is not dict or type(item.get("record")) is not dict:
            return (Admission("REJECT_FOR_EMPIRICAL", "INVALID_CORE_VERSION"),)
        record = item["record"]
        version = item.get("version_id")
        if (type(version) is not str or version != "obs-v1:" + _hash(record)
                or record.get("payload_digest") is None):
            return (Admission("REJECT_FOR_EMPIRICAL", "CORE_VERSION_DIGEST_MISMATCH"),)
        # Revision details and gap states are *not* manufactured into evidence.
        # A Core post-commit reference is not a trusted post-COMMIT timestamp.
        normalized = dict(version_id=version, manifest_digest=pinned_digest,
                          gap_state=body["gap_states"].get(record.get("logical_bar_id"), "UNKNOWN"),
                          payload_digest=record["payload_digest"],
                          bar_close_ms=record.get("bar_close_ms"),
                          first_local_seen_ms=record.get("first_local_seen_ms"),
                          ingest_committed_ms=None, provider_available_ms=record.get("provider_available_ms"),
                          provider_evidence_ref=record.get("provider_evidence_ref"),
                          clock_evidence_ref=record.get("clock_evidence_ref"),
                          supersedes_version_id=record.get("supersedes_version_id"),
                          revision_first_seen_ms=None)
        local = admit_revision(normalized, cutoff_ms=cutoff_ms,
                               expected_manifest_digest=pinned_digest,
                               verified_source_timing=False)
        results.append(local)
    if not results:
        return (Admission("UNKNOWN_PENDING_EVIDENCE", "EMPTY_CORE_UNIVERSE"),)
    return tuple(results)
