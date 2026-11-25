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
import time

FEED_SCHEMA_COLUMNS = {
    "final_bar": {"symbol", "interval", "open_ms", "close_ms", "open", "high",
                  "low", "close", "volume", "received_ms", "payload_sha256"},
    "open_gap": {"symbol", "interval", "start_ms", "end_ms", "reason", "status"},
    "service_event": {"at_ms", "kind", "detail"},
    "engineering_fixture": {"schema", "fixture_id"},
    "final_bar_lineage": {"symbol", "interval", "open_ms", "receipt_json", "receipt_sha256"},
}
HEX = re.compile(r"^[0-9a-f]{64}$")
MINUTE_MS = 60_000
DAY_MS = 86_400_000
MAX_WINDOW_BARS = 10_080
_QUERY_CLOCK = time.monotonic
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


def _feed_db(path, *, allow_synthetic_fixture=False,
             expected_producer_code_sha256=None, query_deadline=None):
    path = Path(path).resolve()
    _need(path.is_file(), "FEED_DATABASE_MISSING")
    if allow_synthetic_fixture:
        _need(_in_temp(path), "SYNTHETIC_SOURCE_OUTSIDE_TEMP")
    if type(expected_producer_code_sha256) is not str or not HEX.fullmatch(
            expected_producer_code_sha256):
        raise ValueError("FEED_SOURCE_LINEAGE_UNVERIFIED")
    db = None
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=2000")
        if query_deadline is not None:
            db.set_progress_handler(
                lambda: 1 if _QUERY_CLOCK() >= query_deadline else 0, 500)
        # Every integrity check/read uses this one immutable SQLite snapshot.
        db.execute("BEGIN")
        check = db.execute("PRAGMA quick_check").fetchone()[0]
        _need(check == "ok", "FEED_DATABASE_CORRUPT")
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "final_bar_lineage" not in tables:
            raise ValueError("FEED_SOURCE_LINEAGE_UNVERIFIED")
        for table, required in FEED_SCHEMA_COLUMNS.items():
            if table == "engineering_fixture" and not allow_synthetic_fixture:
                continue
            found = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            _need(required <= found, "FEED_SCHEMA_INCOMPATIBLE")
        if allow_synthetic_fixture:
            marker = db.execute(
                "SELECT schema,fixture_id FROM engineering_fixture").fetchall()
            _need(len(marker) == 1 and marker[0]["schema"] == _FIXTURE_SCHEMA
                  and marker[0]["fixture_id"] == "generated-in-test-helper",
                  "SYNTHETIC_FIXTURE_MARKER_INVALID")
        return db
    except sqlite3.Error as exc:
        if db is not None:
            db.close()
        if query_deadline is not None and _QUERY_CLOCK() >= query_deadline:
            raise ValueError("FEED_QUERY_BUDGET_EXCEEDED") from None
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise ValueError("FEED_DATABASE_BUSY") from None
        raise ValueError("FEED_DATABASE_INVALID") from exc
    except Exception:
        if db is not None:
            db.close()
        raise


