"""Offline Binance wire adapter and isolated durable research projection."""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from aql.models.bar import MarketBar

PAIR = "BTCUSDT"
IDENTITY = dict(venue="BINANCE", market="SPOT", symbol=PAIR, quote="USDT", timezone="UTC")
INTERVALS = {"1m": 60_000, "15m": 900_000}
MAX_ROWS = 4096
MAX_FRAME = 4096
ROTATE_MS = 86_390_000


def need(condition, code):
    if not condition:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def hash_bytes(raw):
    return sha256(raw).hexdigest()


def ms(value):
    need(type(value) is int and 0 <= value <= 2**53-1, "INTEGER_MS_REQUIRED")
    return value


def number(value, positive=False):
    need(isinstance(value, str) and 0 < len(value) <= 40, "DECIMAL_STRING")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("DECIMAL_STRING") from exc
    need(result.is_finite() and (result > 0 if positive else result >= 0)
         and -24 <= result.as_tuple().exponent <= 0 and result.adjusted() <= 16, "DECIMAL_RANGE")
    return result


def pairs(items):
    result = dict(items)
    need(len(result) == len(items), "DUPLICATE_JSON_KEY")
    return result


def candle(data, interval, received, event, final):
    step = INTERVALS[interval]
    start, close = ms(data["t"]), ms(data["T"])
    need(start % step == 0 and close == start+step-1, "KLINE_GRID")
    need(type(final) is bool and start <= (event if event is not None else received), "KLINE_FINALITY")
    if final:
        need(close <= received and (event is None or close <= event), "FUTURE_FINAL_BAR")
    prices = {name: data[key] for name, key in zip(("open","high","low","close","volume"), "ohlcv")}
    o, h, l, c, _ = (number(value, key != "volume") for key, value in prices.items())
    need(l <= min(o, c) <= max(o, c) <= h, "OHLC_RANGE")
    return dict(interval=interval, open_ms=start, end_ms_exclusive=close+1, final=final, **prices)


def normalize(raw, received):
    ms(received)
    need(type(raw) is bytes and 0 < len(raw) <= MAX_FRAME, "FRAME_BOUND")
    outer = json.loads(raw, object_pairs_hook=pairs)
    need(set(outer) == {"stream", "data"}, "COMBINED_STREAM")
    stream, data = outer["stream"], outer["data"]
    need(data["s"] == PAIR, "SOURCE_IDENTITY")
    if stream == "btcusdt@trade":
        need(data["e"] == "trade", "WIRE_EVENT")
        event, sequence = ms(data["E"]), ms(data["t"])
        need(ms(data["T"]) <= event, "TRADE_CLOCK")
        number(data["p"], True)
        number(data["q"], True)
        material = dict(price=data["p"], quantity=data["q"], trade_ms=data["T"])
        channel, key = "trade", str(sequence)
    elif stream == "btcusdt@bookTicker":
        need("E" not in data, "BBO_UNEXPECTED_CLOCK")
        event, sequence = None, ms(data["u"])
        bid, ask = number(data["b"], True), number(data["a"], True)
        need(bid <= ask, "CROSSED_BBO")
        number(data["B"])
        number(data["A"])
        material = dict(bid=data["b"], ask=data["a"], bid_quantity=data["B"], ask_quantity=data["A"])
        channel, key = "bbo", str(sequence)
    else:
        need(stream in ("btcusdt@kline_1m", "btcusdt@kline_15m"), "UNSUBSCRIBED_STREAM")
        interval = stream.rsplit("_", 1)[1]
        k = data["k"]
        need(data["e"] == "kline" and k["s"] == PAIR and k["i"] == interval, "KLINE_IDENTITY")
        event, sequence = ms(data["E"]), None
        material = candle(k, interval, received, event, k["x"])
        channel = interval if material["final"] else interval+":partial"
        key = str(material["open_ms"]) if material["final"] else f"{material['open_ms']}:{event}"
    need(event is None or event <= received, "EVENT_CLOCK_FUTURE")
    return dict(schema="aql.binance.spot.observation.v1", source=IDENTITY,
                source_version="BINANCE_SPOT_WS_MS_V1", evidence="OFFLINE_FIXTURE",
                channel=channel, key=key, event_ms=event, receive_ms=received,
                first_known_at_ms=None, sequence=sequence, material=material,
                raw_sha256=hash_bytes(raw), transport="WS")


