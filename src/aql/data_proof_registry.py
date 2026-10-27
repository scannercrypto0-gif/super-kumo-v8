"""SQLite append-only custody for Core observation revisions (offline, opt-in).

The registry is not connected to the realtime collector or Factory yet.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from aql.data_proof import ObservationVersion, ProofError, verify_chain


class RevisionRegistry:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS observation_revisions (
                version_id TEXT PRIMARY KEY,
                logical_bar_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(logical_bar_id, version_number)
            )
        """)

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
            return "APPENDED"
        except (Exception,):
            self._db.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self._db.close()
