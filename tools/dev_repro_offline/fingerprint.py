"""
Stage 2 — Environment Fingerprint
Deterministic, privacy-safe schema covering runtime, OS, filesystem,
locale, and git state.  No credentials, no home paths, no user names.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import locale
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── privacy filters ─────────────────────────────────────────────────────────

_HOME = str(Path.home())
_USER = os.environ.get("USER", os.environ.get("USERNAME", ""))


def _redact(value: str) -> str:
    """Remove home path and username from any string."""
    v = value.replace(_HOME, "<HOME>")
    if _USER:
        v = v.replace(_USER, "<USER>")
    return v


def _safe_env(key: str, default: str = "") -> str:
    return _redact(os.environ.get(key, default))


# ── git helpers ──────────────────────────────────────────────────────────────

def _git(args: list[str], cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=10, cwd=cwd
        )
        return result.stdout.strip() if result.returncode == 0 else f"ERROR:{result.stderr.strip()[:120]}"
    except Exception as exc:
        return f"EXCEPTION:{exc}"


# ── dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class GitState:
    head_sha: str
    branch: str
    is_dirty: bool
    untracked_count: int
    remote_url_redacted: str
    describe: str


@dataclass
class RuntimeInfo:
    python_version: str
    python_executable_hash: str   # SHA-256 of interpreter path string (no path exposed)
    platform_system: str
    platform_release: str
    platform_machine: str
    locale_encoding: str
    filesystem_encoding: str
    path_sep: str
    line_sep_repr: str            # 'LF', 'CRLF', or 'CR'


@dataclass
class PackageVersions:
    pytest: str
    pip: str


@dataclass
class EnvironmentFingerprint:
    schema_version: str
    captured_at_utc: str
    repo_root_hash: str           # SHA-256 of redacted absolute path
    git: GitState
    runtime: RuntimeInfo
    packages: PackageVersions
    digest: str = ""              # SHA-256(canonical JSON of all other fields)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("digest", None)
        return d

    def compute_digest(self) -> str:
        canon = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()


# ── collection ───────────────────────────────────────────────────────────────

def _pkg_version(pkg: str) -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version(pkg)
    except Exception:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", pkg],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "UNKNOWN"


def _line_sep_repr() -> str:
    sep = os.linesep
    if sep == "\r\n":
        return "CRLF"
    if sep == "\r":
        return "CR"
    return "LF"


def collect(repo_root: Optional[str] = None) -> EnvironmentFingerprint:
    """
    Collect a privacy-safe environment fingerprint.

    Parameters
    ----------
    repo_root : str, optional
        Absolute path to repository root. Defaults to cwd.
    """
    root = str(Path(repo_root).resolve()) if repo_root else os.getcwd()
    root_hash = hashlib.sha256(_redact(root).encode()).hexdigest()

    # git state
    head_sha = _git(["rev-parse", "HEAD"], root)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    status_out = _git(["status", "--porcelain"], root)
    is_dirty = bool(status_out and not status_out.startswith("ERROR"))
    untracked = sum(1 for l in status_out.splitlines() if l.startswith("??"))
    remote_url = _git(["remote", "get-url", "origin"], root)
    # scrub tokens embedded in HTTPS URLs  https://TOKEN@github.com/...
    if "@" in remote_url:
        parts = remote_url.split("@", 1)
        remote_url = "<REDACTED_AUTH>@" + parts[1]
    describe = _git(["describe", "--tags", "--always", "--dirty"], root)

    git_state = GitState(
        head_sha=head_sha,
        branch=branch,
        is_dirty=is_dirty,
        untracked_count=untracked,
        remote_url_redacted=remote_url,
        describe=describe,
    )

    # python hash — we hash the path string, not expose it
    py_path_hash = hashlib.sha256(
        _redact(sys.executable).encode()
    ).hexdigest()[:16]

    enc = locale.getpreferredencoding(False) or "UNKNOWN"
    fs_enc = sys.getfilesystemencoding() or "UNKNOWN"

    runtime = RuntimeInfo(
        python_version=sys.version.split()[0],
        python_executable_hash=py_path_hash,
        platform_system=platform.system(),
        platform_release=platform.release(),
        platform_machine=platform.machine(),
        locale_encoding=enc,
        filesystem_encoding=fs_enc,
        path_sep=os.sep,
        line_sep_repr=_line_sep_repr(),
    )

    packages = PackageVersions(
        pytest=_pkg_version("pytest"),
        pip=_pkg_version("pip"),
    )

    fp = EnvironmentFingerprint(
        schema_version="env_fingerprint.v1",
        captured_at_utc=datetime.now(timezone.utc).isoformat(),
        repo_root_hash=root_hash,
        git=git_state,
        runtime=runtime,
        packages=packages,
    )
    fp.digest = fp.compute_digest()
    return fp


def save(fp: EnvironmentFingerprint, path: Path) -> None:
    """Write fingerprint to JSON file (no overwrite — fail closed)."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Fingerprint already exists at {path}; will not overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {"fingerprint": asdict(fp)},
            fh, indent=2, ensure_ascii=False
        )
        fh.flush()
        import os as _os
        _os.fsync(fh.fileno())
