"""Late PERSISTED ACK behind fast cursor must be recovered by full sweep."""
from aql.data_proof_g1_checkpoint import (
    ProofReconcileCheckpoint, reconcile_checkpointed_page)
from aql.data_proof_g1_sweep import sweep_persisted_proofs
from aql.data_proof_registry import RevisionRegistry
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def _bar(i):
    return MarketBar(symbol="BTCUSDT", interval="1m",
        bar_open=i * 60000, bar_close=i * 60000 + 59999,
        open=1., high=2., low=1., close=2., volume=5.,
        is_final=True, source="binance_ws",
        ingested_at=i * 60000 + 60001).with_checksum()


def test_sweep_recovers_late_ack_behind_checkpoint(tmp_path):
    journal = DurableJournal(str(tmp_path / "journal.sqlite"))
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    checkpoint = ProofReconcileCheckpoint(tmp_path / "cursor.sqlite")
    for i in range(3):
        journal.commit(_bar(i))
    journal.mark_persisted(_bar(0).stable_key())
    journal.mark_persisted(_bar(2).stable_key())
    first = reconcile_checkpointed_page(journal, registry, checkpoint,
        symbol="BTCUSDT", interval="1m", limit=10)
    assert first["added"] == 2
    assert checkpoint.cursor(journal.instance_id, "BTCUSDT", "1m") > 0
    assert not registry.revisions(_bar(1).stable_key())
    journal.mark_persisted(_bar(1).stable_key())
    fast = reconcile_checkpointed_page(journal, registry, checkpoint,
        symbol="BTCUSDT", interval="1m", limit=10)
    assert fast["added"] == 0
    sweep = sweep_persisted_proofs(journal, registry,
        symbol="BTCUSDT", interval="1m", page_size=1, max_pages=5)
    assert sweep["complete"] and sweep["added"] == 1
    assert len(registry.revisions(_bar(1).stable_key())) == 1
    again = sweep_persisted_proofs(journal, registry,
        symbol="BTCUSDT", interval="1m", page_size=2, max_pages=5)
    assert again["complete"] and again["added"] == 0
    checkpoint.close()
    registry.close()