def rest_candle(row, interval, received, server_time):
    """Convert a bounded, authorized-mode fixture response into recovery only."""
    ms(received)
    ms(server_time)
    need(type(row) is list and len(row) == 12 and interval in INTERVALS, "REST_KLINE_SHAPE")
    need(ms(row[6])+2000 <= server_time <= received and received-server_time <= 2000,
         "REST_OPEN_OR_STALE_SNAPSHOT")
    data = dict(zip(("t","o","h","l","c","v","T"), row[:7]))
    material = candle(data, interval, received, None, True)
    return dict(schema="aql.binance.spot.observation.v1", source=IDENTITY,
                source_version="BINANCE_SPOT_REST_MS_V1", evidence="OFFLINE_FIXTURE",
                channel=interval, key=str(material["open_ms"]), event_ms=None,
                receive_ms=received, first_known_at_ms=None, sequence=None, material=material,
                raw_sha256=hash_bytes(canonical(row)), transport="REST_RECOVERY")


class Gap(ValueError):
    def __init__(self, channel, previous, following, step):
        super().__init__("SEQUENCE_GAP")
        self.channel, self.first, self.stop, self.step = channel, previous+step, following, step


class Feed:
    """Own fixture journal. Records lacking observed data COMMIT remain unreadable."""

    def __init__(self, root, *, max_rows=MAX_ROWS):
        need(type(max_rows) is int and 4 <= max_rows <= MAX_ROWS, "STORE_BOUND")
        root = Path(root).absolute()
        need(all(not p.is_symlink() and not (p.exists() and getattr(p.lstat(),"st_file_attributes",0)&0x400)
                 for p in (root, *root.parents)), "REPARSE_CUSTODY")
        if root.exists():
            need((root/"fixture-store").is_file() and (root/"fixture-store").read_bytes() == b"303-offline-v1",
                 "UNOWNED_STORE")
        else:
            root.mkdir()
            (root/"fixture-store").write_bytes(b"303-offline-v1")
        self.path = root/"observations.sqlite"
        need(not self.path.is_symlink() and not (self.path.exists() and getattr(self.path.lstat(),"st_file_attributes",0)&0x400),
             "REPARSE_STORE")
        self.max_rows = max_rows
        self.unhealthy = False
        with self.tx() as db:
            db.execute("PRAGMA max_page_count=16384")
            db.execute("CREATE TABLE IF NOT EXISTS records (channel TEXT, key TEXT, generation INTEGER, "
                       "recv INTEGER, ack INTEGER, ack_sha TEXT, digest TEXT, raw BLOB, doc BLOB, PRIMARY KEY(channel,key))")
            db.execute("CREATE TABLE IF NOT EXISTS feed_state (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "generation INTEGER, start INTEGER, last_receive INTEGER, enabled INTEGER, fault TEXT)")
            db.execute("INSERT OR IGNORE INTO feed_state VALUES (1,0,0,0,0,'OFFLINE')")
            db.execute("CREATE TABLE IF NOT EXISTS gap (channel TEXT PRIMARY KEY, next INTEGER, stop INTEGER, step INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS quarantine (id INTEGER PRIMARY KEY, recv INTEGER, reason TEXT, wire_sha TEXT)")
            db.execute("UPDATE feed_state SET enabled=0,fault='DISCONNECTED' WHERE enabled=1")

    @contextmanager
    def tx(self, read=False):
        db = sqlite3.connect(self.path.as_uri()+"?mode=ro" if read else self.path, uri=read, timeout=5)
        try:
            if not read:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("BEGIN")
            yield db
            if not read:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def state(db):
        return db.execute("SELECT generation,start,last_receive,enabled,fault FROM feed_state").fetchone()

    def start(self, now):
        ms(now)
        with self.tx() as db:
            generation, _, last, _, fault = self.state(db)
            need(now >= last, "LOCAL_CLOCK_REGRESSION")
            need(fault in ("OFFLINE","DISCONNECTED"), "UNRESOLVED_FEED_FAULT")
            need(not db.execute("SELECT 1 FROM records WHERE ack IS NULL LIMIT 1").fetchone(), "UNCONFIRMED_COMMIT")
            db.execute("UPDATE feed_state SET generation=?,start=?,last_receive=?,enabled=1,fault='NONE'",
                       (generation+1, now, now))
            return generation+1

    def stop(self, now):
        ms(now)
        with self.tx() as db:
            _, _, last, _, fault = self.state(db)
            need(now >= last, "LOCAL_CLOCK_REGRESSION")
            if fault in ("NONE", "OFFLINE", "DISCONNECTED"):
                db.execute("UPDATE feed_state SET enabled=0,last_receive=?,fault='DISCONNECTED'", (now,))

    def fault(self, reason):
        with self.tx() as db:
            db.execute("UPDATE feed_state SET enabled=0,fault=?", (reason,))

    def ingest(self, raw, received, commit_clock, *, crash=False):
        try:
            record = normalize(raw, received)
            return self._commit(record, raw, commit_clock, crash=crash)
        except Gap as gap:
            with self.tx() as db:
                db.execute("INSERT INTO gap VALUES (?,?,?,?)", (gap.channel,gap.first,gap.stop,gap.step))
                db.execute("UPDATE feed_state SET enabled=0,fault='SEQUENCE_GAP'")
            raise
        except (ValueError, KeyError, TypeError, sqlite3.DatabaseError) as exc:
            self.unhealthy = True
            try:
                reason = str(exc)[:160]
                with self.tx() as db:
                    db.execute("UPDATE feed_state SET enabled=0,fault=?", (reason,))
                    if db.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0] < 256:
                        db.execute("INSERT INTO quarantine(recv,reason,wire_sha) VALUES (?,?,?)",
                                   (received,reason,hash_bytes(raw) if type(raw) is bytes else None))
            except sqlite3.DatabaseError:
                pass  # Keep local fail-closed latch if the store is unavailable.
            raise

    def _commit(self, record, raw, commit_clock, *, crash=False, recovery=False):
        channel, key, received = (record[k] for k in ("channel","key","receive_ms"))
        raw_doc = canonical(record)
        with self.tx() as db:
            generation, start, last, enabled, fault = self.state(db)
            need(received >= last, "LOCAL_CLOCK_REGRESSION")
            if recovery:
                gap = db.execute("SELECT next,stop,step FROM gap WHERE channel=?", (channel,)).fetchone()
                need(not enabled and fault == "SEQUENCE_GAP" and gap and int(key) == gap[0] < gap[1]
                     and (gap[1]-gap[0])//gap[2] <= 32, "RECOVERY_NOT_EXPECTED")
            else:
                need(enabled and received-start < ROTATE_MS, "ROTATE_OR_DISCONNECTED")
            need(not db.execute("SELECT 1 FROM records WHERE ack IS NULL LIMIT 1").fetchone(), "UNCONFIRMED_COMMIT")
            prev = db.execute("SELECT doc,ack FROM records WHERE channel=? AND key=?", (channel,key)).fetchone()
            if prev:
                old = json.loads(prev[0])
                need(old["material"] == record["material"], "REVISION_QUARANTINE")
                need(prev[1] is not None, "UNCONFIRMED_COMMIT")
                return "DUPLICATE"
            last_doc = db.execute("SELECT doc FROM records WHERE channel=? ORDER BY rowid DESC LIMIT 1", (channel,)).fetchone()
            if last_doc:
                previous = json.loads(last_doc[0])
                if channel == "trade":
                    need(record["sequence"] > previous["sequence"], "OUT_OF_ORDER")
                    if record["sequence"] != previous["sequence"]+1:
                        raise Gap(channel, previous["sequence"], record["sequence"], 1)
                elif channel == "bbo":
                    need(record["sequence"] > previous["sequence"], "OUT_OF_ORDER")
                elif channel in INTERVALS:
                    old, new = previous["material"]["open_ms"], record["material"]["open_ms"]
                    need(new > old, "OUT_OF_ORDER")
                    if new != previous["material"]["end_ms_exclusive"]:
                        raise Gap(channel, old, new, INTERVALS[channel])
            need(db.execute("SELECT COUNT(*) FROM records").fetchone()[0] < self.max_rows, "STORAGE_FULL")
            db.execute("INSERT INTO records VALUES (?,?,?,?,NULL,NULL,?,?,?)",
                       (channel,key,generation,received,hash_bytes(raw_doc),raw,raw_doc))
            db.execute("UPDATE feed_state SET last_receive=?", (received,))
        if crash:
            import os
            os._exit(73)
        # Sample the local clock only after data COMMIT has returned. An absent
        # second transaction after a crash cannot be reconstructed from recv.
        ack = ms(commit_clock())
        need(received <= ack, "COMMIT_CLOCK_REGRESSION")
        with self.tx() as db:
            ack_sha = hash_bytes(canonical([hash_bytes(raw_doc), generation, ack]))
            db.execute("UPDATE records SET ack=?,ack_sha=? WHERE channel=? AND key=? AND ack IS NULL",
                       (ack,ack_sha,channel,key))
            if recovery:
                db.execute("UPDATE gap SET next=next+step WHERE channel=?", (channel,))
                db.execute("DELETE FROM gap WHERE next=stop")
                if not db.execute("SELECT 1 FROM gap LIMIT 1").fetchone():
                    db.execute("UPDATE feed_state SET fault='DISCONNECTED'")
        return "STORED"

    def recover_candle(self, row, interval, received, server_time, commit_clock):
        record = rest_candle(row, interval, received, server_time)
        return self._commit(record, canonical(row), commit_clock, recovery=True)

    def recover_trade(self, row, received, commit_clock):
        ms(received)
        need(ms(row["time"]) <= received, "FUTURE_TRADE_RECOVERY")
        number(row["price"], True)
        number(row["qty"], True)
        sequence = ms(row["id"])
        raw = canonical(row)
        need(len(raw) <= MAX_FRAME, "FRAME_BOUND")
        record = dict(schema="aql.binance.spot.observation.v1", source=IDENTITY,
                      source_version="BINANCE_SPOT_REST_MS_V1", evidence="OFFLINE_FIXTURE",
                      channel="trade", key=str(sequence), event_ms=None, receive_ms=received,
                      first_known_at_ms=None, sequence=sequence,
                      material=dict(price=row["price"], quantity=row["qty"], trade_ms=row["time"]),
                      raw_sha256=hash_bytes(raw), transport="REST_RECOVERY")
        return self._commit(record, raw, commit_clock, recovery=True)

    def read(self, cutoff):
        """Read only current-generation final WS marks by observed durable cutoff."""
        ms(cutoff)
        if self.unhealthy:
            return self.blocked("STORE_OR_FEED_FAULT")
        try:
            return self._read(cutoff)
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError):
            return self.blocked("STORE_CORRUPTION")

    def _read(self, cutoff):
        with self.tx(read=True) as db:
            generation, start, last, enabled, fault = self.state(db)
            if not enabled or cutoff < last or cutoff-start >= ROTATE_MS:
                return self.blocked(fault if not enabled else "CLOCK_OR_ROTATION")
            if db.execute("SELECT 1 FROM records WHERE ack IS NULL LIMIT 1").fetchone():
                return self.blocked("UNCONFIRMED_COMMIT")
            selected = {}
            for channel in ("trade","bbo","1m","15m"):
                found = db.execute("SELECT ack,ack_sha,digest,raw,doc FROM records WHERE channel=? AND generation=? "
                                   "AND ack<=? ORDER BY rowid DESC LIMIT 1", (channel,generation,cutoff)).fetchone()
                if found is None:
                    return self.blocked("WARMUP_OR_ASOF")
                ack, ack_sha, digest, raw, doc = found
                record = json.loads(doc)
                if (hash_bytes(doc) != digest or hash_bytes(raw) != record["raw_sha256"]
                        or ack_sha != hash_bytes(canonical([digest,generation,ack])) or record["receive_ms"] > ack):
                    return self.blocked("STORE_TAMPER")
                if record["transport"] != "WS":
                    return self.blocked("RECOVERY_NOT_LIVE")
                selected[channel] = {**record, "commit_ms": ack}
            trade, quote = selected["trade"], selected["bbo"]
            if cutoff-trade["event_ms"] > 2000 or cutoff-quote["receive_ms"] > 2000:
                return self.blocked("STALE_PRICE")
            for interval, step in INTERVALS.items():
                row = selected[interval]
                if (row["material"]["end_ms_exclusive"] < (cutoff-5000)//step*step
                        or row["receive_ms"]-row["material"]["end_ms_exclusive"] > 5000):
                    return self.blocked("STALE_FINAL_BAR")
            bars = {}
            for interval in INTERVALS:
                row = selected[interval]
                m = row["material"]
                # G1's float view is a compatibility projection. Exact decimal
                # material and original bytes remain available for reconciliation.
                bar = MarketBar(symbol=PAIR, interval=interval, bar_open=m["open_ms"],
                                bar_close=m["end_ms_exclusive"]-1, is_final=True,
                                source="binance_ws_offline_fixture", ingested_at=row["receive_ms"],
                                **{k: float(m[k]) for k in ("open","high","low","close","volume")})
                bars[interval] = bar.with_checksum().to_dict()
            return dict(status="OFFLINE_RESEARCH_INPUT_READY", trading_authority="NONE", orders=0,
                        execution="UNKNOWN_BBO_EVENT_TIME_AND_FILL", source=IDENTITY,
                        as_of_ms=cutoff, bars=bars, records=selected)

    @staticmethod
    def blocked(reason):
        return dict(status="RESEARCH_BLOCKED", reason=reason, bars={}, trading_authority="NONE", orders=0)
