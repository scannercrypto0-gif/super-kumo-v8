"""Fail-closed W1 research provenance gate; no Paper or historical F1 backfill.

A custody record is supplied by a trusted read-only adapter, not generated from
the effect under examination. This module checks hashes and identity only;
the adapter must independently establish that receipt and ACK are originals.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from .aql_w1_opportunity_outcomes import EvidenceError


@dataclass(frozen=True)
class F4Custody:
    receipt_bytes: bytes
    ack_bytes: bytes
    expected_receipt_sha256: str
    expected_ack_sha256: str
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str
    source_version: str
    source_bytes_sha256: str
    policy_version: str
    correction_generation: str
    run_manifest_sha256: str
    f1_selection_sha256: str | None = None


def _valid_sha(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def verify_f3_custody(effects, custody_by_identity: Mapping,
                      selected_source_by_identity: Mapping):
    """Require externally pinned receipt/ACK and immutable source selection.

    The source mapping is an independent, versioned decision of the caller,
    keyed by (trial, opportunity, producer, envelope). It must not be derived
    from the F3 effect. No original P0 F1 is synthesized.
    """
    from .aql_w1_typed_contract import F3EffectV1

    effects = tuple(effects)
    if len(custody_by_identity) != len(effects) or len(selected_source_by_identity) != len(effects):
        raise EvidenceError("missing or extra F4 custody/source selection")
    seen = set()
    for effect in effects:
        if not isinstance(effect, F3EffectV1):
            raise EvidenceError("untyped F3 effect")
        key = (effect.trial_id, effect.opportunity_id,
               effect.producer_event_id, effect.envelope_sha256)
        if key in seen:
            raise EvidenceError("duplicate F3 effect")
        seen.add(key)
        custody = custody_by_identity.get(key)
        source = selected_source_by_identity.get(key)
        if not isinstance(custody, F4Custody) or not isinstance(source, Mapping):
            raise EvidenceError("missing authenticated custody/source")
        for field in ("expected_receipt_sha256", "expected_ack_sha256",
                      "source_bytes_sha256", "run_manifest_sha256"):
            if not _valid_sha(getattr(custody, field)):
                raise EvidenceError("invalid custody digest: " + field)
        if not isinstance(custody.receipt_bytes, bytes) or not isinstance(custody.ack_bytes, bytes):
            raise EvidenceError("receipt/ACK must be original bytes")
        if sha256(custody.receipt_bytes).hexdigest() != custody.expected_receipt_sha256:
            raise EvidenceError("F4 receipt bytes mismatch")
        if sha256(custody.ack_bytes).hexdigest() != custody.expected_ack_sha256:
            raise EvidenceError("ACK bytes mismatch")
        if effect.consumer_receipt_sha256 != custody.expected_receipt_sha256:
            raise EvidenceError("F3 receipt does not match original F4")
        if key != (custody.trial_id, custody.opportunity_id,
                   custody.producer_event_id, custody.envelope_sha256):
            raise EvidenceError("F4/C2 identity mismatch")
        if effect.source_version != custody.source_version:
            raise EvidenceError("F3 source version mismatch")
        fields = ("source_version", "source_bytes_sha256", "policy_version",
                  "correction_generation", "run_manifest_sha256",
                  "expected_receipt_sha256", "expected_ack_sha256")
        if any(source.get(f) != getattr(custody, f) for f in fields):
            raise EvidenceError("unselected source/policy/correction or ACK lineage")
        if effect.f1_selection_sha256 is not None:
            if not _valid_sha(effect.f1_selection_sha256) or (
                custody.f1_selection_sha256 != effect.f1_selection_sha256
            ):
                raise EvidenceError("F1 selection receipt not authenticated")
        elif custody.f1_selection_sha256 is not None:
            raise EvidenceError("recorded F1 link omitted from F3")
    if set(custody_by_identity) != seen or set(selected_source_by_identity) != seen:
        raise EvidenceError("orphan custody/source selection")
    return True
