"""Optional durable delivery queue, isolated from the receive process.

Cooperating exporters/delivery writers use one nonblocking OS lock. Protected
ACLs are required: checks cannot defeat adversarial parent-directory renames.
No automatic retention/deletion policy or independent custody assertion.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import re
from contextlib import contextmanager
from aql.archive.local import check_path, mkdir, sync_dir, writer_lock
from aql.guardian_receipt import validate_receipt


class OutboxError(Exception):
    pass


class OutboxBusy(OutboxError):
    pass


def encode(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


class EvidenceOutbox:
    def __init__(self, root):
        self.root = check_path(root)
        self.pending = check_path(self.root / 'pending')
        self.acked = check_path(self.root / 'acknowledged')
        mkdir(self.pending)
        mkdir(self.acked)
        self.last_errors = []

    def _read(self, path):
        return check_path(path).read_bytes()

    @contextmanager
    def _lock(self):
        guard = writer_lock(self.root)
        try:
            guard.__enter__()
        except OSError:
            # Windows byte-lock contention is PermissionError, unlike flock's
            # BlockingIOError. Do not mislabel it as a permanent ACL denial.
            raise OutboxBusy('OUTBOX_LOCK_UNAVAILABLE') from None
        try:
            yield
        finally:
            guard.__exit__(None, None, None)

    def _ack(self, path, key):
        try:
            ack = json.loads(self._read(path))
            validate_receipt(ack['receipt'], key)
            if ack['sha256'] != key or ack['remote_id'] != ack['receipt']['remote_id']:
                raise ValueError('mismatch')
            return ack
        except (ValueError, KeyError, TypeError):
            raise OutboxError('INVALID_LOCAL_ACK') from None

    def _publish(self, path, data):
        """Under writer_lock: never replace a differing committed object."""
        check_path(path)
        if path.exists():
            if self._read(path) != data:
                raise OutboxError('LOCAL_OBJECT_CONFLICT')
            return
        fd, name = tempfile.mkstemp(prefix='.new-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            check_path(path)
            os.replace(name, path)
            sync_dir(path.parent)  # No portable Windows directory fsync.
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def enqueue(self, bundle):
        blob = encode(bundle)
        key = digest(blob)
        # Exporter is a separate process. Contention fails promptly, never waits
        # on a network send. queue_snapshot makes failure visible/retryable.
        with self._lock():
            ack = check_path(self.acked / (key + '.json'))
            if ack.exists():
                self._ack(ack, key)
                return key
            self._publish(self.pending / (key + '.json'), blob)
        return key

    def _remove_pending(self, path):
        check_path(path).unlink()
        sync_dir(self.pending)

    def _error(self, key, exc):
        # Never serialize messages, subprocess argv/stdout/stderr or paths.
        from aql.evidence_guardian import GuardianError
        if isinstance(exc, GuardianError):
            code, retryable = exc.code, exc.retryable
        elif isinstance(exc, OutboxBusy):
            code, retryable = 'OUTBOX_LOCK_UNAVAILABLE', True
        elif isinstance(exc, PermissionError):
            code, retryable = 'LOCAL_PERMISSION_DENIED', False
        elif isinstance(exc, OSError):
            code, retryable = ('LOCAL_DISK_FULL' if exc.errno == 28 else 'LOCAL_IO_OR_LOCK'), True
        elif isinstance(exc, (ValueError, KeyError, TypeError, OutboxError)):
            code, retryable = 'INVALID_LOCAL_DATA_OR_RECEIPT', False
        else:
            code, retryable = 'SENDER_FAILED', True
        self.last_errors.append(dict(sha256=key, code=code, retryable=retryable))

    def deliver(self, sender, *, max_items=20):
        """At-least-once send, one immutable logical ACK per digest.

        ACK-before-pending-unlink replay validates/reuses the durable receipt
        without sender calls or ACK replacement. Failures retain evidence.
        """
        if not callable(sender) or type(max_items) is not int or max_items < 1:
            raise ValueError('invalid sender or limit')
        outcomes = []
        self.last_errors = []
        try:
            with self._lock():
                check_path(self.pending)
                check_path(self.acked)
                for path in sorted(self.pending.glob('*.json'))[:max_items]:
                    key = path.stem
                    if not re.fullmatch(r'[0-9a-f]{64}', key):
                        outcomes.append((None, 'INVALID_OBJECT_NAME'))
                        continue
                    try:
                        blob = self._read(path)
                        if digest(blob) != key:
                            outcomes.append((key, 'TAMPERED_LOCAL'))
                            continue
                        ack = check_path(self.acked / path.name)
                        if ack.exists():
                            self._ack(ack, key)
                            # Retry an earlier uncertain directory sync before
                            # removing pending. Windows power-loss still unproved.
                            # Windows _commit requires a writable descriptor;
                            # opening r+b does not change the retained bytes.
                            with ack.open('r+b') as handle:
                                os.fsync(handle.fileno())
                            sync_dir(self.acked)
                        else:
                            receipt = sender(json.loads(blob), key)
                            validate_receipt(receipt, key)
                            self._publish(ack, encode(dict(sha256=key,
                                remote_id=receipt['remote_id'], receipt=receipt)))
                        self._remove_pending(path)
                        outcomes.append((key, 'REMOTE_RECEIPT_RECORDED_NOT_INDEPENDENTLY_VERIFIED'))
                    except Exception as exc:
                        self._error(key, exc)
                        outcomes.append((key, 'PENDING_EXTERNAL_ANCHOR'))
        except Exception as exc:
            self._error(None, exc)
        return outcomes

    def pending_count(self):
        return len(list(check_path(self.pending).glob('*.json')))
