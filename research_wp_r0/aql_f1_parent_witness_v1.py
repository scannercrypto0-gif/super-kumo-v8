"""Read-only Core F1 original-source witness and RAW parent binding.

No new trusted clock, archive, signature authority, or mutable custody store.
The supplied external retriever MUST obtain independent evidence from immutable
host records; self-reported timestamps and self-hashed manifests are insufficient.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping

from .aql_f1_decision_capture_v1 import CaptureError, _fail, _fields, _int, _is_hash, digest
from .aql_f1_provenance_v1 import make_provenance_verifier

PARENT_FIELDS = {
    "schema_version", "parent_source_id", "parent_source_version",
    "parent_source_bytes_sha256", "parent_manifest_sha256",
    "source_id", "source_version", "source_bytes_sha256",
    "correction_generation", "correction_lineage_sha256",
    "source_published_at_ms", "correction_published_at_ms",
    "source_finalized_at_ms", "parent_receipt_ref", "parent_binding_sha256",
}


def validate_parent_binding(record: Mapping[str, Any],
                            binding: Mapping[str, Any],
                            *, parent_manifest_bytes: bytes,
                            parent_bytes: bytes,
                            parent_witness: Callable[[Mapping[str, Any]], bool] | None) -> bool:
    """Validate exact original RAW parent bytes, manifest bytes and external witness.

    parent_witness MUST independently verify the source issuer/publication
    timeline and durable parent receipt; a synthetic callback is only a test.
    """
    try:
        _fields(dict(binding), PARENT_FIELDS, "RAW_PARENT_BINDING")
        if binding["schema_version"] != "aql.f1-raw-parent-binding.v1":
            return False
        if type(parent_bytes) is not bytes or type(parent_manifest_bytes) is not bytes:
            return False
        if any(binding[key] != record[key] for key in (
            "source_id", "source_version", "source_bytes_sha256",
            "correction_generation", "correction_lineage_sha256")):
            return False
        if not all(_is_hash(binding[key]) for key in (
            "parent_source_bytes_sha256", "parent_manifest_sha256")):
            return False
        if (binding["parent_source_bytes_sha256"] != hashlib.sha256(parent_bytes).hexdigest()
                or binding["parent_manifest_sha256"] != hashlib.sha256(parent_manifest_bytes).hexdigest()):
            return False
        if not all(type(binding[key]) is str and binding[key] for key in (
            "parent_source_id", "parent_source_version", "parent_receipt_ref")):
            return False
        if not all(_int(binding[key]) for key in (
            "source_published_at_ms", "correction_published_at_ms",
            "source_finalized_at_ms")):
            return False
        cutoff = record["decision_cutoff_ms"]
        if (binding["source_finalized_at_ms"] > binding["source_published_at_ms"]
                or binding["source_published_at_ms"] > cutoff
                or binding["correction_published_at_ms"] > cutoff):
            return False
        if binding["parent_binding_sha256"] != digest({
            key: value for key, value in binding.items()
            if key != "parent_binding_sha256"}):
            return False
        # Source bytes at the F1 decision may represent a strictly bounded
        # derived prefix. Never pretend they equal the parent unless an
        # external custodian attests the lineage in parent_witness.
        if parent_witness is None or not callable(parent_witness):
            return False
        return parent_witness(binding) is True
    except Exception:
        return False


def make_parent_bound_provenance_verifier(
    registry: Mapping[str, str],
    evidence_lookup: Callable[[Mapping[str, Any]], Mapping[str, Any] | None],
    *, source_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    freeze_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    durable_anchor_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    parent_witness: Callable[[Mapping[str, Any]], bool] | None = None,
) -> Callable[[Mapping[str, Any]], bool]:
    """Conjunctive F1+parent verifier for existing Core/Factory proof_verifier.

    Evidence lookup returns the three original Core proofs plus a
    'raw_parent_binding', 'raw_parent_bytes' and 'raw_parent_manifest_bytes'.
    Callback presence alone never proves independence or operational PIT.
    """
    core = make_provenance_verifier(
        registry, evidence_lookup, source_attestor=source_attestor,
        freeze_attestor=freeze_attestor,
        durable_anchor_verifier=durable_anchor_verifier,
    )

    def verify(record: Mapping[str, Any]) -> bool:
        try:
            if not core(record):
                return False
            evidence = evidence_lookup(record)
            if not isinstance(evidence, Mapping):
                return False
            binding = evidence.get("raw_parent_binding")
            if not isinstance(binding, Mapping):
                return False
            return validate_parent_binding(
                record, binding,
                parent_bytes=evidence.get("raw_parent_bytes"),
                parent_manifest_bytes=evidence.get("raw_parent_manifest_bytes"),
                parent_witness=parent_witness,
            )
        except Exception:
            return False
    return verify
