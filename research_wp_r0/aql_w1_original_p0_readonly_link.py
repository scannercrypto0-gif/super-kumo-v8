"""Read-only original P0 receipt / isolated ACK-copy / manifest linkage.

No original files are written. Caller MUST supply independently retained SHA256
anchors and explicit field paths from the actual historical schema. Unknown
canonical serialization or missing anchors fail closed; no inferred F1.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .aql_w1_opportunity_outcomes import EvidenceError


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _anchored(raw: bytes, expected: str, label: str):
    if not isinstance(expected, str) or len(expected) != 64 or any(
        c not in "0123456789abcdef" for c in expected
    ):
        raise EvidenceError("missing independent SHA256 anchor: " + label)
    if _digest(raw) != expected:
        raise EvidenceError("original bytes mismatch independent anchor: " + label)


def _field(obj, path):
    if not isinstance(path, str) or not path:
        raise EvidenceError("missing historical schema field mapping")
    value = obj
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise EvidenceError("missing original field: " + path)
        value = value[part]
    if value is None or value == "":
        raise EvidenceError("empty original field: " + path)
    return value


def verify_original_linkage(*, receipt_path, ack_copy_path, manifest_path,
                            anchors, fields, expected_identity):
    """Verify a SINGLE anchored receipt against an anchored ACK-copy + manifest.

    anchors must be independently sourced, never calculated from the supplied
    paths by this function. fields maps each semantic to a historical JSON
    dotted path; no guessed canonical domain or hardcoded historical schema.
    expected_identity is an independently pinned four-field C2 identity.
    """
    required_anchors = ("receipt_sha256", "ack_copy_sha256", "manifest_sha256")
    if not isinstance(anchors, dict) or any(k not in anchors for k in required_anchors):
        raise EvidenceError("BLOCKED_MISSING_ORIGINAL_CUSTODY")
    raw = {}
    for key, path in (("receipt", receipt_path), ("ack_copy", ack_copy_path),
                      ("manifest", manifest_path)):
        if not isinstance(path, (str, Path)) or not Path(path).is_file():
            raise EvidenceError("BLOCKED_MISSING_ORIGINAL_CUSTODY: " + key)
        raw[key] = Path(path).read_bytes()
    for key, anchor in (("receipt", "receipt_sha256"),
                        ("ack_copy", "ack_copy_sha256"),
                        ("manifest", "manifest_sha256")):
        _anchored(raw[key], anchors[anchor], key)
    try:
        receipt = json.loads(raw["receipt"])
        manifest = json.loads(raw["manifest"])
        ack_rows = [json.loads(line) for line in raw["ack_copy"].splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise EvidenceError("invalid original JSON or JSONL") from exc
    if not isinstance(receipt, dict) or not isinstance(manifest, dict):
        raise EvidenceError("invalid original object schema")
    if not isinstance(fields, dict) or not isinstance(expected_identity, dict):
        raise EvidenceError("missing schema map or pinned C2 identity")
    names = ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256")
    if set(expected_identity) != set(names):
        raise EvidenceError("incomplete independent C2 identity")
    for name in names:
        if _field(receipt, fields.get("receipt_" + name)) != expected_identity[name]:
            raise EvidenceError("original receipt C2 identity mismatch")
    receipt_pointer = _field(receipt, fields.get("receipt_pointer"))
    source = _field(receipt, fields.get("receipt_source_version"))
    policy = _field(receipt, fields.get("receipt_policy_version"))
    generation = _field(receipt, fields.get("receipt_correction_generation"))
    if _field(manifest, fields.get("manifest_source_version")) != source:
        raise EvidenceError("manifest source mismatch")
    if _field(manifest, fields.get("manifest_policy_version")) != policy:
        raise EvidenceError("manifest policy mismatch")
    if _field(manifest, fields.get("manifest_correction_generation")) != generation:
        raise EvidenceError("manifest correction mismatch")
    matches = []
    for ack in ack_rows:
        if not isinstance(ack, dict):
            raise EvidenceError("invalid ACK record")
        if _field(ack, fields.get("ack_receipt_pointer")) == receipt_pointer:
            matches.append(ack)
    if len(matches) != 1:
        raise EvidenceError("missing or duplicate ACK receipt pointer")
    ack = matches[0]
    for name in names:
        if _field(ack, fields.get("ack_" + name)) != expected_identity[name]:
            raise EvidenceError("ACK C2 identity mismatch")
    if _field(ack, fields.get("ack_source_version")) != source:
        raise EvidenceError("ACK source mismatch")
    return {
        "status": "ANCHORED_ORIGINAL_RECEIPT_AND_ISOLATED_ACK_COPY_MATCH",
        "receipt_sha256": _digest(raw["receipt"]),
        "ack_copy_sha256": _digest(raw["ack_copy"]),
        "manifest_sha256": _digest(raw["manifest"]),
        "receipt_pointer": receipt_pointer,
        "source_version": source,
        "policy_version": policy,
        "correction_generation": generation,
        "f1_original": "NOT_RECORDED_IN_P0",
        "ack_authority": "ISOLATED_COPY_ONLY_NOT_RUNTIME_ACK",
        "read_only": True,
    }
