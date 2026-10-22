"""
AQL Durable Local Journal — G1-WP01-MVP

Implements: append-only SQLite-backed journal with WAL commit durability,
stable event identity, checksum verification, corrupt/truncated record detection,
idempotent replay, and gap detection.

Architecture decision G1-ARCH (Option B):
  Binance WebSocket → DurableJournal → IdempotentConsumer → OperationalStorage

Durability guarantee:
  With PRAGMA synchronous=FULL and WAL mode, SQLite guarantees that a
  successful COMMIT call has been flushed and fsynced to disk before returning.
  No additional manual fsync on the WAL or database file is required or safe
  during an active session.

  Reference: https://www.sqlite.org/pragma.html#pragma_synchronous
  "FULL: SQLite will use the xSync method of the VFS to ensure that content
   is safely written to the disk surface prior to continuing."
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple

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

# Pragma settings for durability (WAL + full fsync on every COMMIT)
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
    - A bar appended via commit() has been durably written before return.
      SQLite WAL + synchronous=FULL provides this; no manual fsync is used.
    - Duplicate appends (same stable_key) are silently ignored (idempotent).
    - Corrupt entries (checksum mismatch) are detected on read and flagged.
    - replay() returns all LOCAL_COMMITTED entries in open-time order.
    - startup_reconcile() detects gaps that arose from unclean shutdown
      (e.g. SIGKILL where _on_close was never called).
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
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

    def commit(self, bar: MarketBar) -> bool:
        """
        Append a bar to the journal.  Returns True if newly committed,
        False if already present (idempotent).
        Sets bar.state = LOCAL_COMMITTED and bar.committed_at.

        Durability: PRAGMA synchronous=FULL guarantees that the COMMIT call
        itself fsyncs the WAL before returning.  No additional file-level
        fsync is performed (opening the WAL file during an active session
        is unsafe and unnecessary).
        """
        now_ms = int(time.time() * 1000)
        bar.committed_at = now_ms
        bar.state = BarState.LOCAL_COMMITTED
        payload = json.dumps(bar.to_dict(), sort_keys=True)

        conn = self._connect()
        try:
            # Separate try/except blocks so that ROLLBACK is only attempted
            # when BEGIN/INSERT/COMMIT itself failed — never after a successful COMMIT.
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
                # With synchronous=FULL, this COMMIT call fsyncs to disk before
                # returning.  No additional file-level fsync needed or safe.
                conn.execute("COMMIT")
            except sqlite3.Error:
                # COMMIT has NOT succeeded — safe to rollback.
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        except Exception as exc:
            logger.error("Journal commit failed: %s", exc)
            raise
        finally:
            conn.close()

        if changes == 0:
            logger.debug("Duplicate ignored: %s", bar.stable_key())
            return False

        logger.debug("Committed: %s", bar.stable_key())
        return True

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
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE journal_entries SET state = ? WHERE stable_key = ?",
                    (BarState.PERSISTED.value, stable_key),
                )
                conn.execute("COMMIT")
            except sqlite3.Error:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        finally:
            conn.close()

    def startup_reconcile(
        self,
        store,
        symbol: str,
        interval: str,
    ) -> Tuple[int, int, int, Optional[int], Optional[int]]:
        """
        On process restart (including after SIGKILL):

        1. Replay journal LOCAL_COMMITTED entries absent from the operational
           store and upsert them directly — every missing bar gets a confirmed
           write, with per-key ACK and journal state update.  This is the
           real journal-to-store replay that guarantees no bar is permanently
           lost between a durable journal commit and a store write.

        2. Compute the gap from the last durably known bar to now for the
           subsequent REST recovery pass.

        Returns:
          (bars_replayed, replay_inserted, replay_errors, gap_start_ms, gap_end_ms)

          bars_replayed:   number of journal bars found missing from the store
          replay_inserted: number successfully upserted into the store this call
          replay_errors:   number that failed to upsert (store write error)
          gap_start_ms:    open_time of first potentially-missing bar
                           (last_known_bar_open + interval_ms), or None
          gap_end_ms:      current time in ms, or None

        If there is no stored data at all, returns (0, 0, 0, None, None).

        Design note: REST gap recovery is NOT called from here.  The caller
        (pipeline) uses the returned gap bounds to invoke recover_gap().
        """
        from ..recovery.gap_recovery import _binance_interval_ms

        interval_ms = _binance_interval_ms(interval)

        # Step 1: replay journal — find bars committed locally but absent from store
        journal_bars = self.replay(symbol=symbol, interval=interval, final_only=True)
        stored_keys = store.get_stored_keys(symbol, interval)

        bars_replayed = 0
        replay_inserted = 0
        replay_errors = 0

        for bar in journal_bars:
            if bar.bar_open in stored_keys:
                # Already in store — sync journal state to PERSISTED
                try:
                    self.mark_persisted(bar.stable_key())
                except Exception as exc:
                    logger.warning(
                        "startup_reconcile: mark_persisted failed for %s (non-fatal): %s",
                        bar.stable_key(), exc,
                    )
            else:
                # Missing from store — perform real upsert (journal-to-store replay)
                bars_replayed += 1
                try:
                    store.upsert(bar)
                    replay_inserted += 1
                    try:
                        self.mark_persisted(bar.stable_key())
                    except Exception as exc:
                        logger.warning(
                            "startup_reconcile: mark_persisted failed after upsert "
                            "for %s (non-fatal): %s", bar.stable_key(), exc,
                        )
                except Exception as exc:
                    replay_errors += 1
                    logger.error(
                        "startup_reconcile: store upsert failed for %s: %s",
                        bar.stable_key(), exc,
                    )

        # Step 2: compute REST recovery gap from last known bar to now
        # Re-read stored_keys to include bars just replayed
        _, last_store_open = store.get_range(symbol, interval)
        last_journal_open: Optional[int] = (
            max(b.bar_open for b in journal_bars) if journal_bars else None
        )

        candidates = [x for x in [last_journal_open, last_store_open] if x is not None]
        if not candidates:
            return bars_replayed, replay_inserted, replay_errors, None, None

        last_known_open = max(candidates)
        gap_start_ms = last_known_open + interval_ms
        gap_end_ms = int(time.time() * 1000)

        if gap_start_ms >= gap_end_ms:
            return bars_replayed, replay_inserted, replay_errors, None, None

        logger.info(
            "startup_reconcile: symbol=%s interval=%s "
            "bars_replayed=%d replay_inserted=%d replay_errors=%d "
            "gap_start=%d gap_end=%d gap_duration_s=%.0f",
            symbol, interval,
            bars_replayed, replay_inserted, replay_errors,
            gap_start_ms, gap_end_ms,
            (gap_end_ms - gap_start_ms) / 1000,
        )
        return bars_replayed, replay_inserted, replay_errors, gap_start_ms, gap_end_ms

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
