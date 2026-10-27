"""Core data-proof v1: immutable, explicitly local observation evidence.

This contract never claims provider publication time or external custody.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


class ProofError(ValueError):
    pass


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ObservationVersion:
    logical_bar_id: str
    version_number: int
    payload_digest: str
    bar_open_ms: int
    bar_close_ms: int
    first_local_seen_ms: int | None
    source_id: str
    supersedes_version_id: str | None = None
    provider_available_ms: int | None = None
    provider_evidence_ref: str | None = None
    clock_evidence_ref: str | None = None
    local_commit_evidence_ref: str | None = None

    def __post_init__(self):
        if not self.logical_bar_id or not self.source_id:
            raise ProofError("identity and source required")
        if type(self.version_number) is not int or self.version_number < 1:
            raise ProofError("invalid version number")
        if len(self.payload_digest) != 64 or any(c not in "0123456789abcdef" for c in self.payload_digest):
            raise ProofError("invalid payload SHA256")
        if type(self.bar_open_ms) is not int or type(self.bar_close_ms) is not int or self.bar_close_ms < self.bar_open_ms:
            raise ProofError("invalid bar interval")
        for timestamp in (self.first_local_seen_ms, self.provider_available_ms):
            if timestamp is not None and (type(timestamp) is not int or timestamp < 0):
                raise ProofError("invalid evidence timestamp")
        if self.provider_available_ms is not None and not self.provider_evidence_ref:
            raise ProofError("provider availability requires independent evidence reference")
        if self.version_number == 1 and self.supersedes_version_id is not None:
            raise ProofError("first version cannot supersede")
        if self.version_number > 1 and not self.supersedes_version_id:
            raise ProofError("revision must reference previous version")

    @property
    def version_id(self) -> str:
        return "obs-v1:" + _digest(self.__dict__)

    def eligibility(self, decision_cutoff_ms: int) -> str:
        """Conservative admission hint, not a Factory scientific PASS."""
        if type(decision_cutoff_ms) is not int:
            raise ProofError("invalid decision cutoff")
        if self.first_local_seen_ms is None:
            return "UNKNOWN_PENDING_EVIDENCE"
        if self.first_local_seen_ms > decision_cutoff_ms:
            return "REJECT_LATE"
        if self.provider_available_ms is not None and self.provider_available_ms > decision_cutoff_ms:
            return "REJECT_LATE"
        if not self.clock_evidence_ref or not self.local_commit_evidence_ref:
            return "UNKNOWN_PENDING_EVIDENCE"
        return "LOCAL_EVIDENCE_ONLY"


def verify_chain(versions: tuple[ObservationVersion, ...]) -> None:
    """Reject branching, missing ancestors and revisions with reversed local arrival."""
    seen = {}
    previous = None
    for version in versions:
        if version.version_id in seen:
            raise ProofError("duplicate observation revision")
        if previous is not None:
            if version.logical_bar_id != previous.logical_bar_id or version.source_id != previous.source_id:
                raise ProofError("cross-bar revision")
            if version.version_number != previous.version_number + 1:
                raise ProofError("nonconsecutive revision")
            if version.supersedes_version_id != previous.version_id:
                raise ProofError("broken revision ancestry")
            if (previous.first_local_seen_ms is not None and version.first_local_seen_ms is not None
                    and version.first_local_seen_ms < previous.first_local_seen_ms):
                raise ProofError("revision precedes previous observation")
        elif version.version_number != 1:
            raise ProofError("missing initial revision")
        seen[version.version_id] = version
        previous = version
