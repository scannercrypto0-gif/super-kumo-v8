"""Sealed bounded JSONL segments with transactional independent checkpoints.

Opt-in offline sidecar. No journal/hot ACK mutation or production wiring.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import sqlite3
import time
import uuid

from .contracts import canonical, digest, market_envelope, parse

MAX_BYTES = 262144
MAX_RECORD_BYTES = 16384


def source_row(conn, sequence):
    size = conn.execute("SELECT length(CAST(payload_json AS BLOB))+length(stable_key)+length(checksum) FROM journal_entries WHERE id=?", (sequence,)).fetchone()
    if size is None:
        return None
    if size[0] > MAX_RECORD_BYTES:
        raise ValueError("Oversized source record denied before materialization")
    return conn.execute("SELECT id,stable_key,payload_json,checksum FROM journal_entries WHERE id=?", (sequence,)).fetchone()


def check_path(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(getattr(info, "st_mode", 0)) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Symlink/reparse paths denied")
    return path


def child(root, relative):
    if type(relative) is not str or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Invalid relative inventory path")
    parts = relative.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("Path escape denied")
    path = check_path(Path(root).joinpath(*parts))
    path.relative_to(Path(root).absolute())
    return path


def sync_dir(path):
    if os.name == "nt":
        return False  # No portable directory fsync; never claim power-loss certification.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def mkdir(path):
    path = check_path(path)
    if not path.exists():
        mkdir(path.parent)
        path.mkdir(exist_ok=True)
        sync_dir(path.parent)
    return path


def write_new(path, data):
    check_path(path)
    with open(path, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def read_small(path, maximum=MAX_BYTES):
    path = check_path(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Regular archive file required")
    with open(path, "rb") as handle:
        value = handle.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("Archive file exceeds bound")
    return value


def ro(path):
    path = check_path(path)
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.25)
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + 2
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    return conn


@contextmanager
def writer_lock(root):
    """Real interprocess lock, fixed inode; never unlink a held lock file."""
    lock = check_path(Path(root) / "writer.lock")
    with open(lock, "a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0"); handle.flush(); os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(seq INTEGER PRIMARY KEY,record_id TEXT UNIQUE NOT NULL,
 hash TEXT NOT NULL,segment TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS segments(path TEXT PRIMARY KEY,manifest_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS coverage(symbol TEXT,interval TEXT,last_open INTEGER,
 PRIMARY KEY(symbol,interval));
CREATE TABLE IF NOT EXISTS pending(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 path TEXT NOT NULL,manifest_hash TEXT NOT NULL);
"""


def verify_segment(path, *, expected_hash):
    path = check_path(path)
    manifest = parse(read_small(path / "manifest.json", 65536))
    stored = manifest.pop("manifest_hash")
    if stored != expected_hash or digest(manifest) != stored:
        raise ValueError("Manifest commitment mismatch")
    raw = read_small(path / "records.jsonl")
    if hashlib.sha256(raw).hexdigest() != manifest["data_sha256"]:
        raise ValueError("Archive payload corruption")
    rows = [parse(line) for line in raw.splitlines()]
    if len(rows) != manifest["count"] or not 1 <= len(rows) <= 128:
        raise ValueError("Invalid bounded record count")
    for record in rows:
        fields = dict(record); stored = fields.pop("envelope_hash")
        if digest(fields) != stored or record["schema"] != "aql.market-archive.v1":
            raise ValueError("Envelope integrity failure")
    if ([r["source_seq"] for r in rows] != manifest["source_sequences"] or
            digest([r["record_id"] for r in rows]) != manifest["key_digest"] or
            digest([r["envelope_hash"] for r in rows]) != manifest["envelope_digest"]):
        raise ValueError("Key/sequence reconciliation failure")
    return rows, {**manifest, "manifest_hash": expected_hash}


