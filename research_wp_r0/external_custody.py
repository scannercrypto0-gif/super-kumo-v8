"""WP-R11: external checkpoint custody *contract* and read-back verification.

This module has NO network client, credentials, real external repository, or
tamperproof time source. It requires a provider adapter to be supplied later.
A read-back proves only adapter consistency: actual independence and access
controls require a separately audited external custodian, owner authorization,
and immutable retention. No strategy certification or trading permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Protocol, runtime_checkable

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import (
    OwnerCheckpoint, export_checkpoint, verify_owner_checkpoint,
)


def _id(value: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in value
    ):
        raise ValueError("Checkpoint namespace and owner identity must use safe ASCII IDs")
    return value


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class CustodyPolicy:
    """Owner-approved configuration, NOT verified authorisation."""
    owner_id: str
    custodian_id: str
    namespace: str
    external_independence_verified: bool = False

    def __post_init__(self) -> None:
        _id(self.owner_id)
        _id(self.custodian_id)
        _id(self.namespace)
        if type(self.external_independence_verified) is not bool:
            raise ValueError("External independence must be a bool")


@runtime_checkable
class ImmutableCheckpointStore(Protocol):
    """Integration boundary; MUST be independently reviewed before use.

    put_once MUST never overwrite an existing key. The adapter must guarantee
    byte-for-byte durable storage with independent retention and owner-scoped
    immutable permissions, NOT merely optimistic existence checks.
    """
    def put_once(self, key: str, content: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...


@dataclass(frozen=True)
class CustodyReceipt:
    key: str
    payload_digest: str
    checkpoint: OwnerCheckpoint
    independently_verified: bool
    status: str


class PublicationStatus(str, Enum):
    STORED_UNVERIFIED = "STORED_UNVERIFIED"
    READBACK_VERIFIED = "READBACK_VERIFIED"


def checkpoint_key(policy: CustodyPolicy, checkpoint: OwnerCheckpoint) -> str:
    """Bind custodian namespace, family, sequence AND exact journal head."""
    return (
        f"{_id(policy.namespace)}/{_id(policy.owner_id)}/"
        f"{checkpoint.family_digest}/{checkpoint.sequence:020d}-{checkpoint.head}.json"
    )


def _readback(store: ImmutableCheckpointStore, key: str, expected: bytes) -> None:
    raw = store.read(key)
    if type(raw) is not bytes or raw != expected:
        raise JournalIntegrityError("External checkpoint read-back mismatch")


def publish_checkpoint(
    journal: DurableTrialJournal, *,
    policy: CustodyPolicy,
    store: ImmutableCheckpointStore,
) -> CustodyReceipt:
    """Fail closed on any write/read failure. No trust inferred from read-back.

    A failed put may still have committed remotely; stable content-addressed
    keys make exact idempotent retries possible if put_once provides that
    contract. Never 'fix' a conflict by overwriting the original.
    """
    if not policy.external_independence_verified:
        raise JournalIntegrityError(
            "Independent owner-authorised custody not verified; publication denied"
        )
    checkpoint = export_checkpoint(journal)
    key = checkpoint_key(policy, checkpoint)
    expected = checkpoint.to_json_bytes()
    # Store contract: put_once must reject conflicting bytes and not overwrite.
    store.put_once(key, expected)
    _readback(store, key, expected)
    return CustodyReceipt(
        key=key, payload_digest=_hash(expected), checkpoint=checkpoint,
        independently_verified=True, status=PublicationStatus.READBACK_VERIFIED.value,
    )


def verify_stored_checkpoint(
    journal: DurableTrialJournal, *,
    policy: CustodyPolicy,
    store: ImmutableCheckpointStore,
    checkpoint: OwnerCheckpoint,
) -> CustodyReceipt:
    """Verify independently retained exact bytes, then pin journal history.

    This function's 'verified' flag is conditional on the caller's separately
    validated policy and adapter; it is NOT a cryptographic attestation.
    """
    if not policy.external_independence_verified:
        raise JournalIntegrityError("External custody has not been independently verified")
    key = checkpoint_key(policy, checkpoint)
    expected = checkpoint.to_json_bytes()
    _readback(store, key, expected)
    verify_owner_checkpoint(journal, checkpoint, independently_trusted=True)
    return CustodyReceipt(key, _hash(expected), checkpoint, True,
                          PublicationStatus.READBACK_VERIFIED.value)
