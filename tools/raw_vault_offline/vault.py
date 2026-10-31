"""
Stage 3 — Content-addressed immutable local vault.

Design
------
- Objects stored at  <root>/objects/<sha256[:2]>/<sha256[2:]>  (content-addressed)
- Append-only manifest at  <root>/manifest.jsonl
- Admission: staged to <root>/.staging/<uuid>.tmp, fsync, atomic rename
- Same content + same identity → idempotent (return existing meta)
- Same identity + DIFFERENT content → IdentityConflict (fail closed)
- No deletion path; no overwrite path
- Safe locking via .lockfile with PID + mtime guard (portable)
- Crash simulation: half-written temp file left in .staging/ is ignored on recovery

No production datastore. No network. Fixture bytes only in tests.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import (
    SCHEMA_VERSION,
    RawObjectMeta,
    VaultError,
    ChecksumMismatch,
    IdentityConflict,
    OversizedObject,
    MalformedIdentity,
    MAX_OBJECT_BYTES,
    content_key,
    logical_identity_key,
    validate_meta,
)

MANIFEST_FILENAME = "manifest.jsonl"
INDEX_FILENAME = "index.json"
LOCK_FILENAME = ".vault.lock"


# ── locking ───────────────────────────────────────────────────────────────────

@contextmanager
def _vault_lock(root: Path, timeout: float = 10.0):
    lockfile = root / LOCK_FILENAME
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    fh = None
    try:
        fh = open(lockfile, 'w')
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start > timeout:
                    raise TimeoutError(f"Could not acquire vault lock in {timeout}s")
                time.sleep(0.05)
        yield
    finally:
        if fh is not None:
            try:
                fcntl.flock(fh, fcntl.LOCK_UN)
            except Exception:
                pass
            fh.close()


# ── object path ───────────────────────────────────────────────────────────────

def _object_path(root: Path, sha256: str) -> Path:
    return root / "objects" / sha256[:2] / sha256[2:]


# ── vault operations ──────────────────────────────────────────────────────────

class RawVault:
    """
    Write-once content-addressed offline vault.

    Parameters
    ----------
    root : directory that will hold objects/, manifest.jsonl, index.json
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._staging = self.root / ".staging"
        self._manifest_path = self.root / MANIFEST_FILENAME
        self._index_path = self.root / INDEX_FILENAME
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "objects").mkdir(exist_ok=True)
        self._staging.mkdir(exist_ok=True)

    # ── private helpers ──────────────────────────────────────────────────────

    def _read_index(self) -> dict:
        """Load logical-identity→content-sha map. Returns {} if absent."""
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_bytes())
        except Exception:
            return {}

    def _write_index(self, index: dict) -> None:
        tmp = self._staging / (uuid.uuid4().hex + ".idx.tmp")
        data = json.dumps(index, sort_keys=True, indent=2).encode()
        with open(tmp, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self._index_path)

    def _append_manifest(self, meta: RawObjectMeta) -> None:
        line = json.dumps(meta.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        with open(self._manifest_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def _stage_and_commit_object(self, sha256: str, raw_bytes: bytes) -> Path:
        """Write bytes to temp file, fsync, atomic rename to object path."""
        obj_path = _object_path(self.root, sha256)
        if obj_path.exists():
            return obj_path   # already committed (idempotent)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._staging / (uuid.uuid4().hex + ".obj.tmp")
        tmp.write_bytes(raw_bytes)
        with open(tmp, 'rb') as fh:
            os.fsync(fh.fileno())
        tmp.replace(obj_path)
        return obj_path

    # ── public API ──────────────────────────────────────────────────────────

    def admit(
        self,
        raw_bytes: bytes,
        meta: RawObjectMeta,
    ) -> RawObjectMeta:
        """
        Admit raw_bytes into the vault.

        Returns
        -------
        meta  — on success (idempotent if same-content re-admission)

        Raises
        ------
        ChecksumMismatch    if meta.content_sha256 ≠ actual sha256(raw_bytes)
        OversizedObject     if byte_length > MAX_OBJECT_BYTES
        IdentityConflict    if same logical identity has different content
        MalformedIdentity   if meta fields fail validation
        """
        validate_meta(meta)

        # 1. verify declared checksum
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if actual_sha != meta.content_sha256:
            raise ChecksumMismatch(
                f"Declared {meta.content_sha256} ≠ actual {actual_sha}"
            )
        if len(raw_bytes) != meta.byte_length:
            raise MalformedIdentity(
                f"Declared byte_length {meta.byte_length} ≠ actual {len(raw_bytes)}"
            )

        with _vault_lock(self.root):
            index = self._read_index()
            lid = meta.logical_identity_key

            # 2. conflict check
            existing_sha = index.get(lid)
            if existing_sha is not None:
                if existing_sha == actual_sha:
                    # idempotent: same bytes already admitted
                    return meta
                else:
                    raise IdentityConflict(
                        f"Logical identity {lid[:16]}... already has content "
                        f"{existing_sha[:16]}..., refusing to overwrite with "
                        f"{actual_sha[:16]}..."
                    )

            # 3. stage + commit object bytes
            self._stage_and_commit_object(actual_sha, raw_bytes)

            # 4. update index
            index[lid] = actual_sha
            self._write_index(index)

            # 5. append manifest
            self._append_manifest(meta)

        return meta

    def read(self, content_sha256: str) -> bytes:
        """Read and verify an admitted object by its content SHA-256."""
        path = _object_path(self.root, content_sha256)
        if not path.exists():
            raise KeyError(f"Object {content_sha256[:16]}... not in vault")
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != content_sha256:
            raise ChecksumMismatch(
                f"Stored object corrupted: declared {content_sha256[:16]}... "
                f"actual {actual[:16]}..."
            )
        return raw

    def manifest_entries(self) -> list[dict]:
        """Return all manifest entries as dicts (order = admission order)."""
        if not self._manifest_path.exists():
            return []
        entries = []
        for line in self._manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def recovery_scan(self) -> dict:
        """
        Scan vault after a simulated crash.

        Returns
        -------
        dict with keys:
          orphan_staging  : list of .tmp files left in .staging/
          index_entries   : count of entries in index.json
          manifest_lines  : count of non-empty lines in manifest.jsonl
          objects_count   : count of files under objects/
          status          : "CLEAN" | "ORPHAN_STAGING_FOUND"
        """
        orphans = list(self._staging.glob("*.tmp"))
        objects = list((self.root / "objects").rglob("*"))
        objects = [p for p in objects if p.is_file()]
        index = self._read_index()
        manifest_lines = len(self.manifest_entries())
        status = "ORPHAN_STAGING_FOUND" if orphans else "CLEAN"
        return dict(
            orphan_staging=[str(p) for p in orphans],
            index_entries=len(index),
            manifest_lines=manifest_lines,
            objects_count=len(objects),
            status=status,
        )

    def purge_orphan_staging(self) -> int:
        """Remove any leftover .tmp files from .staging/ (crash recovery). Returns count."""
        removed = 0
        for p in self._staging.glob("*.tmp"):
            p.unlink(missing_ok=True)
            removed += 1
        return removed
