"""Crash-boundary test: terminate a child after proof write, before checkpoint.

This exercises a real process exit (os._exit) rather than graceful close.
On restart the cursor must remain behind; replay is idempotent.
"""
import os
import subprocess
import sys
import textwrap

from aql.data_proof_g1_checkpoint import (
    ProofReconcileCheckpoint, reconcile_checkpointed_page)
from aql.data_proof_registry import RevisionRegistry
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def test_forced_exit_after_evidence_before_checkpoint(tmp_path):
    journal_path = str(tmp_path / "journal.sqlite")
    proof_path = str(tmp_path / "proof.sqlite")
    checkpoint_path = str(tmp_path / "cursor.sqlite")
    journal = DurableJournal(journal_path)
    bar = MarketBar(symbol="BTCUSDT", interval="1m", bar_open=0,
                    bar_close=59999, open=1., high=2., low=1.,
                    close=2., volume=5., is_final=True,
                    source="binance_ws", ingested_at=60001).with_checksum()
    journal.commit(bar)
    journal.mark_persisted(bar.stable_key())

    child = textwrap.dedent("""
        import os, sys
        from aql.data_proof_g1_checkpoint import ProofReconcileCheckpoint
        from aql.data_proof_g1_paged_reconcile import reconcile_persisted_page
        from aql.data_proof_registry import RevisionRegistry
        from aql.journal.durable_journal import DurableJournal
        journal = DurableJournal(sys.argv[1])
        registry = RevisionRegistry(sys.argv[2])
        checkpoint = ProofReconcileCheckpoint(sys.argv[3])
        result = reconcile_persisted_page(journal, registry,
            symbol="BTCUSDT", interval="1m", limit=1)
        assert result["added"] == 1
        # Simulated power/process boundary: bypass finally and SQLite close.
        os._exit(37)
    """)
    result = subprocess.run([sys.executable, "-c", child,
                             journal_path, proof_path, checkpoint_path],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 37, result.stderr
    registry = RevisionRegistry(proof_path)
    checkpoint = ProofReconcileCheckpoint(checkpoint_path)
    reopened = DurableJournal(journal_path)
    assert checkpoint.cursor(reopened.instance_id, "BTCUSDT", "1m") == 0
    assert len(registry.revisions(bar.stable_key())) == 1
    replay = reconcile_checkpointed_page(reopened, registry, checkpoint,
        symbol="BTCUSDT", interval="1m", limit=1)
    assert replay["existing"] == 1 and replay["added"] == 0
    assert checkpoint.cursor(reopened.instance_id, "BTCUSDT", "1m") > 0
    checkpoint.close()
    registry.close()
