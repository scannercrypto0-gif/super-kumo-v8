"""Local synthetic falsifiers for #151; no owner SMB/cloud access."""
import errno
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from aql.archive.local import writer_lock
from aql.binance_observer import ObserverLedger
from aql.evidence_guardian import GuardianError, RcloneDriveSender
from aql.evidence_outbox import EvidenceOutbox, OutboxError, digest, encode
from tests.guardian_fixtures import receipt

SUCCESS = 'REMOTE_RECEIPT_RECORDED_NOT_INDEPENDENTLY_VERIFIED'
PENDING = 'PENDING_EXTERNAL_ANCHOR'


@pytest.mark.parametrize('change', [
    {'download_sha256': '0'*64}, {'status': 'UPLOADED'}, {'vault_id': 'wrong'},
    {'remote_id': 'wrong'}, {'independent_custody': True}, {'issuer_attestation': True},
    {'version': 2}, {'version': True}, {'version': 1.0},
])
def test_receipt_falsifiers_keep_pending(tmp_path, change):
    q = EvidenceOutbox(tmp_path)
    key = q.enqueue({'v': 1})
    assert q.deliver(lambda *_: receipt(key, **change)) == [(key, PENDING)]
    assert q.pending_count() == 1 and not list(q.acked.glob('*.json'))
    assert q.last_errors[0]['retryable'] is False


def test_incomplete_sender_receipt_cannot_discard_evidence(tmp_path):
    q = EvidenceOutbox(tmp_path)
    key = q.enqueue({'a': 1})
    assert q.deliver(lambda *_: dict(sha256=key, remote_id='unverified')) == [(key, PENDING)]
    assert q.pending_count() == 1


@pytest.mark.parametrize('version', [None, 1])
def test_prior_receipts_and_ack_before_unlink_recovery(tmp_path, version, monkeypatch):
    q = EvidenceOutbox(tmp_path)
    key = q.enqueue({'a': 1})
    monkeypatch.setattr(q, '_remove_pending', lambda *_: (_ for _ in ()).throw(OSError('crash')))
    ack = receipt(key) if version is None else receipt(key, version=version)
    assert q.deliver(lambda *_: ack) == [(key, PENDING)]
    committed = (q.acked/(key+'.json')).read_bytes()
    assert q.pending_count() == 1
    reopened = EvidenceOutbox(tmp_path)
    assert reopened.deliver(lambda *_: pytest.fail('duplicate sender')) == [(key, SUCCESS)]
    assert (q.acked/(key+'.json')).read_bytes() == committed
    assert reopened.enqueue({'a': 1}) == key
    assert reopened.pending_count() == 0


def test_corrupt_existing_ack_is_not_replaced(tmp_path):
    q = EvidenceOutbox(tmp_path)
    key = q.enqueue({'a': 1})
    ack = q.acked/(key+'.json'); ack.write_bytes(b'{partial')
    assert q.deliver(lambda *_: pytest.fail('must not repair silently')) == [(key, PENDING)]
    assert ack.read_bytes() == b'{partial' and q.pending_count() == 1
    with pytest.raises(OutboxError):
        q.enqueue({'a': 1})


@pytest.mark.parametrize('where', ['fsync', 'replace'])
def test_ack_write_failure_retains_pending_and_retries(tmp_path, monkeypatch, where):
    import aql.evidence_outbox as module
    q = EvidenceOutbox(tmp_path); key = q.enqueue({'a': 1})
    calls = []
    def sender(*_):
        calls.append(1); return receipt(key)
    with monkeypatch.context() as patch:
        patch.setattr(module.os, where, lambda *a: (_ for _ in ()).throw(OSError(errno.ENOSPC, 'secret')))
        assert q.deliver(sender) == [(key, PENDING)]
    assert q.pending_count() == 1 and not list(q.acked.glob('*.json'))
    assert q.last_errors == [dict(sha256=key, code='LOCAL_DISK_FULL', retryable=True)]
    assert q.deliver(sender) == [(key, SUCCESS)]


