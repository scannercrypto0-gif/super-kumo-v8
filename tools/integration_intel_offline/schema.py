"""Versioned JSON schema for offline PR snapshot import.

Evidence classification per Issue #210 §Stage 2:
  VERIFIED_REMOTE_METADATA  — fetched directly from GitHub REST API (read-only)
  SELF_REPORTED             — from PR title/body (not independently verified)
  INFERRED                  — derived by this toolkit from other fields
  UNKNOWN                   — source cannot be determined

Schema version: integration-intel-snapshot-1
"""
from __future__ import annotations
import hashlib
import json
from typing import Any, Literal

SCHEMA_VERSION = "integration-intel-snapshot-1"

# Valid confidence labels for all evidence fields
EvidenceKind = Literal[
    "VERIFIED_REMOTE_METADATA",
    "SELF_REPORTED",
    "INFERRED",
    "UNKNOWN",
]

VALID_KINDS: frozenset[str] = frozenset(
    ["VERIFIED_REMOTE_METADATA", "SELF_REPORTED", "INFERRED", "UNKNOWN"]
)

# Required top-level keys in a snapshot document
SNAPSHOT_REQUIRED_KEYS = frozenset([
    "schema_version",
    "snapshot_at",          # ISO-8601 UTC timestamp
    "main_head_sha",        # str, 7+ hex chars
    "access_limits",        # list[str] — what could NOT be verified
    "prs",                  # list[PRRecord]
])

# Required keys in each PR record
PR_REQUIRED_KEYS = frozenset([
    "number",               # int
    "head_sha",             # str, 7+ hex chars — VERIFIED_REMOTE_METADATA
    "base_ref",             # str — VERIFIED_REMOTE_METADATA
    "draft",                # bool — VERIFIED_REMOTE_METADATA
    "title",                # str — SELF_REPORTED
    "state",                # "open" | "closed" — VERIFIED_REMOTE_METADATA
    "evidence_kind",        # EvidenceKind for head_sha
    "merged",               # bool | None — VERIFIED if from API, else UNKNOWN
    "merged_evidence_kind", # EvidenceKind for merged field
])


class SnapshotParseError(ValueError):
    """Raised when a snapshot document fails schema validation."""


def validate_snapshot(doc: Any) -> dict:
    """Parse and validate a snapshot document. Raises SnapshotParseError on any violation.

    Returns the validated document unchanged (no mutation).
    Separation of concerns: this function only validates shape and evidence labels.
    Semantic analysis (DAG, collisions) is done by downstream modules.
    """
    if not isinstance(doc, dict):
        raise SnapshotParseError("Snapshot must be a JSON object")

    missing = SNAPSHOT_REQUIRED_KEYS - set(doc.keys())
    if missing:
        raise SnapshotParseError(f"Snapshot missing required keys: {sorted(missing)}")

    if doc["schema_version"] != SCHEMA_VERSION:
        raise SnapshotParseError(
            f"Unsupported schema_version '{doc['schema_version']}'; expected '{SCHEMA_VERSION}'"
        )

    if not isinstance(doc["snapshot_at"], str) or not doc["snapshot_at"]:
        raise SnapshotParseError("snapshot_at must be a non-empty ISO-8601 string")

    if not isinstance(doc["main_head_sha"], str) or len(doc["main_head_sha"]) < 7:
        raise SnapshotParseError("main_head_sha must be a hex string of ≥7 chars")

    if not isinstance(doc["access_limits"], list) or not doc["access_limits"]:
        raise SnapshotParseError("access_limits must be a non-empty list of strings")

    if not isinstance(doc["prs"], list):
        raise SnapshotParseError("prs must be a list")

    seen_numbers: set[int] = set()
    for i, pr in enumerate(doc["prs"]):
        _validate_pr_record(pr, index=i, seen=seen_numbers)

    return doc


def _validate_pr_record(pr: Any, *, index: int, seen: set[int]) -> None:
    if not isinstance(pr, dict):
        raise SnapshotParseError(f"PR[{index}] must be an object")

    missing = PR_REQUIRED_KEYS - set(pr.keys())
    if missing:
        raise SnapshotParseError(f"PR[{index}] missing keys: {sorted(missing)}")

    n = pr["number"]
    if not isinstance(n, int) or n < 1:
        raise SnapshotParseError(f"PR[{index}].number must be a positive int")
    if n in seen:
        raise SnapshotParseError(f"Duplicate PR number {n} at index {index}")
    seen.add(n)

    sha = pr["head_sha"]
    if not isinstance(sha, str) or len(sha) < 7:
        raise SnapshotParseError(f"PR#{n}.head_sha must be ≥7 hex chars")

    if not isinstance(pr["base_ref"], str) or not pr["base_ref"]:
        raise SnapshotParseError(f"PR#{n}.base_ref must be a non-empty string")

    if not isinstance(pr["draft"], bool):
        raise SnapshotParseError(f"PR#{n}.draft must be bool")

    if not isinstance(pr["title"], str):
        raise SnapshotParseError(f"PR#{n}.title must be a string")

    if pr["state"] not in ("open", "closed"):
        raise SnapshotParseError(f"PR#{n}.state must be 'open' or 'closed'")

    if pr["evidence_kind"] not in VALID_KINDS:
        raise SnapshotParseError(
            f"PR#{n}.evidence_kind '{pr['evidence_kind']}' not in {sorted(VALID_KINDS)}"
        )

    if pr["merged"] is not None and not isinstance(pr["merged"], bool):
        raise SnapshotParseError(f"PR#{n}.merged must be bool or null")

    if pr["merged_evidence_kind"] not in VALID_KINDS:
        raise SnapshotParseError(
            f"PR#{n}.merged_evidence_kind '{pr['merged_evidence_kind']}' not in {sorted(VALID_KINDS)}"
        )

    # A merged=True claim with UNKNOWN evidence is suspicious but not blocked;
    # downstream merger must flag it as INFERRED_MERGE_CLAIM.


def snapshot_digest(doc: dict) -> str:
    """Deterministic SHA-256 digest of a validated snapshot."""
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def load_snapshot(path: str) -> tuple[dict, str]:
    """Load, validate, and digest a snapshot file. Returns (doc, digest)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    doc = validate_snapshot(raw)
    return doc, snapshot_digest(doc)