def _verify_lineage(row, *, expected_producer_code_sha256):
    try:
        if row["lineage_json"] is None or row["lineage_sha256"] is None:
            raise ValueError("FEED_SOURCE_LINEAGE_UNVERIFIED")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("FEED_LINEAGE_DUPLICATE_KEY")
                result[key] = value
            return result
        body = json.loads(row["lineage_json"], object_pairs_hook=unique)
        required = {
            "schema", "producer_id", "producer_code_sha256", "provider", "market",
            "symbol", "interval", "open_ms", "close_ms", "available_at_ms",
            "finality", "ohlcv", "trades", "event_payload_sha256",
            "replay_identity_sha256", "normalized_row_sha256",
        }
        _need(type(body) is dict and set(body) == required,
              "FEED_LINEAGE_SCHEMA_INVALID")
        _need(body["schema"] == "atlas.realtime-market-feed.normalized-bar-attestation.v1"
              and body["producer_id"] == "atlas.realtime_market_feed.service.Store.ingest"
              and body["producer_code_sha256"] == expected_producer_code_sha256,
              "FEED_PRODUCER_IDENTITY_MISMATCH")
        _need(body["provider"] == "BINANCE" and body["market"] == "SPOT"
              and body["symbol"] == row["symbol"] and body["interval"] == row["interval"]
              and body["interval"] == "1m" and body["open_ms"] == row["open_ms"]
              and body["close_ms"] == row["close_ms"]
              and body["available_at_ms"] == row["received_ms"]
              and body["finality"] == "FINAL",
              "FEED_LINEAGE_IDENTITY_MISMATCH")
        ohlcv = {"o": row["open"], "h": row["high"], "l": row["low"],
                 "c": row["close"], "v": row["volume"]}
        _need(body["ohlcv"] == ohlcv and body["trades"] == row["trades"]
              and body["event_payload_sha256"] == row["payload_sha256"],
              "FEED_LINEAGE_ROW_MISMATCH")
        _need(type(body["event_payload_sha256"]) is str
              and HEX.fullmatch(body["event_payload_sha256"]) is not None,
              "FEED_RECEIPT_INVALID")
        normalized = {
            "provider":body["provider"], "market":body["market"],
            "symbol":body["symbol"], "interval":body["interval"],
            "open_ms":body["open_ms"], "close_ms":body["close_ms"],
            "available_at_ms":body["available_at_ms"], "finality":body["finality"],
            "ohlcv":body["ohlcv"], "trades":body["trades"],
            "event_payload_sha256":body["event_payload_sha256"],
        }
        _need(body["normalized_row_sha256"] == hashlib.sha256(
                  json.dumps(normalized,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest(),
              "FEED_NORMALIZED_ROW_DIGEST_MISMATCH")
        replay = {key: body[key] for key in
                  ("provider","market","symbol","interval","open_ms","close_ms",
                   "event_payload_sha256")}
        replay_sha = hashlib.sha256(json.dumps(replay,sort_keys=True,
            separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
        _need(body["replay_identity_sha256"] == replay_sha,
              "FEED_REPLAY_IDENTITY_MISMATCH")
        canonical_body = json.dumps(body,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True,allow_nan=False)
        _need(row["lineage_json"] == canonical_body
              and row["lineage_sha256"] == hashlib.sha256(canonical_body.encode()).hexdigest(),
              "FEED_LINEAGE_SEAL_INVALID")
        return body, row["lineage_sha256"]
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("FEED_"):
            raise
        raise ValueError("FEED_LINEAGE_INVALID") from None


def project_feed_window(database, *, symbol, start_ms, end_ms, now_ms,
                        max_age_ms=120_000, max_bars=MAX_WINDOW_BARS,
                        allow_synthetic_fixture=False,
                        expected_producer_code_sha256=None,
                        query_budget_ms=5_000, metrics=None):
    """Read one coherent finalized 1m window and verify its pinned producer receipts.

    Legacy rows without a forward-only normalized producer receipt remain blocked.
    The receipt is a local producer attestation, not a Binance signature or rights
    proof. The bounded read never writes the source database.
    """
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
    _need(type(query_budget_ms) is int and 1 <= query_budget_ms <= 60_000,
          "QUERY_BUDGET_INVALID")
    if allow_synthetic_fixture and expected_producer_code_sha256 is None:
        from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256
        expected_producer_code_sha256 = PRODUCER_CODE_SHA256
    _need(type(expected_producer_code_sha256) is str
          and HEX.fullmatch(expected_producer_code_sha256) is not None,
          "FEED_SOURCE_LINEAGE_UNVERIFIED")

    from aql.research_timeframes import project_finalized_1m
    deadline = _QUERY_CLOCK() + query_budget_ms / 1000
    db = _feed_db(database, allow_synthetic_fixture=allow_synthetic_fixture,
                  expected_producer_code_sha256=expected_producer_code_sha256,
                  query_deadline=deadline)
    read_started = _QUERY_CLOCK()
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
            """SELECT f.symbol,f.interval,f.open_ms,f.close_ms,f.open,f.high,f.low,f.close,
                      f.volume,f.trades,f.received_ms,f.payload_sha256,
                      l.receipt_json AS lineage_json,l.receipt_sha256 AS lineage_sha256
               FROM final_bar AS f LEFT JOIN final_bar_lineage AS l
                 ON l.symbol=f.symbol AND l.interval=f.interval AND l.open_ms=f.open_ms
               WHERE f.symbol=? AND f.interval='1m' AND f.open_ms>=? AND f.open_ms<?
               ORDER BY f.open_ms""",
            (symbol, start_ms, end_ms)).fetchall()
        _need(_QUERY_CLOCK() <= deadline, "FEED_QUERY_BUDGET_EXCEEDED")
        snapshot_ms = round((_QUERY_CLOCK() - read_started) * 1000, 3)
    except sqlite3.Error as exc:
        if _QUERY_CLOCK() >= deadline:
            raise ValueError("FEED_QUERY_BUDGET_EXCEEDED") from None
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise ValueError("FEED_DATABASE_BUSY") from None
        raise ValueError("FEED_DATABASE_INVALID") from exc
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()

    _need(rows, "SYMBOL_OR_WINDOW_MISSING")
    _need(len(rows) == count, "WINDOW_INCOMPLETE")
    normalized = []
    decoded_source_bytes = 0
    for i, row in enumerate(rows):
        _need(_QUERY_CLOCK() <= deadline, "FEED_QUERY_BUDGET_EXCEEDED")
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
        body, receipt_sha = _verify_lineage(
            row, expected_producer_code_sha256=expected_producer_code_sha256)
        values = {key: row[col] for key, col in
                  (("o", "open"), ("h", "high"), ("l", "low"),
                   ("c", "close"), ("v", "volume"))}
        o, h, l, c, v = (_decimal(values[k]) for k in ("o", "h", "l", "c", "v"))
        _need(l <= min(o, c) <= max(o, c) <= h, "OHLC_INVALID")
        normalized.append(dict(symbol=symbol, interval="1m", open_ms=opened,
                               final=True, **values, source_sha256=receipt_sha,
                               available_at_ms=body["available_at_ms"]))
        decoded_source_bytes += len(row["lineage_json"].encode("utf-8")) + sum(
            len(str(row[key]).encode("utf-8")) for key in
            ("symbol","interval","open_ms","close_ms","open","high","low","close",
             "volume","trades","received_ms","payload_sha256"))
    if metrics is not None:
        metrics.update({"selected_bars":len(rows), "decoded_source_bytes":decoded_source_bytes,
                        "read_snapshot_ms":snapshot_ms, "query_budget_ms":query_budget_ms})
    return [project_finalized_1m([bar], "1m", source_class="FORWARD_UNQUALIFIED")
            for bar in normalized]


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
    _need(snapshot.get("dataset_id") == "BINANCE_VISION:SPOT:BTCUSDT:1m:RETROSPECTIVE_NON_PIT"
          and type(snapshot.get("event_watermark")) is int
          and snapshot.get("event_watermark") > 0
          and type(snapshot.get("event_head_sha256")) is str
          and HEX.fullmatch(snapshot["event_head_sha256"]) is not None
          and type(snapshot.get("as_of_ms")) is int,
          "REGISTRY_SNAPSHOT_INCOMPLETE")
    _need(type(snapshot.get("sources")) is list
          and type(snapshot.get("covered_intervals")) is list
          and type(snapshot.get("internal_gaps")) is list
          and type(snapshot.get("archive_unavailable_boundaries")) is list
          and type(snapshot.get("conflicts")) is list,
          "REGISTRY_SNAPSHOT_INCOMPLETE")
    return snapshot


def _native_daily_context(context, daily_row, warehouse_root):
    """Re-read the requested bars and Registry from the pinned native warehouse.

    Caller-provided query objects are claims only. A proposal is possible only
    when the native Warehouse query reproduces both the complete row set and
    exact Registry snapshot from the same read-only source root.
    """
    _need(type(context) is dict and type(context.get("bars")) is list
          and type(context.get("requested_window")) is list
          and len(context["requested_window"]) == 2
          and type(context.get("cutoff_ms")) is int,
          "DAILY_QUERY_CONTEXT_REQUIRED")
    start, end = context["requested_window"]
    _need(type(start) is int and type(end) is int and start < end
          and daily_row is not None
          and type(daily_row.get("interval")) is str,
          "DAILY_QUERY_CONTEXT_INVALID")
    _need(warehouse_root is not None, "NATIVE_WAREHOUSE_ROOT_REQUIRED")
    root = Path(warehouse_root).resolve()
    from aql.warehouse.engine import HistoricalWarehouse
    warehouse = HistoricalWarehouse(root, test_root=_in_temp(root))
    native = warehouse.query(
        daily_row["interval"], start, end,
        cutoff_ms=context["cutoff_ms"], include_registry=True)
    _need(native["requested_window"] == [start, end]
          and native["cutoff_ms"] == context["cutoff_ms"]
          and native["bars"] == context["bars"]
          and native["registry"] == context.get("registry"),
          "DAILY_NATIVE_READBACK_MISMATCH")
    _need(daily_row in native["bars"], "DAILY_QUERY_ROW_NOT_BOUND")
    return native


def _daily_context_binding(context, daily_row, warehouse_root):
    native = _native_daily_context(context, daily_row, warehouse_root)
    row = daily_row
    snapshot = _registry_snapshot(native["registry"])
    _need(type(row.get("open_ms")) is int
          and type(row.get("close_exclusive_ms")) is int
          and row["open_ms"] < row["close_exclusive_ms"]
          and row["available_at_ms"] <= native["cutoff_ms"],
          "DAILY_QUERY_WINDOW_MISMATCH")
    _need(any(type(span) is list and len(span) == 2
              and type(span[0]) is int and type(span[1]) is int
              and span[0] <= row["open_ms"]
              and row["close_exclusive_ms"] <= span[1]
              for span in snapshot["covered_intervals"]),
          "DAILY_REGISTRY_COVERAGE_MISMATCH")
    for gap_collection in (snapshot["internal_gaps"],
                           snapshot["archive_unavailable_boundaries"]):
        _need(not any(type(gap) is list and len(gap) == 2
                      and type(gap[0]) is int and type(gap[1]) is int
                      and gap[0] < row["close_exclusive_ms"]
                      and gap[1] > row["open_ms"]
                      for gap in gap_collection), "DAILY_REGISTRY_GAP")
    _need(snapshot["as_of_ms"] >= row["available_at_ms"],
          "DAILY_REGISTRY_AS_OF_TOO_OLD")
    _need(not snapshot["conflicts"], "DAILY_REGISTRY_CONFLICTS_PRESENT")
    from datetime import datetime, timezone
    date = datetime.fromtimestamp(row["open_ms"] / 1000, tz=timezone.utc).date().isoformat()
    key = f"data/spot/daily/klines/{row['symbol']}/1m/{row['symbol']}-1m-{date}.zip"
    candidates = []
    for source in snapshot["sources"]:
        if type(source) is not dict:
            continue
        first, last = source.get("first_open_ms"), source.get("last_open_ms")
        zip_sha = source.get("source_zip_sha256")
        receipt_sha = source.get("source_receipt_sha256")
        if (source.get("key") == key and type(first) is int and type(last) is int
                and first <= row["open_ms"]
                and last + MINUTE_MS >= row["close_exclusive_ms"]
                and type(zip_sha) is str and HEX.fullmatch(zip_sha)
                and type(receipt_sha) is str and HEX.fullmatch(receipt_sha)):
            candidates.append(source)
    _need(candidates, "DAILY_ARCHIVE_RECEIPT_NOT_BOUND")
    return snapshot, candidates


def build_registry_proposal(reconciliation, daily_query_context, *, warehouse_root=None):
    """Propose only after a read-only native query reproduces bars and Registry."""
    from aql.warehouse.storage import canonical, seal
    verified = _verify_reconciliation(reconciliation)
    daily_row = verified["daily_row"]
    _need(daily_row is not None, "NOT_VERIFIABLE_DAILY_ROW_ABSENT")
    snapshot, sources = _daily_context_binding(
        daily_query_context, daily_row, warehouse_root)
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
