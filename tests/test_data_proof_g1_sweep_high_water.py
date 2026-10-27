"""Fixed high-water sweep ignores newly appended rows until next cycle."""
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


def test_new_entries_wait_until_next_bounded_sweep_cycle(tmp_path):
    journal = DurableJournal(str(tmp_path / "journal.sqlite"))
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    progress = SweepProgress(tmp_path / "sweep.sqlite")
    for i in range(2):
        b = _bar(i)
        journal.commit(b)
        journal.mark_persisted(b.stable_key())

    first = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=1, max_pages=1)
    assert not first["complete"] and first["added"] == 1
    state = progress.state(journal.instance_id, "BTCUSDT", "1m")
    assert state is not None
    watermark = state[1]

    late = _bar(2)
    journal.commit(late)
    journal.mark_persisted(late.stable_key())
    assert journal.startup_entry_boundary() > watermark

    second = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=1, max_pages=3)
    assert second["complete"] and second["added"] == 1
    assert not registry.revisions(late.stable_key())

    next_cycle = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=2, max_pages=3)
    assert next_cycle["complete"] and next_cycle["added"] == 1
    assert len(registry.revisions(late.stable_key())) == 1
    progress.close()
    registry.close()
