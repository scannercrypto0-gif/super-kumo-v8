"""Fail-closed engineering bridge from feed SQLite to isolated research fixtures.

The current feed stores a SHA of the original WebSocket event but not the event
bytes. It therefore cannot prove that persisted OHLCV still matches that SHA.
Production feed rows are explicitly blocked as UNVERIFIED. Generated fixtures
are admitted only from the OS temporary directory and only through the
engineering-test-only writer.
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
    "open_gap": {"symbol", "interval", "start_ms", "end_ms", "reason", "status"},
    "service_event": {"at_ms", "kind", "detail"},
    "engineering_fixture": {"schema", "fixture_id"},
}
HEX = re.compile(r"^[0-9a-f]{64}$")
MINUTE_MS = 60_000
DAY_MS = 86_400_000
MAX_WINDOW_BARS = 10_080
_FIXTURE_SCHEMA = "aql.realtime-feed.generated-fixture.v1"
_SNAPSHOT_TEST_HOOK = None


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


def _in_temp(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path(tempfile.gettempdir()).resolve())
        return True
    except ValueError:
        return False


def _feed_db(path, *, allow_synthetic_fixture=False):
    path = Path(path).resolve()
    _need(path.is_file(), "FEED_DATABASE_MISSING")
    if allow_synthetic_fixture:
        _need(_in_temp(path), "SYNTHETIC_SOURCE_OUTSIDE_TEMP")
    db = None
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=2000")
        # Every subsequent validation/read must share this same SQLite snapshot.
        db.execute("BEGIN")
        check = db.execute("PRAGMA quick_check").fetchone()[0]
        _need(check == "ok", "FEED_DATABASE_CORRUPT")
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, required in FEED_SCHEMA_COLUMNS.items():
            if table == "engineering_fixture" and not allow_synthetic_fixture:
                continue
            _need(table in tables, "FEED_SCHEMA_INCOMPATIBLE")
            found = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            _need(required <= found, "FEED_SCHEMA_INCOMPATIBLE")
        if not allow_synthetic_fixture:
            # Producer currently persists only the raw-event digest, not the raw
            # bytes or a normalized-row receipt. A 64-hex string is not proof.
            raise ValueError("FEED_SOURCE_LINEAGE_UNVERIFIED")
        marker = db.execute(
            "SELECT schema,fixture_id FROM engineering_fixture").fetchall()
        _need(len(marker) == 1 and marker[0]["schema"] == _FIXTURE_SCHEMA
              and marker[0]["fixture_id"] == "generated-in-test-helper",
              "SYNTHETIC_FIXTURE_MARKER_INVALID")
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
                        max_age_ms=120_000, max_bars=MAX_WINDOW_BARS,
                        allow_synthetic_fixture=False):
    """Read one coherent finalized 1m window; production feed lineage is blocked."""
    _need(type(symbol) is str and symbol.isalnum() and symbol == symbol.upper(),
          "SYMBOL_REQUIRED")
    _need(all(type(x) is int and x >= 0 for x in (start_ms, end_ms, now_ms))
          and start_ms < end_ms and start_ms % MINUTE_MS == 0
          and end_ms % MINUTE_MS == 0, "UTC_WINDOW_INVALID")
    count = (end_ms - start_ms) // MINUTE_MS
    _need(0 < count <= max_bars <= MAX_WINDOW_BARS, "WINDOW_BOUND")
    _need(end_ms <= now_ms, "WINDOW_NOT_FINAL")
    _need(type(max_age_ms) is int and 0 < max_age_ms <= DAY_MS,
          "FRESHNESS_BOUND")

    from aql.research_timeframes import project_finalized_1m
    db = _feed_db(database, allow_synthetic_fixture=allow_synthetic_fixture)
    try:
        gaps = db.execute(
            """SELECT start_ms,end_ms,reason FROM open_gap
               WHERE symbol=? AND interval='1m' AND status='OPEN'
                 AND start_ms < ? AND end_ms > ? ORDER BY start_ms""",
            (symbol, end_ms, start_ms)).fetchall()
        hook = _SNAPSHOT_TEST_HOOK
        if hook is not None:
            hook()
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
        if db.in_transaction:
            db.rollback()
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
    """Write generated test fixtures only; refuses non-temp sources and targets."""
    _need(engineering_test_only is True, "INTEGRATION_DISABLED")
    source = Path(database).resolve()
    target = Path(research_store_path).resolve()
    _need(_in_temp(source) and _in_temp(target) and target != source,
          "ISOLATED_RESEARCH_STORE_REQUIRED")
    rows = project_feed_window(source, symbol=symbol, start_ms=start_ms,
                               end_ms=end_ms, now_ms=now_ms,
                               allow_synthetic_fixture=True)
    from aql.research_bar_store import ResearchBarStore
    with ResearchBarStore(target) as store:
        store.insert_batch(rows)
        verified = [store.read(symbol, "1m", row["open_ms"]) for row in rows]
    _need(all(item is not None and item["source_class"] == "FORWARD_UNQUALIFIED"
              for item in verified), "RESEARCH_READBACK_FAILED")
    return {"status": "SYNTHETIC_FORWARD_BARS_COPIED",
            "rows": len(verified), "first_open_ms": start_ms,
            "last_open_ms": end_ms - MINUTE_MS,
            "evidence_class": "GENERATED_TEST_FIXTURE",
            "trading_authority": "NONE"}


def _verified_projection(row, *, source_class):
    if type(row) is not dict:
        return False
    try:
        from aql.research_timeframes import WIDTHS, WEEK_ORIGIN_MS
        from aql.warehouse.storage import canonical, seal
        if row.get("schema") != "aql.research.finalized-timeframe.v1":
            return False
        if row.get("source_class") != source_class:
            return False
        if row.get("trading_authority") != "NONE" or row.get("pit_oos") != "NOT_ATTESTED":
            return False
        symbol, interval, opened = row.get("symbol"), row.get("interval"), row.get("open_ms")
        if type(symbol) is not str or not symbol.isalnum() or symbol != symbol.upper():
            return False
        if interval not in WIDTHS or type(opened) is not int or opened < 0:
            return False
        width = WIDTHS[interval]
        origin = WEEK_ORIGIN_MS if interval == "1w" else 0
        if (opened - origin) % (width * MINUTE_MS):
            return False
        if type(row.get("close_exclusive_ms")) is not int or row["close_exclusive_ms"] != opened + width * MINUTE_MS:
            return False
        available = row.get("available_at_ms")
        if type(available) is not int or available < row["close_exclusive_ms"]:
            return False
        if type(row.get("constituent_count")) is not int or row["constituent_count"] != width:
            return False
        members = row.get("constituent_sha256")
        if type(members) is not list or len(members) != width or any(
            type(x) is not str or not HEX.fullmatch(x) for x in members
        ):
            return False
        vals = [_decimal(row.get(k)) for k in ("o", "h", "l", "c", "v")]
        o, h, l, c, _v = vals
        if not l <= min(o, c) <= max(o, c) <= h:
            return False
        digest = row.get("sha256")
        if type(digest) is not str or not HEX.fullmatch(digest):
            return False
        body = {k: v for k, v in row.items() if k != "sha256"}
        return digest == seal(canonical(body))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False


def _reconciliation_body(realtime_bar, daily_bar):
    if realtime_bar is None and daily_bar is None:
        raise ValueError("BOTH_SOURCE_ROWS_MISSING")
    if realtime_bar is not None and not _verified_projection(
            realtime_bar, source_class="FORWARD_UNQUALIFIED"):
        raise ValueError("PROJECTED_ROW_INVALID")
    if daily_bar is not None and not _verified_projection(
            daily_bar, source_class="RETROSPECTIVE_NON_PIT"):
        raise ValueError("PROJECTED_ROW_INVALID")
    identity = ("symbol", "interval", "open_ms", "close_exclusive_ms")
    rkey = {k: realtime_bar.get(k) for k in identity} if realtime_bar else None
    dkey = {k: daily_bar.get(k) for k in identity} if daily_bar else None
    body = {
        "schema": "aql.realtime-daily-reconciliation.v2",
        "venue": "BINANCE",
        "market": "SPOT",
        "realtime_row": realtime_bar,
        "daily_row": daily_bar,
        "realtime_row_sha256": realtime_bar["sha256"] if realtime_bar else None,
        "daily_row_sha256": daily_bar["sha256"] if daily_bar else None,
        "realtime_key": rkey,
        "daily_key": dkey,
        "write_performed": False,
        "duplicate_insert": False,
        "trading_authority": "NONE",
    }
    if realtime_bar is None:
        body.update(status="MISSING_REALTIME",
                    recovery="AUTHORIZED_BOUNDED_RECOVERY_REQUIRED")
        return body
    if daily_bar is None:
        body.update(status="REALTIME_ONLY_WAIT_DAILY")
        return body
    if rkey != dkey:
        body.update(status="CONFLICT", reason="SOURCE_KEY_MISMATCH")
    elif any(_decimal(realtime_bar[k]) != _decimal(daily_bar[k])
             for k in ("o", "h", "l", "c", "v")):
        body.update(status="CONFLICT", reason="OHLCV_MISMATCH")
    else:
        body.update(status="MATCH_IDEMPOTENT")
    return body


def reconcile_daily_bar(realtime_bar, daily_bar):
    """Reconcile sealed projections; no hash-shape-only or status-only verdicts."""
    from aql.warehouse.storage import canonical, seal
    body = _reconciliation_body(realtime_bar, daily_bar)
    body["reconciliation_sha256"] = seal(canonical(body))
    return body


def _verify_reconciliation(reconciliation):
    from aql.warehouse.storage import canonical, seal
    _need(type(reconciliation) is dict
          and reconciliation.get("schema") == "aql.realtime-daily-reconciliation.v2",
          "RECONCILIATION_REQUIRED")
    digest = reconciliation.get("reconciliation_sha256")
    body = {k: v for k, v in reconciliation.items() if k != "reconciliation_sha256"}
    _need(type(digest) is str and HEX.fullmatch(digest)
          and digest == seal(canonical(body)), "RECONCILIATION_SEAL_INVALID")
    expected = _reconciliation_body(body.get("realtime_row"), body.get("daily_row"))
    _need(body == expected, "RECONCILIATION_STATUS_OR_LINEAGE_INVALID")
    return {**expected, "reconciliation_sha256": digest}


def _registry_snapshot(snapshot):
    from aql.warehouse.storage import canonical, seal
    _need(type(snapshot) is dict
          and snapshot.get("schema") == "aql.warehouse.registry-snapshot.v1",
          "REGISTRY_SNAPSHOT_REQUIRED")
    body = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
    _need(snapshot.get("snapshot_sha256") == seal(canonical(body))
          and snapshot.get("source_class") == "RETROSPECTIVE_NON_PIT"
          and snapshot.get("trading_authority") == "NONE",
          "REGISTRY_SNAPSHOT_INVALID")
    _need(type(snapshot.get("sources")) is list
          and type(snapshot.get("covered_intervals")) is list
          and type(snapshot.get("internal_gaps")) is list
          and type(snapshot.get("conflicts")) is list,
          "REGISTRY_SNAPSHOT_INCOMPLETE")
    return snapshot


def _daily_context_binding(context, daily_row):
    _need(type(context) is dict and type(context.get("bars")) is list
          and type(context.get("requested_window")) is list
          and len(context["requested_window"]) == 2
          and type(context.get("cutoff_ms")) is int,
          "DAILY_QUERY_CONTEXT_REQUIRED")
    rows = context["bars"]
    _need(daily_row is not None and daily_row in rows,
          "DAILY_QUERY_ROW_NOT_BOUND")
    row = daily_row
    start, end = context["requested_window"]
    _need(type(start) is int and type(end) is int
          and start <= row["open_ms"] and row["close_exclusive_ms"] <= end
          and row["available_at_ms"] <= context["cutoff_ms"],
          "DAILY_QUERY_WINDOW_MISMATCH")
    snapshot = _registry_snapshot(context.get("registry"))
    _need(any(type(span) is list and len(span) == 2
              and type(span[0]) is int and type(span[1]) is int
              and span[0] <= row["open_ms"]
              and row["close_exclusive_ms"] <= span[1]
              for span in snapshot["covered_intervals"]),
          "DAILY_REGISTRY_COVERAGE_MISMATCH")
    _need(not any(type(gap) is list and len(gap) == 2
                  and type(gap[0]) is int and type(gap[1]) is int
                  and gap[0] < row["close_exclusive_ms"]
                  and gap[1] > row["open_ms"]
                  for gap in snapshot["internal_gaps"]),
          "DAILY_REGISTRY_GAP")
    _need(not snapshot["conflicts"], "DAILY_REGISTRY_CONFLICTS_PRESENT")
    from datetime import datetime, timezone
    date = datetime.fromtimestamp(row["open_ms"] / 1000, tz=timezone.utc).date().isoformat()
    key = f"data/spot/daily/klines/{row['symbol']}/1m/{row['symbol']}-1m-{date}.zip"
    candidates = [source for source in snapshot["sources"]
                  if type(source) is dict and source.get("key") == key
                  and source.get("first_open_ms") <= row["open_ms"]
                  and source.get("last_open_ms") + MINUTE_MS >= row["close_exclusive_ms"]
                  and type(source.get("source_zip_sha256")) is str
                  and HEX.fullmatch(source["source_zip_sha256"])
                  and type(source.get("source_receipt_sha256")) is str
                  and HEX.fullmatch(source["source_receipt_sha256"])]
    _need(candidates, "DAILY_ARCHIVE_RECEIPT_NOT_BOUND")
    return snapshot, candidates


def build_registry_proposal(reconciliation, daily_query_context):
    """Create a proposal only when a sealed daily query and Registry cover the same bar."""
    from aql.warehouse.storage import canonical, seal
    verified = _verify_reconciliation(reconciliation)
    daily_row = verified["daily_row"]
    _need(daily_row is not None, "NOT_VERIFIABLE_DAILY_ROW_ABSENT")
    snapshot, sources = _daily_context_binding(daily_query_context, daily_row)
    source_pins = sorted({item["source_zip_sha256"] for item in sources})
    receipt_pins = sorted({item["source_receipt_sha256"] for item in sources})
    proposal = {
        "schema": "aql.realtime-warehouse-reconciliation-proposal.v2",
        "status": "PROPOSED_ONLY",
        "evidence_class": "GENERATED_SYNTHETIC_FIXTURE",
        "venue": verified["venue"], "market": verified["market"],
        "bar_key": verified["daily_key"],
        "reconciliation_sha256": verified["reconciliation_sha256"],
        "realtime_row_sha256": verified["realtime_row_sha256"],
        "daily_row_sha256": verified["daily_row_sha256"],
        "registry_snapshot_sha256": snapshot["snapshot_sha256"],
        "registry_event_watermark": snapshot["event_watermark"],
        "daily_source_zip_sha256s": source_pins,
        "daily_source_receipt_sha256s": receipt_pins,
        "registry_coverage": {
            "covered_intervals": snapshot["covered_intervals"],
            "internal_gaps": snapshot["internal_gaps"],
            "archive_unavailable_boundaries": snapshot["archive_unavailable_boundaries"],
            "conflicts": snapshot["conflicts"],
        },
        "source_classes": ["FORWARD_UNQUALIFIED", "RETROSPECTIVE_NON_PIT"],
        "registry_mutation": False, "warehouse_mutation": False,
        "original_data_mutation": False, "trading_authority": "NONE",
    }
    proposal["proposal_sha256"] = seal(canonical(proposal))
    return proposal
