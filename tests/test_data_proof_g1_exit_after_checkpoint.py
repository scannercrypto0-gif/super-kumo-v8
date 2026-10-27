"""Abrupt exit after durable checkpoint: restart must not duplicate or skip."""
import subprocess
import sys
import textwrap

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


def test_exit_after_checkpoint_then_resume_next_persisted(tmp_path):
    journal_path = str(tmp_path / "journal.sqlite")
    proof_path = str(tmp_path / "proof.sqlite")
    checkpoint_path = str(tmp_path / "checkpoint.sqlite")
    journal = DurableJournal(journal_path)
    for i in range(2):
        bar = _bar(i)
        journal.commit(bar)
        journal.mark_persisted(bar.stable_key())

    child = textwrap.dedent("""
        import os, sys
        from aql.data_proof_g1_checkpoint import (
            ProofReconcileCheckpoint, reconcile_checkpointed_page)
        from aql.data_proof_registry import RevisionRegistry
        from aql.journal.durable_journal import DurableJournal
        journal = DurableJournal(sys.argv[1])
        registry = RevisionRegistry(sys.argv[2])
        checkpoint = ProofReconcileCheckpoint(sys.argv[3])
        result = reconcile_checkpointed_page(journal, registry, checkpoint,
            symbol="BTCUSDT", interval="1m", limit=1)
        assert result["added"] == 1 and result["next_cursor"] > 0
        os._exit(38)
    """)
    result = subprocess.run([sys.executable, "-c", child,
        journal_path, proof_path, checkpoint_path],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 38, result.stderr
    registry = RevisionRegistry(proof_path)
    checkpoint = ProofReconcileCheckpoint(checkpoint_path)
    reopened = DurableJournal(journal_path)
    assert checkpoint.cursor(reopened.instance_id, "BTCUSDT", "1m") > 0
    resumed = reconcile_checkpointed_page(reopened, registry, checkpoint,
        symbol="BTCUSDT", interval="1m", limit=1)
    assert resumed["added"] == 1
    assert len(registry.revisions(_bar(0).stable_key())) == 1
    assert len(registry.revisions(_bar(1).stable_key())) == 1
    checkpoint.close()
    registry.close()
