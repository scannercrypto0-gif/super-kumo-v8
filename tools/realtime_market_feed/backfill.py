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


def _event(database: Path, kind: str, detail: str) -> None:
    db = sqlite3.connect(database, timeout=10)
    try:
        db.execute("PRAGMA busy_timeout=10000")
        with db:
            db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                       (time.time_ns() // 1_000_000, kind, detail[:300]))
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
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return (symbol, "1m", opened, closed, opened_price, high, low, close, volume, trades,
            received_ms, digest)


def recover_gap(database: str | Path, symbol: str, start_ms: int, end_ms: int, *, fetch_json=_fetch_json):
    """Recover one half-open gap, closing it only after every expected minute verifies."""
    path = Path(database).resolve()
    symbol = symbol.upper()
    if not symbol.isalnum() or start_ms < 0 or end_ms <= start_ms:
        raise ValueError("BACKFILL_GAP_RANGE")
    if start_ms % STEP_MS or end_ms % STEP_MS:
        raise ValueError("BACKFILL_GAP_GRID")
    expected_count = (end_ms - start_ms) // STEP_MS
    if expected_count > MAX_RECOVERY_BARS:
        _event(path, "GAP_BACKFILL_LIMIT", f"{symbol}:{start_ms}:{end_ms}:bars={expected_count}")
        return {"status": "OPEN_LIMIT_EXCEEDED", "bars": 0}

    _event(path, "GAP_BACKFILL_STARTED", f"{symbol}:{start_ms}:{end_ms}")
    try:
        server = fetch_json(BASE + "/api/v3/time")
        server_ms = server.get("serverTime") if isinstance(server, dict) else None
        if type(server_ms) is not int:
            raise ValueError("BACKFILL_SERVER_TIME")
        received_ms = time.time_ns() // 1_000_000
        if end_ms > server_ms:
            raise ValueError("BACKFILL_RANGE_NOT_CLOSED")

        rows = []
        cursor = start_ms
        while cursor < end_ms:
            count = min(MAX_PAGE, (end_ms - cursor) // STEP_MS)
            query = urlencode({"symbol": symbol, "interval": "1m", "startTime": cursor,
                               "endTime": end_ms - 1, "limit": count})
            batch = fetch_json(BASE + "/api/v3/klines?" + query)
            if not isinstance(batch, list) or not batch:
                raise ValueError("BACKFILL_KLINES_EMPTY")
            if len(batch) > count:
                raise ValueError("BACKFILL_KLINES_OVERFLOW")
            for row in batch:
                expected = cursor
                rows.append(_parse_row(row, symbol, expected, server_ms, received_ms))
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
                    if not existing:
                        db.execute("INSERT INTO final_bar VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", item)
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
                changed = db.execute(
                    """UPDATE open_gap SET status='CLOSED' WHERE symbol=? AND interval='1m'
                       AND start_ms=? AND end_ms=? AND status='OPEN'""",
                    (symbol, start_ms, end_ms)).rowcount
                if changed != 1:
                    raise ValueError("BACKFILL_GAP_CLOSE_RACE")
                db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                           (received_ms,"GAP_BACKFILL_COMPLETED",
                            f"{symbol}:{start_ms}:{end_ms}:bars={expected_count}:source=REST"))
        finally:
            db.close()
        return {"status": "CLOSED", "bars": expected_count}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        reason = type(exc).__name__ + ":" + str(exc)
        _event(path, "GAP_BACKFILL_FAILED", f"{symbol}:{start_ms}:{end_ms}:{reason}")
        return {"status": "OPEN_FAILED", "bars": 0, "reason": reason[:180]}


def recover_open_gaps(database: str | Path, symbol: str):
    path = Path(database).resolve()
    symbol = symbol.upper()
    db = sqlite3.connect(path, timeout=10)
    try:
        gaps = db.execute(
            """SELECT start_ms,end_ms FROM open_gap WHERE symbol=? AND interval='1m'
               AND status='OPEN' ORDER BY start_ms LIMIT 3""", (symbol,)).fetchall()
    finally:
        db.close()
    return [recover_gap(path, symbol, int(start), int(end)) for start, end in gaps]
