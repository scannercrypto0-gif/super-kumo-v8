"""Confined single-writer storage. Originals are content addressed and create-only.

All managed writes reserve their maximum possible disk footprint in advance.
Daily SQLite shards are rebuilt in bounded scratch files, then atomically
published. An OS lock is released by the kernel after process death.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

from aql.research_warehouse_plan import CAP_BYTES, RESERVE_BYTES

LAYOUT = ('raw', 'catalog', 'bars', 'receipts', 'quarantine')
SHARD_CAP = 16 * 1024 * 1024


def need(ok, code):
    if not ok:
        raise ValueError(code)


def seal(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def safe(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            s = item.lstat()
            need(not stat.S_ISLNK(s.st_mode) and not
                 (getattr(s, 'st_file_attributes', 0) & 0x400), 'REPARSE_PATH_DENIED')
    return path


class Warehouse:
    def __init__(self, root, *, cap=CAP_BYTES, reserve=RESERVE_BYTES, test_root=False):
        self.root = safe(root)
        need(type(cap) is int and 0 < cap <= CAP_BYTES and type(reserve) is int
             and reserve >= 0, 'BUDGET_INVALID')
        if not test_root:
            need(os.name == 'nt' and str(self.root).casefold() ==
                 str(Path('E:/ATLAS/DataWarehouse')).casefold(), 'APPROVED_WINDOWS_ROOT_REQUIRED')
        self.cap, self.reserve = cap, reserve
        self.locked = False

    def path(self, relative):
        p = Path(relative)
        need(not p.is_absolute() and p.parts and p.parts[0] in LAYOUT
             and all(x not in ('.', '..') and ':' not in x for x in p.parts), 'PATH_ESCAPE')
        target = safe(self.root / p)
        need(target.is_relative_to(self.root), 'PATH_ESCAPE')
        return target

    def used(self):
        total = 0
        if self.root.exists():
            for directory, dirs, files in os.walk(self.root, followlinks=False):
                for name in dirs + files:
                    p = safe(Path(directory) / name)
                    if p.is_file():
                        # Hard links from outside the managed root are not owned.
                        need(p.stat().st_nlink == 1, 'EXTERNAL_HARDLINK_DENIED')
                        total += p.stat().st_size
        return total

    def budget(self, maximum):
        need(self.locked, 'WRITER_LOCK_REQUIRED')
        need(type(maximum) is int and maximum >= 0, 'RESERVATION_INVALID')
        used = self.used()
        need(used + maximum <= self.cap, 'WAREHOUSE_BUDGET_EXCEEDED')
        need(shutil.disk_usage(self.root).free - maximum >= self.reserve,
             'WAREHOUSE_FREE_RESERVE')

    @contextmanager
    def writer(self):
        safe(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        lock = safe(self.root / 'catalog')
        lock.mkdir(exist_ok=True)
        target = self.path('catalog/writer.lock')
        need(not target.exists() or target.stat().st_nlink == 1, 'LOCK_HARDLINK_DENIED')
        # Empty persistent lock file; kernel owns liveness, not stale PID text.
        with target.open('a+b') as stream:
            try:
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError('WAREHOUSE_WRITER_BUSY') from exc
            self.locked = True
            try:
                for d in LAYOUT:
                    self.path(d).mkdir(exist_ok=True)
                self.budget(0)
                policy = self.path('catalog/warehouse-policy.json')
                expected = canonical(dict(schema='aql.warehouse.policy.v1', root=str(self.root),
                                          cap=self.cap, reserve=self.reserve))
                if not policy.exists():
                    existing = [p for p in self.root.rglob('*') if p.is_file()
                                and p != target]
                    need(not existing, 'UNMANAGED_EXISTING_WAREHOUSE_REQUIRES_ADOPTION')
                    self.write_once('catalog/warehouse-policy.json', expected)
                else:
                    need(policy.read_bytes() == expected, 'WAREHOUSE_POLICY_DRIFT')
                yield self
            finally:
                self.locked = False
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def write_once(self, relative, raw):
        p = self.path(relative)
        if p.exists():
            need(p.stat().st_nlink == 1 and p.read_bytes() == raw, 'IMMUTABLE_OBJECT_CONFLICT')
            return p
        self.budget(len(raw))
        # Incomplete object is never published under its final content identity.
        temp = self.path(str(relative) + '.pending')
        if temp.exists():
            need(temp.stat().st_nlink == 1, 'SCRATCH_HARDLINK_DENIED')
            temp.unlink()  # reserved scratch only; not an original
        with temp.open('xb') as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, p)
        return p

    def document(self, section, body):
        raw = canonical(body)
        return self.write_once(f'{section}/{seal(raw)}.json', raw)
