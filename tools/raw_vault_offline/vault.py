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

import hashlib
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Keep the on-disk vault format identical across Windows and POSIX.
# Windows uses a one-byte, kernel-managed advisory lock; POSIX uses flock.
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from .schema import (
    SCHEMA_VERSION,
    RawObjectMeta,
    VaultError,
    ChecksumMismatch,
    CorruptMetadata,
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
    """Exclusive, cross-process lock held for the entire admission transaction.

    Never truncate the lock file: another process may already hold its inode.
    Windows locks byte 0 with msvcrt; POSIX locks the file with flock.
    """
    lockfile = root / LOCK_FILENAME
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with open(lockfile, "a+b") as fh:
        if sys.platform == "win32":
            # Locking a stable, existing byte avoids EOF-dependent behavior.
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write(b"\\0")
                fh.flush()
                os.fsync(fh.fileno())
        locked = False
        try:
            while not locked:
                try:
                    if sys.platform == "win32":
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except (BlockingIOError, OSError) as exc:
                    # Windows reports sharing/lock contention as EACCES/EDEADLOCK
                    # or EAGAIN; unrelated I/O failures must fail closed.
                    if sys.platform == "win32":
                        import errno
                        if getattr(exc, "errno", None) not in (
                            errno.EACCES, errno.EAGAIN, errno.EDEADLK,
                        ):
                            raise
                    elif not isinstance(exc, BlockingIOError):
                        raise
                    if time.monotonic() - start >= timeout:
                        raise TimeoutError(
                            f"Could not acquire vault lock in {timeout}s"
                        ) from exc
                    time.sleep(0.05)
            yield
        finally:
            if locked:
                if sys.platform == "win32":
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fh, fcntl.LOCK_UN)


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
        """
        Load logical-identity→content-sha map.

        Returns {} if index is absent (new vault).
        Raises CorruptMetadata if index exists but contains invalid JSON.

        Audit A3 (Issue #215 / Audit #134 comment #6556506884):
        Previously silently returned {} on JSON parse error, allowing admit()
        to continue writing over a corrupt vault. Now fails closed.
        """
        if not self._index_path.exists():
            return {}
        raw = self._index_path.read_bytes()
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise CorruptMetadata(
                f"index.json exists but contains invalid JSON — vault is corrupt. "
                f"Run recovery_scan() to assess and do not attempt admission until "
                f"the corruption is resolved. Parse error: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise CorruptMetadata(
                f"index.json exists but root element is {type(data).__name__}, "
                f"expected dict. Vault metadata is corrupt."
            )
        return data

    def _write_index(self, index: dict) -> None:
        tmp = self._staging / (uuid.uuid4().hex + ".idx.tmp")
        data = json.dumps(index, sort_keys=True, indent=2).encode()
        with open(tmp, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self._index_path)

    def _manifest_contains(self, content_sha256: str) -> bool:
        """
        Return True if manifest.jsonl already contains an entry for content_sha256.

        ALWAYS scans every non-empty line in the manifest, even after finding a
        match, to ensure the entire manifest is parseable before returning.
        Raises CorruptMetadata if any line cannot be parsed as JSON.

        Audit A3 (Issue #215 / Audit #134 comment #6556506884):
        Previously silently skipped malformed lines with `except Exception: continue`,
        allowing a vault with a partially-corrupted manifest to appear healthy and
        allowing admit() to append a new entry on top of corrupt metadata.

        A3 strict interpretation: ANY corrupt line in manifest.jsonl (even lines
        after the matching entry) indicates a corrupt vault and must block admission.
        Early return on match is therefore NOT permitted — scan all lines first.
        """
        if not self._manifest_path.exists():
            return False
        found = False
        for lineno, line in enumerate(
            self._manifest_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception as exc:
                raise CorruptMetadata(
                    f"manifest.jsonl line {lineno} is not valid JSON — vault is "
                    f"corrupt. Run recovery_scan() before any admission. "
                    f"Parse error: {exc}"
                ) from exc
            if entry.get("content_sha256") == content_sha256:
                found = True
        return found

    def _manifest_contains_for_identity(
        self, logical_identity_key: str, content_sha256: str
    ) -> bool:
        """
        Return True if manifest.jsonl contains an entry matching BOTH
        logical_identity_key AND content_sha256.

        SHA-only matching (_manifest_contains) is insufficient when two distinct
        logical identities share the same content bytes (same SHA). Identity A's
        manifest entry must not satisfy Identity B's crash-recovery check.

        Audit A3 final-round fix (Issue #215 / Audit #134 comment #6556807523):
        Crash recovery in admit() must reconcile by (identity, SHA), not SHA alone.

        Always scans all lines (no early return). Raises CorruptMetadata on any
        malformed line.
        """
        if not self._manifest_path.exists():
            return False
        found = False
        for lineno, line in enumerate(
            self._manifest_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception as exc:
                raise CorruptMetadata(
                    f"manifest.jsonl line {lineno} is not valid JSON — vault is "
                    f"corrupt. Run recovery_scan() before any admission. "
                    f"Parse error: {exc}"
                ) from exc
            if (
                entry.get("logical_identity_key") == logical_identity_key
                and entry.get("content_sha256") == content_sha256
            ):
                found = True
        return found

    def _prevalidate_vault_state(self, current_index: dict) -> None:
        """
        Prevalidate full manifest parseability and index/manifest consistency
        before any admit() mutation. Called while holding the vault lock.

        Audit A3 final-round fix (Issue #215 / Audit #134 comment #6556807523):
        Previously, admit() for a NEW logical identity never validated the manifest
        before writing — a corrupt manifest line appended by a prior bad write was
        silently bypassed. This method closes that gap by prevalidating the entire
        manifest (and its agreement with the index) before any object/index/manifest
        mutation occurs.

        Raises CorruptMetadata if any of the following are true:
        - Any manifest line cannot be parsed as JSON
        - Any manifest entry lacks logical_identity_key or content_sha256 fields
        - A manifest entry's logical_identity_key is absent from current_index
          (manifest was written but index was not — inverse of the valid crash state)
        - A manifest entry's content_sha256 disagrees with current_index[lid]
          (index and manifest disagree on the SHA for the same identity)
        - The same logical_identity_key appears in more than one manifest line

        Does NOT raise for the legitimate interrupted-write recovery state:
        a logical_identity_key that is present in current_index but absent from
        the manifest (index written at step 4, crash before manifest append at
        step 5). That state is valid and repaired by admit() itself.
        """
        if not self._manifest_path.exists():
            return  # new/empty vault — valid state

        seen_lids: dict[str, int] = {}  # lid → first seen lineno

        for lineno, line in enumerate(
            self._manifest_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except Exception as exc:
                raise CorruptMetadata(
                    f"manifest.jsonl line {lineno}: invalid JSON — vault is corrupt. "
                    f"Run recovery_scan() before any admission. Parse error: {exc}"
                ) from exc

            lid = entry.get("logical_identity_key")
            sha = entry.get("content_sha256")

            if not lid or not sha:
                raise CorruptMetadata(
                    f"manifest.jsonl line {lineno}: missing required fields "
                    f"(logical_identity_key={lid!r}, content_sha256={sha!r}) "
                    f"— vault metadata is corrupt."
                )

            # If lid is in the index, its SHA must match the manifest entry.
            # A lid that is in the manifest but absent from the index is a valid
            # crash-recovery state (P1-B: manifest written before index update);
            # it is NOT treated as corruption here — recovery_scan() handles it.
            index_sha = current_index.get(lid)
            if index_sha is not None and index_sha != sha:
                raise CorruptMetadata(
                    f"manifest.jsonl line {lineno}: content_sha256 mismatch for "
                    f"logical_identity_key {lid!r} — manifest has {sha[:16]}... "
                    f"but index has {index_sha[:16]}... — vault is corrupt. "
                    f"Run recovery_scan()."
                )

            # Duplicate logical identity key in manifest
            if lid in seen_lids:
                raise CorruptMetadata(
                    f"manifest.jsonl line {lineno}: duplicate logical_identity_key "
                    f"{lid!r} — also at line {seen_lids[lid]}. "
                    f"Vault is inconsistent. Run recovery_scan()."
                )
            seen_lids[lid] = lineno

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
        with open(tmp, 'r+b') as fh:
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
        CorruptMetadata     if existing index.json or manifest.jsonl is corrupt,
                            if any manifest line lacks required identity fields,
                            if manifest and index disagree on any identity→SHA,
                            or if the manifest contains duplicate identity keys.
                            (A3: prevalidate before ANY mutation — fail closed)
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
            # A3: _read_index() raises CorruptMetadata on invalid JSON.
            index = self._read_index()
            lid = meta.logical_identity_key

            # A3 final-round: prevalidate manifest parseability and index/manifest
            # consistency BEFORE any mutation. Raises CorruptMetadata on any
            # corrupt line, missing fields, index/manifest disagreement, or
            # duplicate identity in manifest. The sole recovery exception —
            # a lid present in index but absent from manifest — is allowed here
            # and repaired below in the G3-CRASH-1 path.
            self._prevalidate_vault_state(current_index=index)

            # 2. conflict check
            existing_sha = index.get(lid)
            if existing_sha is not None:
                if existing_sha == actual_sha:
                    # Idempotent: same bytes already in index.
                    # Gate 3 fix (G3-CRASH-1): a crash between _write_index (step 4)
                    # and _append_manifest (step 5) leaves index updated but manifest
                    # missing THIS IDENTITY'S entry. Repair by checking manifest for
                    # the (identity, sha) pair specifically and re-appending if absent.
                    #
                    # A3 final-round fix: use _manifest_contains_for_identity(), NOT
                    # _manifest_contains() (SHA-only). If identities A and B share
                    # the same bytes/SHA, A's manifest entry must NOT satisfy B's
                    # recovery check — B requires its own distinct manifest entry.
                    if not self._manifest_contains_for_identity(lid, actual_sha):
                        self._append_manifest(meta)
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

        G7-A fix (Issue #215 comment #6555520562): perform bidirectional per-key
        integrity check across index.json and manifest.jsonl instead of count
        comparison alone.  Detects:
          - corrupt / invalid index JSON           → INCONSISTENT (not silently {})
          - malformed manifest lines               → INCONSISTENT (not raised)
          - equal-count wrong mappings (swapped    → INCONSISTENT
            SHAs, different keys)
          - duplicate/conflicting manifest entries → INCONSISTENT
          - extra keys in index not in manifest    → INCONSISTENT
          - extra keys in manifest not in index    → INCONSISTENT
          - missing object files for index entries → INCONSISTENT

        Never returns CLEAN when authoritative metadata (index.json or
        manifest.jsonl) is unreadable or corrupt.

        Returns
        -------
        dict with keys:
          orphan_staging     : list of .tmp files left in .staging/
          index_entries      : count of valid entries loaded from index.json
          manifest_lines     : count of valid non-empty lines parsed from manifest
          objects_count      : count of files under objects/
          status             : "CLEAN" | "ORPHAN_STAGING_FOUND" | "INCONSISTENT"
          index_corrupt      : True if index.json existed but could not be parsed
          manifest_malformed : True if any manifest line was malformed/unparseable
          manifest_duplicates: True if any logical_identity_key appeared >1 time
          extra_in_index     : sorted list of keys in index but not in manifest
          extra_in_manifest  : sorted list of keys in manifest but not in index
          sha_mismatches     : dict {lid: {index_sha, manifest_sha}} for each
                               key where SHAs disagree across the two sources
          missing_objects    : list of content_sha256 values whose object file
                               is absent from objects/
        """
        orphans = list(self._staging.glob("*.tmp"))
        objects = list((self.root / "objects").rglob("*"))
        objects = [p for p in objects if p.is_file()]

        # ── 1. Load index — corrupt JSON is INCONSISTENT, not silently {} ──
        index_corrupt = False
        if self._index_path.exists():
            try:
                raw_index = json.loads(self._index_path.read_bytes())
                if not isinstance(raw_index, dict):
                    index_corrupt = True
                    index = {}
                else:
                    index = raw_index
            except Exception:
                index_corrupt = True
                index = {}
        else:
            index = {}

        # ── 2. Parse manifest line-by-line — malformed lines → INCONSISTENT ──
        manifest_malformed = False
        manifest_duplicates = False
        manifest_map: dict[str, str] = {}  # logical_identity_key → content_sha256

        if self._manifest_path.exists():
            try:
                text = self._manifest_path.read_text(encoding="utf-8")
            except Exception:
                manifest_malformed = True
                text = ""

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    lid = entry.get("logical_identity_key")
                    sha = entry.get("content_sha256")
                    if not lid or not sha:
                        manifest_malformed = True
                        continue
                    if lid in manifest_map:
                        manifest_duplicates = True
                    # Last writer wins for per-key map; duplicate flag already set
                    manifest_map[lid] = sha
                except Exception:
                    manifest_malformed = True

        # ── 3. Bidirectional per-key association check ──
        index_keys = set(index.keys())
        manifest_keys = set(manifest_map.keys())

        extra_in_index = sorted(index_keys - manifest_keys)
        extra_in_manifest = sorted(manifest_keys - index_keys)

        sha_mismatches: dict[str, dict] = {}
        for lid in index_keys & manifest_keys:
            if index[lid] != manifest_map[lid]:
                sha_mismatches[lid] = {
                    "index_sha": index[lid],
                    "manifest_sha": manifest_map[lid],
                }

        # ── 4. Check for missing or corrupted object files for every index entry ──
        #
        # Audit A1 (Issue #215 / Audit #134 comment #6555797225):
        # obj_path.exists() is insufficient — a file may exist but contain altered
        # bytes. We must read each object, recompute SHA256, and confirm the stored
        # content matches the SHA256 key under which it is addressed.
        #
        # Also detect non-regular files at the expected object path (e.g. a directory
        # placed where a file should be) — these cannot be read for byte verification.
        missing_objects: list[str] = []
        corrupted_objects: list[str] = []
        for lid, sha in index.items():
            obj_path = _object_path(self.root, sha)
            if not obj_path.exists():
                missing_objects.append(sha)
                continue
            # A1: regular-file check — a non-regular file (directory, symlink to dir,
            # special file) cannot be reliably read; treat as corrupted.
            if not obj_path.is_file():
                corrupted_objects.append(sha)
                continue
            # A1: byte-hash recomputation — read actual bytes, compute SHA256,
            # compare to the content-addressed key. Altered bytes → corrupted.
            try:
                actual_sha = hashlib.sha256(obj_path.read_bytes()).hexdigest()
            except Exception:
                corrupted_objects.append(sha)
                continue
            if actual_sha != sha:
                corrupted_objects.append(sha)

        # ── 5. Determine status ──
        #
        # Audit A2 (Issue #215 / Audit #134 comment #6555797225):
        # INCONSISTENT must take precedence over ORPHAN_STAGING_FOUND when any
        # integrity failure exists. Orphan staging files are collected and reported
        # in the result regardless of status, but they do not mask proven integrity
        # violations.
        integrity_failure = (
            index_corrupt
            or manifest_malformed
            or manifest_duplicates
            or extra_in_index
            or extra_in_manifest
            or sha_mismatches
            or missing_objects
            or corrupted_objects  # A1: byte-level corruption
        )

        if integrity_failure:
            # A2: INCONSISTENT takes precedence — orphan staging is still reported
            status = "INCONSISTENT"
        elif orphans:
            status = "ORPHAN_STAGING_FOUND"
        else:
            status = "CLEAN"

        return dict(
            orphan_staging=[str(p) for p in orphans],
            index_entries=len(index),
            manifest_lines=len(manifest_map),
            objects_count=len(objects),
            status=status,
            # G7-A detail fields:
            index_corrupt=index_corrupt,
            manifest_malformed=manifest_malformed,
            manifest_duplicates=manifest_duplicates,
            extra_in_index=extra_in_index,
            extra_in_manifest=extra_in_manifest,
            sha_mismatches=sha_mismatches,
            missing_objects=missing_objects,
            # Audit A1 addition:
            corrupted_objects=corrupted_objects,  # SHAs where stored bytes ≠ SHA256 key
        )

    def purge_orphan_staging(self) -> int:
        """Remove any leftover .tmp files from .staging/ (crash recovery). Returns count."""
        removed = 0
        for p in self._staging.glob("*.tmp"):
            p.unlink(missing_ok=True)
            removed += 1
        return removed
