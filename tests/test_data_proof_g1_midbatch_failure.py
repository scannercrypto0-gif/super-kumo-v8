"""Proof repair must stop at first failed row and retry it after restart."""
from aql.data_proof_g1_checkpoint import (
    ProofReconcileCheckpoint, reconcile_checkpointed_page)
from aql.data_proof_registry import RevisionRegistry
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def _bar(i):
    return MarketBar(symbol="BTCUSDT", interval="1m",
        bar_open=i * 60000, bar_close=i * 60000 + 59999,
        open=1., high=2., low=1., close=2., volume=5.,
        is_final=True, source="binance_ws",
        ingested_at=i * 60000 + 60001).with_checksum()


class FailsOnSecondObservation:
    def __init__(self, delegate, failed_key):
        self.delegate = delegate
        self.failed_key = failed_key

    def revisions(self, key):
        if key == self.failed_key:
            raise RuntimeError("injected registry outage")
        return self.delegate.revisions(key)

    def append(self, observation):
        return self.delegate.append(observation)


def test_mid_batch_failure_checkpoint_and_retry(tmp_path):
    journal = DurableJournal(str(tmp_path / "journal.sqlite"))
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    checkpoint = ProofReconcileCheckpoint(tmp_path / "cursor.sqlite")
    for i in range(3):
        b = _bar(i)
        journal.commit(b)
        journal.mark_persisted(b.stable_key())

    failing = FailsOnSecondObservation(registry, _bar(1).stable_key())
    partial = reconcile_checkpointed_page(journal, failing, checkpoint,
        symbol="BTCUSDT", interval="1m", limit=3)
    assert partial["added"] == 1
    assert partial["failed_key"] == _bar(1).stable_key()
    saved = checkpoint.cursor(journal.instance_id, "BTCUSDT", "1m")
    assert saved == partial["next_cursor"]
    assert len(registry.revisions(_bar(0).stable_key())) == 1
    assert len(registry.revisions(_bar(1).stable_key())) == 0
    assert len(registry.revisions(_bar(2).stable_key())) == 0

    checkpoint.close()
    registry.close()
    checkpoint2 = ProofReconcileCheckpoint(tmp_path / "cursor.sqlite")
    registry2 = RevisionRegistry(tmp_path / "proof.sqlite")
    restarted = DurableJournal(str(tmp_path / "journal.sqlite"))
    assert checkpoint2.cursor(restarted.instance_id, "BTCUSDT", "1m") == saved
    resumed = reconcile_checkpointed_page(restarted, registry2, checkpoint2,
        symbol="BTCUSDT", interval="1m", limit=3)
    assert resumed["failed_key"] is None
    assert resumed["added"] == 2
    assert len(registry2.revisions(_bar(0).stable_key())) == 1
    assert len(registry2.revisions(_bar(1).stable_key())) == 1
    assert len(registry2.revisions(_bar(2).stable_key())) == 1
    checkpoint2.close()
    registry2.close()
