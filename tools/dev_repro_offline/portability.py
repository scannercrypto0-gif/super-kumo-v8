"""
Stage 8 — Cross-Platform Portability Wrappers
Generates Bash and PowerShell wrapper stubs for the runner CLI.
Marks untested platforms explicitly; never claims Windows-tested if not run there.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PlatformStatus(str, Enum):
    TESTED      = "TESTED"
    UNTESTED    = "UNTESTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class PlatformInfo:
    system: str               # "Linux", "Windows", "Darwin"
    status: PlatformStatus
    notes: str = ""


def detect_platform() -> PlatformInfo:
    system = platform.system()
    if system == "Linux":
        return PlatformInfo(system, PlatformStatus.TESTED,
                            "Primary development platform.")
    if system == "Darwin":
        return PlatformInfo(system, PlatformStatus.UNTESTED,
                            "macOS not CI-tested; Bash wrapper should work.")
    if system == "Windows":
        return PlatformInfo(system, PlatformStatus.UNTESTED,
                            "Windows not CI-tested; use PowerShell wrapper.")
    return PlatformInfo(system, PlatformStatus.UNSUPPORTED,
                        f"Unknown platform: {system}")


# ── wrapper generators ────────────────────────────────────────────────────────

_BASH_TEMPLATE = """\
#!/usr/bin/env bash
# AQL dev_repro_offline — Bash wrapper (auto-generated)
# Platform status: {platform_status}
# Notes: {platform_notes}
# SAFE: dry-run by default; pass --execute to actually run tests.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

DRY_RUN=1
for arg in "$@"; do
  case "$arg" in
    --execute) DRY_RUN=0 ;;
  esac
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[DRY-RUN] Preflight + manifest check only (no tests executed)."
  python -m tools.dev_repro_offline.cli --dry-run
else
  echo "[EXECUTE] Running allowed tests."
  python -m tools.dev_repro_offline.cli --execute
fi
"""

_PWSH_TEMPLATE = """\
# AQL dev_repro_offline — PowerShell wrapper (auto-generated)
# Platform status: {platform_status}
# Notes: {platform_notes}
# SAFE: dry-run by default; pass -Execute to actually run tests.
# WARNING: UNTESTED on Windows CI — validate before relying on this.
param([switch]$Execute)

$RepoRoot = git rev-parse --show-toplevel
Push-Location $RepoRoot

if ($Execute) {{
    Write-Host "[EXECUTE] Running allowed tests."
    python -m tools.dev_repro_offline.cli --execute
}} else {{
    Write-Host "[DRY-RUN] Preflight + manifest check only."
    python -m tools.dev_repro_offline.cli --dry-run
}}

Pop-Location
"""


def generate_bash_wrapper(info: PlatformInfo) -> str:
    return _BASH_TEMPLATE.format(
        platform_status=info.status.value,
        platform_notes=info.notes,
    )


def generate_pwsh_wrapper(info: PlatformInfo) -> str:
    return _PWSH_TEMPLATE.format(
        platform_status=info.status.value,
        platform_notes=info.notes,
    )


def write_wrappers(output_dir: Path, info: PlatformInfo) -> dict[str, Path]:
    """
    Write both wrappers into output_dir.
    Returns mapping of wrapper name → path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bash_path = output_dir / "run_repro.sh"
    pwsh_path = output_dir / "run_repro.ps1"

    bash_path.write_text(generate_bash_wrapper(info), encoding="utf-8")
    bash_path.chmod(0o755)

    pwsh_path.write_text(generate_pwsh_wrapper(info), encoding="utf-8")

    return {"bash": bash_path, "powershell": pwsh_path}