def test_uncertain_ack_directory_sync_retried_before_pending_delete(tmp_path, monkeypatch):
    import aql.evidence_outbox as module
    q = EvidenceOutbox(tmp_path); key = q.enqueue({'a': 1})
    with monkeypatch.context() as patch:
        patch.setattr(module, 'sync_dir', lambda *_: (_ for _ in ()).throw(OSError('sync failed')))
        assert q.deliver(lambda *_: receipt(key)) == [(key, PENDING)]
        assert (q.acked/(key+'.json')).exists() and q.pending_count() == 1
        assert q.deliver(lambda *_: pytest.fail('must reuse ACK')) == [(key, PENDING)]
        assert q.pending_count() == 1
    assert q.deliver(lambda *_: pytest.fail('duplicate sender')) == [(key, SUCCESS)]


def test_error_code_cannot_carry_secret_sender_message(tmp_path):
    q = EvidenceOutbox(tmp_path); q.enqueue({'a': 1})
    def sender(*_): raise GuardianError('token=SECRET_NOT_PRINTED')
    q.deliver(sender)
    assert 'SECRET' not in json.dumps(q.last_errors)
    assert q.last_errors[0]['retryable'] is False


def _crash_with_lock(root):
    q = EvidenceOutbox(root)
    with writer_lock(q.root):
        key = next(q.pending.glob('*.json')).stem
        q._publish(q.acked/(key+'.json'), encode(dict(sha256=key,
                   remote_id=receipt(key)['remote_id'], receipt=receipt(key))))
        os._exit(23)


def test_real_child_exit_releases_os_lock_and_replays_ack(tmp_path):
    q = EvidenceOutbox(tmp_path); key = q.enqueue({'a': 1})
    ctx = multiprocessing.get_context('spawn')
    p = ctx.Process(target=_crash_with_lock, args=(str(tmp_path),))
    p.start(); p.join(15)
    if p.is_alive():
        p.terminate(); p.join(); pytest.fail('child failed to exit')
    assert p.exitcode == 23
    assert (tmp_path/'writer.lock').exists()  # persistent file, no PID guessing
    assert EvidenceOutbox(tmp_path).deliver(lambda *_: pytest.fail('duplicate')) == [(key, SUCCESS)]


def _attempt_while_locked(root, result):
    q = EvidenceOutbox(root)
    outputs = q.deliver(lambda *_: (_ for _ in ()).throw(AssertionError('send while locked')))
    result.put((outputs, q.last_errors))


def test_two_processes_cannot_ack_concurrently(tmp_path):
    q = EvidenceOutbox(tmp_path); key = q.enqueue({'a': 1})
    ctx = multiprocessing.get_context('spawn'); result = ctx.Queue()
    with writer_lock(q.root):
        p = ctx.Process(target=_attempt_while_locked, args=(str(tmp_path), result))
        p.start(); p.join(15)
        if p.is_alive():
            p.terminate(); p.join(); pytest.fail('nonblocking lock waited')
        assert p.exitcode == 0
        output, errors = result.get(timeout=3)
        assert output == [] and errors == [dict(sha256=None, code='OUTBOX_LOCK_UNAVAILABLE', retryable=True)]
    result.close(); result.join_thread()
    assert q.deliver(lambda *_: receipt(key)) == [(key, SUCCESS)]


def test_reordered_duplicate_bundles_no_duplicate_ack(tmp_path):
    q = EvidenceOutbox(tmp_path)
    keys = [q.enqueue({'version': n}) for n in (3, 1, 2, 3)]
    calls = []
    q.deliver(lambda b, k: (calls.append(k) or receipt(k)))
    assert len(calls) == len(set(keys)) == 3
    for n in (1, 3, 2): q.enqueue({'version': n})
    assert q.deliver(lambda *_: pytest.fail('duplicate')) == []
    assert len(list(q.acked.glob('*.json'))) == 3


def test_partial_temp_is_ignored_not_deleted(tmp_path):
    q = EvidenceOutbox(tmp_path)
    orphan = q.pending/'.new-orphan'; orphan.write_bytes(b'{partial')
    assert q.deliver(lambda *_: pytest.fail('partial upload')) == []
    assert orphan.read_bytes() == b'{partial'


