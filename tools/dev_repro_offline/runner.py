"""
Stage 5 — Allowlist-Gated Subprocess Runner
Runs only manifest-EXPECTED commands, dry-run by default.
No shell injection, bounded output, explicit opt-in to execute.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .manifest import ManifestEntry, ManifestEntryStatus, TestManifest


class RunStatus(str, Enum):
    PASS        = "PASS"
    FAIL        = "FAIL"
    BLOCKED     = "BLOCKED"    # manifest entry status is BLOCKED — not run
    DRY_RUN     = "DRY_RUN"    # dry_run=True — command printed, not executed
    TIMEOUT     = "TIMEOUT"
    ERROR       = "ERROR"      # subprocess could not be launched
    SKIP        = "SKIP"       # manifest status is SKIP or DEPRECATED


@dataclass
class RunResult:
    entry_id: str
    status: RunStatus
    command: list[str]
    returncode: Optional[int] = None
    stdout_excerpt: str = ""    # capped at MAX_OUTPUT_BYTES
    stderr_excerpt: str = ""
    elapsed_seconds: float = 0.0
    notes: str = ""


@dataclass
class RunReport:
    dry_run: bool
    results: list[RunResult] = field(default_factory=list)

    def summary(self) -> str:
        counts: dict[RunStatus, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        parts = [f"{k.value}={v}" for k, v in sorted(counts.items(), key=lambda x: x[0])]
        tag = "DRY-RUN" if self.dry_run else "EXECUTED"
        return f"RUN [{tag}] " + " ".join(parts)


# ── constants ─────────────────────────────────────────────────────────────────

MAX_OUTPUT_BYTES = 32_768          # 32 KB per stream
DEFAULT_TIMEOUT  = 120             # seconds

# Only these executable prefixes are allowed
_ALLOWED_EXECUTABLES = frozenset([
    "pytest",
    "python",
    "python3",
])


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_command(template: str, module_path: str) -> list[str]:
    """
    Expand the command template and return an argv list.
    The only allowed substitution is {module}.
    No shell=True — arguments are passed as a list.
    """
    filled = template.replace("{module}", module_path)
    return filled.split()


def _allowed(argv: list[str]) -> bool:
    """Check that the executable base name is in the allowlist."""
    if not argv:
        return False
    exe = Path(argv[0]).name
    return exe in _ALLOWED_EXECUTABLES


def _cap(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    b = text.encode("utf-8", errors="replace")
    if len(b) <= max_bytes:
        return text
    return b[:max_bytes].decode("utf-8", errors="replace") + "\n...[TRUNCATED]"


# ── public API ────────────────────────────────────────────────────────────────

def run_entry(
    entry: ManifestEntry,
    repo_root: str,
    *,
    dry_run: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> RunResult:
    """
    Run a single manifest entry.
    dry_run=True (default) prints the command without executing.
    """
    argv = _build_command(entry.command_template, entry.module_path)

    if entry.status == ManifestEntryStatus.BLOCKED:
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.BLOCKED,
            command=argv,
            notes=f"BLOCKED: {entry.notes}",
        )

    if entry.status in (ManifestEntryStatus.SKIP, ManifestEntryStatus.DEPRECATED):
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.SKIP,
            command=argv,
            notes=f"Status={entry.status.value}",
        )

    if not _allowed(argv):
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.BLOCKED,
            command=argv,
            notes=f"Executable '{argv[0] if argv else '?'}' not in allowlist.",
        )

    if dry_run:
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.DRY_RUN,
            command=argv,
            notes="dry_run=True; pass dry_run=False to execute.",
        )

    # ── actual execution ──────────────────────────────────────────────────────
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=repo_root,
        )
        elapsed = time.monotonic() - start
        ok = proc.returncode == 0
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.PASS if ok else RunStatus.FAIL,
            command=argv,
            returncode=proc.returncode,
            stdout_excerpt=_cap(proc.stdout),
            stderr_excerpt=_cap(proc.stderr),
            elapsed_seconds=elapsed,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.TIMEOUT,
            command=argv,
            elapsed_seconds=elapsed,
            notes=f"Timed out after {timeout}s",
            stdout_excerpt=_cap(exc.stdout or ""),
            stderr_excerpt=_cap(exc.stderr or ""),
        )
    except Exception as exc:
        return RunResult(
            entry_id=entry.entry_id,
            status=RunStatus.ERROR,
            command=argv,
            notes=str(exc),
        )


def run_manifest(
    manifest: TestManifest,
    repo_root: str,
    *,
    dry_run: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> RunReport:
    """
    Run all entries in the manifest.
    BLOCKED/SKIP entries are recorded without executing.
    dry_run=True is the safe default.
    """
    report = RunReport(dry_run=dry_run)
    for entry in manifest.entries:
        result = run_entry(entry, repo_root, dry_run=dry_run, timeout=timeout)
        report.results.append(result)
    return report
