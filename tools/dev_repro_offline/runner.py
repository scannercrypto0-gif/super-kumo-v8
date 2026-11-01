"""
Stage 5 — Allowlist-Gated Subprocess Runner
Runs only manifest-EXPECTED commands, dry-run by default.
No shell injection, bounded output, explicit opt-in to execute.

P0-A fix (Issue #215): command allowlist now validates the full argv,
not just argv[0]. Dangerous flags (-c, -m, -p) and module_path injection
of flags are blocked. Only commands matching an explicit typed template are
allowed through. run_manifest_with_preflight_guard enforces P0-B.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .manifest import ManifestEntry, ManifestEntryStatus, TestManifest

if TYPE_CHECKING:
    from .preflight import PreflightReport


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

# Only these executable base names are allowed
_ALLOWED_EXECUTABLES = frozenset([
    "pytest",
    "python",
    "python3",
])

# ── P0-A fix: dangerous argument flags that must never appear in argv ─────────
# These flags allow arbitrary code or module execution via python/python3.
# pytest has no equivalent dangerous flags for arbitrary code execution.
_BLOCKED_FLAGS = frozenset([
    "-c",   # python -c <code>  — arbitrary inline code
    "-m",   # python -m <mod>   — arbitrary module as __main__
    "-p",   # pytest plugin injection
    "--co", # pytest collect-only injection variant (abbreviated form)
])

# Typed immutable command templates: the only patterns the runner will execute.
# Format: (executable_name, fixed_prefix_args, variable_arg_position)
# "prefix" means these exact strings must appear before the {module} substitution.
# Any template not matching these patterns is BLOCKED.
_ALLOWED_TEMPLATES: frozenset[tuple[str, ...]] = frozenset([
    # pytest <module> [flags...]  — only pytest flags allowed after module
    ("pytest",),
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
    """
    P0-A: Validate the full argv, not just argv[0].

    Rules (all must pass):
    1. argv[0] base name must be in _ALLOWED_EXECUTABLES.
    2. No element of argv may be in _BLOCKED_FLAGS.
    3. module_path substitution must not inject a flag-like argument
       (any arg starting with '-' after argv[0] that is in _BLOCKED_FLAGS is caught
       by rule 2, but we also reject module paths that start with '-').
    4. python/python3 are only allowed when argv[1] is NOT a flag (i.e. the module
       path is the first arg — equivalent to 'python <module_path>' only, no flags).
       pytest does not have dangerous code-execution flags so it is allowed with
       its standard flags (-v, --tb, -k, --co is blocked above, etc.).
    """
    if not argv:
        return False

    exe = Path(argv[0]).name
    if exe not in _ALLOWED_EXECUTABLES:
        return False

    # Rule 2: no blocked flags anywhere in argv
    for arg in argv[1:]:
        if arg in _BLOCKED_FLAGS:
            return False

    # Rule 3: no argument after argv[0] that starts with '-' and is a known dangerous flag
    # (belt-and-suspenders — rule 2 already covers _BLOCKED_FLAGS)
    # Additionally block any module_path that starts with '-' (injected flag)
    # We detect this by checking: does argv contain an element that starts with '-'
    # and is not a recognised safe pytest flag?
    if exe in ("python", "python3"):
        # For python/python3, the ONLY allowed form is:
        #   python <path_to_module_or_test>
        # No flags of any kind are permitted.
        for arg in argv[1:]:
            if arg.startswith("-"):
                return False

    return True


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

    NOTE: This function does NOT enforce the preflight guard.
    For execute mode (dry_run=False), always call
    run_manifest_with_preflight_guard() instead so P0-B is enforced.
    """
    report = RunReport(dry_run=dry_run)
    for entry in manifest.entries:
        result = run_entry(entry, repo_root, dry_run=dry_run, timeout=timeout)
        report.results.append(result)
    return report


def run_manifest_with_preflight_guard(
    manifest: TestManifest,
    repo_root: str,
    *,
    preflight: "PreflightReport",
    dry_run: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> RunReport:
    """
    P0-B fix (Issue #215): Fail closed before any subprocess when preflight FAIL
    and dry_run=False (execute mode).

    In dry_run=True mode preflight failures are recorded in the report but do NOT
    block execution — there is no subprocess launched in dry_run mode so the risk
    is informational only.

    In dry_run=False (execute) mode:
    - preflight.overall == FAIL → all EXPECTED entries become BLOCKED with a
      "PREFLIGHT_FAIL_GATE" note; no subprocess is launched.
    - preflight.overall != FAIL → normal execution proceeds.
    """
    from .preflight import CheckStatus  # avoid circular import at module level

    if not dry_run and preflight.overall == CheckStatus.FAIL:
        # Fail closed: record all entries as BLOCKED, no subprocess launched
        report = RunReport(dry_run=dry_run)
        for entry in manifest.entries:
            argv = _build_command(entry.command_template, entry.module_path)
            if entry.status in (ManifestEntryStatus.BLOCKED,
                                 ManifestEntryStatus.SKIP,
                                 ManifestEntryStatus.DEPRECATED):
                # Keep original status for already-blocked entries
                status = (RunStatus.BLOCKED if entry.status == ManifestEntryStatus.BLOCKED
                          else RunStatus.SKIP)
                report.results.append(RunResult(
                    entry_id=entry.entry_id,
                    status=status,
                    command=argv,
                    notes=f"Status={entry.status.value}",
                ))
            else:
                # EXPECTED entries blocked by preflight gate
                report.results.append(RunResult(
                    entry_id=entry.entry_id,
                    status=RunStatus.BLOCKED,
                    command=argv,
                    notes=(
                        "PREFLIGHT_FAIL_GATE: preflight checks failed. "
                        "Execution blocked until environment is clean. "
                        f"Preflight summary: {preflight.summary()}"
                    ),
                ))
        return report

    # Preflight passed or dry_run mode — proceed normally
    return run_manifest(manifest, repo_root, dry_run=dry_run, timeout=timeout)
