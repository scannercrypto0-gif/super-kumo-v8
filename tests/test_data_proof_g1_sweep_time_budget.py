"""Time budget stops between pages, preserving durable progress."""
from unittest.mock import patch

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


def test_sweep_soft_time_budget_preserves_cursor(tmp_path):
    journal = DurableJournal(str(tmp_path / "journal.sqlite"))
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    progress = SweepProgress(tmp_path / "progress.sqlite")
    for i in range(3):
        b = _bar(i)
        journal.commit(b)
        journal.mark_persisted(b.stable_key())
    with patch("aql.data_proof_g1_sweep_progress.time.monotonic_ns",
               side_effect=[0, 2_000_000]):
        partial = run_sweep_slice(journal, registry, progress,
            symbol="BTCUSDT", interval="1m", page_size=1,
            max_pages=3, max_elapsed_ms=1)
    assert partial["pages"] == 1 and not partial["complete"]
    assert progress.state(journal.instance_id, "BTCUSDT", "1m")[0] > 0
    resumed = run_sweep_slice(journal, registry, progress,
        symbol="BTCUSDT", interval="1m", page_size=2, max_pages=3)
    assert resumed["complete"] and resumed["added"] == 2
    progress.close()
    registry.close()
