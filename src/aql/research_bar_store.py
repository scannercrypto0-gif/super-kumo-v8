"""Research-only durable finalized-bar repository. No source acquisition or host activation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from aql.research_timeframes import project_finalized_1m, WIDTHS, MINUTE


def _seal(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


class ResearchBarStore:
    """Append-only SQLite research store; source authenticity remains external."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=10)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS finalized_bars (
            symbol TEXT NOT NULL, interval TEXT NOT NULL, open_ms INTEGER NOT NULL,
            sha256 TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(symbol, interval, open_ms))""")
        self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def insert_1m(self, bar, *, source_class="FORWARD_UNQUALIFIED"):
        # Reuse exact finality, provenance, decimal and clock checks.
        projected = project_finalized_1m([bar], "1m", source_class=source_class)
        self._insert(projected)
        return projected

    def _insert(self, projected):
        with self.db:
            self.insert_batch([projected])

    def insert_batch(self, projected_rows):
        """Atomically append a validated batch; reject any conflicting key."""
        if not isinstance(projected_rows, list) or not projected_rows:
            raise ValueError("BATCH_REQUIRED")
        with self.db:
            for projected in projected_rows:
                self._insert_in_transaction(projected)

    def _insert_in_transaction(self, projected):
        key = (projected["symbol"], projected["interval"], projected["open_ms"])
        payload = json.dumps(projected, sort_keys=True, separators=(",", ":"))
        self.db.execute("INSERT OR IGNORE INTO finalized_bars VALUES (?,?,?,?,?)",
                        (*key, projected["sha256"], payload))
        row = self.db.execute(
            "SELECT sha256,payload FROM finalized_bars WHERE symbol=? AND interval=? AND open_ms=?",
            key).fetchone()
        if row != (projected["sha256"], payload):
            raise ValueError("SOURCE_REWRITE_DENIED")

    def read(self, symbol, interval, open_ms):
        row = self.db.execute(
            "SELECT sha256,payload FROM finalized_bars WHERE symbol=? AND interval=? AND open_ms=?",
            (symbol, interval, open_ms)).fetchone()
        if row is None:
            return None
        try:
            result = json.loads(row[1])
            if type(result) is not dict:
                raise ValueError("STORE_INTEGRITY_FAILED")
            digest = result.pop("sha256")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("STORE_INTEGRITY_FAILED") from exc
        if digest != row[0] or digest != _seal(result) or (result.get("symbol"), result.get("interval"), result.get("open_ms")) != (symbol, interval, open_ms):
            raise ValueError("STORE_INTEGRITY_FAILED")
        result["sha256"] = digest
        return result

    def project(self, symbol, interval, open_ms):
        if interval not in WIDTHS:
            raise ValueError("INTERVAL_UNSUPPORTED")
        count = WIDTHS[interval]
        rows = []
        for i in range(count):
            row = self.read(symbol, "1m", open_ms + i * MINUTE)
            if row is None:
                raise ValueError("SOURCE_GAP")
            rows.append({
                "symbol": row["symbol"], "interval": "1m",
                "open_ms": row["open_ms"], "final": True,
                "o": row["o"], "h": row["h"], "l": row["l"],
                "c": row["c"], "v": row["v"],
                "source_sha256": row["constituent_sha256"][0],
                "available_at_ms": row["available_at_ms"],
            })
        source_classes = {self.read(symbol, "1m", open_ms + i * MINUTE)["source_class"]
                          for i in range(count)}
        if len(source_classes) != 1:
            raise ValueError("MIXED_SOURCE_CLASS")
        result = project_finalized_1m(rows, interval, source_class=source_classes.pop())
        self._insert(result)
        return result
