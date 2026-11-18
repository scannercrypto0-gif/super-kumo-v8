"""
Stage 3 — Test Manifest Catalog
Versioned allowlist of test commands with expected environment SHAs.
Missing tests → BLOCKED (never PASS).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class ManifestEntryStatus(str, Enum):
    EXPECTED   = "EXPECTED"    # command is listed and allowed
    BLOCKED    = "BLOCKED"     # required but not found / not executable
    SKIP       = "SKIP"        # explicitly excluded for this environment
    DEPRECATED = "DEPRECATED"  # entry kept for history, not executed


@dataclass
class ManifestEntry:
    entry_id: str                         # stable identifier  e.g. "CORE-W1-UNIT"
    label: str                            # human label
    command_template: str                 # e.g. "pytest {module} -v --tb=short"
    module_path: str                      # relative path to test module / dir
    expected_sha: str                     # expected HEAD sha this was valid at
    owner_issue: str                      # "#180", "#77", etc.
    status: ManifestEntryStatus = ManifestEntryStatus.EXPECTED
    notes: str = ""


@dataclass
class TestManifest:
    schema_version: str = "test_manifest.v1"
    created_at_utc: str = ""
    base_sha: str = ""                    # repo HEAD this manifest was built against
    entries: list[ManifestEntry] = field(default_factory=list)
    digest: str = ""

    def __post_init__(self):
        if not self.created_at_utc:
            self.created_at_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("digest", None)
        return d

    def compute_digest(self) -> str:
        canon = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()

    def refresh_digest(self) -> None:
        self.digest = self.compute_digest()

    def add(self, entry: ManifestEntry) -> None:
        # Reject duplicates
        ids = {e.entry_id for e in self.entries}
        if entry.entry_id in ids:
            raise ValueError(f"Duplicate entry_id: {entry.entry_id!r}")
        self.entries.append(entry)
        self.refresh_digest()

    def get(self, entry_id: str) -> Optional[ManifestEntry]:
        for e in self.entries:
            if e.entry_id == entry_id:
                return e
        return None

    def allowed_entries(self) -> list[ManifestEntry]:
        return [e for e in self.entries if e.status == ManifestEntryStatus.EXPECTED]

    def blocked_entries(self) -> list[ManifestEntry]:
        return [e for e in self.entries if e.status == ManifestEntryStatus.BLOCKED]


# ── serialisation ─────────────────────────────────────────────────────────────

def save_manifest(manifest: TestManifest, path: Path) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Manifest already exists at {path}; will not overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(manifest), fh, indent=2, ensure_ascii=False)
        fh.flush()
        import os
        os.fsync(fh.fileno())


def load_manifest(path: Path) -> TestManifest:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [ManifestEntry(**e) for e in data.get("entries", [])]
    m = TestManifest(
        schema_version=data.get("schema_version", ""),
        created_at_utc=data.get("created_at_utc", ""),
        base_sha=data.get("base_sha", ""),
        entries=entries,
        digest=data.get("digest", ""),
    )
    # Verify digest
    expected = m.compute_digest()
    if m.digest and m.digest != expected:
        raise ValueError(
            f"Manifest digest mismatch: stored={m.digest[:16]}... "
            f"computed={expected[:16]}... (file may be tampered)"
        )
    return m


# ── factory: build the standard W1 manifest ──────────────────────────────────

# Known SHAs from Issue #212 background:
_CORE_W1_SHA   = "6f8d64f"   # Core W1 (#180) — 12/12 owner-run passes
_FACTORY_W1_SHA = "57c8d35"  # Factory W1 (#77) — 7/7 owner-run passes
_MAIN_SHA       = "dbc191d"  # main branch HEAD at manifest creation


def build_w1_manifest(base_sha: str = _MAIN_SHA) -> TestManifest:
    """
    Build the standard W1 test manifest.
    Entries for Core and Factory are BLOCKED because those SHAs are not
    the current HEAD and cannot be assumed merged.
    Only the dev_repro_offline self-tests are EXPECTED.
    """
    manifest = TestManifest(base_sha=base_sha)

    # ── self-tests (this toolkit — EXPECTED) ─────────────────────────────────
    manifest.add(ManifestEntry(
        entry_id="REPRO-SELF-001",
        label="dev_repro_offline unit tests",
        command_template="pytest {module} -v --tb=short",
        module_path="tools/dev_repro_offline/tests/",
        expected_sha=base_sha,
        owner_issue="#212",
        status=ManifestEntryStatus.EXPECTED,
        notes="Fixture-driven; no live network; no protected namespace imports",
    ))

    # ── Core W1 (BLOCKED — different SHA, not on main) ───────────────────────
    manifest.add(ManifestEntry(
        entry_id="CORE-W1-UNIT",
        label="Core W1 unit tests (#180, SHA 6f8d64f…)",
        command_template="pytest tests/ -v --tb=short -k 'not integration'",
        module_path="tests/",
        expected_sha=_CORE_W1_SHA,
        owner_issue="#180",
        status=ManifestEntryStatus.BLOCKED,
        notes=(
            "Core W1 passes were recorded at SHA 6f8d64f… by Core owner. "
            "That SHA is not the current HEAD and is not verified merged. "
            "Running against current HEAD would produce undefined results."
        ),
    ))

    # ── Factory W1 (BLOCKED — different SHA, stacks on unmerged Core PR) ─────
    manifest.add(ManifestEntry(
        entry_id="FACTORY-W1-UNIT",
        label="Factory W1 unit tests (#77/PR#209, SHA 57c8d35…)",
        command_template="pytest tests/ -v --tb=short -k 'factory'",
        module_path="tests/",
        expected_sha=_FACTORY_W1_SHA,
        owner_issue="#77",
        status=ManifestEntryStatus.BLOCKED,
        notes=(
            "Factory W1 passes (7/7) were recorded at SHA 57c8d35… by Factory owner. "
            "PR #209 stacks on an earlier Core commit (not current HEAD). "
            "Not an integrated verification. Cannot be run here."
        ),
    ))

    manifest.refresh_digest()
    return manifest
