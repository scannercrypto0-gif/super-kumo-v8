"""Durable bounded full-sweep cycle for late persisted journal ACKs.

Separate from fast-path checkpoint. A cycle starts at row zero and walks a
fixed journal high-water mark; only completed cycles reset their cursor.
"""
import sqlite3
import time
from aql.data_proof import ProofError
from aql.data_proof_g1_paged_reconcile import reconcile_persisted_page


class SweepProgress:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS proof_sweep_generation(
            journal_instance TEXT NOT NULL, symbol TEXT NOT NULL,
            interval TEXT NOT NULL, generation INTEGER NOT NULL,
            PRIMARY KEY(journal_instance,symbol,interval))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS proof_sweep_progress(
            journal_instance TEXT NOT NULL, symbol TEXT NOT NULL,
            interval TEXT NOT NULL, cursor INTEGER NOT NULL,
            high_water INTEGER NOT NULL,
            PRIMARY KEY(journal_instance,symbol,interval))""")

    def state(self, instance, symbol, interval):
        row = self.db.execute(
            "SELECT cursor,high_water FROM proof_sweep_progress WHERE journal_instance=? AND symbol=? AND interval=?",
            (instance, symbol, interval)).fetchone()
        return tuple(row) if row else None

    def generation(self, instance, symbol, interval):
        row = self.db.execute(
            "SELECT generation FROM proof_sweep_generation WHERE journal_instance=? AND symbol=? AND interval=?",
            (instance, symbol, interval)).fetchone()
        return int(row[0]) if row else 0

    def save(self, instance, symbol, interval, cursor, high_water, *, expected=None, expected_generation=None):
        if type(expected_generation) is not int or expected_generation < 0:
            raise ProofError("sweep generation token required")
        if any(type(x) is not int or x < 0 for x in (cursor, high_water)):
            raise ProofError("invalid sweep checkpoint")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.state(instance, symbol, interval)
            if self.generation(instance, symbol, interval) != expected_generation:
                raise ProofError("stale sweep generation")
            if current != expected:
                raise ProofError("stale sweep checkpoint update")
            if current is not None and (high_water != current[1] or cursor < current[0]):
                raise ProofError("sweep checkpoint regression")
            if current is None:
                self.db.execute("""INSERT INTO proof_sweep_generation VALUES(?,?,?,1)
                    ON CONFLICT(journal_instance,symbol,interval)
                    DO UPDATE SET generation=generation+1""",
                    (instance, symbol, interval))
            self.db.execute("""INSERT INTO proof_sweep_progress VALUES(?,?,?,?,?)
                ON CONFLICT(journal_instance,symbol,interval)
                DO UPDATE SET cursor=excluded.cursor,high_water=excluded.high_water""",
                (instance, symbol, interval, cursor, high_water))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def clear(self, instance, symbol, interval, *, expected, expected_generation):
        if type(expected_generation) is not int or expected_generation < 0:
            raise ProofError("sweep generation token required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if expected_generation is not None and self.generation(instance, symbol, interval) != expected_generation:
                raise ProofError("stale sweep generation")
            if self.state(instance, symbol, interval) != expected:
                raise ProofError("stale sweep checkpoint clear")
            self.db.execute("DELETE FROM proof_sweep_progress WHERE journal_instance=? AND symbol=? AND interval=?",
                            (instance, symbol, interval))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()


def run_sweep_slice(journal, registry, progress, *, symbol, interval,
                    page_size=256, max_pages=4, max_elapsed_ms=250):
    if type(max_pages) is not int or not 1 <= max_pages <= 10000:
        raise ProofError("invalid sweep slice limit")
    if type(max_elapsed_ms) is not int or not 1 <= max_elapsed_ms <= 60000:
        raise ProofError("invalid sweep time budget")
    started = time.monotonic_ns()
    instance = journal.instance_id
    state = progress.state(instance, symbol, interval)
    generation = progress.generation(instance, symbol, interval)
    if state is None:
        state = (0, journal.startup_entry_boundary())
        progress.save(instance, symbol, interval, *state, expected=None,
                      expected_generation=generation)
        generation = progress.generation(instance, symbol, interval)
    cursor, high_water = state
    added = existing = pages = 0
    for _ in range(max_pages):
        if pages and (time.monotonic_ns() - started) // 1_000_000 >= max_elapsed_ms:
            break
        result = reconcile_persisted_page(journal, registry, symbol=symbol,
            interval=interval, after_entry_id=cursor, limit=page_size,
            max_entry_id=high_water)
        added += result["added"]
        existing += result["existing"]
        pages += 1
        previous = (cursor, high_water)
        cursor = result["next_cursor"]
        progress.save(instance, symbol, interval, cursor, high_water,
                      expected=previous, expected_generation=generation)
        if result["failed_key"]:
            return {"complete": False, "failed_key": result["failed_key"],
                    "added": added, "existing": existing, "pages": pages}
        if result["complete"]:
            progress.clear(instance, symbol, interval,
                           expected=(cursor, high_water),
                           expected_generation=generation)
            return {"complete": True, "failed_key": None,
                    "added": added, "existing": existing, "pages": pages}
    return {"complete": False, "failed_key": None,
            "added": added, "existing": existing, "pages": pages}
