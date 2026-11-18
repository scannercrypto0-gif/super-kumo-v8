"""A partial sweep resumes across restart and resets after completion."""
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


def test_sweep_cycle_resumes_then_restarts_from_zero(tmp_path):
    journal_path = str(tmp_path / "journal.sqlite")
    journal = DurableJournal(journal_path)
    for i in range(3):
        b = _bar(i)
        journal.commit(b)
        journal.mark_persisted(b.stable_key())
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    progress = SweepProgress(tmp_path / "sweep.sqlite")
    first = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=1, max_pages=1)
    assert not first["complete"] and first["added"] == 1
    assert progress.state(journal.instance_id, "BTCUSDT", "1m") is not None
    progress.close()
    progress = SweepProgress(tmp_path / "sweep.sqlite")
    second = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=2, max_pages=2)
    assert second["complete"] and second["added"] == 2
    assert progress.state(journal.instance_id, "BTCUSDT", "1m") is None
    third = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=2, max_pages=3)
    assert third["complete"] and third["added"] == 0
    progress.close()
    registry.close()
