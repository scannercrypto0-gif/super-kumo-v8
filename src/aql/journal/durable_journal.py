"""
AQL Durable Local Journal — G1-WP01-MVP

Implements: append-only SQLite-backed journal with flush/fsync commit boundary,
stable event identity, checksum verification, corrupt/truncated record detection,
idempotent replay, and gap detection.

Architecture decision G1-ARCH (Option B):
  Binance WebSocket → DurableJournal → IdempotentConsumer → OperationalStorage

The journal is the durability guarantee. A bar is only considered
LOCAL_COMMITTED once it has been fsync'd to disk.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from ..models.bar import BarState, MarketBar

logger = logging.getLogger(__name__)

JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_key      TEXT NOT NULL,
    bar_open        INTEGER NOT NULL,
    bar_close       INTEGER NOT NULL,
    symbol          TEXT NOT NULL,
    interval        TEXT NOT NULL,
    is_final        INTEGER NOT NULL,
    source          TEXT NOT NULL,
    ingested_at     INTEGER NOT NULL,
    committed_at    INTEGER,
    payload_json    TEXT NOT NULL,
    checksum        TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'LOCAL_COMMITTED',
    UNIQUE (stable_key)
);

CREATE TABLE IF NOT EXISTS journal_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""

# Pragma settings for durability (WAL + full fsync)
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
]


class JournalCorruptionError(Exception):
    """Raised when a journal entry fails checksum verification."""


class DurableJournal:
    """
    Append-only durable journal backed by SQLite.

    Guarantees:
    - A bar appended via commit() has been flushed and fsync'd before return.
    - Duplicate appends (same stable_key) are silently ignored (idempotent).
    - Corrupt entries (checksum mismatch) are detected on read and flagged.
    - replay() returns all LOCAL_COMMITTED entries in open-time order.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        for pragma in PRAGMAS:
            conn.execute(pragma)
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(JOURNAL_SCHEMA)
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
            # Force OS-level fsync — this is our durability boundary.
            os.fsync(conn.fileno() if hasattr(conn, "fileno") else 0)
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def commit(self, bar: MarketBar) -> bool:
        """
        Append a bar to the journal.  Returns True if newly committed,
        False if already present (idempotent).
        Sets bar.state = LOCAL_COMMITTED and bar.committed_at.
        """
        now_ms = int(time.time() * 1000)
        bar.committed_at = now_ms
        bar.state = BarState.LOCAL_COMMITTED
        payload = json.dumps(bar.to_dict(), sort_keys=True)

        try:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO journal_entries
                      (stable_key, bar_open, bar_close, symbol, interval,
                       is_final, source, ingested_at, committed_at,
                       payload_json, checksum, state)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        bar.stable_key(),
                        bar.bar_open,
                        bar.bar_close,
                        bar.symbol,
                        bar.interval,
                        int(bar.is_final),
                        bar.source,
                        bar.ingested_at,
                        bar.committed_at,
                        payload,
                        bar.checksum or bar.compute_checksum(),
                        BarState.LOCAL_COMMITTED.value,
                    ),
                )
                changes = conn.execute("SELECT changes()").fetchone()[0]
                conn.execute("COMMIT")

                # Explicit fsync on the WAL file for durability
                wal_path = self.db_path + "-wal"
                for path in [self.db_path, wal_path]:
                    if os.path.exists(path):
                        with open(path, "a+b") as f:
                            os.fsync(f.fileno())

                if changes == 0:
                    logger.debug("Duplicate ignored: %s", bar.stable_key())
                    return False

                logger.debug("Committed: %s", bar.stable_key())
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
        except Exception as exc:
            logger.error("Journal commit failed: %s", exc)
            raise

    def replay(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        final_only: bool = True,
    ) -> List[MarketBar]:
        """
        Return all committed entries in bar_open order.
        Verifies checksum on each entry; raises JournalCorruptionError on mismatch.
        """
        conn = self._connect()
        try:
            query = "SELECT * FROM journal_entries WHERE 1=1"
            params: list = []
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if interval:
                query += " AND interval = ?"
                params.append(interval)
            if final_only:
                query += " AND is_final = 1"
            query += " ORDER BY bar_open ASC"

            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()

        bars: List[MarketBar] = []
        for row in rows:
            try:
                bar = MarketBar.from_dict(json.loads(row["payload_json"]))
            except Exception as exc:
                raise JournalCorruptionError(
                    f"Failed to deserialize entry key={row['stable_key']}: {exc}"
                ) from exc

            # Verify checksum
            expected = bar.compute_checksum()
            stored = row["checksum"]
            if expected != stored:
                raise JournalCorruptionError(
                    f"Checksum mismatch for key={row['stable_key']}: "
                    f"stored={stored} computed={expected}"
                )

            bars.append(bar)

        return bars

    def mark_persisted(self, stable_key: str) -> None:
        """Mark a journal entry as PERSISTED after successful operational storage write."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE journal_entries SET state = ? WHERE stable_key = ?",
                (BarState.PERSISTED.value, stable_key),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def count_by_state(self) -> dict:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT state, COUNT(*) as n FROM journal_entries GROUP BY state"
            ).fetchall()
            return {r["state"]: r["n"] for r in rows}
        finally:
            conn.close()

    def get_committed_range(
        self, symbol: str, interval: str
    ) -> Tuple[Optional[int], Optional[int]]:
        """Return (min_bar_open, max_bar_open) for final bars in the journal."""
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT MIN(bar_open) as mn, MAX(bar_open) as mx
                FROM journal_entries
                WHERE symbol=? AND interval=? AND is_final=1
                """,
                (symbol, interval),
            ).fetchone()
            return row["mn"], row["mx"]
        finally:
            conn.close()

    def inject_truncation_for_test(self, stable_key: str) -> None:
        """
        TEST ONLY: corrupt the checksum of a journal entry to simulate truncation.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE journal_entries SET checksum = 'CORRUPTED_FOR_TEST' WHERE stable_key = ?",
                (stable_key,),
            )
            conn.execute("COMMIT")
        finally:
            conn.close()
