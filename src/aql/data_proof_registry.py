"""SQLite append-only custody for Core observation revisions (offline, opt-in).

The registry is not connected to the realtime collector or Factory yet.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from aql.data_proof import ObservationVersion, ProofError, verify_chain


class RevisionRegistry:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS postcommit_receipts (
                version_id TEXT PRIMARY KEY,
                observed_after_commit_ms INTEGER NOT NULL,
                clock_scope TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS observation_revisions (
                version_id TEXT PRIMARY KEY,
                logical_bar_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(logical_bar_id, version_number)
            )
        """)

    def postcommit_receipt(self, version_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT observed_after_commit_ms, clock_scope FROM postcommit_receipts WHERE version_id=?",
            (version_id,)).fetchone()
        return ({"version_id": version_id, "observed_after_commit_ms": row[0],
                 "clock_scope": row[1]} if row else None)

    def revisions(self, logical_bar_id: str) -> tuple[ObservationVersion, ...]:
        rows = self._db.execute(
            "SELECT payload_json FROM observation_revisions WHERE logical_bar_id=? ORDER BY version_number",
            (logical_bar_id,)).fetchall()
        versions = tuple(ObservationVersion(**json.loads(row[0])) for row in rows)
        if versions:
            verify_chain(versions)
        return versions

    def append(self, version: ObservationVersion) -> str:
        """Atomic compare-and-append. Duplicate replay is idempotent."""
        self._db.execute("BEGIN IMMEDIATE")
        revision_committed = False
        try:
            existing = self.revisions(version.logical_bar_id)
            if existing and existing[-1].version_id == version.version_id:
                self._db.execute("COMMIT")
                return "ALREADY_PRESENT"
            verify_chain((*existing, version))
            self._db.execute(
                "INSERT INTO observation_revisions(version_id, logical_bar_id, version_number, payload_json) VALUES (?,?,?,?)",
                (version.version_id, version.logical_bar_id, version.version_number,
                 json.dumps(version.__dict__, sort_keys=True, separators=(",", ":"))))
            self._db.execute("COMMIT")
            revision_committed = True
            # This is a distinct second durable write after the revision COMMIT.
            # A crash before this write leaves receipt absent (UNKNOWN).
            self._db.execute(
                "INSERT INTO postcommit_receipts(version_id,observed_after_commit_ms,clock_scope) VALUES (?,?,?)",
                (version.version_id, time.time_ns() // 1_000_000, "LOCAL_WALL_CLOCK_UNATTESTED"))
            return "APPENDED"
        except Exception:
            if not revision_committed:
                self._db.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self._db.close()
