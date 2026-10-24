"""
AQL Operational Storage — G1-WP01-MVP

SQLite operational store (Supabase deferred — NOT TESTED in MVP).
Idempotent upsert: duplicate bar_open for same symbol/interval is a no-op.
Only final bars are written (is_final=True).
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from ..models.bar import BarState, MarketBar

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_bars (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    interval        TEXT NOT NULL,
    bar_open        INTEGER NOT NULL,
    bar_close       INTEGER NOT NULL,
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    volume          REAL NOT NULL,
    is_final        INTEGER NOT NULL DEFAULT 1,
    source          TEXT NOT NULL,
    ingested_at     INTEGER NOT NULL,
    committed_at    INTEGER,
    checksum        TEXT NOT NULL,
    state           TEXT NOT NULL,
    UNIQUE (symbol, interval, bar_open)
);

CREATE INDEX IF NOT EXISTS idx_bars_symbol_interval_open
    ON market_bars (symbol, interval, bar_open);
"""

PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
]


class OperationalStore:
    """
    SQLite-backed operational storage.
    - Idempotent: duplicate bar_open for same symbol+interval → no new row.
    - Only writes bars with is_final=True.
    - Supabase integration: NOT TESTED (deferred per G1-PLAN-01/B).
    """

    SUPABASE_STATUS = "NOT_TESTED"

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=0.25)
        conn.row_factory = sqlite3.Row
        for pragma in PRAGMAS:
            conn.execute(pragma)
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def upsert(self, bar: MarketBar) -> bool:
        """
        Idempotent upsert. Returns True if new row inserted, False if already exists.
        Only accepts final bars (is_final=True).
        Raises ValueError for non-final bars.
        """
        if not bar.is_final:
            raise ValueError(
                f"Non-final bar rejected: key={bar.stable_key()} "
                "(only final bars permitted in operational store per TIME-01)"
            )

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO market_bars
                  (symbol, interval, bar_open, bar_close, open, high, low, close,
                   volume, is_final, source, ingested_at, committed_at, checksum, state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    bar.symbol,
                    bar.interval,
                    bar.bar_open,
                    bar.bar_close,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    int(bar.is_final),
                    bar.source,
                    bar.ingested_at,
                    bar.committed_at,
                    bar.checksum or bar.compute_checksum(),
                    bar.state.value,
                ),
            )
            changes = conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()
            inserted = changes > 0
            if inserted:
                logger.debug("Stored: %s", bar.stable_key())
            else:
                logger.debug("Duplicate skipped: %s", bar.stable_key())
            return inserted
        finally:
            conn.close()

    def bulk_upsert(self, bars: List[MarketBar]) -> dict:
        """Upsert multiple bars. Returns counts dict."""
        inserted = 0
        skipped = 0
        errors = 0
        for bar in bars:
            try:
                if self.upsert(bar):
                    inserted += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error("bulk_upsert error for %s: %s", bar.stable_key(), exc)
                errors += 1
        return {"inserted": inserted, "skipped": skipped, "errors": errors}

    def count(self, symbol: Optional[str] = None, interval: Optional[str] = None) -> int:
        conn = self._connect()
        try:
            q = "SELECT COUNT(*) FROM market_bars WHERE 1=1"
            params = []
            if symbol:
                q += " AND symbol=?"
                params.append(symbol)
            if interval:
                q += " AND interval=?"
                params.append(interval)
            return conn.execute(q, params).fetchone()[0]
        finally:
            conn.close()

    def get_stored_keys(self, symbol: str, interval: str) -> set:
        """Return set of bar_open values already in the store."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT bar_open FROM market_bars WHERE symbol=? AND interval=?",
                (symbol, interval),
            ).fetchall()
            return {r["bar_open"] for r in rows}
        finally:
            conn.close()

    def get_range(self, symbol: str, interval: str):
        """Return (min_bar_open, max_bar_open) stored."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT MIN(bar_open) as mn, MAX(bar_open) as mx FROM market_bars WHERE symbol=? AND interval=?",
                (symbol, interval),
            ).fetchone()
            return row["mn"], row["mx"]
        finally:
            conn.close()
