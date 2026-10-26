"""Explicit sandbox-only PostgreSQL adapter; SQLite remains the core store.

No credentials are read automatically. The caller supplies an isolated sandbox
connection factory. Connection exceptions are deliberately redacted.
"""
from __future__ import annotations
from typing import Protocol
from contextlib import contextmanager
import json
import sqlite3
import time
from ..models.bar import MarketBar


class BarStore(Protocol):
    def upsert(self, bar: MarketBar) -> bool: ...


class StoreUnavailable(RuntimeError):
    pass


class PostgresSandboxStore:
    def __init__(self, connect, *, sandbox: bool, attempts=3, sleep=time.sleep):
        if sandbox is not True:
            raise ValueError("Explicit sandbox authorization required")
        if type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError("Retry bound must be 1..3")
        self.connect, self.attempts, self.sleep = connect, attempts, sleep

    def upsert(self, bar: MarketBar) -> bool:
        if bar.is_final is not True:
            raise ValueError("Non-final bar rejected")
        if bar.checksum is not None and bar.checksum != bar.compute_checksum():
            raise ValueError("Bar checksum mismatch")
        values = (bar.symbol, bar.interval, bar.bar_open, bar.bar_close,
                  bar.open, bar.high, bar.low, bar.close, bar.volume,
                  bar.is_final, bar.source, bar.ingested_at, bar.committed_at,
                  bar.checksum or bar.compute_checksum(), bar.state.value)
        for attempt in range(self.attempts):
            conn = None
            try:
                conn = self.connect()
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout = '5s'")
                    cur.execute("""
                        INSERT INTO aql_sandbox.market_bars
                        (symbol, interval, bar_open, bar_close, open, high, low,
                         close, volume, is_final, source, ingested_at,
                         committed_at, checksum, state)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (symbol, interval, bar_open) DO NOTHING
                        RETURNING bar_open
                    """, values)
                    inserted = cur.fetchone() is not None
                    if not inserted:
                        cur.execute("SELECT checksum FROM aql_sandbox.market_bars "
                                    "WHERE symbol=%s AND interval=%s AND bar_open=%s",
                                    (bar.symbol, bar.interval, bar.bar_open))
                        existing = cur.fetchone()
                        if existing is None or existing[0] != values[-2]:
                            raise ValueError("Conflicting or unconfirmed duplicate")
                conn.commit()
                return inserted
            except Exception as exc:
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                code = getattr(exc, "sqlstate", "") or ""
                transient = (isinstance(exc, (TimeoutError, ConnectionError)) or (
                    not code and type(exc).__module__.startswith("psycopg")
                    and type(exc).__name__ in ("OperationalError", "InterfaceError"))) or (
                    code.startswith(("08", "40")) or code in ("55P03", "57P01"))
                if not transient or attempt + 1 == self.attempts:
                    raise StoreUnavailable("Sandbox write unconfirmed; durable replay retained") from None
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            self.sleep(min(0.1 * 2**attempt, 0.4))
        raise AssertionError("unreachable")


class SandboxReplicator:
    """Independent durable cursor: local store ACK never ACKs remote delivery.

    One bounded page per call, remote commit BEFORE local cursor commit.
    Crash between the two repeats an idempotent remote write.
    """
    def __init__(self, journal, remote: BarStore, checkpoint_path: str,
                 *, consumer_id="supabase-sandbox", batch_size=64):
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("Invalid batch size")
        self.journal, self.remote = journal, remote
        self.path, self.consumer_id, self.batch_size = checkpoint_path, consumer_id, batch_size
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS delivery_cursor "
                         "(consumer TEXT PRIMARY KEY, journal_path TEXT NOT NULL, seq INTEGER NOT NULL)")
        from pathlib import Path
        self.identity = str(Path(journal.db_path).resolve()) + "#" + journal.instance_id
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO delivery_cursor VALUES (?, ?, 0)",
                         (consumer_id, self.identity))
            if conn.execute("SELECT journal_path FROM delivery_cursor WHERE consumer=?",
                            (consumer_id,)).fetchone()[0] != self.identity:
                raise ValueError("Cursor belongs to a different journal")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=0.25)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            with conn:
                yield conn
        finally:
            conn.close()

    def deliver_once(self):
        from pathlib import Path
        if str(Path(self.journal.db_path).resolve()) + "#" + self.journal.instance_id != self.identity:
            raise ValueError("Journal replaced; delivery denied")
        with self._connect() as checkpoint:
            cursor = checkpoint.execute("SELECT seq FROM delivery_cursor WHERE consumer=?",
                                        (self.consumer_id,)).fetchone()[0]
        conn = self.journal._connect()
        try:
            from ..delivery.authority import deny_legacy
            deny_legacy(conn)
            maximum = conn.execute("SELECT COALESCE(MAX(id),0) FROM journal_entries").fetchone()[0]
            if cursor > maximum:
                raise ValueError("Journal rollback behind delivery cursor")
            rows = conn.execute("SELECT id,payload_json,checksum FROM journal_entries "
                                "WHERE id>? ORDER BY id LIMIT ?",
                                (cursor, self.batch_size)).fetchall()
        finally:
            conn.close()
        delivered = 0
        for row in rows:
            bar = MarketBar.from_dict(json.loads(row["payload_json"]))
            if bar.compute_checksum() != row["checksum"]:
                raise ValueError("Journal integrity failure; remote cursor unchanged")
            self.journal.require_eligible(bar.stable_key())
            self.remote.upsert(bar)  # Matching remote key/content is required before ACK.
            self.journal.require_eligible(bar.stable_key())
            with self._connect() as checkpoint:
                checkpoint.execute("UPDATE delivery_cursor SET seq=MAX(seq,?) WHERE consumer=?",
                                   (row["id"], self.consumer_id))
            delivered += 1
        return delivered
