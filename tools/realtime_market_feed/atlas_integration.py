"""Fail-closed, read-only bridge from the independent feed to research fixtures.

This module is engineering-only. It never starts a socket, repairs a gap,
mutates the Binance feed database, or enables live Scanner/Factory routing.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile

FEED_SCHEMA_COLUMNS = {
    "final_bar": {"symbol", "interval", "open_ms", "close_ms", "open", "high",
                  "low", "close", "volume", "received_ms", "payload_sha256"},
    "open_gap": {"symbol", "interval", "start_ms", "end_ms", "status"},
    "service_event": {"at_ms", "kind", "detail"},
}
HEX = re.compile(r"^[0-9a-f]{64}$")
MINUTE_MS = 60_000
MAX_WINDOW_BARS = 10_080


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _decimal(value):
    _need(type(value) is str, "DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("DECIMAL_INVALID") from exc
    _need(number.is_finite() and number >= 0, "DECIMAL_INVALID")
    return number


def _feed_db(path):
    path = Path(path).resolve()
    _need(path.is_file(), "FEED_DATABASE_MISSING")
    db = None
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        check = db.execute("PRAGMA quick_check").fetchone()[0]
        _need(check == "ok", "FEED_DATABASE_CORRUPT")
        for table, required in FEED_SCHEMA_COLUMNS.items():
            found = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            _need(required <= found, "FEED_SCHEMA_INCOMPATIBLE")
        return db
    except sqlite3.Error as exc:
        if db is not None:
            db.close()
        raise ValueError("FEED_DATABASE_INVALID") from exc
    except Exception:
        if db is not None:
            db.close()
        raise


def project_feed_window(database, *, symbol, start_ms, end_ms, now_ms,
                        max_age_ms=120_000, max_bars=MAX_WINDOW_BARS):
    """Read an exact finalized 1m range and project it with #330's native rules."""
    _need(type(symbol) is str and symbol.isalnum() and symbol == symbol.upper(),
          "SYMBOL_REQUIRED")
    _need(all(type(x) is int and x >= 0 for x in (start_ms, end_ms, now_ms))
          and start_ms < end_ms and start_ms % MINUTE_MS == 0
          and end_ms % MINUTE_MS == 0, "UTC_WINDOW_INVALID")
    count = (end_ms - start_ms) // MINUTE_MS
    _need(0 < count <= max_bars <= MAX_WINDOW_BARS, "WINDOW_BOUND")
    _need(end_ms <= now_ms, "WINDOW_NOT_FINAL")
    _need(type(max_age_ms) is int and 0 < max_age_ms <= 86_400_000,
          "FRESHNESS_BOUND")

    from aql.research_timeframes import project_finalized_1m
    db = _feed_db(database)
    try:
        gaps = db.execute(
            """SELECT start_ms,end_ms,reason FROM open_gap
               WHERE symbol=? AND interval='1m' AND status='OPEN'
                 AND start_ms < ? AND end_ms > ? ORDER BY start_ms""",
            (symbol, end_ms, start_ms)).fetchall()
        _need(not gaps, "OPEN_HISTORY_GAP")
        conflicts = db.execute(
            """SELECT detail FROM service_event
               WHERE kind='FINAL_BAR_CONFLICT' AND detail LIKE ?""",
            (symbol + ":%",)).fetchall()
        for item in conflicts:
            match = re.fullmatch(re.escape(symbol) + r":([0-9]+)", item["detail"])
            _need(match is not None, "FEED_CONFLICT_EVENT_UNSCOPED")
            opened = int(match.group(1))
            _need(not start_ms <= opened < end_ms, "FEED_BAR_CONFLICT")
        rows = db.execute(
            """SELECT symbol,interval,open_ms,close_ms,open,high,low,close,volume,
                      received_ms,payload_sha256
               FROM final_bar WHERE symbol=? AND interval='1m'
                 AND open_ms>=? AND open_ms<? ORDER BY open_ms""",
            (symbol, start_ms, end_ms)).fetchall()
    except sqlite3.Error as exc:
        raise ValueError("FEED_DATABASE_INVALID") from exc
    finally:
        db.close()

    _need(rows, "SYMBOL_OR_WINDOW_MISSING")
    _need(len(rows) == count, "WINDOW_INCOMPLETE")
    normalized = []
    for i, row in enumerate(rows):
        opened = start_ms + i * MINUTE_MS
        _need(row["symbol"] == symbol and row["interval"] == "1m"
              and type(row["open_ms"]) is int and row["open_ms"] == opened
              and type(row["close_ms"]) is int
              and row["close_ms"] == opened + MINUTE_MS - 1,
              "UTC_GRID_OR_FINALITY_INVALID")
        received = row["received_ms"]
        _need(type(received) is int and received <= now_ms,
              "FEED_RECEIPT_CLOCK_INVALID")
        if i == count - 1:
            _need(now_ms - received <= max_age_ms, "FEED_STALE")
        receipt = row["payload_sha256"]
        _need(type(receipt) is str and HEX.fullmatch(receipt) is not None,
              "FEED_RECEIPT_INVALID")
        values = {key: row[col] for key, col in
                  (("o", "open"), ("h", "high"), ("l", "low"),
                   ("c", "close"), ("v", "volume"))}
        o, h, l, c, v = (_decimal(values[k]) for k in ("o", "h", "l", "c", "v"))
        _need(l <= min(o, c) <= max(o, c) <= h, "OHLC_INVALID")
        normalized.append(dict(symbol=symbol, interval="1m", open_ms=opened,
                               final=True, **values, source_sha256=receipt,
                               available_at_ms=received))
    return [project_finalized_1m([bar], "1m", source_class="FORWARD_UNQUALIFIED")
            for bar in normalized]


