"""Bounded prospective F1 provenance verification interface (research-only).

This module DOES NOT issue trusted clocks, freeze attestations or durable anchors.
The host must separately own and verify original source publication, pre-F3
freeze, and external immutable receipt evidence. Caller-supplied attestations
alone are never a substitute for independent authority.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .aql_f1_decision_capture_v1 import (
    CaptureError, _fail, _fields, _id, _int, _is_hash, digest,
    validate_commit_receipt, validate_f1,
)

SOURCE_FIELDS = {
    "schema_version", "pair_id", "arm", "f1_record_sha256",
    "source_id", "source_version", "source_bytes_sha256",
    "correction_generation", "correction_lineage_sha256",
    "source_asof_ms", "source_published_at_ms", "correction_published_at_ms",
    "source_available_at_ms", "decision_cutoff_ms", "source_receipt_sha256",
}
FREEZE_FIELDS = {
    "schema_version", "pair_id", "arm", "f1_record_sha256",
    "arm_event_sha256", "frozen_at_ms", "f3_started_at_ms",
    "freeze_ref", "freeze_receipt_sha256",
}
ATTESTED = ("source", "freeze", "commit")

def _source(source: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    _fields(source, SOURCE_FIELDS, "SOURCE_PUBLICATION_PROOF")
    if source["schema_version"] != "aql.f1-source-publication-proof.v1":
        _fail("SOURCE_PROOF_SCHEMA")
    for key in ("pair_id", "arm", "f1_record_sha256", "source_id",
                "source_version", "source_bytes_sha256", "correction_generation",
                "correction_lineage_sha256", "source_asof_ms",
                "source_available_at_ms", "decision_cutoff_ms"):
        if source[key] != record[key]:
            _fail("SOURCE_PROOF_BINDING_" + key)
    if not all(_int(source[key]) for key in
               ("source_published_at_ms", "correction_published_at_ms")):
        _fail("SOURCE_PUBLICATION_CLOCK")
    cutoff = record["decision_cutoff_ms"]
    if (source["source_asof_ms"] > source["source_published_at_ms"]
            or source["source_published_at_ms"] > cutoff
            or source["correction_published_at_ms"] > cutoff
            or source["source_available_at_ms"] > cutoff):
        _fail("SOURCE_OR_CORRECTION_PUBLISHED_LATE")
    if source["source_receipt_sha256"] != digest({
            k: v for k, v in source.items() if k != "source_receipt_sha256"}):
        _fail("SOURCE_PROOF_DIGEST")

def _freeze(freeze: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    _fields(freeze, FREEZE_FIELDS, "PRE_F3_FREEZE_PROOF")
    if freeze["schema_version"] != "aql.f1-pre-f3-freeze-proof.v1":
        _fail("FREEZE_PROOF_SCHEMA")
    for key in ("pair_id", "arm", "f1_record_sha256", "arm_event_sha256"):
        if freeze[key] != record[key]:
            _fail("FREEZE_PROOF_BINDING_" + key)
    if not _id(freeze["freeze_ref"]) or not all(_int(freeze[k]) for k in
                                                ("frozen_at_ms", "f3_started_at_ms")):
        _fail("FREEZE_PROOF_FIELDS")
    if (freeze["frozen_at_ms"] < record["decision_cutoff_ms"]
            or freeze["frozen_at_ms"] > freeze["f3_started_at_ms"]):
        _fail("FREEZE_NOT_BEFORE_F3")
    if freeze["freeze_receipt_sha256"] != digest({
            k: v for k, v in freeze.items() if k != "freeze_receipt_sha256"}):
        _fail("FREEZE_PROOF_DIGEST")

def verify_original_provenance(
    record: Mapping[str, Any], registry: Mapping[str, str],
    *, source_proof: Mapping[str, Any] | None,
    freeze_proof: Mapping[str, Any] | None,
    commit_receipt: Mapping[str, Any] | None,
    source_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    freeze_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    durable_anchor_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
) -> bool:
    """Return True only after all independent host verifiers affirm the evidence.

    Valid proof-shaped JSON with matching hashes is NOT independent proof.
    Missing/rejected/exceptional verifiers fail closed to False. The callbacks
    MUST independently retrieve/attest the source publication, frozen pre-F3
    event and externally durable receipt/anchor respectively; self-issued
    lambda-True callbacks are test doubles, never operational evidence.
    """
    try:
        validate_f1(dict(record), dict(registry))
        if any(proof is None for proof in (source_proof, freeze_proof, commit_receipt)):
            return False
        if any(cb is None or not callable(cb) for cb in (
                source_attestor, freeze_attestor, durable_anchor_verifier)):
            return False
        _source(source_proof, record)
        _freeze(freeze_proof, record)
        validate_commit_receipt(commit_receipt, record)
        if commit_receipt["committed_at_ms"] < freeze_proof["frozen_at_ms"]:
            _fail("COMMIT_PRECEDES_FREEZE")
        if commit_receipt["committed_at_ms"] > freeze_proof["f3_started_at_ms"]:
            _fail("COMMIT_AFTER_F3")
        return (source_attestor(source_proof) is True
                and freeze_attestor(freeze_proof) is True
                and durable_anchor_verifier(commit_receipt) is True)
    except (CaptureError, KeyError, TypeError, ValueError, OverflowError):
        return False
    except Exception:
        # External verifier failures are never converted to positive evidence.
        return False

def make_provenance_verifier(
    registry: Mapping[str, str],
    evidence_lookup: Callable[[Mapping[str, Any]], Mapping[str, Any] | None],
    *, source_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    freeze_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    durable_anchor_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
) -> Callable[[Mapping[str, Any]], bool]:
    """Construct a fail-closed adapter for Core status_slots(proof_verifier=).

    The lookup and three attestors are trusted-host dependencies, not implemented
    or authenticated by this library. Never claim a genuine original without
    separately audited host authority, source cutoff and immutable storage.
    """
    def verify(record: Mapping[str, Any]) -> bool:
        try:
            evidence = evidence_lookup(record)
            if not isinstance(evidence, Mapping):
                return False
            return verify_original_provenance(
                record, registry,
                source_proof=evidence.get("source_proof"),
                freeze_proof=evidence.get("freeze_proof"),
                commit_receipt=evidence.get("commit_receipt"),
                source_attestor=source_attestor,
                freeze_attestor=freeze_attestor,
                durable_anchor_verifier=durable_anchor_verifier,
            )
        except Exception:
            return False
    return verify
