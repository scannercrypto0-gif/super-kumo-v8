"""Local-only runtime seams. Remote delivery never runs in the observer process."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time

from aql.utc_evidence import ClockSample, assess


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.new-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, sort_keys=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def clock_metadata(ledger, sample_path, wall_ms, monotonic_ns, *, maximum_ms=100):
    """Consume a session-bound diagnostic from the separate UTC collector."""
    sample = None
    ref = None
    try:
        doc = json.loads(Path(sample_path).read_text(encoding='utf-8'))
        if doc['observer_session'] == ledger.session:
            sample = ClockSample(**doc['sample'])
            ref = ledger.record('UTC_DIAGNOSTIC', dict(sample=asdict(sample),
                session=ledger.session, authenticated=False, issuer_attestation=False,
                measurement=doc))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return dict(utc_sample_ref=ref,
                utc_diagnostic=assess(sample, monotonic_ns, maximum_ms, now_wall_ms=wall_ms),
                utc_policy_max_uncertainty_ms=maximum_ms)


def queue_snapshot(ledger, outbox):
    """Storage failure is visible, retryable, and does not stop market capture."""
    try:
        key = ledger.queue_external_evidence(outbox)
        return dict(status='LOCAL_QUEUED', sha256=key)
    except Exception as exc:
        return dict(status='LOCAL_QUEUE_FAILED', error=type(exc).__name__)


def snapshot_loop(db_path, outbox_path, stop):
    """A read-only SQLite snapshot in a child process; no watcher serialization."""
    import sqlite3
    from aql.binance_observer import ObserverLedger
    from aql.evidence_outbox import EvidenceOutbox
    while True:
        ledger = None
        try:
            ledger = ObserverLedger.__new__(ObserverLedger)
            ledger.db = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro',
                                        uri=True, isolation_level=None, timeout=.1)
            ledger.db.execute('BEGIN')
            result = queue_snapshot(ledger, EvidenceOutbox(outbox_path))
        except Exception as exc:
            result = dict(status='LOCAL_QUEUE_FAILED', error=type(exc).__name__)
        finally:
            if ledger is not None and hasattr(ledger, 'db'):
                ledger.close()
        print(json.dumps(result), flush=True)
        if stop.is_set():
            return
        stop.wait(30)
