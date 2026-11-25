"""Bounded read-only Binance Spot market feed with durable SQLite state.

This is an engineering candidate. It never places orders and does not claim
provider-rights approval or production readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sqlite3
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import websocket

LOG = logging.getLogger("atlas.realtime_feed")
WS_HOST = "data-stream.binance.vision"
MAX_SYMBOLS = 64
MAX_BACKOFF_SECONDS = 60
MIN_RECONNECT_INTERVAL_SECONDS = 15
MAX_SOCKET_AGE_SECONDS = 23 * 60 * 60 + 50 * 60


def utc_ms() -> int:
    return time.time_ns() // 1_000_000


def normalize_symbols(value: str) -> list[str]:
    symbols = sorted({item.strip().lower() for item in value.split(",") if item.strip()})
    if not symbols or len(symbols) > MAX_SYMBOLS:
        raise ValueError("SYMBOL_COUNT_OUT_OF_RANGE")
    if any(not item.isalnum() or item != item.lower() for item in symbols):
        raise ValueError("INVALID_SYMBOL")
    return symbols


def make_url(symbols: list[str]) -> str:
    streams = []
    for symbol in symbols:
        streams.extend((f"{symbol}@trade", f"{symbol}@bookTicker", f"{symbol}@kline_1m"))
    return f"wss://{WS_HOST}/stream?streams=" + quote("/".join(streams), safe="@/")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS latest_quote(
          symbol TEXT PRIMARY KEY, bid TEXT NOT NULL, bid_qty TEXT NOT NULL,
          ask TEXT NOT NULL, ask_qty TEXT NOT NULL, update_id INTEGER NOT NULL,
          received_ms INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS latest_trade(\n          symbol TEXT PRIMARY KEY, trade_id INTEGER NOT NULL, price TEXT NOT NULL,\n          quantity TEXT NOT NULL, event_ms INTEGER NOT NULL, received_ms INTEGER NOT NULL,\n          buyer_is_maker INTEGER NOT NULL);\n        CREATE TABLE IF NOT EXISTS final_bar(
          symbol TEXT NOT NULL, interval TEXT NOT NULL, open_ms INTEGER NOT NULL,
          close_ms INTEGER NOT NULL, open TEXT NOT NULL, high TEXT NOT NULL,
          low TEXT NOT NULL, close TEXT NOT NULL, volume TEXT NOT NULL,
          trades INTEGER NOT NULL, received_ms INTEGER NOT NULL, payload_sha256 TEXT NOT NULL,
          PRIMARY KEY(symbol, interval, open_ms));
        CREATE TABLE IF NOT EXISTS open_gap(
          id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, interval TEXT NOT NULL,
          start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, reason TEXT NOT NULL,
          detected_ms INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN',
          UNIQUE(symbol, interval, start_ms, end_ms));
        CREATE TABLE IF NOT EXISTS service_event(
          id INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, kind TEXT NOT NULL,
          detail TEXT NOT NULL);
        """)
        self.db.commit()

    def event(self, kind: str, detail: str = "") -> None:
        with self.db:
            self.db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                            (utc_ms(), kind, detail[:300]))

    def ingest(self, raw: str, received_ms: int | None = None) -> str:
        received_ms = received_ms or utc_ms()
        envelope = json.loads(raw)
        data = envelope.get("data", envelope)
        kind = data.get("e")
        symbol = str(data.get("s", "")).upper()
        if not symbol:
            raise ValueError("MISSING_SYMBOL")
        if kind == "trade":\n            trade_id, event_ms = int(data["t"]), int(data["T"])\n            with self.db:\n                self.db.execute("""INSERT INTO latest_trade VALUES(?,?,?,?,?,?,?)\n                    ON CONFLICT(symbol) DO UPDATE SET trade_id=excluded.trade_id,\n                    price=excluded.price,quantity=excluded.quantity,event_ms=excluded.event_ms,\n                    received_ms=excluded.received_ms,buyer_is_maker=excluded.buyer_is_maker\n                    WHERE excluded.trade_id > latest_trade.trade_id""",\n                    (symbol,trade_id,str(data["p"]),str(data["q"]),event_ms,received_ms,int(bool(data["m"]))))\n            return "trade"\n        if kind == "bookTicker":
            bid, ask = data.get("b"), data.get("a")
            bid_qty, ask_qty = data.get("B"), data.get("A")
            update_id = int(data["u"])
            if not all(isinstance(v, str) and v for v in (bid, ask, bid_qty, ask_qty)):
                raise ValueError("INVALID_BOOK_TICKER")
            with self.db:
                self.db.execute("""INSERT INTO latest_quote VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(symbol) DO UPDATE SET bid=excluded.bid,bid_qty=excluded.bid_qty,
                    ask=excluded.ask,ask_qty=excluded.ask_qty,update_id=excluded.update_id,
                    received_ms=excluded.received_ms
                    WHERE excluded.update_id >= latest_quote.update_id""",
                    (symbol,bid,bid_qty,ask,ask_qty,update_id,received_ms))
            return "bookTicker"
        if kind == "kline":
            k = data.get("k") or {}
            if k.get("i") != "1m":
                raise ValueError("UNSUPPORTED_KLINE_INTERVAL")
            if not k.get("x"):
                return "provisional_ignored"
            opened, closed = int(k["t"]), int(k["T"])
            digest = hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            with self.db:
                previous = self.db.execute(
                    "SELECT open_ms FROM final_bar WHERE symbol=? AND interval='1m' ORDER BY open_ms DESC LIMIT 1",
                    (symbol,)).fetchone()
                if previous and opened > previous[0] + 60_000:
                    self.db.execute("""INSERT OR IGNORE INTO open_gap
                      (symbol,interval,start_ms,end_ms,reason,detected_ms)
                      VALUES(?,'1m',?,?,?,?)""",
                      (symbol, previous[0]+60_000, opened, "MISSING_FINALIZED_MINUTES", received_ms))
                cur = self.db.execute("""INSERT OR IGNORE INTO final_bar VALUES
                  (?,'1m',?,?,?,?,?,?,?,?,?,?)""",
                  (symbol,opened,closed,str(k["o"]),str(k["h"]),str(k["l"]),str(k["c"]),
                   str(k["v"]),int(k["n"]),received_ms,digest))
                existing = self.db.execute(
                    "SELECT payload_sha256 FROM final_bar WHERE symbol=? AND interval='1m' AND open_ms=?",
                    (symbol,opened)).fetchone()
                if existing and existing[0] != digest:
                    self.db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                                    (received_ms,"FINAL_BAR_CONFLICT",symbol+":"+str(opened)))
            return "final_bar"
        return "ignored"


