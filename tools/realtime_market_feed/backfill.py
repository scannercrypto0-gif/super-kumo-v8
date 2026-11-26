"""Bounded, fail-closed recovery of missing finalized 1m Spot candles."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://data-api.binance.vision"
STEP_MS = 60_000
MAX_PAGE = 1_000
MAX_RECOVERY_BARS = 1_440
HTTP_TIMEOUT_SECONDS = 8


def _fetch_json(url: str):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ATLAS-RealtimeFeed/1"})
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError("BACKFILL_HTTP_STATUS")
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise RuntimeError("BACKFILL_RESPONSE_TOO_LARGE")
    return json.loads(raw)


def _event(database: Path, kind: str, detail: str, run_id=None) -> None:
    db = sqlite3.connect(database, timeout=10)
    try:
        db.execute("PRAGMA busy_timeout=10000")
        with db:
            db.execute("""INSERT INTO service_event
                (run_id,at_ms,monotonic_ms,kind,detail) VALUES(?,?,?,?,?)""",
                (run_id,time.time_ns()//1_000_000,time.monotonic_ns()//1_000_000,
                 kind,detail[:300]))
    finally:
        db.close()


def _decimal(value, *, positive=False) -> str:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise ValueError("BACKFILL_DECIMAL_FORMAT")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("BACKFILL_DECIMAL_FORMAT") from exc
    if not number.is_finite() or (number <= 0 if positive else number < 0):
        raise ValueError("BACKFILL_DECIMAL_RANGE")
    return value


def _parse_row(row, symbol: str, expected_open: int, server_ms: int, received_ms: int):
    if not isinstance(row, list) or len(row) != 12:
        raise ValueError("BACKFILL_KLINE_SHAPE")
    opened, closed = row[0], row[6]
    if type(opened) is not int or type(closed) is not int:
        raise ValueError("BACKFILL_KLINE_TIME_TYPE")
    if opened != expected_open or opened % STEP_MS or closed != opened + STEP_MS - 1:
        raise ValueError("BACKFILL_KLINE_GRID")
    if closed >= server_ms:
        raise ValueError("BACKFILL_KLINE_NOT_FINAL")
    if type(received_ms) is not int or received_ms <= closed:
        raise ValueError("BACKFILL_RECEIVED_BEFORE_CLOSE")
    opened_price = _decimal(row[1], positive=True)
    high = _decimal(row[2], positive=True)
    low = _decimal(row[3], positive=True)
    close = _decimal(row[4], positive=True)
    volume = _decimal(row[5])
    try:
        trades = row[8]
    except IndexError as exc:
        raise ValueError("BACKFILL_KLINE_SHAPE") from exc
    if type(trades) is not int or trades < 0:
        raise ValueError("BACKFILL_TRADE_COUNT")
    if Decimal(high) < max(Decimal(opened_price), Decimal(close), Decimal(low)):
        raise ValueError("BACKFILL_OHLC_RANGE")
    if Decimal(low) > min(Decimal(opened_price), Decimal(close), Decimal(high)):
        raise ValueError("BACKFILL_OHLC_RANGE")
    material = {
        "symbol": symbol, "interval": "1m", "open_ms": opened, "close_ms": closed,
        "open": opened_price, "high": high, "low": low, "close": close,
        "volume": volume, "trades": trades,
    }
    digest = hashlib.sha256(json.dumps(row, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return (symbol, "1m", opened, closed, opened_price, high, low, close, volume, trades,
            received_ms, digest)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


REST_LINEAGE_SCHEMA = "atlas.realtime-market-feed.rest-backfill-attestation.v1"
REST_PRODUCER_ID = "atlas.realtime_market_feed.backfill.recover_gap"
REST_SOURCE_CLASS = "BINANCE_SPOT_PUBLIC_REST_MARKET_DATA"
REST_PRODUCER_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _rest_receipt(item, request, request_sha256, batch_sha256):
    symbol, interval, opened, closed, op, high, low, close, volume, trades, received, response_sha = item
    normalized = {
        "provider": "BINANCE", "market": "SPOT", "source_class": REST_SOURCE_CLASS,
        "symbol": symbol, "interval": interval, "open_ms": opened, "close_ms": closed,
        "available_at_ms": received, "finality": "FINAL",
        "ohlcv": {"o": op, "h": high, "l": low, "c": close, "v": volume},
        "trades": trades, "response_row_sha256": response_sha,
    }
    replay = {k: normalized[k] for k in
              ("provider", "market", "source_class", "symbol", "interval",
               "open_ms", "close_ms", "response_row_sha256")}
    body = {
        "schema": REST_LINEAGE_SCHEMA, "producer_id": REST_PRODUCER_ID,
        "producer_code_sha256": REST_PRODUCER_CODE_SHA256,
        **normalized, "request": request, "request_sha256": request_sha256,
        "response_batch_sha256": batch_sha256,
        "replay_identity_sha256": _sha256(_canonical(replay)),
        "normalized_row_sha256": _sha256(_canonical(normalized)),
    }
    encoded = _canonical(body)
    return encoded.decode("utf-8"), _sha256(encoded)


def _valid_existing_receipt(db, symbol, opened):
    row = db.execute(
        """SELECT receipt_json,receipt_sha256 FROM final_bar_lineage
           WHERE symbol=? AND interval='1m' AND open_ms=?""",
        (symbol, opened)).fetchone()
    if not row:
        return False
    try:
        body = json.loads(row[0])
        canonical = _canonical(body)
        return row[0] == canonical.decode("utf-8") and row[1] == _sha256(canonical)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def recover_gap(database: str | Path, symbol: str, start_ms: int, end_ms: int, *,
                fetch_json=_fetch_json, run_id=None):
    """Recover one half-open gap with a distinct, forward-only REST receipt."""
    path = Path(database).resolve()
    symbol = symbol.upper()
    if not symbol.isalnum() or start_ms < 0 or end_ms <= start_ms:
        raise ValueError("BACKFILL_GAP_RANGE")
    if start_ms % STEP_MS or end_ms % STEP_MS:
        raise ValueError("BACKFILL_GAP_GRID")
    expected_count = (end_ms - start_ms) // STEP_MS
    if expected_count > MAX_RECOVERY_BARS:
        _event(path, "GAP_BACKFILL_LIMIT", f"{symbol}:{start_ms}:{end_ms}:bars={expected_count}", run_id)
        return {"status": "OPEN_LIMIT_EXCEEDED", "bars": 0}

    _event(path, "GAP_BACKFILL_STARTED", f"{symbol}:{start_ms}:{end_ms}", run_id)
    try:
        server = fetch_json(BASE + "/api/v3/time")
        server_ms = server.get("serverTime") if isinstance(server, dict) else None
        if type(server_ms) is not int:
            raise ValueError("BACKFILL_SERVER_TIME")
        if end_ms > server_ms:
            raise ValueError("BACKFILL_RANGE_NOT_CLOSED")

        rows, sources = [], {}
        cursor = start_ms
        while cursor < end_ms:
            count = min(MAX_PAGE, (end_ms - cursor) // STEP_MS)
            request = {"base_url": BASE, "endpoint": "/api/v3/klines", "symbol": symbol,
                       "interval": "1m", "startTime": cursor,
                       "endTime": end_ms - 1, "limit": count}
            query = urlencode({k: v for k, v in request.items() if k != "endpoint"})
            batch = fetch_json(BASE + request["endpoint"] + "?" + query)
            batch_received_ms = time.time_ns() // 1_000_000
            if not isinstance(batch, list) or not batch:
                raise ValueError("BACKFILL_KLINES_EMPTY")
            if len(batch) > count:
                raise ValueError("BACKFILL_KLINES_OVERFLOW")
            request_sha = _sha256(_canonical(request))
            batch_sha = _sha256(_canonical(batch))
            for source_row in batch:
                item = _parse_row(source_row, symbol, cursor, server_ms, batch_received_ms)
                rows.append(item)
                sources[item[2]] = (request, request_sha, batch_sha)
                cursor += STEP_MS
            if cursor < end_ms and len(batch) != count:
                raise ValueError("BACKFILL_KLINES_INCOMPLETE")
        if len(rows) != expected_count:
            raise ValueError("BACKFILL_KLINES_INCOMPLETE")

        db = sqlite3.connect(path, timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            with db:
                gap = db.execute(
                    "SELECT status FROM open_gap WHERE symbol=? AND interval='1m' AND start_ms=? AND end_ms=?",
                    (symbol, start_ms, end_ms)).fetchone()
                if not gap or gap[0] != "OPEN":
                    return {"status": "GAP_NO_LONGER_OPEN", "bars": 0}
                for item in rows:
                    existing = db.execute(
                        """SELECT close_ms,open,high,low,close,volume,trades FROM final_bar
                           WHERE symbol=? AND interval='1m' AND open_ms=?""",
                        (symbol, item[2])).fetchone()
                    expected = (item[3], item[4], item[5], item[6], item[7], item[8], item[9])
                    if existing and tuple(existing) != expected:
                        raise ValueError("BACKFILL_EXISTING_BAR_CONFLICT")
                    if existing:
                        # Never retrofit a receipt to a legacy row. A prior WS or
                        # REST row can participate only if its existing seal is intact.
                        if not _valid_existing_receipt(db, symbol, item[2]):
                            raise ValueError("BACKFILL_EXISTING_RECEIPT_UNVERIFIED")
                    else:
                        db.execute("INSERT INTO final_bar VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", item)
                        request, request_sha, batch_sha = sources[item[2]]
                        receipt_json, receipt_sha = _rest_receipt(
                            item, request, request_sha, batch_sha)
                        db.execute(
                            """INSERT INTO final_bar_lineage
                               (symbol,interval,open_ms,receipt_json,receipt_sha256)
                               VALUES(?,'1m',?,?,?)""",
                            (symbol, item[2], receipt_json, receipt_sha))
                stored = db.execute(
                    """SELECT open_ms,close_ms,open,high,low,close,volume,trades FROM final_bar
                       WHERE symbol=? AND interval='1m' AND open_ms>=? AND open_ms<? ORDER BY open_ms""",
                    (symbol, start_ms, end_ms)).fetchall()
                if len(stored) != expected_count:
                    raise ValueError("BACKFILL_COMMIT_COUNT_MISMATCH")
                for index, item in enumerate(rows):
                    expected = (item[2],item[3],item[4],item[5],item[6],item[7],item[8],item[9])
                    if tuple(stored[index]) != expected:
                        raise ValueError("BACKFILL_COMMIT_CONTENT_MISMATCH")
                    if not _valid_existing_receipt(db, symbol, item[2]):
                        raise ValueError("BACKFILL_RECEIPT_COMMIT_MISMATCH")
                changed = db.execute(
                    """UPDATE open_gap SET status='CLOSED' WHERE symbol=? AND interval='1m'
                       AND start_ms=? AND end_ms=? AND status='OPEN'""",
                    (symbol, start_ms, end_ms)).rowcount
                if changed != 1:
                    raise ValueError("BACKFILL_GAP_CLOSE_RACE")
                db.execute("""INSERT INTO service_event
                           (run_id,at_ms,monotonic_ms,kind,detail) VALUES(?,?,?,?,?)""",
                           (run_id,time.time_ns()//1_000_000,time.monotonic_ns()//1_000_000,
                            "GAP_BACKFILL_COMPLETED",
                            f"{symbol}:{start_ms}:{end_ms}:bars={expected_count}:source=REST"))
        finally:
            db.close()
        return {"status": "CLOSED", "bars": expected_count}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        reason = type(exc).__name__ + ":" + str(exc)
        _event(path, "GAP_BACKFILL_FAILED", f"{symbol}:{start_ms}:{end_ms}:{reason}", run_id)
        return {"status": "OPEN_FAILED", "bars": 0, "reason": reason[:180]}

def recover_open_gaps(database: str | Path, symbol: str, *, run_id=None):
    path = Path(database).resolve()
    symbol = symbol.upper()
    db = sqlite3.connect(path, timeout=10)
    try:
        gaps = db.execute(
            """SELECT start_ms,end_ms FROM open_gap WHERE symbol=? AND interval='1m'
               AND status='OPEN' ORDER BY start_ms LIMIT 3""", (symbol,)).fetchall()
    finally:
        db.close()
    return [recover_gap(path, symbol, int(start), int(end), run_id=run_id) for start, end in gaps]
