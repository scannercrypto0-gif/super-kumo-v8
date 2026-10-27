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

  CORE-ARCH-58: the added receipt observes successful SQLite COMMIT return.
  It is not a hardware fsync-completion clock or proof of power-loss survival.
  Legacy committed_at remains a pre-COMMIT marker.

  Reference: https://www.sqlite.org/pragma.html#pragma_synchronous
  "FULL: SQLite will use the xSync method of the VFS to ensure that content
   is safely written to the disk surface prior to continuing."
"""
from __future__ import annotations

import json
import uuid
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ..models.bar import BarState, MarketBar
from ..lanes import WritePriority
from ..g1_integrity import (CommitEvidenceError, IntegrityAccess, ContentConflictError, content, fingerprint,
    init_integrity, post_commit_receipt, receipt, record_event, require_eligible_db)

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


class DurableJournal(IntegrityAccess):
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
        self.write_priority = WritePriority()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False, timeout=0.25)
        conn.row_factory = sqlite3.Row
        for pragma in PRAGMAS:
            conn.execute(pragma)
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(JOURNAL_SCHEMA)
            init_integrity(conn)
            conn.execute("INSERT OR IGNORE INTO journal_meta(key,value) VALUES ('instance_id',?)",
                         (uuid.uuid4().hex,))
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()

    @property
    def instance_id(self) -> str:
        conn = self._connect()
        try:
            row = conn.execute("SELECT value FROM journal_meta WHERE key='instance_id'").fetchone()
            if row is None:
                raise JournalCorruptionError("Journal identity missing")
            return row[0]
        finally:
            conn.close()

    def commit(self, bar: MarketBar, *, background: bool = False) -> bool:
        with self.write_priority.hold(background):
            return self._commit(bar)

    def _original_bar(self, conn, key):
        row = conn.execute("SELECT payload_json FROM journal_entries WHERE stable_key=?", (key,)).fetchone()
        return MarketBar.from_dict(json.loads(row[0])) if row else None

    def commit_receipt(self, key):
        """Core-only v1 observed data-COMMIT return; never backfill legacy times."""
        conn = self._connect()
        try:
            result = receipt(conn,"BAR",key)
            bar = self._original_bar(conn,key)
            marker = conn.execute("SELECT version FROM g1_record_contracts WHERE stable_key=?", (key,)).fetchone()
            result["record_contract_version"] = marker[0] if marker else (0 if bar is not None else None)
            if not result["version"]:
                result["status"] = ("NO_RECORD" if bar is None else
                    "V1_COMPLETION_UNCONFIRMED" if marker else "LEGACY_COMPLETION_UNVERIFIED")
            if result["version"] and (marker is None or marker[0] != 1 or bar is None
                    or result["content_digest"] != fingerprint(content(bar))):
                raise JournalCorruptionError("Commit receipt/content mismatch")
            return result
        finally:
            conn.close()

    def _commit(self, bar: MarketBar) -> bool:
        # committed_at remains the historical pre-attempt marker. No MarketBar
        # fields/checksums/export schemas are changed by the new sidecar receipt.
        material = content(bar)
        now_ms = int(time.time() * 1000)
        bar.committed_at = now_ms
        bar.state = BarState.LOCAL_COMMITTED
        conn = self._connect()
        from ..delivery.authority import enabled, prepare_candidate
        if enabled(conn):
            conn.close()
            prepare_candidate(self,bar)
            conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            prior = self._original_bar(conn,bar.stable_key())
            from ..delivery.authority import enabled, activation_reserved, PublicationDenied
            if activation_reserved(conn) and not enabled(conn):
                raise PublicationDenied("Incomplete v2 activation; legacy writes denied")
            if prior is None and enabled(conn):
                raise PublicationDenied("Finite v2 source is frozen; no legacy appends")
            if prior is not None and content(prior) != material:
                evidence = record_event(conn,prior,bar)
                conn.execute("COMMIT")  # conflict evidence survives raised error
                try:
                    post_commit_receipt(conn,"AUDIT",evidence["event_id"],fingerprint(evidence),evidence["detected_at_ms"])
                except CommitEvidenceError:
                    # Quarantine already committed; lack of a timing receipt
                    # must not conceal the content conflict or enable ACK.
                    raise ContentConflictError(evidence)
                raise ContentConflictError(evidence)
            require_eligible_db(conn,bar.stable_key())
            if prior is not None:
                if enabled(conn):
                    # A legacy collector created before activation must not
                    # treat a matching retry as authority to write another DB.
                    raise PublicationDenied("Activated source refuses legacy writer retries")
                conn.execute("COMMIT")
                return False  # identical retry; no fabricated new/legacy timestamp
            conn.execute("INSERT INTO journal_entries "
                "(stable_key,bar_open,bar_close,symbol,interval,is_final,source,ingested_at,committed_at,payload_json,checksum,state) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                    bar.stable_key(),bar.bar_open,bar.bar_close,bar.symbol,bar.interval,
                    int(bar.is_final),bar.source,bar.ingested_at,bar.committed_at,
                    json.dumps(bar.to_dict(),sort_keys=True),bar.checksum or bar.compute_checksum(),
                    BarState.LOCAL_COMMITTED.value))
            conn.execute("INSERT INTO g1_record_contracts VALUES (?,1)",(bar.stable_key(),))
            conn.execute("COMMIT")
            # This observation follows the data COMMIT; its own persistence is
            # a separate FULL transaction. Failure never invents a v1 receipt.
            post_commit_receipt(conn,"BAR",bar.stable_key(),fingerprint(material),max(now_ms,bar.ingested_at))
            return True
        except Exception:
            if conn.in_transaction: conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def startup_entry_boundary(self) -> int:
        """Last journal row ID committed before collection starts.

        AUTOINCREMENT journal IDs form a durable insertion-order boundary;
        this is not a market-time timestamp or a row-count assumption.
        """
        conn = self._connect()
        try:
            from ..delivery.authority import deny_legacy
            deny_legacy(conn)
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM journal_entries").fetchone()
            return int(row[0])
        finally:
            conn.close()

    def replay(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        final_only: bool = True,
        *, pending_only: bool = False, limit: int | None = None,
        include_quarantined: bool = False,
        max_entry_id: int | None = None,
        persisted_only: bool = False,
        after_entry_id: int | None = None,
    ) -> List[MarketBar]:
        """
        Return eligible committed entries in bar_open order.
        include_quarantined=True is FORENSIC ONLY, never decision permission.
        Verifies checksum on each entry; raises JournalCorruptionError on mismatch.
        """
        conn = self._connect()
        try:
            query = "SELECT * FROM journal_entries WHERE 1=1"
            from ..delivery.authority import deny_legacy
            deny_legacy(conn)
            params: list = []
            if after_entry_id is not None:
                if type(after_entry_id) is not int or after_entry_id < 0:
                    raise ValueError("Non-negative journal cursor required")
                query += " AND id > ?"
                params.append(after_entry_id)
            if max_entry_id is not None:
                if type(max_entry_id) is not int or max_entry_id < 0:
                    raise ValueError("Non-negative journal entry boundary required")
                query += " AND id <= ?"
                params.append(max_entry_id)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if interval:
                query += " AND interval = ?"
                params.append(interval)
            if final_only:
                query += " AND is_final = 1"
            if persisted_only and pending_only:
                raise ValueError("pending_only and persisted_only are mutually exclusive")
            if persisted_only:
                query += " AND state = ?"
                params.append(BarState.PERSISTED.value)
            if pending_only:
                query += " AND state = ?"
                params.append(BarState.LOCAL_COMMITTED.value)
            if not include_quarantined:
                query += " AND stable_key NOT IN (SELECT stable_key FROM g1_integrity_events)"
            query += " ORDER BY id ASC" if after_entry_id is not None else " ORDER BY bar_open ASC"
            if limit is not None:
                if type(limit) is not int or limit < 1:
                    raise ValueError("Positive batch limit required")
                query += " LIMIT ?"
                params.append(limit)

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
        with self.write_priority.hold(background=True):
            self._mark_persisted(stable_key)

    def _mark_persisted(self, stable_key: str) -> None:
        """Mark a journal entry as PERSISTED after successful operational storage write."""
        conn = self._connect()
        try:
            from ..delivery.authority import deny_legacy
            deny_legacy(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                require_eligible_db(conn,stable_key)
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
        *,
        startup_max_entry_id: int | None = None,
    ) -> Tuple[int, int, int, List[Tuple[int, int]]]:
        """
        On process restart (including after SIGKILL):

        1. Replay journal LOCAL_COMMITTED entries absent from the operational
           store and upsert them directly — every missing bar gets a confirmed
           write, with per-key ACK and journal state update.  This is the
           real journal-to-store replay that guarantees no bar is permanently
           lost between a durable journal commit and a store write.

        2. Detect ALL gaps in the known bar sequence:
           a. Internal gaps — holes between consecutive known bar_opens
              (e.g. bars A,B,D,E present → C is an internal gap).
           b. Trailing gap — from last known bar to now.

           Internal gaps are returned first, trailing gap last, all as a
           flat list of (gap_start_ms, gap_end_ms) tuples.  The caller
           (pipeline) iterates the list and calls recover_gap() per gap.

        Returns:
          (bars_replayed, replay_inserted, replay_errors, gaps)

          bars_replayed:   number of journal bars found missing from the store
          replay_inserted: number successfully upserted into the store this call
          replay_errors:   number that failed to upsert (store write error)
          gaps:            List[(gap_start_ms, gap_end_ms)] — all detected gaps,
                           internal first then trailing; empty when no gaps.

        If there is no stored data at all, returns (0, 0, 0, []).

        Design note: REST gap recovery is NOT called from here.  The caller
        (pipeline) uses the returned gap list to invoke recover_gap().
        """
        from ..recovery.gap_recovery import _binance_interval_ms
        from ..delivery.authority import register_legacy_writer
        register_legacy_writer(self, 'startup-reconcile')

        interval_ms = _binance_interval_ms(interval)

        # Step 1: replay journal — find bars committed locally but absent from store
        journal_bars = self.replay(symbol=symbol, interval=interval, final_only=True,
                                   max_entry_id=startup_max_entry_id)
        stored_keys = store.get_stored_keys(symbol, interval)

        bars_replayed = 0
        replay_inserted = 0
        replay_errors = 0

        for bar in journal_bars:
            missing = bar.bar_open not in stored_keys
            bars_replayed += int(missing)
            try:
                self.require_eligible(bar.stable_key())
                store.upsert(bar)  # validates matching content even for existing keys
                self.mark_persisted(bar.stable_key())
                replay_inserted += int(missing)
            except ContentConflictError as exc:
                from ..g1_integrity import propagate_conflict
                propagate_conflict(exc,self,store)
                replay_errors += 1
            except Exception as exc:
                replay_errors += 1
                logger.error("startup_reconcile failed for %s: %s",bar.stable_key(),exc)

        # Step 2: detect ALL gaps (internal + trailing) in the known bar sequence.
        # Re-read store keys to include any bars just upserted in the replay above.
        store_opens_after: set = store.get_stored_keys(symbol, interval)
        # A replayed key may have become quarantined during reconciliation.
        quarantined = self.quarantined_keys(symbol, interval)
        journal_opens: set = {b.bar_open for b in journal_bars if b.stable_key() not in quarantined}
        store_opens_after -= {int(key.rsplit(':', 1)[1]) for key in quarantined}

        all_known_opens: List[int] = sorted(journal_opens | store_opens_after)
        gaps: List[Tuple[int, int]] = []

        if not all_known_opens:
            return bars_replayed, replay_inserted, replay_errors, gaps

        # 2a. Internal gaps: consecutive known opens separated by > interval_ms
        for i in range(len(all_known_opens) - 1):
            expected_next = all_known_opens[i] + interval_ms
            actual_next = all_known_opens[i + 1]
            if actual_next > expected_next:
                # One or more bars missing between all_known_opens[i] and all_known_opens[i+1].
                # gap_start = first missing bar_open; gap_end = first present bar after gap
                # (recover_gap will align internally and expect bars in [expected_next, actual_next)).
                gaps.append((expected_next, actual_next))

        # 2b. Trailing gap: from last known bar to now
        last_known_open = all_known_opens[-1]
        trailing_start = last_known_open + interval_ms
        trailing_end = int(time.time() * 1000)
        if trailing_start < trailing_end:
            gaps.append((trailing_start, trailing_end))

        if gaps:
            logger.info(
                "startup_reconcile: symbol=%s interval=%s "
                "bars_replayed=%d replay_inserted=%d replay_errors=%d "
                "gaps_detected=%d: %s",
                symbol, interval,
                bars_replayed, replay_inserted, replay_errors,
                len(gaps), gaps,
            )

        return bars_replayed, replay_inserted, replay_errors, gaps

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
        """Return eligible final-bar bounds; physical rows remain available for audit."""
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT MIN(bar_open) as mn, MAX(bar_open) as mx
                FROM journal_entries
                WHERE symbol=? AND interval=? AND is_final=1
                AND stable_key NOT IN (SELECT stable_key FROM g1_integrity_events)
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
