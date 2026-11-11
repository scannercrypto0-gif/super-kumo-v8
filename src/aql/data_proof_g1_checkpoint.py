"""Crash-safe progress tracking for offline G1 proof reconciliation.

Cursor is scoped to a specific journal instance and stream. The checkpoint
moves only after successful, idempotent evidence registration. It is not a
claim of provider provenance or end-to-end stream completeness.
"""
import sqlite3
from aql.data_proof import ProofError
from aql.data_proof_g1_paged_reconcile import reconcile_persisted_page


class ProofReconcileCheckpoint:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS proof_reconcile_progress(
            journal_instance TEXT NOT NULL, symbol TEXT NOT NULL,
            interval TEXT NOT NULL, cursor INTEGER NOT NULL,
            PRIMARY KEY(journal_instance,symbol,interval))""")

    def cursor(self, journal_instance, symbol, interval):
        row = self.db.execute(
            "SELECT cursor FROM proof_reconcile_progress WHERE journal_instance=? AND symbol=? AND interval=?",
            (journal_instance, symbol, interval)).fetchone()
        return int(row[0]) if row else 0

    def advance(self, journal_instance, symbol, interval, cursor):
        if type(cursor) is not int or cursor < 0:
            raise ProofError("invalid proof reconciliation checkpoint")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.cursor(journal_instance, symbol, interval)
            if cursor < old:
                raise ProofError("reconciliation checkpoint regression")
            self.db.execute("""INSERT INTO proof_reconcile_progress
                (journal_instance,symbol,interval,cursor) VALUES(?,?,?,?)
                ON CONFLICT(journal_instance,symbol,interval)
                DO UPDATE SET cursor=excluded.cursor""",
                (journal_instance, symbol, interval, cursor))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()


def reconcile_checkpointed_page(journal, registry, checkpoint, *,
                                symbol, interval, limit=256):
    instance = journal.instance_id
    start = checkpoint.cursor(instance, symbol, interval)
    result = reconcile_persisted_page(journal, registry, symbol=symbol,
        interval=interval, after_entry_id=start, limit=limit)
    # A successful prefix is safe to checkpoint; the failed row is retried.
    checkpoint.advance(instance, symbol, interval, result["next_cursor"])
    return result
