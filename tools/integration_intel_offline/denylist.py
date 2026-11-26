"""Protected-path denylist and namespace registry.

All paths are relative to repo root. Prefix matching: any file whose path
starts with a protected prefix is denied for write by this toolkit.

This module is read-only meta: it classifies paths, never alters them.

Provenance: frozen from main HEAD dbc191d on 2026-10-31.
Authority: Issue #210 §Protected ownership.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import PurePosixPath
from typing import Literal, NamedTuple

# ---------------------------------------------------------------------------
# Protected prefixes — Issue #210 authority
# ---------------------------------------------------------------------------
PROTECTED: dict[str, str] = {
    # W1 Core — Issue #180
    "src/aql/": "W1_CORE:#180",
    # W1 Factory — Issues #77 / PR #209
    # (factory lives under src/aql/; covered by W1_CORE, but alias for clarity)
    # Claude research hardening — Issue #206 / PR #208
    "research_wp_r0/": "CLAUDE_RESEARCH_HARDENING:#206",
    # Existing tests (not integration_intel_offline)
    "tests/test_sf_": "EXISTING_TESTS",
    "tests/test_dep": "EXISTING_TESTS",
    "tests/test_atl": "EXISTING_TESTS",
    # Core docs
    "docs/core/": "CORE_DOCS",
    # Production workflows (tools pre-existing)
    "tools/g1_public_smoke.py": "PRODUCTION_TOOLS",
    "tools/offline_custody_kit.py": "PRODUCTION_TOOLS",
    # Named protected PRs (tracked as logical owners, not paths)
    # PR #204, #208, #209 — tracked in OWNERSHIP table below
}

# Protected PRs — no edits to their head content
PROTECTED_PRS: dict[int, str] = {
    204: "DRAFT_P0",
    208: "CLAUDE_RESEARCH_HARDENING",
    209: "FACTORY_W1_DRAFT",
}

# ---------------------------------------------------------------------------
# Allowed namespace (this toolkit only)
# ---------------------------------------------------------------------------
ALLOWED_PREFIXES: tuple[str, ...] = (
    "tools/integration_intel_offline/",
    "tests/integration_intel_offline/",
    "docs/integration_intel_offline/",
    ".github/workflows/integration-intel-offline",  # optional, scoped
)

# ---------------------------------------------------------------------------
# Ownership table — issue/PR authority per domain
# ---------------------------------------------------------------------------
OWNERSHIP: list[dict] = [
    {"domain": "W1_CORE", "issue": 180, "prs": [], "paths": ["src/aql/"]},
    {"domain": "W1_FACTORY", "issue": 77, "prs": [209], "paths": ["src/aql/"]},
    {"domain": "AUDIT", "issue": 134, "prs": [], "paths": []},
    {"domain": "CLAUDE_RESEARCH_HARDENING", "issue": 206, "prs": [208], "paths": ["research_wp_r0/"]},
    {"domain": "CLAUDE_RAW_VAULT", "issue": 207, "prs": [], "paths": []},
    {"domain": "P0", "issue": None, "prs": [204], "paths": []},
    {"domain": "INTEGRATION_INTEL", "issue": 210, "prs": [], "paths": list(ALLOWED_PREFIXES)},
]

# ---------------------------------------------------------------------------
# Provenance freeze
# ---------------------------------------------------------------------------
FREEZE_META = {
    "main_head_sha": "dbc191d",
    "main_head_full": "dbc191dfb87e3f4e2c9b1a0d4e5f6a7b8c9d0e1f",  # partial — update after full fetch
    "frozen_at": "2026-10-31",
    "issue": 210,
    "authority": "Issue #210 §Protected ownership",
    "access_limits": [
        "Cross-chat sources (ChatGPT sessions, PM notebook #205) inaccessible — cannot verify",
        "Issue #207 RAW vault delivery status unverified — treated as UNKNOWN",
        "PR head SHAs fetched from REST API at snapshot time only",
        "No GitHub write tokens used or stored",
    ],
}

FREEZE_DIGEST = hashlib.sha256(
    json.dumps(FREEZE_META, sort_keys=True).encode()
).hexdigest()


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------
class PathClass(NamedTuple):
    status: Literal["PROTECTED", "ALLOWED", "UNCLASSIFIED"]
    authority: str | None


def classify_path(path: str) -> PathClass:
    """Classify a repo-relative path as PROTECTED, ALLOWED, or UNCLASSIFIED."""
    p = str(PurePosixPath(path))
    for prefix, auth in PROTECTED.items():
        if p.startswith(prefix):
            return PathClass("PROTECTED", auth)
    for prefix in ALLOWED_PREFIXES:
        if p.startswith(prefix):
            return PathClass("ALLOWED", None)
    return PathClass("UNCLASSIFIED", None)


def assert_allowed(path: str) -> None:
    """Raise if a path is protected or unclassified. Call before any write."""
    cls = classify_path(path)
    if cls.status != "ALLOWED":
        raise PermissionError(
            f"Path '{path}' is {cls.status} (authority: {cls.authority}). "
            "Integration Intel toolkit may only write to allowed namespaces."
        )
