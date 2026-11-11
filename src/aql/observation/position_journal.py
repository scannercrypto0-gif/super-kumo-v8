"""Offline durable event journal; no trading, price retrieval or cloud dependencies."""
from dataclasses import asdict
import hashlib
import json
import os
import stat
import threading
from contextlib import contextmanager
from pathlib import Path
from .positions import PositionContractError, PositionEvent, PositionLedger

class JournalIntegrityError(PositionContractError): pass

_WRITER_MUTEX = threading.Lock()


def _checked_path(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise JournalIntegrityError('symlink/reparse journal path rejected')
            if part == path and not stat.S_ISREG(info.st_mode):
                raise JournalIntegrityError('journal must be a regular file')
    return path


def _identity(path):
    info = path.stat()
    return info.st_dev, info.st_ino


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JournalIntegrityError('duplicate JSON field')
        result[key] = value
    return result


@contextmanager
def _exclusive_writer(path):
    """Exclusive local writer lease; orphaned locks require manual recovery."""
    path = _checked_path(path)
    lock_path = path.with_name(path.name + '.writer.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise JournalIntegrityError('writer lock held or orphaned; inspect before recovery') from exc
    owner_identity = os.fstat(fd).st_dev, os.fstat(fd).st_ino
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(str(os.getpid()))
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        # Never remove a replacement lock or infer orphan ownership from a PID.
        if lock_path.is_symlink() or not lock_path.exists() or _identity(lock_path) != owner_identity or lock_path.read_bytes() != str(os.getpid()).encode():
            raise JournalIntegrityError('writer lock replaced/missing; operator inspection required')
        lock_path.unlink()


class DurablePositionJournal:
    """Single-writer append-only JSONL with fsync; torn trailing records fail closed.

    Cooperating writers use an exclusive sidecar lock. Orphan locks fail closed.
    """
    def __init__(self, path):
        self.path=_checked_path(path)
        self.ledger=PositionLedger()
        self._tail='0'*64
        self._replay()
        self._expected_size=self.path.stat().st_size if self.path.exists() else 0
        self._expected_identity=_identity(self.path) if self.path.exists() else None
    def _replay(self):
        if not self.path.exists(): return
        with self.path.open('rb') as f:
            for number,raw in enumerate(f,1):
                if not raw.endswith(b'\n'): raise JournalIntegrityError(f'torn record at line {number}')
                try:
                    row=json.loads(raw, object_pairs_hook=_unique_fields)
                    if set(row)!= {'previous','event','digest'} or row['previous']!=self._tail:
                        raise JournalIntegrityError(f'chain mismatch at line {number}')
                    material=json.dumps({'previous':row['previous'],'event':row['event']},sort_keys=True,separators=(',',':')).encode()
                    if hashlib.sha256(material).hexdigest()!=row['digest']:
                        raise JournalIntegrityError(f'checksum mismatch at line {number}')
                    e=PositionEvent(**row['event'])
                    if self.ledger.append(e)!='inserted': raise JournalIntegrityError(f'duplicate record at line {number}')
                    self._tail=row['digest']
                except (ValueError,TypeError,KeyError,UnicodeError,PositionContractError) as exc:
                    raise JournalIntegrityError(f'invalid journal line {number}') from exc
    def append(self,event):
        with _WRITER_MUTEX:
            with _exclusive_writer(self.path):
                return self._append_locked(event)

    def _append_locked(self,event):
        # Refuse stale instances and out-of-band changes before every write.
        # This detects sequential conflicts but is NOT a cross-process lock.
        current_size=self.path.stat().st_size if self.path.exists() else 0
        current_identity=_identity(self.path) if self.path.exists() else None
        if current_identity != self._expected_identity:
            raise JournalIntegrityError('journal path replaced outside this writer')
        if current_size != self._expected_size:
            raise JournalIntegrityError('journal changed outside this writer; reopen and replay')
        # Same-size edits are also unsafe; verify the complete chain against disk.
        probe=object.__new__(DurablePositionJournal)
        probe.path=self.path
        probe.ledger=PositionLedger()
        probe._tail='0'*64
        probe._replay()
        if probe._tail != self._tail:
            raise JournalIntegrityError('journal contents changed outside this writer')
        if not isinstance(event,PositionEvent): raise PositionContractError('invalid event')
        # Validate against a disposable replay before touching durable bytes.
        # Reuse the fully verified disposable disk replay. Rebuilding a second
        # ledger wastes O(n) work and trusts mutable public in-memory state.
        candidate=probe.ledger
        result=candidate.append(event)
        if result=='duplicate': return 'duplicate'
        row={'previous':self._tail,'event':asdict(event)}
        material=json.dumps(row,sort_keys=True,separators=(',',':')).encode()
        row['digest']=hashlib.sha256(material).hexdigest()
        encoded=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('ab') as f:
            if f.write(encoded) != len(encoded):
                raise JournalIntegrityError('short journal write; inspect before recovery')
            f.flush()
            os.fsync(f.fileno())
            written_identity=os.fstat(f.fileno()).st_dev, os.fstat(f.fileno()).st_ino
        if _identity(self.path) != written_identity:
            raise JournalIntegrityError('journal replaced during append; inspect durable bytes')
        self.ledger=candidate
        self._tail=row['digest']
        self._expected_size+=len(encoded)
        self._expected_identity=written_identity
        return 'inserted'
