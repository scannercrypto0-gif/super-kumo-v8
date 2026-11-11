"""Paged repair moves across batches and stops at a failed row."""
from aql.data_proof_g1_paged_reconcile import reconcile_persisted_page
from aql.data_proof_registry import RevisionRegistry
from aql.models.bar import MarketBar


def bar(index):
    b = MarketBar(symbol="BTCUSDT", interval="1m",
        bar_open=index * 60000, bar_close=index * 60000 + 59999,
        open=1., high=2., low=1., close=2., volume=5., is_final=True,
        source="binance_ws", ingested_at=index * 60000 + 60001).with_checksum()
    b._journal_entry_id = index + 1
    return b


class Journal:
    def replay(self, *args, **kwargs):
        assert kwargs["persisted_only"] is True
        return [bar(i) for i in range(3)
                if i + 1 > kwargs["after_entry_id"]][:kwargs["limit"]]


def test_cursor_crosses_multiple_pages_without_loss(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    cursor = 0
    for _ in range(3):
        page = reconcile_persisted_page(Journal(), registry, symbol="BTCUSDT",
                                        interval="1m", after_entry_id=cursor, limit=2)
        assert page["failed_key"] is None
        cursor = page["next_cursor"]
        if page["complete"]:
            break
    assert cursor == 3
    assert len(registry.revisions("BTCUSDT:1m:120000")) == 1
    registry.close()