class LocalArchive:
    def __init__(self, journal_path, root, *, market, build, policy,
                 batch_size=64, reserve_bytes=10_000_000_000, fault=None):
        for value in (market, build, policy):
            if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
                raise ValueError("Explicit safe market/build/policy required")
        if type(batch_size) is not int or not 1 <= batch_size <= 128:
            raise ValueError("Batch size must be1..128")
        if type(reserve_bytes) is not int or reserve_bytes < 0:
            raise ValueError("Explicit nonnegative disk reserve required")
        self.journal_path = check_path(journal_path)
        self.root = mkdir(root)
        self.root_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        self.market, self.build, self.policy = market, build, policy
        self.batch_size, self.reserve_bytes = batch_size, reserve_bytes
        self.fault = fault or (lambda stage: None)
        self.last_error = None
        self.last_check_ms = None
        self.last_backup_ms = None
        with self.source() as conn:
            self.journal_id = conn.execute("SELECT value FROM journal_meta WHERE key='instance_id'").fetchone()[0]
        self.identity = digest([str(self.journal_path), self.journal_id, market, build, policy])
        with writer_lock(self.root), self.catalog() as conn:
            conn.executescript(SCHEMA)
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('identity',?)", (self.identity,))
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('cursor','0')")
            if conn.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0] != self.identity:
                raise ValueError("Archive belongs to different source/configuration")

    @contextmanager
    def source(self):
        conn = ro(self.journal_path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def catalog(self):
        if (self.root.stat().st_dev, self.root.stat().st_ino) != self.root_identity:
            raise ValueError("Archive directory replaced")
        check_path(self.root / "catalog.sqlite")
        conn = sqlite3.connect(self.root / "catalog.sqlite", timeout=0.25)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            with conn:
                yield conn
        finally:
            conn.close()

    def guard(self, catalog, source):
        check_path(self.root)
        if (self.root.stat().st_dev, self.root.stat().st_ino) != self.root_identity:
            raise ValueError("Archive directory replaced")
        identity = source.execute("SELECT value FROM journal_meta WHERE key='instance_id'").fetchone()
        if not identity or identity[0] != self.journal_id:
            raise ValueError("Journal replaced")
        if catalog.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0] != self.identity:
            raise ValueError("Catalog identity replaced")
        cursor = int(catalog.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0])
        maximum = source.execute("SELECT COALESCE(MAX(id),0) FROM journal_entries").fetchone()[0]
        if cursor > maximum:
            raise ValueError("Journal rollback behind archive watermark")
        if cursor:
            row = source_row(source, cursor)
            if row is None or self.envelope(row)["envelope_hash"] != catalog.execute("SELECT hash FROM records WHERE seq=?", (cursor,)).fetchone()[0]:
                raise ValueError("Journal anchor changed")
        return cursor

    def envelope(self, row):
        return market_envelope(row, journal_id=self.journal_id, market=self.market,
                               build=self.build, policy=self.policy, cutoff_ms=int(time.time()*1000))

    def adopt(self, conn, source, pending):
        relative, expected = pending
        records, manifest = verify_segment(child(self.root, relative), expected_hash=expected)
        sync_dir(child(self.root, relative)); sync_dir(child(self.root, relative).parent)
        cursor = self.guard(conn, source)
        if records[0]["source_seq"] <= cursor:
            raise ValueError("Pending segment overlaps acknowledged watermark")
        for record in records:
            row = source_row(source, record["source_seq"])
            if row is None or self.envelope(row) != record:
                raise ValueError("Archive/source mismatch")
            old = conn.execute("SELECT hash FROM records WHERE record_id=?", (record["record_id"],)).fetchone()
            if old:
                raise ValueError("Conflicting/duplicate source identity")
            conn.execute("INSERT INTO records VALUES (?,?,?,?)", (record["source_seq"], record["record_id"], record["envelope_hash"], relative))
            conn.execute("INSERT OR REPLACE INTO coverage VALUES (?,?,?)",
                         (record["bar"]["symbol"], record["bar"]["interval"], record["bar"]["bar_open"]))
        conn.execute("INSERT INTO segments VALUES (?,?)", (relative, expected))
        self.fault("before_ack")
        conn.execute("UPDATE meta SET value=? WHERE key='cursor'", (str(manifest["completion_watermark"]),))
        conn.execute("DELETE FROM pending")
        return len(records)

    def drain_once(self, stop_event=None):
        try:
            result = self._drain(stop_event)
            self.last_error = None
            return result
        except Exception as error:
            self.last_error = type(error).__name__  # never log raw paths/payloads/secrets
            raise
        finally:
            self.last_check_ms = int(time.time()*1000)

    def _drain(self, stop_event):
        import shutil
        with writer_lock(self.root), self.catalog() as conn, self.source() as source:
            cursor = self.guard(conn, source)
            pending = conn.execute("SELECT path,manifest_hash FROM pending").fetchone()
            if pending and child(self.root, pending[0]).exists():
                return self.adopt(conn, source, pending)
            if stop_event is not None and stop_event.is_set():
                return 0
            if shutil.disk_usage(self.root).free < self.reserve_bytes + 2*MAX_BYTES:
                raise OSError("Archive disk reserve reached")
            sequences = source.execute("SELECT id FROM journal_entries WHERE id>? ORDER BY id LIMIT ?", (cursor, self.batch_size)).fetchall()
            rows = [source_row(source, row[0]) for row in sequences]
            if not rows:
                return 0
            records, payloads = [], []
            partition = None
            for row in rows:
                record = self.envelope(row)
                date = datetime.fromtimestamp(record["bar"]["bar_open"]/1000, timezone.utc).strftime("%Y-%m-%d")
                current = (self.market, record["bar"]["interval"], date)
                if partition is not None and current != partition:
                    break
                if not re.fullmatch(r"[A-Za-z0-9]{1,12}", current[1]):
                    raise ValueError("Invalid partition interval")
                payload = canonical(record)+b"\n"
                if sum(map(len, payloads)) + len(payload) > MAX_BYTES:
                    break
                partition = current
                records.append(record); payloads.append(payload)
            if not records:
                raise ValueError("Record exceeds batch byte limit")
            raw = b"".join(payloads)
            # Gaps are explicitly within THIS segment/symbol coverage, not global completeness.
            coverage = {}
            from ..recovery.gap_recovery import _binance_interval_ms
            for record in records:
                bar = record["bar"]; symbol = bar["symbol"]
                if symbol not in coverage:
                    previous = conn.execute("SELECT last_open FROM coverage WHERE symbol=? AND interval=?", (symbol, bar["interval"])).fetchone()
                    coverage[symbol] = {"count": 0, "first_open_ms": bar["bar_open"], "last_open_ms": previous[0] if previous else None, "previous_segment_open_ms": previous[0] if previous else None, "gaps": [], "out_of_order": False}
                item = coverage[symbol]
                if item["last_open_ms"] is not None:
                    delta = bar["bar_open"] - item["last_open_ms"]
                    width = _binance_interval_ms(bar["interval"])
                    if delta <= 0: item["out_of_order"] = True
                    elif delta > width: item["gaps"].append([item["last_open_ms"]+width, bar["bar_open"]])
                item["count"] += 1; item["last_open_ms"] = bar["bar_open"]
            manifest = {"schema": "aql.segment.v1", "journal_id": self.journal_id,
                        "build": self.build, "policy": self.policy, "partition": list(partition),
                        "count": len(records), "source_sequences": [r["source_seq"] for r in records],
                        "completion_watermark": records[-1]["source_seq"],
                        "min_open_ms": min(r["bar"]["bar_open"] for r in records),
                        "max_close_ms": max(r["bar"]["bar_close"] for r in records),
                        "data_sha256": hashlib.sha256(raw).hexdigest(),
                        "key_digest": digest([r["record_id"] for r in records]),
                        "envelope_digest": digest([r["envelope_hash"] for r in records]),
                        "coverage": coverage, "coverage_scope": "OBSERVED_JOURNAL_PREFIX_NOT_FULL_MARKET",
                        "cross_segment_coverage": "PREVIOUS_ARCHIVED_SYMBOL_OPEN_BOUND",
                        "missing_fields": sorted(set(k for r in records for k in r["missing"]))}
            mh = digest(manifest)
            relative = "/".join(("segments", *partition, f"{records[0]['source_seq']}-{records[-1]['source_seq']}-{mh[:20]}"))
            if pending and tuple(pending) != (relative, mh):
                raise ValueError("Pending source/configuration changed")
            conn.execute("INSERT OR IGNORE INTO pending VALUES (1,?,?)", (relative, mh))
            conn.commit()  # Intent survives restart; independent of existing journal ACK.
            destination = child(self.root, relative)
            mkdir(destination.parent)
            temporary = child(self.root, relative+".partial")
            if temporary.exists():
                quarantine = mkdir(self.root/"quarantine") / uuid.uuid4().hex
                os.rename(temporary, quarantine); sync_dir(quarantine.parent); sync_dir(temporary.parent)
            temporary.mkdir(); sync_dir(temporary.parent)
            self.fault("before_write")
            write_new(temporary/"records.jsonl", raw)
            self.fault("after_data")
            write_new(temporary/"manifest.json", canonical({**manifest, "manifest_hash": mh}))
            self.fault("after_manifest")
            sync_dir(temporary)
            if destination.exists():
                raise ValueError("Refusing to overwrite sealed segment")
            os.rename(temporary, destination)
            sync_dir(destination.parent)
            self.fault("after_rename")
            return self.adopt(conn, source, (relative, mh))

    def health(self, *, now_ms=None, max_age_ms=60000, backup_max_age_ms=3600000):
        import shutil
        now_ms = int(time.time()*1000) if now_ms is None else now_ms
        data = {"status": "UNHEALTHY", "last_error": self.last_error,
                "directory_fsync": "UNSUPPORTED" if os.name == "nt" else "SUPPORTED",
                "off_device_protection": "NOT_VERIFIED", "backup_age_ms": None}
        try:
            with self.catalog() as conn, self.source() as source:
                cursor = self.guard(conn, source)
                data["backlog"] = source.execute("SELECT COUNT(*) FROM journal_entries WHERE id>?", (cursor,)).fetchone()[0]
                data["watermark"] = cursor
            data["free_bytes"] = shutil.disk_usage(self.root).free
            data["backup_age_ms"] = None if self.last_backup_ms is None else now_ms-self.last_backup_ms
            fresh = self.last_check_ms is not None and 0 <= now_ms-self.last_check_ms <= max_age_ms
            backed = data["backup_age_ms"] is not None and 0 <= data["backup_age_ms"] <= backup_max_age_ms
            if fresh and not self.last_error and data["free_bytes"] >= self.reserve_bytes+2*MAX_BYTES:
                data["status"] = "HEALTHY" if not data["backlog"] and backed and os.name != "nt" else "DEGRADED"
        except Exception as error:
            data["telemetry_error"] = type(error).__name__
        return data


class ArchiveService:
    """Only bounded wake-up jobs in RAM; records stay in the durable journal."""
    def __init__(self, archive):
        from ..lanes import BackgroundLane
        self.archive = archive
        self.lane = BackgroundLane(capacity=1)

    def request(self):
        return self.lane.submit(lambda stop: self.archive.drain_once(stop))

    def finish(self, timeout=1):
        return self.lane.finish(timeout)
