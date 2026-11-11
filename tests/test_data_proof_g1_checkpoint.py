"""Persistent checkpoint resumes real journal repair after process reopen."""
import pytest
from aql.data_proof import ProofError
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


def test_checkpointed_real_journal_restart(tmp_path):
    journal_path = str(tmp_path / "journal.sqlite")
    proof_path = tmp_path / "proof.sqlite"
    checkpoint_path = tmp_path / "cursor.sqlite"
    journal = DurableJournal(journal_path)
    for i in range(3):
        journal.commit(_bar(i))
        journal.mark_persisted(_bar(i).stable_key())
    registry = RevisionRegistry(proof_path)
    checkpoint = ProofReconcileCheckpoint(checkpoint_path)
    first = reconcile_checkpointed_page(journal, registry, checkpoint,
        symbol="BTCUSDT", interval="1m", limit=1)
    assert first["added"] == 1
    first_cursor = first["next_cursor"]
    checkpoint.close()
    registry.close()
    journal2 = DurableJournal(journal_path)
    registry2 = RevisionRegistry(proof_path)
    checkpoint2 = ProofReconcileCheckpoint(checkpoint_path)
    assert checkpoint2.cursor(journal2.instance_id, "BTCUSDT", "1m") == first_cursor
    second = reconcile_checkpointed_page(journal2, registry2, checkpoint2,
        symbol="BTCUSDT", interval="1m", limit=2)
    assert second["added"] == 2
    assert second["next_cursor"] > first_cursor
    with pytest.raises(ProofError, match="regression"):
        checkpoint2.advance(journal2.instance_id, "BTCUSDT", "1m", 0)
    assert len(registry2.revisions(_bar(2).stable_key())) == 1
    checkpoint2.close()
    registry2.close()