class LiveService:
    def __init__(self, symbols: list[str], store: Store, stop_after_seconds: int = 0):
        self.symbols, self.store = symbols, store
        self.stop_after_seconds = stop_after_seconds
        self.started = time.monotonic()
        self.last_attempt = 0.0
        self.attempts = 0
        self.stop = False

    def run(self) -> None:
        delay = 2.0
        while not self.stop:
            if self.stop_after_seconds and time.monotonic()-self.started >= self.stop_after_seconds:
                break
            wait = MIN_RECONNECT_INTERVAL_SECONDS - (time.monotonic()-self.last_attempt)
            if wait > 0:
                time.sleep(min(wait, 5))
                continue
            self.last_attempt = time.monotonic()
            self.attempts += 1
            opened = time.monotonic()
            self.store.event("CONNECTING", f"attempt={self.attempts}")
            app = websocket.WebSocketApp(make_url(self.symbols),
                on_open=lambda _app: self.store.event("CONNECTED", f"symbols={len(self.symbols)}"),
                on_message=lambda _app,msg: self._on_message(msg),
                on_error=lambda _app,err: self.store.event("SOCKET_ERROR", type(err).__name__),
                on_close=lambda _app,code,msg: self.store.event("DISCONNECTED", str(code or "")[:40]))
            elapsed = time.monotonic()-self.started
            lifetime = MAX_SOCKET_AGE_SECONDS
            if self.stop_after_seconds:
                lifetime = min(lifetime, max(0.1, self.stop_after_seconds-elapsed))
            timer = threading.Timer(lifetime, app.close)
            timer.daemon = True
            timer.start()
            try:
                app.run_forever(ping_interval=0, ping_timeout=None,
                    sslopt={"cert_reqs": 2, "check_hostname": True},
                    reconnect=0, skip_utf8_validation=False)
            except Exception as exc:
                self.store.event("SOCKET_EXCEPTION", type(exc).__name__)
            finally:
                timer.cancel()
            lived = time.monotonic()-opened
            if lived >= MAX_SOCKET_AGE_SECONDS-1:
                self.store.event("PLANNED_ROTATION")
            if lived >= 300:
                delay = 2.0
            self.store.event("RECONNECT_WAIT", f"seconds={delay:.1f}")
            pause = delay + random.uniform(0, min(1.0, delay/4))
            if self.stop_after_seconds:
                pause = min(pause, max(0, self.stop_after_seconds-(time.monotonic()-self.started)))
            time.sleep(pause)
            delay = min(MAX_BACKOFF_SECONDS, delay*2)

    def _on_message(self, raw: str) -> None:
        try:
            self.store.ingest(raw)
        except Exception as exc:
            self.store.event("MESSAGE_REJECTED", type(exc).__name__)
            LOG.exception("Rejected feed message")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Persistent data directory on E:")
    parser.add_argument("--symbols", default="BTCUSDT", help="Comma-separated Spot symbols")
    parser.add_argument("--observe-seconds", type=int, default=0,
                        help="Optional bounded live check; zero means continuous")
    args = parser.parse_args()
    root = Path(args.root)
    if os.name == "nt" and root.drive.upper() != "E:":
        raise SystemExit("DATA_ROOT_MUST_BE_ON_E")
    if args.observe_seconds < 0 or args.observe_seconds > 86_400:
        raise SystemExit("OBSERVE_DURATION_OUT_OF_RANGE")
    symbols = normalize_symbols(args.symbols)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store(root / "market-feed.sqlite")
    store.event("SERVICE_START", f"symbols={len(symbols)}")
    try:
        LiveService(symbols, store, args.observe_seconds).run()
    finally:
        store.event("SERVICE_STOP")
        store.db.close()


if __name__ == "__main__":
    main()
