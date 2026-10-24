"""Opt-in local snapshots and bounded verified restore. No pruning or offsite I/O."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
import uuid

from .contracts import canonical, digest, market_envelope, parse
from .local import check_path, child, mkdir, read_small, ro, source_row, sync_dir, write_new, writer_lock, verify_segment


def sqlite_snapshot(source, target, *, timeout=30, max_bytes=2_000_000_000):
    """Coherent SQLite backup, including committed WAL pages; bounded callback."""
    source, target = check_path(source), check_path(target)
    if target.exists():
        raise ValueError("Snapshot target must be new")
    deadline = time.monotonic()+timeout
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite snapshot deadline")
        if total*page_size > max_bytes:
            raise ValueError("SQLite snapshot byte budget")
    original = ro(source)
    page_size = original.execute("PRAGMA page_size").fetchone()[0]
    if original.execute("PRAGMA page_count").fetchone()[0]*page_size > max_bytes:
        original.close()
        raise ValueError("SQLite snapshot byte budget")
    # backup() has its own overall deadline; ro() SQL progress limit isn't a snapshot SLA.
    copied = sqlite3.connect(target, timeout=0.25)
    try:
        original.backup(copied, pages=128, progress=progress, sleep=0.01)
        if copied.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Incoherent SQLite snapshot")
    finally:
        original.close(); copied.close()
    with open(target, "r+b") as handle:
        os.fsync(handle.fileno())


def file_hash(path, *, max_bytes=2_000_000_000, deadline=None):
    path = check_path(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Regular snapshot file required")
    total = 0; hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk: break
            total += len(chunk)
            if total > max_bytes or deadline is not None and time.monotonic() > deadline:
                raise ValueError("Snapshot byte/time budget exhausted")
            hasher.update(chunk)
    return total, hasher.hexdigest()


def copy_new(source, target, *, budget, deadline):
    check_path(source); check_path(target)
    mkdir(target.parent)
    with open(source, "rb") as reader, open(target, "xb") as writer:
        while True:
            data = reader.read(1 << 20)
            if not data: break
            budget[0] -= len(data)
            if budget[0] < 0 or time.monotonic() > deadline:
                raise ValueError("Copy byte/time budget exhausted")
            writer.write(data)
        writer.flush(); os.fsync(writer.fileno())
    sync_dir(target.parent)


def verify_backup(root, *, expected_digest, max_files=8192, max_bytes=2_000_000_000, timeout=60):
    root = check_path(root)
    deadline = time.monotonic()+timeout
    inventory = parse(read_small(root/"inventory.json", 4 << 20))
    stored = inventory.pop("inventory_hash")
    if stored != expected_digest or digest(inventory) != stored or inventory["schema"] != "aql.backup.v1":
        raise ValueError("Backup retained commitment mismatch")
    if not 2 <= len(inventory["files"]) <= max_files:
        raise ValueError("Inventory file bound")
    seen = set(); total = 0
    allowed_dirs = set()
    for item in inventory["files"]:
        if time.monotonic() > deadline: raise TimeoutError("Verification deadline")
        if item["path"] in seen: raise ValueError("Duplicate inventory entry")
        seen.add(item["path"])
        path = child(root, item["path"])
        parts = item["path"].split("/")
        if len(parts) > 16: raise ValueError("Inventory path depth bound")
        allowed_dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
        size, actual = file_hash(path, max_bytes=max_bytes-total, deadline=deadline)
        total += size
        if size != item["bytes"] or actual != item["sha256"]:
            raise ValueError("Backup file checksum mismatch")
    for required in ("journal.sqlite", "archive/catalog.sqlite"):
        if required not in seen: raise ValueError("Required snapshot missing")
    # Verify exact file inventory, excluding no hidden attacker-controlled extras.
    actual_paths = set()
    expected_files = seen | {"inventory.json"}
    def scan(directory):
        # Stream entries: os.walk materializes an unbounded directory before
        # yielding. Reject even empty unlisted directories; depth is bounded16.
        with os.scandir(directory) as entries:
            for entry in entries:
                if time.monotonic() > deadline: raise TimeoutError("Verification deadline")
                path = check_path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.is_dir(follow_symlinks=False):
                    if relative not in allowed_dirs: raise ValueError("Unexpected snapshot directory")
                    scan(path)
                elif entry.is_file(follow_symlinks=False):
                    if relative not in expected_files: raise ValueError("Unexpected snapshot file")
                    actual_paths.add(relative)
                else:
                    raise ValueError("Nonregular snapshot entry")
    scan(root)
    if actual_paths != seen | {"inventory.json"}: raise ValueError("Unexpected snapshot files")
    # Only sealed SQLite backup-API outputs may use immutable=1 (never live WAL DBs).
    def sealed(path):
        conn = sqlite3.connect(check_path(path).as_uri()+"?mode=ro&immutable=1", uri=True, timeout=0.25)
        conn.row_factory = sqlite3.Row
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        return conn
    journal, catalog = sealed(root/"journal.sqlite"), sealed(root/"archive/catalog.sqlite")
    try:
        for conn in (journal, catalog):
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        if "operational.sqlite" in seen:
            operational = sealed(root/"operational.sqlite")
            try:
                if operational.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Operational SQLite integrity check failed")
            finally:
                operational.close()
        if catalog.execute("SELECT COUNT(*) FROM pending").fetchone()[0]:
            raise ValueError("Snapshot has unresolved archive intent")
        source_id = journal.execute("SELECT value FROM journal_meta WHERE key='instance_id'").fetchone()[0]
        if source_id != inventory["journal_id"]:
            raise ValueError("Snapshot journal identity mismatch")
        count = 0
        for relative, mh in catalog.execute("SELECT path,manifest_hash FROM segments ORDER BY path"):
            for name in ("records.jsonl", "manifest.json"):
                if "archive/"+relative+"/"+name not in seen:
                    raise ValueError("Missing sealed segment")
            records, manifest = verify_segment(child(root/"archive", relative), expected_hash=mh)
            for record in records:
                row = source_row(journal, record["source_seq"])
                if row is None or market_envelope(row, journal_id=source_id, market=record["market"], build=record["build"], policy=record["policy"], cutoff_ms=253402300799999) != record:
                    raise ValueError("Restored journal/archive record mismatch")
                index = catalog.execute("SELECT record_id,hash,segment FROM records WHERE seq=?", (record["source_seq"],)).fetchone()
                if tuple(index or ()) != (record["record_id"], record["envelope_hash"], relative):
                    raise ValueError("Restored index/key/hash mismatch")
                count += 1
                if time.monotonic() > deadline: raise TimeoutError("Verification deadline")
        indexed = catalog.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        index_max = catalog.execute("SELECT COALESCE(MAX(seq),0) FROM records").fetchone()[0]
        cursor = int(catalog.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0])
        maximum = journal.execute("SELECT COALESCE(MAX(id),0) FROM journal_entries").fetchone()[0]
        prefix = journal.execute("SELECT COUNT(*) FROM journal_entries WHERE id<=?", (cursor,)).fetchone()[0]
        if count != indexed or cursor != index_max or cursor > maximum or prefix != count:
            raise ValueError("Restored record inventory/watermark mismatch")
        journal_count = 0
        for sequence in journal.execute("SELECT id FROM journal_entries ORDER BY id"):
            row = source_row(journal, sequence[0])
            market_envelope(row, journal_id=source_id, market=inventory["market"],
                            build=inventory["build"], policy=inventory["policy"], cutoff_ms=253402300799999)
            journal_count += 1
            if time.monotonic() > deadline: raise TimeoutError("Journal validation deadline")
        if time.monotonic() > deadline: raise TimeoutError("Verification deadline")
        return {"records": count, "watermark": cursor, "journal_max_seq": maximum,
                "journal_records": journal_count,
                "files": len(seen), "bytes": total, "inventory_hash": stored,
                "off_device_protection": "NOT_VERIFIED"}
    finally:
        journal.close(); catalog.close()


def create_backup(archive, destination, *, operational_path=None, max_files=8192,
                  max_bytes=2_000_000_000, timeout=60):
    destination = check_path(destination)
    # Separate directory is required, but separation is NOT proof of another device.
    if destination == archive.root or destination.is_relative_to(archive.root) or archive.root.is_relative_to(destination):
        raise ValueError("Backup destination must not overlap primary archive")
    mkdir(destination)
    temporary = destination/(uuid.uuid4().hex+".partial")
    temporary.mkdir(); mkdir(temporary/"archive")
    deadline = time.monotonic()+timeout
    budget = [max_bytes]
    inventory = {"schema": "aql.backup.v1", "created_ms": int(time.time()*1000),
                 "journal_id": archive.journal_id, "files": [],
                 "market": archive.market, "build": archive.build, "policy": archive.policy,
                 "independent_device": "UNVERIFIED", "offsite": "NOT_PERFORMED"}
    with writer_lock(archive.root), archive.catalog() as catalog, archive.source() as source:
        archive.guard(catalog, source)
        if catalog.execute("SELECT COUNT(*) FROM pending").fetchone()[0]:
            raise ValueError("Resolve pending archive intent before backup")
        sqlite_snapshot(archive.journal_path, temporary/"journal.sqlite", timeout=max(0, deadline-time.monotonic()), max_bytes=budget[0])
        budget[0] -= (temporary/"journal.sqlite").stat().st_size
        sqlite_snapshot(archive.root/"catalog.sqlite", temporary/"archive/catalog.sqlite", timeout=max(0, deadline-time.monotonic()), max_bytes=budget[0])
        budget[0] -= (temporary/"archive/catalog.sqlite").stat().st_size
        names = ["journal.sqlite", "archive/catalog.sqlite"]
        if operational_path is not None:
            sqlite_snapshot(operational_path, temporary/"operational.sqlite", timeout=max(0, deadline-time.monotonic()), max_bytes=budget[0])
            budget[0] -= (temporary/"operational.sqlite").stat().st_size
            names.append("operational.sqlite")
        for relative, mh in catalog.execute("SELECT path,manifest_hash FROM segments ORDER BY path"):
            verify_segment(child(archive.root, relative), expected_hash=mh)
            for name in ("records.jsonl", "manifest.json"):
                if len(names) >= max_files: raise ValueError("Backup inventory file limit")
                target = "archive/"+relative+"/"+name
                copy_new(child(archive.root, relative+"/"+name), child(temporary, target), budget=budget, deadline=deadline)
                names.append(target)
        for relative in names:
            size, hashed = file_hash(child(temporary, relative), max_bytes=max_bytes, deadline=deadline)
            inventory["files"].append({"path": relative, "bytes": size, "sha256": hashed})
        if sum(f["bytes"] for f in inventory["files"]) > max_bytes:
            raise ValueError("Backup total byte budget")
        commitment = digest(inventory)
        write_new(temporary/"inventory.json", canonical({**inventory, "inventory_hash": commitment}))
        sync_dir(temporary/"archive"); sync_dir(temporary)
        evidence = verify_backup(temporary, expected_digest=commitment, max_files=max_files, max_bytes=max_bytes, timeout=max(0, deadline-time.monotonic()))
        final = destination/uuid.uuid4().hex
        os.rename(temporary, final); sync_dir(destination)
        archive.last_backup_ms = inventory["created_ms"]
        return final, evidence


def restore_backup(backup, destination, *, expected_digest, max_bytes=2_000_000_000, timeout=60):
    backup, destination = check_path(backup), check_path(destination)
    # No overwrite, even for an empty existing directory; no replacement of a primary.
    if destination.exists() or destination.is_relative_to(backup) or backup.is_relative_to(destination):
        raise ValueError("Restore requires new non-overlapping disposable directory")
    deadline = time.monotonic()+timeout
    evidence = verify_backup(backup, expected_digest=expected_digest, max_bytes=max_bytes, timeout=timeout)
    mkdir(destination.parent)
    temporary = destination.parent/(uuid.uuid4().hex+".restore-partial")
    temporary.mkdir()
    inventory = parse(read_small(backup/"inventory.json", 4 << 20))
    budget = [max_bytes+4*(1 << 20)]
    for relative in [item["path"] for item in inventory["files"]]+["inventory.json"]:
        copy_new(child(backup, relative), child(temporary, relative), budget=budget, deadline=deadline)
    sync_dir(temporary)
    restored = verify_backup(temporary, expected_digest=expected_digest, max_bytes=max_bytes, timeout=max(0, deadline-time.monotonic()))
    if restored != evidence: raise ValueError("Restore reconciliation mismatch")
    if destination.exists(): raise ValueError("Restore target appeared; refusing overwrite")
    os.rename(temporary, destination); sync_dir(destination.parent)
    return restored
