"""WP-R10: offline owner checkpoint exchange, not an automatic trust service.

A checkpoint is only trusted if the owner independently verifies and retains
its exact bytes OUTSIDE the writable research environment. JSON and SHA-256
alone do not prove author identity or protect against replacement of both
journal and checkpoint by the same adversary.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.trial_holdout import fingerprint

SCHEMA = "AQL-RESEARCH-CHECKPOINT-V1"


def _hex64(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(
        digit in "0123456789abcdef" for digit in value
    )


@dataclass(frozen=True)
class OwnerCheckpoint:
    family_digest: str
    sequence: int
    head: str
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ValueError("Unsupported checkpoint schema")
        if not _hex64(self.family_digest) or not _hex64(self.head):
            raise ValueError("Canonical 64-character SHA-256 digests required")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("Checkpoint sequence must be positive integer")

    def to_json_bytes(self) -> bytes:
        return (json.dumps({
            "schema": self.schema,
            "family_digest": self.family_digest,
            "sequence": self.sequence,
            "head": self.head,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")

    @classmethod
    def from_json_bytes(cls, content: bytes) -> "OwnerCheckpoint":
        if type(content) is not bytes or len(content) > 512 or not content.endswith(b"\n"):
            raise ValueError("Invalid checkpoint byte format")
        try:
            value = json.loads(content.decode("ascii"))
            if type(value) is not dict or set(value) != {
                "schema", "family_digest", "sequence", "head"
            }:
                raise ValueError("Wrong checkpoint fields")
            obj = cls(**value)
            if obj.to_json_bytes() != content:
                raise ValueError("Noncanonical checkpoint encoding")
            return obj
        except (UnicodeError, TypeError, ValueError) as exc:
            raise ValueError("Malformed checkpoint") from exc

    @property
    def receipt_digest(self) -> str:
        """Compare this with the independent owner's copy, NOT with the journal."""
        return fingerprint({
            "schema": self.schema,
            "family_digest": self.family_digest,
            "sequence": self.sequence,
            "head": self.head,
        })


def export_checkpoint(journal: DurableTrialJournal) -> OwnerCheckpoint:
    """Read and replay existing disk state before producing *untrusted* bytes.

    The caller must arrange independent authenticated custody and timestamp.
    This does not write an external file, email or remote network request.
    """
    journal._require_healthy()
    try:
        journal._restore()
    except BaseException:
        journal._poisoned = True
        raise
    return OwnerCheckpoint(journal.family.digest, journal.sequence, journal.head)


def verify_owner_checkpoint(
    journal: DurableTrialJournal, checkpoint: OwnerCheckpoint,
    *, independently_trusted: bool,
) -> None:
    """Fail closed unless the caller asserts independent checkpoint custody.

    This flag is a contract assertion, NOT cryptographic proof of authenticity.
    The on-disk prefix is replayed and pinned by verify_anchor.
    """
    if independently_trusted is not True:
        raise JournalIntegrityError("Checkpoint not independently trusted")
    if checkpoint.family_digest != journal.family.digest:
        raise JournalIntegrityError("Checkpoint belongs to another research family")
    journal.verify_anchor(expected_head=checkpoint.head,
                          expected_sequence=checkpoint.sequence)

