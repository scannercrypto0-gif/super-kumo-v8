"""End-to-end opt-in JournalConsumer -> SQLite observation registry seam."""
from aql.data_proof_g1_composition import make_g1_revision_observer
from aql.data_proof_registry import RevisionRegistry
from aql.lanes import JournalConsumer
from aql.models.bar import MarketBar


class Journal:
    def __init__(self, bars):
        self.bars = bars
        self.ack = []

    def replay(self, *args, **kwargs):
        return self.bars

    def require_eligible(self, key):
        return None

    def mark_persisted(self, key):
        self.ack.append(key)


class Store:
    def upsert(self, bar):
        return True


def _bar():
    return MarketBar(symbol="BTCUSDT", interval="1m", bar_open=0,
                     bar_close=59999, open=1., high=2., low=1.,
                     close=2., volume=5., is_final=True,
                     source="binance_ws", ingested_at=60001).with_checksum()


def test_journal_consumer_to_registry_and_reopen(tmp_path):
    path = tmp_path / "proof.sqlite"
    registry = RevisionRegistry(path)
    journal = Journal([_bar()])
    consumer = JournalConsumer(journal, Store(), "BTCUSDT", "1m",
        after_persisted=make_g1_revision_observer(registry))
    assert consumer.drain_once() == 1
    assert consumer.sidecopy_errors == 0
    assert journal.ack == ["BTCUSDT:1m:0"]
    registry.close()
    reopened = RevisionRegistry(path)
    assert len(reopened.revisions("BTCUSDT:1m:0")) == 1
    consumer2 = JournalConsumer(journal, Store(), "BTCUSDT", "1m",
        after_persisted=make_g1_revision_observer(reopened))
    assert consumer2.drain_once() == 1
    assert len(reopened.revisions("BTCUSDT:1m:0")) == 1
    reopened.close()


def test_registry_failure_cannot_undo_journal_ack(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    observer = make_g1_revision_observer(registry)
    registry.close()
    journal = Journal([_bar()])
    consumer = JournalConsumer(journal, Store(), "BTCUSDT", "1m",
                               after_persisted=observer)
    assert consumer.drain_once() == 1
    assert journal.ack == ["BTCUSDT:1m:0"]
    assert consumer.sidecopy_errors == 1