def test_invalid_object_filename_not_logged_or_sent(tmp_path):
    q = EvidenceOutbox(tmp_path)
    (q.pending/'SECRET.json').write_bytes(b'{}')
    assert q.deliver(lambda *_: pytest.fail('invalid name')) == [(None, 'INVALID_OBJECT_NAME')]


@pytest.mark.parametrize('error,expected,retryable', [
    (subprocess.CalledProcessError(3, ['secret'], stderr=b'token=SECRET'), 'REMOTE_DIRECTORY_MISSING', False),
    (subprocess.CalledProcessError(5, ['secret'], stderr=b'token=SECRET'), 'REMOTE_TRANSIENT', True),
    (subprocess.CalledProcessError(7, ['secret'], stderr=b'token=SECRET'), 'REMOTE_COMMAND_FAILED_REVIEW_REQUIRED', False),
    (subprocess.TimeoutExpired(['secret'], 1), 'REMOTE_TIMEOUT_UNKNOWN', True),
])
def test_remote_errors_sanitized_and_directory_missing_never_uploads(tmp_path, error, expected, retryable):
    ledger = ObserverLedger(tmp_path/'l.db'); bundle = ledger.bundle(); ledger.close()
    q = EvidenceOutbox(tmp_path/'q'); key = q.enqueue(bundle); calls = []
    def run(args, **kw): calls.append(args[1]); raise error
    sender = RcloneDriveSender('atlas_vault:', runner=run)
    assert q.deliver(sender) == [(key, PENDING)]
    assert calls == ['cat'] and q.pending_count() == 1
    assert q.last_errors == [dict(sha256=key, code=expected, retryable=retryable)]
    assert 'SECRET' not in json.dumps(q.last_errors)


def test_interrupted_upload_safe_retry_and_remote_conflict_not_overwritten(tmp_path):
    ledger = ObserverLedger(tmp_path/'l.db'); bundle = ledger.bundle(); ledger.close()
    q = EvidenceOutbox(tmp_path/'q'); key = q.enqueue(bundle)
    objects = {}; uploads = []
    def run(args, **kw):
        if args[1] == 'cat':
            if args[2] not in objects: raise subprocess.CalledProcessError(4, args)
            return SimpleNamespace(stdout=objects[args[2]])
        assert args[1] == 'copyto' and '--immutable' in args
        uploads.append(1); objects[args[3]] = b'interrupted'
        raise subprocess.TimeoutExpired(args, 1)
    sender = RcloneDriveSender('atlas_vault:', runner=run)
    assert q.deliver(sender) == [(key, PENDING)]
    assert q.deliver(sender) == [(key, PENDING)]
    assert uploads == [1]  # existing conflicting bytes never overwritten
    assert q.last_errors[0]['code'] == 'REMOTE_CONTENT_CONFLICT'
    objects['atlas_vault:'+key+'.json'] = encode(bundle)  # simulated operator repair, not automatic
    assert q.deliver(sender) == [(key, SUCCESS)] and uploads == [1]


def test_symlink_pending_file_fails_closed_when_supported(tmp_path):
    q = EvidenceOutbox(tmp_path/'q'); key = q.enqueue({'a': 1})
    path = q.pending/(key+'.json'); outside = tmp_path/'outside'; outside.write_bytes(path.read_bytes())
    path.unlink()
    try: path.symlink_to(outside)
    except OSError:
        # No privilege mutation. Windows junction/reparse policy independently
        # covered below by synthetic metadata; actual ACL proof stays deferred.
        pytest.skip('Windows symlink privilege unavailable; no privilege changes authorized')
    assert q.deliver(lambda *_: pytest.fail('symlink sent')) == [(key, PENDING)]
    assert outside.read_bytes() == encode({'a': 1})


def test_windows_reparse_metadata_rejected(tmp_path, monkeypatch):
    from aql.archive.local import check_path
    original = Path.lstat
    def lstat(path, *a, **kw):
        if path == tmp_path:
            return SimpleNamespace(st_mode=0o40755, st_file_attributes=0x400)
        return original(path, *a, **kw)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(ValueError, match='reparse'):
        check_path(tmp_path)
