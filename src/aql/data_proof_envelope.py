"""Deterministic, content-addressed offline Core -> Factory proof envelope.

No provider attestation, real PIT certification or realtime G1 integration.
"""
from __future__ import annotations

from hashlib import sha256
import json

from aql.data_proof import ObservationVersion, ProofError, verify_chain


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def export_envelope(*, consumer: str, epoch: int,
                    versions: tuple[ObservationVersion, ...],
                    gap_states: dict[str, str] | None = None) -> dict:
    if not consumer or type(epoch) is not int or epoch < 0:
        raise ProofError("invalid consumer or epoch")
    groups: dict[str, list[ObservationVersion]] = {}
    for version in versions:
        groups.setdefault(version.logical_bar_id, []).append(version)
    for group in groups.values():
        verify_chain(tuple(group))
    gaps = gap_states or {}
    if any(v not in {"CONFIRMED", "WITHHELD", "IN_DOUBT", "UNKNOWN"} for v in gaps.values()):
        raise ProofError("invalid gap state")
    body = {
        "schema": "core-data-proof-envelope-v1",
        "consumer": consumer,
        "epoch": epoch,
        "versions": [
            {"version_id": v.version_id, "record": v.__dict__}
            for v in sorted(versions, key=lambda x: (x.logical_bar_id, x.version_number))
        ],
        "gap_states": dict(sorted(gaps.items())),
        "provenance_scope": "LOCAL_ONLY_UNATTESTED",
    }
    return {**body, "manifest_sha256": sha256(_bytes(body)).hexdigest()}


def verify_envelope(envelope: dict, *, consumer: str, minimum_epoch: int,
                    pinned_sha256: str) -> tuple[ObservationVersion, ...]:
    if type(envelope) is not dict or not isinstance(pinned_sha256, str):
        raise ProofError("invalid envelope")
    body = {k: v for k, v in envelope.items() if k != "manifest_sha256"}
    digest = sha256(_bytes(body)).hexdigest()
    if digest != pinned_sha256 or envelope.get("manifest_sha256") != digest:
        raise ProofError("manifest pin mismatch")
    if body.get("schema") != "core-data-proof-envelope-v1" or body.get("consumer") != consumer:
        raise ProofError("schema or consumer mismatch")
    if type(body.get("epoch")) is not int or body["epoch"] < minimum_epoch:
        raise ProofError("stale epoch")
    if body.get("provenance_scope") != "LOCAL_ONLY_UNATTESTED":
        raise ProofError("unsupported provenance scope")
    items = body.get("versions")
    if not isinstance(items, list):
        raise ProofError("invalid revisions")
    versions = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("record"), dict):
            raise ProofError("invalid version entry")
        version = ObservationVersion(**item["record"])
        if item.get("version_id") != version.version_id:
            raise ProofError("version digest mismatch")
        versions.append(version)
    groups: dict[str, list[ObservationVersion]] = {}
    for version in versions:
        groups.setdefault(version.logical_bar_id, []).append(version)
    for group in groups.values():
        verify_chain(tuple(group))
    if not isinstance(body.get("gap_states"), dict) or any(
        v not in {"CONFIRMED", "WITHHELD", "IN_DOUBT", "UNKNOWN"}
        for v in body["gap_states"].values()
    ):
        raise ProofError("invalid gap state")
    if len({v.version_id for v in versions}) != len(versions):
        raise ProofError("duplicate version")
    return tuple(versions)