def copy_to_research_store(database, research_store_path, *, symbol, start_ms,
                           end_ms, now_ms, engineering_test_only=False):
    """Explicit synthetic-only writer; refuses targets outside the OS temp root."""
    _need(engineering_test_only is True, "INTEGRATION_DISABLED")
    source = Path(database).resolve()
    target = Path(research_store_path).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    _need(target != source and target.is_relative_to(temp_root),
          "ISOLATED_RESEARCH_STORE_REQUIRED")
    rows = project_feed_window(source, symbol=symbol, start_ms=start_ms,
                               end_ms=end_ms, now_ms=now_ms)
    from aql.research_bar_store import ResearchBarStore
    with ResearchBarStore(target) as store:
        store.insert_batch(rows)
        verified = [store.read(symbol, "1m", row["open_ms"]) for row in rows]
    _need(all(item is not None and item["source_class"] == "FORWARD_UNQUALIFIED"
              for item in verified), "RESEARCH_READBACK_FAILED")
    return {"status": "SYNTHETIC_FORWARD_BARS_COPIED",
            "rows": len(verified), "first_open_ms": start_ms,
            "last_open_ms": end_ms - MINUTE_MS,
            "trading_authority": "NONE"}


def reconcile_daily_bar(realtime_bar, daily_bar):
    """Compare exact source keys and decimal OHLCV; never writes either source."""
    if realtime_bar is None and daily_bar is None:
        raise ValueError("BOTH_SOURCE_ROWS_MISSING")
    if daily_bar is None:
        row = realtime_bar
        _need(_provenance(row, realtime=True), "SOURCE_PROVENANCE_REQUIRED")
        return {"status": "REALTIME_ONLY_WAIT_DAILY", "realtime_sha256": row["sha256"],
                "daily_sha256": None, "write_performed": False}
    if realtime_bar is None:
        _need(_provenance(daily_bar, realtime=False), "SOURCE_PROVENANCE_REQUIRED")
        return {"status": "MISSING_REALTIME", "realtime_sha256": None,
                "daily_sha256": daily_bar["sha256"],
                "recovery": "AUTHORIZED_BOUNDED_RECOVERY_REQUIRED",
                "write_performed": False}
    _need(_provenance(realtime_bar, realtime=True)
          and _provenance(daily_bar, realtime=False), "SOURCE_PROVENANCE_REQUIRED")
    identity = ("symbol", "interval", "open_ms")
    if any(realtime_bar.get(k) != daily_bar.get(k) for k in identity):
        return {"status": "CONFLICT", "reason": "SOURCE_KEY_MISMATCH",
                "realtime_sha256": realtime_bar["sha256"],
                "daily_sha256": daily_bar["sha256"], "write_performed": False}
    if realtime_bar.get("close_exclusive_ms") != daily_bar.get("close_exclusive_ms"):
        return {"status": "CONFLICT", "reason": "CLOSE_TIME_MISMATCH",
                "realtime_sha256": realtime_bar["sha256"],
                "daily_sha256": daily_bar["sha256"], "write_performed": False}
    for field in ("o", "h", "l", "c", "v"):
        if _decimal(realtime_bar[field]) != _decimal(daily_bar[field]):
            return {"status": "CONFLICT", "reason": "OHLCV_MISMATCH",
                    "field": field, "realtime_value": realtime_bar[field],
                    "daily_value": daily_bar[field],
                    "realtime_sha256": realtime_bar["sha256"],
                    "daily_sha256": daily_bar["sha256"], "write_performed": False}
    return {"status": "MATCH_IDEMPOTENT", "realtime_sha256": realtime_bar["sha256"],
            "daily_sha256": daily_bar["sha256"], "duplicate_insert": False,
            "write_performed": False}


