"""File-level collision analyzer.

Classifies pairs of PRs as:
  DIRECT_WRITE_COLLISION    — both PRs modify the same normalized path
  POSSIBLE_SHARED_CONTRACT  — one modifies a path the other reads/imports
  NON_OVERLAP               — no shared paths

Also:
  - Case-sensitive normalization (Linux-native; flags Windows ambiguity)
  - Path traversal rejection (.. components)
  - Protected-path fail-closed: any collision touching a protected path
    is escalated to PROTECTED_PATH_COLLISION

Never issues a merge recommendation. Read-only classification only.
"""
from __future__ import annotations
import os
from pathlib import PurePosixPath
from typing import Literal

from tools.integration_intel_offline.denylist import classify_path

CollisionKind = Literal[
    "DIRECT_WRITE_COLLISION",
    "PROTECTED_PATH_COLLISION",
    "POSSIBLE_SHARED_CONTRACT",
    "NON_OVERLAP",
]


class PathNormError(ValueError):
    """Raised when a path cannot be safely normalized."""


def normalize_path(path: str) -> str:
    """Normalize to repo-relative PurePosixPath, reject traversal attempts."""
    # Reject any path that contains ".." or is absolute
    p = PurePosixPath(path)
    parts = p.parts
    if any(part == ".." for part in parts):
        raise PathNormError(f"Path traversal rejected: {path!r}")
    if p.is_absolute():
        raise PathNormError(f"Absolute path rejected: {path!r}")
    return str(p)


def normalize_set(paths: list[str]) -> set[str]:
    """Normalize a list of paths, discarding empty strings."""
    result = set()
    for p in paths:
        p = p.strip()
        if p:
            result.add(normalize_path(p))
    return result


def case_variants(paths: set[str]) -> list[tuple[str, str]]:
    """Return pairs of paths that differ only in case (Windows collision risk)."""
    lower_map: dict[str, list[str]] = {}
    for p in paths:
        lower_map.setdefault(p.lower(), []).append(p)
    conflicts = []
    for variants in lower_map.values():
        if len(variants) > 1:
            for i in range(len(variants)):
                for j in range(i + 1, len(variants)):
                    conflicts.append((variants[i], variants[j]))
    return conflicts


def classify_collision(
    paths_a: list[str],
    paths_b: list[str],
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """Classify the collision between two sets of changed paths.

    Returns a dict with:
      kind: CollisionKind
      shared_paths: list of shared normalized paths
      protected_collisions: list of protected paths involved
      case_conflicts: list of case-variant pairs
      analysis_note: human-readable explanation
    """
    norm_a = normalize_set(paths_a)
    norm_b = normalize_set(paths_b)
    shared = norm_a & norm_b

    # Check protected paths in shared set
    protected_shared = [p for p in shared if classify_path(p).status == "PROTECTED"]

    # Case-sensitivity check across combined set
    combined = norm_a | norm_b
    case_conflicts = case_variants(combined)

    if protected_shared:
        kind: CollisionKind = "PROTECTED_PATH_COLLISION"
        note = (
            f"PRs {label_a} and {label_b} both touch protected paths: {protected_shared}. "
            "Neither PR may proceed without owner authorization."
        )
    elif shared:
        kind = "DIRECT_WRITE_COLLISION"
        note = (
            f"PRs {label_a} and {label_b} both modify: {sorted(shared)}. "
            "Manual conflict resolution required before either can be reviewed."
        )
    else:
        # Check possible shared contract: a path in A is a parent dir of something in B
        possible = []
        for pa in norm_a:
            for pb in norm_b:
                if pb.startswith(pa + "/") or pa.startswith(pb + "/"):
                    possible.append((pa, pb))
        if possible:
            kind = "POSSIBLE_SHARED_CONTRACT"
            note = (
                f"PRs {label_a} and {label_b} have overlapping directory trees: {possible}. "
                "Review for import/interface contract conflicts."
            )
        else:
            kind = "NON_OVERLAP"
            note = f"PRs {label_a} and {label_b} have no overlapping paths."

    return {
        "kind": kind,
        "shared_paths": sorted(shared),
        "protected_collisions": protected_shared,
        "case_conflicts": case_conflicts,
        "analysis_note": note,
        "classification": "READ_ONLY__NOT_A_MERGE_DECISION",
    }


def analyze_snapshot_collisions(prs_with_paths: list[dict]) -> list[dict]:
    """Pairwise collision analysis across all PRs in a snapshot.

    Each element of prs_with_paths must have: number, changed_paths (list[str]).
    Returns list of collision records, one per pair where kind != NON_OVERLAP.
    """
    results = []
    n = len(prs_with_paths)
    for i in range(n):
        for j in range(i + 1, n):
            a = prs_with_paths[i]
            b = prs_with_paths[j]
            col = classify_collision(
                a["changed_paths"],
                b["changed_paths"],
                label_a=f"#{a['number']}",
                label_b=f"#{b['number']}",
            )
            if col["kind"] != "NON_OVERLAP":
                results.append({
                    "pr_a": a["number"],
                    "pr_b": b["number"],
                    **col,
                })
    return results
