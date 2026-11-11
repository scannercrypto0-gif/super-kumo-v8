"""
Stage 6 — Immutable Evidence Bundles
Write-once, digest-protected evidence package.
No overwrite.  Tamper detection on load.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .fingerprint import EnvironmentFingerprint
from .manifest import TestManifest
from .preflight import PreflightReport, CheckStatus
from .runner import RunReport, RunStatus


@dataclass
class EvidenceBundle:
    schema_version: str = "evidence_bundle.v1"
    bundle_id: str = ""
    created_at_utc: str = ""
    issue: str = "#212"
    fingerprint_digest: str = ""
    manifest_digest: str = ""
    preflight_overall: str = ""
    run_summary: str = ""
    blocked_entries: list[str] = field(default_factory=list)
    pass_entries: list[str] = field(default_factory=list)
    fail_entries: list[str] = field(default_factory=list)
    # redacted excerpt from stdout — never full output
    excerpts: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    digest: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("digest", None)
        return d

    def compute_digest(self) -> str:
        canon = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()

    def refresh_digest(self) -> None:
        self.digest = self.compute_digest()


def build_evidence_bundle(
    fp: EnvironmentFingerprint,
    manifest: TestManifest,
    preflight: PreflightReport,
    run_report: RunReport,
    *,
    bundle_id: str = "",
    notes: str = "",
    max_excerpt_chars: int = 2000,
) -> EvidenceBundle:
    """
    Assemble an immutable evidence bundle from all stage outputs.
    Excerpts are capped; no raw credentials or home paths included.
    """
    import uuid
    bid = bundle_id or str(uuid.uuid4())[:12]

    blocked = [r.entry_id for r in run_report.results if r.status == RunStatus.BLOCKED]
    passed  = [r.entry_id for r in run_report.results if r.status == RunStatus.PASS]
    failed  = [r.entry_id for r in run_report.results if r.status == RunStatus.FAIL]

    excerpts: dict[str, str] = {}
    for r in run_report.results:
        if r.stdout_excerpt:
            excerpts[r.entry_id + ".stdout"] = r.stdout_excerpt[:max_excerpt_chars]
        if r.stderr_excerpt and r.status not in (RunStatus.PASS, RunStatus.DRY_RUN):
            excerpts[r.entry_id + ".stderr"] = r.stderr_excerpt[:max_excerpt_chars]

    bundle = EvidenceBundle(
        bundle_id=bid,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        fingerprint_digest=fp.digest,
        manifest_digest=manifest.digest,
        preflight_overall=preflight.overall.value,
        run_summary=run_report.summary(),
        blocked_entries=blocked,
        pass_entries=passed,
        fail_entries=failed,
        excerpts=excerpts,
        notes=notes,
    )
    bundle.refresh_digest()
    return bundle


def save_bundle(bundle: EvidenceBundle, path: Path) -> None:
    """Write bundle to JSON — raises FileExistsError if path exists (immutable)."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Evidence bundle already exists at {path}; will not overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(bundle)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())


def load_bundle(path: Path) -> EvidenceBundle:
    """Load and verify bundle digest (tamper detection)."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    b = EvidenceBundle(**data)
    stored = b.digest
    b.digest = ""
    expected = b.compute_digest()
    if stored and stored != expected:
        raise ValueError(
            f"Evidence bundle digest mismatch: stored={stored[:16]}… "
            f"computed={expected[:16]}… (file may be tampered)"
        )
    b.digest = stored
    return b