def _provenance(row, *, realtime):
    if type(row) is not dict or not HEX.fullmatch(str(row.get("sha256", ""))):
        return False
    if realtime:
        hashes = row.get("constituent_sha256")
        return (row.get("source_class") == "FORWARD_UNQUALIFIED"
                and type(hashes) is list and bool(hashes)
                and all(type(h) is str and HEX.fullmatch(h) for h in hashes))
    hashes = row.get("constituent_sha256")
    return (row.get("source_class") == "RETROSPECTIVE_NON_PIT"
            and type(hashes) is list and bool(hashes)
            and all(type(h) is str and HEX.fullmatch(h) for h in hashes))


def build_registry_proposal(reconciliation, registry_snapshot):
    """Return a content-addressed proposal; Registry C remains read-only."""
    from aql.warehouse.storage import canonical, seal
    _need(type(registry_snapshot) is dict
          and registry_snapshot.get("schema") == "aql.research.warehouse.registry-snapshot.v1",
          "REGISTRY_SNAPSHOT_REQUIRED")
    body = {k: v for k, v in registry_snapshot.items() if k != "snapshot_sha256"}
    _need(registry_snapshot.get("snapshot_sha256") == seal(canonical(body))
          and registry_snapshot.get("source_class") == "RETROSPECTIVE_NON_PIT"
          and registry_snapshot.get("trading_authority") == "NONE",
          "REGISTRY_SNAPSHOT_INVALID")
    _need(reconciliation.get("status") in {
        "MATCH_IDEMPOTENT", "MISSING_REALTIME", "CONFLICT", "REALTIME_ONLY_WAIT_DAILY"},
        "RECONCILIATION_REQUIRED")
    proposal = {
        "schema": "aql.realtime-warehouse-reconciliation-proposal.v1",
        "status": "PROPOSED_ONLY",
        "reconciliation": reconciliation,
        "registry_snapshot_sha256": registry_snapshot["snapshot_sha256"],
        "registry_event_watermark": registry_snapshot["event_watermark"],
        "source_classes": ["FORWARD_UNQUALIFIED", "RETROSPECTIVE_NON_PIT"],
        "registry_mutation": False, "warehouse_mutation": False,
        "original_data_mutation": False, "trading_authority": "NONE",
    }
    proposal["proposal_sha256"] = seal(canonical(proposal))
    return proposal
