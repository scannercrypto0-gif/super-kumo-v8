"""Injected runtime faults; these are not owner-host/cloud deployment proofs."""
from dataclasses import asdict
import json
import subprocess
import time
import pytest
from aql.binance_observer import ObserverLedger
from aql.evidence_outbox import EvidenceOutbox, digest, encode
from aql.evidence_guardian import RcloneDriveSender
from aql.observer_runtime import atomic_json, clock_metadata, queue_snapshot
from aql.utc_evidence import ClockSample
from tests.guardian_fixtures import receipt


def test_event_clock_binding_expiry_restart_and_step(tmp_path):
    ledger = ObserverLedger(tmp_path/'l.db')
    path = tmp_path/'clock.json'
    sample = ClockSample(1_000_000_000, 1000, 'diagnostic', 2, 3, 4, 60000, True)
    atomic_json(path, dict(observer_session=ledger.session, sample=asdict(sample)))
    meta = clock_metadata(ledger, path, 2000, 2_000_000_000)
    ref = meta["utc_sample_ref"]
    assert ref == ledger.entries()[-1]['hash']
    assert meta['utc_diagnostic']['status'] == 'UTC_DIAGNOSTIC_BOUNDED_NOT_ATTESTED'
    for wall, mono in [(62000, 62_000_000_000), (20000, 2_000_000_000), (0, 0)]:
        assert clock_metadata(ledger, path, wall, mono)['utc_diagnostic']['status'] == 'UNKNOWN'
    ledger.close()
    ledger = ObserverLedger(tmp_path/'l.db')
    assert clock_metadata(ledger, path, 2000, 2_000_000_000)['utc_diagnostic']['status'] == 'UNKNOWN'
    assert ledger.bundle()['utc_status'] == 'UNKNOWN'
    ledger.close()


def test_queue_failure_is_visible_and_retryable(tmp_path):
    ledger = ObserverLedger(tmp_path/'l.db')
    class Failing(EvidenceOutbox):
        def enqueue(self, bundle):
            raise OSError('disk outage')
    assert queue_snapshot(ledger, Failing(tmp_path/'bad'))['status'] == 'LOCAL_QUEUE_FAILED'
    ledger.record('HEARTBEAT', {'coverage':'UNKNOWN'})
    assert queue_snapshot(ledger, EvidenceOutbox(tmp_path/'good'))['status'] == 'LOCAL_QUEUED'
    ledger.close()


def test_guardian_download_tamper_retry_and_no_duplicate(tmp_path):
    ledger = ObserverLedger(tmp_path/'l.db')
    queue = EvidenceOutbox(tmp_path/'q')
    sha = queue.enqueue(ledger.bundle())
    sender = RcloneDriveSender('atlas:')
    remote = {}
    bad = [False]
    from types import SimpleNamespace
    def run(args, **kwargs):
        op = args[1]
        if op == 'copyto':
            assert not remote
            from pathlib import Path
            remote['blob'] = Path(args[2]).read_bytes()
            return SimpleNamespace(stdout=b'')
        if op == 'cat':
            if not remote:
                raise subprocess.CalledProcessError(4, args)
            return SimpleNamespace(stdout=b'tampered' if bad[0] else remote['blob'])
        raise AssertionError(op)
    sender.runner = run
    bad[0] = True
    assert queue.deliver(sender)[0][1] == 'PENDING_EXTERNAL_ANCHOR'
    assert queue.pending_count() == 1
    bad[0] = False
    assert queue.deliver(sender)[0][1] == 'REMOTE_RECEIPT_RECORDED_NOT_INDEPENDENTLY_VERIFIED'
    assert queue.deliver(sender) == []
    ack = json.loads((tmp_path/'q'/'acknowledged'/(sha+'.json')).read_text())
    assert ack['receipt']['download_sha256'] == sha
    assert ack['receipt']['independent_custody'] is False
    ledger.close()


def test_ack_tamper_cannot_silently_suppress_enqueue(tmp_path):
    from aql.evidence_outbox import OutboxError
    q = EvidenceOutbox(tmp_path/'q')
    bundle = {'a': 1}
    sha = q.enqueue(bundle)
    q.deliver(lambda b, h: receipt(h))
    ack = tmp_path/'q'/'acknowledged'/(sha+'.json')
    ack.write_text('{}')
    with pytest.raises(OutboxError):
        q.enqueue(bundle)


def test_snapshot_process_restores_after_offline_and_does_not_write_ledger(tmp_path):
    import multiprocessing
    import sqlite3
    from aql.observer_runtime import snapshot_loop
    ledger = ObserverLedger(tmp_path/'l.db')
    head = ledger.verify()
    ctx = multiprocessing.get_context('spawn')
    stop = ctx.Event()
    stop.set()  # one real child-process snapshot, without a network sender
    p = ctx.Process(target=snapshot_loop, args=(tmp_path/'l.db', tmp_path/'q', stop))
    p.start()
    p.join(10)
    if p.is_alive():
        p.terminate()
        p.join()
        pytest.fail('snapshot worker hung')
    assert p.exitcode == 0
    assert ledger.verify() == head
    q = EvidenceOutbox(tmp_path/'q')
    assert q.pending_count() == 1
    assert q.deliver(lambda *_: None)[0][1] == 'PENDING_EXTERNAL_ANCHOR'
    # Guardian absent does not prevent a durable writer commit.
    ledger.record('HEARTBEAT', {'coverage':'UNKNOWN'})
    assert ledger.verify() != head
    ledger.close()


@pytest.mark.parametrize('status,expected', [
    ('Leap Indicator: 0\nRoot Dispersion: 7.7618s', True),
    ('Leap Indicator: 3\nRoot Dispersion: 0.001s', False),
    ('localized unsupported output', False),
])
def test_windows_root_dispersion_is_preserved(monkeypatch, status, expected):
    from types import SimpleNamespace
    import aql.utc_sampler as collector
    from aql.utc_evidence import assess
    monkeypatch.setattr(collector.sys, 'platform', 'win32')
    monkeypatch.setattr(collector, 'measure_sntp', lambda *a, **k:
        ClockSample(1_000_000_000, 1000, 'test', 2, 3, 4, 60000, True))
    monkeypatch.setattr(collector.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=0, stdout=status))
    result = collector.collect('session')
    sample = ClockSample(**result['sample'])
    assert sample.synchronized is expected
    if expected:
        assert sample.root_dispersion_ms == pytest.approx(7761.8)
    assert assess(sample, 2_000_000_000, 100)['status'] == 'UNKNOWN'
