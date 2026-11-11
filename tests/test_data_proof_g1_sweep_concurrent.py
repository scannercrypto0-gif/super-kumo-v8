"""Concurrent G1 journal writes and offline proof sweep.

This is a correctness/latency smoke test, not a benchmark or an SLO claim.
"""
import threading
import time

from aql.data_proof_g1_sweep_progress import SweepProgress, run_sweep_slice
from aql.data_proof_registry import RevisionRegistry
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def _bar(i):
    return MarketBar(symbol="BTCUSDT", interval="1m",
        bar_open=i * 60000, bar_close=i * 60000 + 59999,
        open=1., high=2., low=1., close=2., volume=5.,
        is_final=True, source="binance_ws",
        ingested_at=i * 60000 + 60001).with_checksum()


def test_concurrent_journal_commit_and_bounded_sweep(tmp_path):
    journal = DurableJournal(str(tmp_path / "journal.sqlite"))
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    progress = SweepProgress(tmp_path / "sweep.sqlite")
    for i in range(10):
        b = _bar(i)
        journal.commit(b)
        journal.mark_persisted(b.stable_key())

    started = threading.Event()
    errors = []
    latencies_ms = []

    def writer():
        started.set()
        try:
            for i in range(10, 20):
                b = _bar(i)
                t0 = time.monotonic_ns()
                journal.commit(b)
                journal.mark_persisted(b.stable_key())
                latencies_ms.append((time.monotonic_ns() - t0) / 1_000_000)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    assert started.wait(5)
    try:
        first = run_sweep_slice(journal, registry, progress,
            symbol="BTCUSDT", interval="1m", page_size=2,
            max_pages=3, max_elapsed_ms=1000)
    finally:
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors
    assert len(latencies_ms) == 10
    assert first["pages"] <= 3
    # Once the writer has stopped, a fresh cycle must cover every persisted row.
    for _ in range(20):
        result = run_sweep_slice(journal, registry, progress,
            symbol="BTCUSDT", interval="1m", page_size=3,
            max_pages=4, max_elapsed_ms=1000)
        if result["complete"]:
            break
    assert result["complete"]
    # A complete cycle may have started before the concurrent writes; run one
    # additional full cycle to guarantee a post-writer high-water mark.
    for _ in range(20):
        result = run_sweep_slice(journal, registry, progress,
            symbol="BTCUSDT", interval="1m", page_size=3,
            max_pages=4, max_elapsed_ms=1000)
        if result["complete"]:
            break
    assert result["complete"]
    for i in range(20):
        assert len(registry.revisions(_bar(i).stable_key())) == 1
    progress.close()
    registry.close()
