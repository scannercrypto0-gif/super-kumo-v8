"""Integration with actual SQLite DurableJournal and operational ACK state."""
from aql.data_proof_g1_paged_reconcile import reconcile_persisted_page
from aql.data_proof_registry import RevisionRegistry
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def _bar(index):
    return MarketBar(symbol="BTCUSDT", interval="1m",
                     bar_open=index * 60000, bar_close=index * 60000 + 59999,
                     open=1., high=2., low=1., close=2., volume=5.,
                     is_final=True, source="binance_ws",
                     ingested_at=index * 60000 + 60001).with_checksum()


def test_real_sqlite_journal_persisted_cursor_reopen(tmp_path):
    path = str(tmp_path / "journal.sqlite")
    journal = DurableJournal(path)
    for i in range(3):
        journal.commit(_bar(i))
    journal.mark_persisted(_bar(0).stable_key())
    journal.mark_persisted(_bar(2).stable_key())
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    first = reconcile_persisted_page(journal, registry, symbol="BTCUSDT",
                                     interval="1m", limit=1)
    assert first["added"] == 1
    assert first["next_cursor"] > 0
    assert not first["complete"]
    registry.close()
    reopened = RevisionRegistry(tmp_path / "proof.sqlite")
    journal2 = DurableJournal(path)
    second = reconcile_persisted_page(journal2, reopened, symbol="BTCUSDT",
        interval="1m", after_entry_id=first["next_cursor"], limit=1)
    assert second["added"] == 1
    assert len(reopened.revisions(_bar(0).stable_key())) == 1
    assert len(reopened.revisions(_bar(1).stable_key())) == 0
    assert len(reopened.revisions(_bar(2).stable_key())) == 1
    assert second["next_cursor"] > first["next_cursor"]
    reopened.close()
