"""
Stage 5 — Allowlist-Gated Subprocess Runner
Runs only manifest-EXPECTED commands, dry-run by default.
No shell injection, bounded output, explicit opt-in to execute.

P0-A fix (Issue #215): command allowlist now validates the full argv,
not just argv[0]. Dangerous flags (-c, -m, -p) and module_path injection
of flags are blocked. Only commands matching an explicit typed template are
allowed through. run_manifest_with_preflight_guard enforces P0-B.

Gate 1 fix (Issue #215): strengthened _allowed() to close three gaps:
  G1-GAP-1: removed python/python3 from _ALLOWED_EXECUTABLES — they are
    not used in the manifest and their presence permitted arbitrary file
    execution (e.g. python ../../evil.py with no flags).
  G1-GAP-2: added path traversal and absolute path rejection for the
    module_path position (any argv element containing '../' or starting
    with '/' or '~' is BLOCKED).
  G1-GAP-4: added flag-injection detection for the module_path slot —
    any pytest argv element in position 1 (the module slot) that starts
    with '-' is BLOCKED (e.g. module_path='--forked' → BLOCKED).

Gate 5 escalated-gaps fix (Issue #215):
  G5-GAP-1: replaced _BLOCKED_FLAGS denylist with _APPROVED_PYTEST_FLAGS
    allowlist in Rule 2 — any flag not in the approved set is BLOCKED
    (e.g. --forked, --randomly-seed are no longer silently allowed).
  G5-GAP-2: run_entry() now accepts current_sha= and validates it against
    entry.expected_sha; a mismatch returns BLOCKED before any subprocess.
  G5-GAP-3: run_manifest(dry_run=False) now raises RuntimeError unless
    called internally via run_manifest_with_preflight_guard() — prevents
    callers from bypassing the P0-B preflight gate in execute mode.
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

# Only these executable base names are allowed.
# Gate 1 fix (G1-GAP-1): python/python3 removed — the manifest never uses
# them, and their presence permitted arbitrary file execution with no flags.
# If python execution is needed in future it must be re-added with strict
# approved-path enforcement.
_ALLOWED_EXECUTABLES = frozenset([
    "pytest",
])

# ── P0-A fix: dangerous argument flags that must never appear in argv ─────────
# These flags allow arbitrary code or module execution via python/python3.
# pytest has no equivalent dangerous flags for arbitrary code execution.
# Kept for backward reference; superseded by _APPROVED_PYTEST_FLAGS allowlist
# in Gate 5 (G5-GAP-1 fix).
_BLOCKED_FLAGS = frozenset([
    "-c",   # python -c <code>  — arbitrary inline code
    "-m",   # python -m <mod>   — arbitrary module as __main__
    "-p",   # pytest plugin injection
    "--co", # pytest collect-only injection variant (abbreviated form)
])

# ── Gate 5 / G5-GAP-1: approved pytest flags allowlist ───────────────────────
# Only these flags may appear in pytest argv.  Any flag not in this set is
# BLOCKED (allowlist model, not denylist).  Values following -k (e.g. "unit",
# "not integration") do not start with '-' and are not flag-checked.
# Source: the three command_template patterns used in the W1 manifest.
_APPROVED_PYTEST_FLAGS = frozenset([
    "-v",            # verbose output
    "-k",            # keyword/filter expression (value is next token)
    "-x",            # stop on first failure
    "-q",            # quiet
    "-s",            # no capture (stdout passthrough)
])

# --tb= prefix is approved; the suffix (short/long/no/auto/line/native) varies.
_APPROVED_PYTEST_FLAG_PREFIXES: tuple[str, ...] = (
    "--tb=",
)


def _is_approved_pytest_flag(arg: str) -> bool:
    """Return True if arg is an approved pytest flag or --tb=<anything>."""
    if arg in _APPROVED_PYTEST_FLAGS:
        return True
    for prefix in _APPROVED_PYTEST_FLAG_PREFIXES:
        if arg.startswith(prefix):
            return True
    return False


# Internal sentinel: run_manifest() passes this to indicate it was called from
# run_manifest_with_preflight_guard() (Gap 3 fix).
_PREFLIGHT_GUARD_TOKEN = object()

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
    Validate the full argv, not just argv[0].

    Rules (ALL must pass for the argv to be allowed):

    Rule 1 — Executable allowlist:
      argv[0] base name must be in _ALLOWED_EXECUTABLES (currently only 'pytest').
      Gate 1 fix (G1-GAP-1): python/python3 removed; manifest never uses them.

    Rule 2 — Approved pytest flags allowlist (Gate 5 / G5-GAP-1):
      Every element of argv[1:] that starts with '-' must be in
      _APPROVED_PYTEST_FLAGS or match an _APPROVED_PYTEST_FLAG_PREFIXES prefix.
      Replaces the old _BLOCKED_FLAGS denylist: instead of blocking known-bad
      flags, we block EVERYTHING not explicitly approved.  --forked, --randomly-seed
      and any other unapproved flag will now fail here.

    Rule 3 — No path traversal or absolute paths:
      No argv[1:] element may contain '../' (traversal) or start with '/' or '~'.
      Gate 1 fix (G1-GAP-2): pytest ../../etc/ and pytest /absolute/ are BLOCKED.

    Rule 4 — No module-position flag injection:
      argv[1] (the module/path slot after the executable) must not start with '-'.
      Gate 1 fix (G1-GAP-4): module_path='--forked' expanding to pytest --forked
      is BLOCKED; prevents flag injection through the module substitution slot.
      (Belt-and-suspenders: Rule 2 also catches this since --forked is unapproved.)
    """
    if not argv:
        return False

    exe = Path(argv[0]).name
    if exe not in _ALLOWED_EXECUTABLES:
        return False

    # Rule 2 (Gate 5 / G5-GAP-1): approved pytest flags allowlist.
    # Any element starting with '-' that is NOT in the approved set is BLOCKED.
    for arg in argv[1:]:
        if arg.startswith("-") and not _is_approved_pytest_flag(arg):
            return False

    # Rule 3 (Gate 1 / G1-GAP-2): no path traversal or absolute paths
    # Applied to ALL non-flag args (path-like positions).
    for arg in argv[1:]:
        if arg.startswith("/") or arg.startswith("~"):
            return False  # absolute path / home expansion
        if "../" in arg or arg == ".." or arg.endswith("/.."):
            return False  # path traversal sequence

    # Rule 4 (Gate 1 / G1-GAP-4): module-position flag injection
    # argv[1] is where the module_path substitution lands. If it starts with '-',
    # it was injected as a flag (e.g. module_path='--forked' → argv[1]='--forked').
    # Rule 2 also catches this, but Rule 4 makes the rejection explicit.
    if len(argv) >= 2 and argv[1].startswith("-"):
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
    current_sha: Optional[str] = None,
) -> RunResult:
    """
    Run a single manifest entry.
    dry_run=True (default) prints the command without executing.

    Gate 5 / G5-GAP-2: current_sha= (optional) — when provided AND
    entry.expected_sha is set, the two are compared using prefix matching
    (either is a prefix of the other → match).  A mismatch returns BLOCKED
    before any subprocess is launched, catching stale manifest entries running
    against a different commit than they were designed for.
    Pass current_sha=None (the default) to skip this check (backwards compatible).
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

    # Gate 5 / G5-GAP-2: runtime SHA check
    if current_sha and entry.expected_sha:
        sha_match = (
            current_sha.startswith(entry.expected_sha) or
            entry.expected_sha.startswith(current_sha)
        )
        if not sha_match:
            return RunResult(
                entry_id=entry.entry_id,
                status=RunStatus.BLOCKED,
                command=argv,
                notes=(
                    f"SHA_MISMATCH: entry.expected_sha={entry.expected_sha!r} "
                    f"does not match current_sha={current_sha!r}. "
                    "Update the manifest or switch to the correct commit (G5-GAP-2)."
                ),
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
    _preflight_guard_token: object = None,
) -> RunReport:
    """
    Run all entries in the manifest.
    BLOCKED/SKIP entries are recorded without executing.
    dry_run=True is the safe default.

    Gate 5 / G5-GAP-3: DIRECT EXECUTE MODE IS PROHIBITED.
    Calling run_manifest(dry_run=False) without the internal preflight guard
    would bypass the P0-B gate and launch subprocesses in an unvalidated
    environment.  This function now raises RuntimeError when dry_run=False
    and the internal _preflight_guard_token sentinel is not provided.

    For execute mode (dry_run=False), always call
    run_manifest_with_preflight_guard() instead — it validates the environment
    through the preflight gate BEFORE delegating to this function with the
    sentinel token.  dry_run=True mode remains unrestricted (no subprocess
    is launched in dry-run mode, so the risk is absent).
    """
    # Gate 5 / G5-GAP-3: enforce preflight guard for execute mode
    if not dry_run and _preflight_guard_token is not _PREFLIGHT_GUARD_TOKEN:
        raise RuntimeError(
            "Direct call to run_manifest(dry_run=False) is prohibited. "
            "Use run_manifest_with_preflight_guard() to enforce the P0-B "
            "preflight gate before launching subprocesses. (G5-GAP-3 fix)"
        )

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

    # Preflight passed or dry_run mode — proceed normally.
    # Pass the internal sentinel token so run_manifest() permits execute mode.
    return run_manifest(
        manifest, repo_root,
        dry_run=dry_run, timeout=timeout,
        _preflight_guard_token=_PREFLIGHT_GUARD_TOKEN,
    )
