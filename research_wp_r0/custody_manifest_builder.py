"""Offline research evidence manifest builder. No custody attestation or anchor upload.

Run on a finalized, quiescent research bundle. The returned digest must be
retained independently; this function never claims independent protection.
"""
import hashlib
import json
import os
from pathlib import Path
import stat


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_custody_manifest(bundle_root):
    """Write manifest exactly once, reject unsafe entries and concurrent drift."""
    root = Path(bundle_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Bundle root must be a directory")
    manifest = root / "custody-manifest.json"
    # Exclusive creation: never overwrite existing evidence manifest.
    if manifest.exists() or manifest.is_symlink():
        raise FileExistsError("Manifest already exists")
    entries = []
    pending = [root]
    while pending:
        folder = pending.pop()
        for path in folder.iterdir():
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError("Symlink in evidence bundle")
            if stat.S_ISDIR(mode):
                pending.append(path)
            elif stat.S_ISREG(mode):
                if path == manifest:
                    raise FileExistsError("Manifest appeared during inventory")
                entries.append((path.relative_to(root).as_posix(), path, path.stat()))
            else:
                raise ValueError("Unsupported filesystem entry")
    if not entries:
        raise ValueError("Empty evidence bundle")
    rows = []
    for name, path, before in sorted(entries):
        digest = _digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Evidence changed while hashing")
        rows.append({"path": name, "sha256": digest})
    # Detect added/deleted files before publishing the manifest.
    current = set()
    pending = [root]
    while pending:
        for path in pending.pop().iterdir():
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                pending.append(path)
            elif not stat.S_ISREG(mode):
                raise ValueError("Unsafe entry appeared during inventory")
            else:
                current.add(path.relative_to(root).as_posix())
    if current != {r["path"] for r in rows}:
        raise ValueError("Bundle changed during inventory")
    raw = (json.dumps({"schema": "atlas-custody-v1", "files": rows},
                      sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    with manifest.open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    return {"manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "file_count": len(rows), "independent_custody_verified": False}
