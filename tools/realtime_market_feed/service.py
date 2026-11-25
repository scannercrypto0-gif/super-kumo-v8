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
import uuid
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

# A code-pinned normalized producer attestation. It binds each newly inserted
# finalized bar to its event digest and exact normalized row. It is not a
# Binance signature or external origin proof; old rows are never backfilled.
LINEAGE_SCHEMA = "atlas.realtime-market-feed.normalized-bar-attestation.v1"
PRODUCER_ID = "atlas.realtime_market_feed.service.Store.ingest"
PRODUCER_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        CREATE TABLE IF NOT EXISTS latest_trade(
          symbol TEXT PRIMARY KEY, trade_id INTEGER NOT NULL, price TEXT NOT NULL,
          quantity TEXT NOT NULL, event_ms INTEGER NOT NULL, received_ms INTEGER NOT NULL,
          buyer_is_maker INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS final_bar(
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
        CREATE TABLE IF NOT EXISTS final_bar_lineage(
          symbol TEXT NOT NULL, interval TEXT NOT NULL, open_ms INTEGER NOT NULL,
          receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL,
          PRIMARY KEY(symbol, interval, open_ms));
        CREATE TABLE IF NOT EXISTS service_run(
          run_id TEXT PRIMARY KEY, producer_code_sha256 TEXT NOT NULL,
          symbols_json TEXT NOT NULL, requested_observe_seconds INTEGER NOT NULL,
          started_ms INTEGER NOT NULL, stopped_ms INTEGER);
        """)
        self.db.commit()

    def event(self, kind: str, detail: str = "") -> None:
        with self.db:
            self.db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                            (utc_ms(), kind, detail[:300]))

    def begin_run(self, symbols: list[str], observe_seconds: int) -> str:
        run_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("""INSERT INTO service_run
              (run_id,producer_code_sha256,symbols_json,requested_observe_seconds,started_ms)
              VALUES(?,?,?,?,?)""",
              (run_id,PRODUCER_CODE_SHA256,json.dumps(sorted(symbols),separators=(",",":")),
               observe_seconds,utc_ms()))
        return run_id

    def end_run(self, run_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE service_run SET stopped_ms=? WHERE run_id=? AND stopped_ms IS NULL",
                            (utc_ms(),run_id))

    def ingest(self, raw: str, received_ms: int | None = None) -> str:
        received_ms = received_ms or utc_ms()
        envelope = json.loads(raw)
        data = envelope.get("data", envelope)
        kind = data.get("e")
        if kind is None and {"u", "b", "B", "a", "A"}.issubset(data):
            kind = "bookTicker"
        symbol = str(data.get("s", "")).upper()
        if not symbol:
            raise ValueError("MISSING_SYMBOL")
        if kind == "trade":
            trade_id, event_ms = int(data["t"]), int(data["T"])
            with self.db:
                self.db.execute("""INSERT INTO latest_trade VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(symbol) DO UPDATE SET trade_id=excluded.trade_id,
                    price=excluded.price,quantity=excluded.quantity,event_ms=excluded.event_ms,
                    received_ms=excluded.received_ms,buyer_is_maker=excluded.buyer_is_maker
                    WHERE excluded.trade_id > latest_trade.trade_id""",
                    (symbol,trade_id,str(data["p"]),str(data["q"]),event_ms,received_ms,int(bool(data["m"]))))
            return "trade"
        if kind == "bookTicker":
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
            event_digest = _sha256(_canonical(data))
            ohlcv = {"o":str(k["o"]), "h":str(k["h"]), "l":str(k["l"]),
                     "c":str(k["c"]), "v":str(k["v"])}
            normalized = {
                "provider":"BINANCE", "market":"SPOT", "symbol":symbol,
                "interval":"1m", "open_ms":opened, "close_ms":closed,
                "available_at_ms":received_ms, "finality":"FINAL",
                "ohlcv":ohlcv, "trades":int(k["n"]),
                "event_payload_sha256":event_digest,
            }
            replay_identity = _sha256(_canonical({
                "provider":"BINANCE", "market":"SPOT", "symbol":symbol,
                "interval":"1m", "open_ms":opened, "close_ms":closed,
                "event_payload_sha256":event_digest,
            }))
            body = {
                "schema":LINEAGE_SCHEMA, "producer_id":PRODUCER_ID,
                "producer_code_sha256":PRODUCER_CODE_SHA256,
                **normalized, "replay_identity_sha256":replay_identity,
                "normalized_row_sha256":_sha256(_canonical(normalized)),
            }
            receipt_json = _canonical(body).decode("utf-8")
            receipt_sha = _sha256(_canonical(body))
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
                  (symbol,opened,closed,ohlcv["o"],ohlcv["h"],ohlcv["l"],ohlcv["c"],
                   ohlcv["v"],normalized["trades"],received_ms,event_digest))
                existing = self.db.execute(
                    """SELECT close_ms,open,high,low,close,volume,trades
                       FROM final_bar WHERE symbol=? AND interval='1m' AND open_ms=?""",
                    (symbol,opened)).fetchone()
                candidate = (closed,ohlcv["o"],ohlcv["h"],ohlcv["l"],ohlcv["c"],
                             ohlcv["v"],normalized["trades"])
                if existing and tuple(existing) != candidate:
                    self.db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                                    (received_ms,"FINAL_BAR_CONFLICT",symbol+":"+str(opened)))
                elif cur.rowcount == 1:
                    # Forward-only: legacy rows are never retrofitted on replay.
                    self.db.execute("""INSERT INTO final_bar_lineage
                      (symbol,interval,open_ms,receipt_json,receipt_sha256)
                      VALUES(?,'1m',?,?,?)""",
                      (symbol,opened,receipt_json,receipt_sha))
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
        self._recovery_lock = threading.Lock()
        self._recovering_symbols = set()
        self._recovery_last_attempt = {}

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
            outcome = self.store.ingest(raw)
            if outcome == "final_bar":
                envelope = json.loads(raw)
                data = envelope.get("data", envelope)
                symbol = str(data.get("s", "")).upper()
                if symbol:
                    self._queue_gap_recovery(symbol)
        except Exception as exc:
            self.store.event("MESSAGE_REJECTED", type(exc).__name__)
            LOG.exception("Rejected feed message")

    def _queue_gap_recovery(self, symbol: str) -> None:
        now = time.monotonic()
        with self._recovery_lock:
            if symbol in self._recovering_symbols:
                return
            last_attempt = self._recovery_last_attempt.get(symbol)
            if last_attempt is not None and now - last_attempt < 60:
                return
            self._recovery_last_attempt[symbol] = now
            self._recovering_symbols.add(symbol)
        worker = threading.Thread(target=self._recover_gaps, args=(symbol,), daemon=True)
        worker.start()

    def _recover_gaps(self, symbol: str) -> None:
        try:
            from tools.realtime_market_feed.backfill import recover_open_gaps
            recover_open_gaps(self.store.path, symbol)
        except Exception as exc:
            db = sqlite3.connect(self.store.path, timeout=10)
            try:
                with db:
                    db.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                               (utc_ms(),"GAP_BACKFILL_WORKER_ERROR",type(exc).__name__))
            finally:
                db.close()
            LOG.exception("Gap recovery worker failed")
        finally:
            with self._recovery_lock:
                self._recovering_symbols.discard(symbol)


def build_report(path: str | Path) -> dict:
    db = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        trade = db.execute("SELECT * FROM latest_trade ORDER BY symbol").fetchall()
        quotes = db.execute("SELECT * FROM latest_quote ORDER BY symbol").fetchall()
        bars = db.execute("""SELECT symbol,open_ms,close_ms,close,received_ms FROM final_bar
                             WHERE (symbol,open_ms) IN
                             (SELECT symbol,MAX(open_ms) FROM final_bar GROUP BY symbol)
                             ORDER BY symbol""").fetchall()
        gaps = db.execute("""SELECT symbol,interval,start_ms,end_ms,reason,detected_ms
                             FROM open_gap WHERE status='OPEN' ORDER BY symbol,start_ms""").fetchall()
        events = db.execute("""SELECT at_ms,kind,detail FROM service_event
                               ORDER BY id DESC LIMIT 20""").fetchall()
        has_run_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='service_run'").fetchone()
        run = None
        if has_run_table:
            row = db.execute("""SELECT run_id,producer_code_sha256,symbols_json,
                requested_observe_seconds,started_ms,stopped_ms FROM service_run
                ORDER BY started_ms DESC LIMIT 1""").fetchone()
            if row:
                run = {"schema":"aql.realtime-market-feed.observation-run.v1",
                       "run_id":row["run_id"],"producer_code_sha256":row["producer_code_sha256"],
                       "symbols":json.loads(row["symbols_json"]),
                       "requested_observe_seconds":row["requested_observe_seconds"],
                       "started_ms":row["started_ms"],"stopped_ms":row["stopped_ms"]}
        return {"schema":"atlas.realtime-market-feed.report.v1","as_of_ms":utc_ms(),
                "trades":[dict(row) for row in trade],"quotes":[dict(row) for row in quotes],
                "latest_final_bars":[dict(row) for row in bars],
                "open_gaps":[dict(row) for row in gaps],"recent_events":[dict(row) for row in events],
                "observation":run,
                "readiness":"OBSERVED_ONLY" if trade and quotes and bars and not gaps else "NOT_READY",
                "orders":0,"trading_authority":"NONE"}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Persistent data directory on E:")
    parser.add_argument("--symbols", default="BTCUSDT", help="Comma-separated Spot symbols")
    parser.add_argument("--observe-seconds", type=int, default=0,
                        help="Optional bounded live check; zero means continuous")
    parser.add_argument("--report", action="store_true", help="Read-only local status report")
    args = parser.parse_args()
    root = Path(args.root)
    if os.name == "nt" and root.drive.upper() != "E:":
        raise SystemExit("DATA_ROOT_MUST_BE_ON_E")
    if args.observe_seconds < 0 or args.observe_seconds > 86_400:
        raise SystemExit("OBSERVE_DURATION_OUT_OF_RANGE")
    symbols = normalize_symbols(args.symbols)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_path = root / "market-feed.sqlite"
    if args.report:
        print(json.dumps(build_report(db_path),sort_keys=True))
        return
    store = Store(db_path)
    run_id = store.begin_run(symbols, args.observe_seconds)
    store.event("SERVICE_START", f"symbols={len(symbols)}")
    try:
        LiveService(symbols, store, args.observe_seconds).run()
    finally:
        store.event("SERVICE_STOP")
        store.end_run(run_id)
        store.db.close()


if __name__ == "__main__":
    main()
