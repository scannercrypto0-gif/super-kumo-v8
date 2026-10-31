"""
Tests for Stage 8: archival_sim — queue, crash recovery, idempotency, retry, retention.
"""
import hashlib
import json

import pytest

from tools.raw_vault_offline.archival_sim import (
    ArchivalQueue,
    QueueItemState,
    retention_dry_run,
)
from tools.raw_vault_offline.schema import logical_identity_key
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.tests._helpers import make_meta


# ── helpers ───────────────────────────────────────────────────────────────────

def _raw_bytes(seed: str = "q") -> bytes:
    return f"archival sim test data seed={seed}".encode()


def _admit(vault: RawVault, raw: bytes, instrument: str = "BTCUSDT",
           interval: str = "15m",
           start: str = "2024-01-01T00:00:00Z",
           end: str = "2024-01-02T00:00:00Z"):
    meta = make_meta(raw, instrument=instrument, interval=interval,
                     coverage_start=start, coverage_end=end)
    vault.admit(raw, meta)
    return meta


# ── basic enqueue + process + ack ─────────────────────────────────────────────

def test_enqueue_process_ack(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault)

    raw = _raw_bytes("v1")
    meta = _admit(vault, raw)

    item = queue.enqueue(meta.content_sha256, meta.to_dict())
    assert item.state == QueueItemState.PENDING

    processed = queue.process_next()
    assert processed is not None
    assert processed.state == QueueItemState.VERIFIED

    acked = queue.ack(processed.item_id)
    assert acked.state == QueueItemState.ACKED


def test_process_next_returns_none_when_empty(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault)
    assert queue.process_next() is None


# ── idempotency: same sha already VERIFIED ────────────────────────────────────

def test_enqueue_idempotent_verified(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault)

    raw = _raw_bytes("v1")
    meta = _admit(vault, raw)

    queue.enqueue(meta.content_sha256, meta.to_dict())
    queue.process_next()  # → VERIFIED

    # re-enqueue same sha
    item2 = queue.enqueue(meta.content_sha256, meta.to_dict())
    assert item2.state in (QueueItemState.VERIFIED, QueueItemState.ACKED)


# ── crash recovery: PROCESSING → PENDING on restart ──────────────────────────

def test_crash_recovery(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue_dir = tmp_path / "queue"
    queue = ArchivalQueue(queue_dir, vault)

    raw = _raw_bytes("v1")
    meta = _admit(vault, raw)
    item = queue.enqueue(meta.content_sha256, meta.to_dict())

    # simulate crash: manually mark PROCESSING in queue log
    from tools.raw_vault_offline.archival_sim import QueueItem
    item.state = QueueItemState.PROCESSING
    item.attempts = 1
    line = json.dumps(item.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    with open(queue_dir / "archival_queue.jsonl", "a") as fh:
        fh.write(line)

    # restart
    queue2 = ArchivalQueue(queue_dir, vault)
    items = queue2.all_items()
    processing_after_restart = [i for i in items if i.state == QueueItemState.PROCESSING]
    pending_after_restart = [i for i in items if i.state == QueueItemState.PENDING]
    # PROCESSING items must have been reset to PENDING
    assert len(processing_after_restart) == 0
    assert len(pending_after_restart) >= 1


# ── failed retry ─────────────────────────────────────────────────────────────

def test_process_nonexistent_object_fails(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault)

    # enqueue sha that is NOT in vault
    phantom_sha = "f" * 64
    lid = logical_identity_key(
        vendor="test", instrument="GHOST", market="spot", interval="1m",
        coverage_start_utc="2024-01-01T00:00:00Z",
        coverage_end_utc="2024-01-02T00:00:00Z",
        source_format="csv_zip", format_version="v1",
    )
    meta_dict = {"content_sha256": phantom_sha, "logical_identity_key": lid}
    queue.enqueue(phantom_sha, meta_dict, max_retries=2)

    item = queue.process_next()
    assert item.state in (QueueItemState.FAILED, QueueItemState.PERMANENT_FAIL)
    assert item.last_error is not None


def test_retry_failed(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault)

    phantom_sha = "e" * 64
    queue.enqueue(phantom_sha, {}, max_retries=5)
    queue.process_next()  # → FAILED (not PERMANENT_FAIL, attempts=1 < 5)

    retried = queue.retry_failed()
    assert len(retried) >= 1


# ── ack requires VERIFIED state ───────────────────────────────────────────────

def test_ack_requires_verified(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault)

    raw = _raw_bytes("v1")
    meta = _admit(vault, raw)
    item = queue.enqueue(meta.content_sha256, meta.to_dict())
    # item is PENDING — cannot ACK
    with pytest.raises(ValueError):
        queue.ack(item.item_id)


# ── queue capacity limit ──────────────────────────────────────────────────────

def test_queue_overflow(tmp_path):
    vault = RawVault(tmp_path / "vault")
    queue = ArchivalQueue(tmp_path / "queue", vault, max_size=2)

    for i in range(2):
        queue.enqueue(f"{'0'*63}{i}", {})

    with pytest.raises(OverflowError):
        queue.enqueue("1" * 64, {})


# ── retention dry-run ─────────────────────────────────────────────────────────

def test_retention_dry_run_max_objects(tmp_path):
    vault = RawVault(tmp_path / "vault")
    for i in range(5):
        raw = _raw_bytes(f"obj{i}")
        _admit(vault, raw, instrument=f"ASSET{i}UST",
               start=f"2024-01-0{i+1}T00:00:00Z",
               end=f"2024-01-0{i+2}T00:00:00Z")

    report = retention_dry_run(vault, max_objects=3)
    assert report.dry_run is True
    assert report.total_objects == 5
    assert len(report.would_evict) == 2   # oldest 2 beyond limit of 3
    assert len(report.would_retain) == 3


def test_retention_dry_run_does_not_delete(tmp_path):
    vault = RawVault(tmp_path / "vault")
    raw = _raw_bytes("keep")
    _admit(vault, raw)

    report = retention_dry_run(vault, max_objects=0)
    assert report.dry_run is True
    # object still exists in vault
    sha = hashlib.sha256(raw).hexdigest()
    recovered = vault.read(sha)
    assert recovered == raw
