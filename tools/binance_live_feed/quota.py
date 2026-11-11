"""Single shared-IP dispatch authority for the offline Binance Spot lane."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import sqlite3

REST_WEIGHTS = {"time": 1, "exchangeInfo": 20, "klines": 2, "aggTrades": 4,
                "bookTicker": 2, "depth100": 5, "trades": 25}
STREAMS = frozenset(("btcusdt@trade", "btcusdt@bookTicker", "btcusdt@kline_1m", "btcusdt@kline_15m"))


@dataclass(frozen=True)
class Limits:
    rest_weight: int
    connections: int = 300
    ws_messages: int = 5
    subscriptions: int = 1024

    def __post_init__(self):
        if any(type(v) is not int or v < 2 for v in vars(self).values()):
            raise ValueError("UNKNOWN_OR_INSUFFICIENT_QUOTA")


class Quota:
    """Atomic rolling budgets shared by all workers via a single SQLite owner.

    A future deployment routes all egress for the same IP through this owner.
    Do not put the SQLite file on a network filesystem or shard by worker.
    """

    def __init__(self, path, limits):
        self.path, self.limits = path, limits
        with self.tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS quota_config (id INTEGER PRIMARY KEY CHECK(id=1), limits TEXT)")
            db.execute("INSERT OR IGNORE INTO quota_config VALUES (1,?)", (repr(limits),))
            if db.execute("SELECT limits FROM quota_config").fetchone()[0] != repr(limits):
                raise ValueError("QUOTA_POLICY_DRIFT")
            db.execute("CREATE TABLE IF NOT EXISTS usage (kind TEXT, at INTEGER, amount INTEGER)")
            db.execute("CREATE INDEX IF NOT EXISTS usage_window ON usage(kind,at)")
            db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS sockets (id TEXT PRIMARY KEY, opened INTEGER, last_ping INTEGER, streams TEXT)")

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, key, default=0):
        row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    @staticmethod
    def set(db, key, value):
        db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, value))

    def clock(self, db, now):
        if type(now) is not int or not self.get(db, "clock") <= now <= 2**53-1:
            raise ValueError("QUOTA_CLOCK_REGRESSION")
        self.set(db, "clock", now)
        db.execute("DELETE FROM usage WHERE at<=?", (now-300_000,))

    @staticmethod
    def used(db, kind, now, window):
        return db.execute("SELECT COALESCE(SUM(amount),0) FROM usage WHERE kind=? AND at>?",
                          (kind, now-window)).fetchone()[0]

    def charge(self, db, kind, now, window, amount, cap):
        if self.used(db, kind, now, window) + amount > cap:
            return False
        db.execute("INSERT INTO usage VALUES (?,?,?)", (kind, now, amount))
        return True

    def rest(self, endpoint, now, *, recovery=False):
        weight = REST_WEIGHTS[endpoint]
        with self.tx() as db:
            self.clock(db, now)
            if self.get(db, "ban") or now < self.get(db, "retry_at"):
                return None
            if recovery and now < self.get(db, "recovery_at"):
                return None
            if self.get(db, "pending"):
                # Unknown outcome consumes its reservation. Reconcile explicitly
                # after timeout rather than handing another worker a free retry.
                return None
            cap = self.limits.rest_weight // 2
            has_header = self.get(db, "header_minute", -1) == now//60_000
            observed = self.get(db, "weight_header") if has_header else 0
            since_header = self.used(db, "rest", now, max(1, now-self.get(db, "header_at"))) if has_header else 0
            if observed + since_header + weight > cap:
                return None
            if not self.charge(db, "rest", now, 60_000, weight, cap):
                return None
            token = self.get(db, "serial") + 1
            self.set(db, "serial", token)
            self.set(db, "pending", token)
            self.set(db, "pending_since", now)
            if recovery:
                self.set(db, "recovery_at", now+1000)
            return token

    def result(self, token, now, status, *, retry_after_ms=None, used_weight=None):
        with self.tx() as db:
            self.clock(db, now)
            if not token or token != self.get(db, "pending"):
                raise ValueError("UNMATCHED_REST_RESULT")
            self.set(db, "pending", 0)
            if used_weight is not None:
                if type(used_weight) is not int or used_weight < 0:
                    raise ValueError("INVALID_WEIGHT_HEADER")
                old = self.get(db, "weight_header") if self.get(db, "header_minute", -1) == now//60_000 else 0
                self.set(db, "weight_header", max(used_weight, old))
                self.set(db, "header_minute", now//60_000)
                self.set(db, "header_at", now)
            if status == 418:
                self.set(db, "ban", 1)  # operator review, no automatic ban probing
            elif status == 429 or status == 0 or 500 <= status <= 599:
                failures = min(self.get(db, "failures")+1, 8)
                self.set(db, "failures", failures)
                jitter = int(hashlib.sha256(str(token).encode()).hexdigest()[:4], 16) % 251
                backoff = min(60_000, 1000 * 2**(failures-1)) + jitter
                hint = retry_after_ms if type(retry_after_ms) is int and retry_after_ms >= 0 else 0
                wait = max(backoff, hint, 60_000 if status == 429 and not hint else 0)
                self.set(db, "retry_at", now+wait)
            elif 200 <= status < 300:
                self.set(db, "failures", 0)
                self.set(db, "retry_at", 0)
            else:
                self.set(db, "retry_at", now+60_000)

    def expire_request(self, now):
        with self.tx() as db:
            self.clock(db, now)
            token = self.get(db, "pending")
            due = token and now-self.get(db, "pending_since") >= 5000
        if due:
            self.result(token, now, 0)
        return bool(due)

    def connect(self, socket_id, now, streams):
        if not isinstance(socket_id, str) or not 1 <= len(socket_id) <= 64:
            raise ValueError("SOCKET_ID")
        streams = tuple(streams)
        if (not streams or len(set(streams)) != len(streams) or not set(streams) <= STREAMS
                or len(streams) > self.limits.subscriptions // 2):
            return False
        with self.tx() as db:
            self.clock(db, now)
            if self.get(db, "ban") or now < self.get(db, "ws_retry_at"):
                return False
            db.execute("DELETE FROM sockets WHERE opened<=?", (now-86_390_000,))
            if db.execute("SELECT COUNT(*) FROM sockets").fetchone()[0] >= 1:
                return False
            if not self.charge(db, "connect", now, 300_000, 1, self.limits.connections//2):
                return False
            db.execute("INSERT INTO sockets VALUES (?,?,?,?)", (socket_id, now, now, json.dumps(sorted(streams))))
            return True

    def alive(self, socket_id, now):
        with self.tx() as db:
            self.clock(db, now)
            row = db.execute("SELECT opened,last_ping FROM sockets WHERE id=?", (socket_id,)).fetchone()
            return bool(row and now-row[0] < 86_390_000 and now-row[1] < 60_000 and not self.get(db, "ban"))

    def disconnect(self, socket_id, now, failed=True):
        with self.tx() as db:
            self.clock(db, now)
            removed = db.execute("DELETE FROM sockets WHERE id=?", (socket_id,)).rowcount
            if removed and failed:
                count = min(self.get(db, "ws_failures")+1, 7)
                self.set(db, "ws_failures", count)
                jitter = int(hashlib.sha256(socket_id.encode()).hexdigest()[:4], 16) % 251
                self.set(db, "ws_retry_at", now+min(60_000, 1000*2**(count-1))+jitter)

    def ws(self, socket_id, now, frame, *, streams=()):
        if frame not in ("PONG", "SUBSCRIBE", "UNSUBSCRIBE"):
            return False
        if frame != "PONG" and (not streams or not set(streams) <= STREAMS
                                or len(set(streams)) != len(streams)
                                or len(streams) > self.limits.subscriptions//2):
            return False
        with self.tx() as db:
            self.clock(db, now)
            socket = db.execute("SELECT opened,last_ping,streams FROM sockets WHERE id=?", (socket_id,)).fetchone()
            if self.get(db, "ban") or not socket or now-socket[0] >= 86_390_000 or now-socket[1] >= 60_000:
                return False
            if frame != "PONG" and not set(streams) <= set(json.loads(socket[2])):
                return False
            cap = self.limits.ws_messages//2
            kind = "ws:" + socket_id
            if frame != "PONG" and self.used(db, kind+":control", now, 1000) >= max(0, cap-1):
                return False
            if not self.charge(db, kind, now, 1000, 1, cap):
                return False
            if frame == "PONG":
                db.execute("UPDATE sockets SET last_ping=? WHERE id=?", (now, socket_id))
                self.set(db, "ws_failures", 0)
            else:
                db.execute("INSERT INTO usage VALUES (?,?,1)", (kind+":control", now))
            return True


class RecoveryQueue:
    """Bounded coalesced pending work, with a slot reserved for essential work."""

    def __init__(self, capacity=16):
        if not 2 <= capacity <= 32:
            raise ValueError("QUEUE_CAPACITY")
        self.capacity = capacity
        self.items = {}
        self.high_water = self.rejected = 0

    def offer(self, key, endpoint, *, essential=False):
        if not isinstance(key, str) or not 1 <= len(key) <= 96 or endpoint not in REST_WEIGHTS:
            raise ValueError("QUEUE_ITEM")
        item = (not essential, endpoint)
        if key in self.items:
            if self.items[key] != item:
                raise ValueError("QUEUE_KEY_CONFLICT")
            return True
        if len(self.items) >= self.capacity-int(not essential):
            self.rejected += 1
            return False
        self.items[key] = item
        self.high_water = max(self.high_water, len(self.items))
        return True

    def dispatch(self, quota, now):
        if not self.items:
            return None
        key = min(self.items, key=lambda k: self.items[k][0])
        recovery, endpoint = self.items[key]
        token = quota.rest(endpoint, now, recovery=recovery)
        if token is None:
            return None
        del self.items[key]
        return key, endpoint, token
