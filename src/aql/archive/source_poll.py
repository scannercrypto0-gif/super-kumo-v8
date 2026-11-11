"""Offline admission polling with durable exclusive egress fencing."""
from contextlib import contextmanager
import math
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError

from .contracts import canonical, digest, parse, timestamp
from .source_view import require, is_pin

MAX_BODY = 256_000


class PollFence:
    """One local transactional owner. No request code or production activation.

    Calls sharing an egress must share the owner. An unacknowledged claim
    consumes weight and keeps the fence closed until explicitly reconciled.
    """

    def __init__(self, root, *, scope, verified_weight, window_ms=60_000, max_attempts=128):
        require(type(scope) is str and 0 < len(scope) <= 128 and scope.startswith("FIXTURE:")
                and type(verified_weight) is int and 2 <= verified_weight <= 20_000
                and type(window_ms) is int and 1000 <= window_ms <= 300_000
                and type(max_attempts) is int and 1 <= max_attempts <= 128,"FENCE_POLICY")
        self.root = Path(root).absolute()
        for item in (self.root,*self.root.parents):
            require(not item.is_symlink() and not (item.exists() and getattr(item.lstat(),"st_file_attributes",0)&0x400),
                    "FENCE_REPARSE")
        if not self.root.exists():
            self.root.mkdir()
            (self.root/"owner").write_bytes(b"core-source-poll-v1")
        require((self.root/"owner").is_file() and (self.root/"owner").read_bytes()==b"core-source-poll-v1",
                "UNOWNED_FENCE")
        self.path = self.root/"fence.sqlite"
        require(not self.path.is_symlink() and not (self.path.exists() and getattr(self.path.lstat(),"st_file_attributes",0)&0x400),
                "FENCE_REPARSE")
        self.cap,self.window,self.max_attempts = verified_weight//2,window_ms,max_attempts
        pin = digest([scope,verified_weight,window_ms,max_attempts])
        with self.tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "policy TEXT, clock INTEGER, retry INTEGER, failures INTEGER, ban INTEGER)")
            db.execute("INSERT OR IGNORE INTO control VALUES (1,?,0,0,0,0)",(pin,))
            require(db.execute("SELECT policy FROM control").fetchone()[0]==pin,"FENCE_POLICY_DRIFT")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, at INTEGER, weight INTEGER, "
                       "state TEXT, result BLOB, seal TEXT)")

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path,timeout=1)
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
    def clock(db, now):
        timestamp(now)
        clock,retry,failures,ban = db.execute("SELECT clock,retry,failures,ban FROM control").fetchone()
        require(now>=clock,"POLL_CLOCK_REGRESSION")
        db.execute("UPDATE control SET clock=?",(now,))
        return retry,failures,ban

    def claim(self, request_pin, now, weight):
        require(is_pin(request_pin) and type(weight) is int and 0 < weight <= self.cap,"POLL_WEIGHT")
        with self.tx() as db:
            retry,_,ban = self.clock(db,now)
            old = db.execute("SELECT state,result,seal,weight FROM attempts WHERE id=?",(request_pin,)).fetchone()
            if old:
                require(old[3]==weight,"POLL_REPLAY_CONFLICT")
                if old[0]=="PENDING":
                    return "PENDING_ACK",None
                result = parse(old[1])
                require(digest(result)==old[2],"POLL_RECEIPT_TAMPER")
                return "REPLAY",result
            if ban or now<retry:
                return "COOLDOWN_OR_BAN",None
            if db.execute("SELECT 1 FROM attempts WHERE state='PENDING' LIMIT 1").fetchone():
                return "EXCLUSIVE_OWNER_BUSY",None
            count = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            if count>=self.max_attempts:
                return "SESSION_CAP",None
            used = db.execute("SELECT COALESCE(SUM(weight),0) FROM attempts WHERE at>?",(now-self.window,)).fetchone()[0]
            if used+weight>self.cap:
                return "QUOTA_BACKPRESSURE",None
            db.execute("INSERT INTO attempts VALUES (?,?,?,'PENDING',NULL,NULL)",(request_pin,now,weight))
            return "CLAIMED",None

    def complete(self, request_pin, now, status, *, retry_after=None, result_pin=None, lost=False, measurements=None):
        require(type(status) is int and (status==0 or 100<=status<=599)
                and (result_pin is None or is_pin(result_pin)),"POLL_RESULT")
        if measurements is not None:
            require(set(measurements)=={"wall_us","cpu_us","payload_bytes"}
                    and all(type(v) is int and v>=0 for v in measurements.values()),"POLL_METRICS")
        with self.tx() as db:
            _,failures,ban = self.clock(db,now)
            row = db.execute("SELECT at,state FROM attempts WHERE id=?",(request_pin,)).fetchone()
            require(row and row[1]=="PENDING","POLL_NO_PENDING")
            require(not lost or (status==0 and now-row[0]>=5000),"LOST_ACK_NOT_DUE")
            state = "ACK" if 200<=status<300 and result_pin is not None else "UNKNOWN"
            retry = 0
            if state!="ACK":
                failures = min(8,failures+1)
                try:
                    hint = float(retry_after)
                except (ValueError,TypeError,OverflowError):
                    hint = math.nan
                if not math.isfinite(hint) or hint<0:
                    hint = 60 if status==429 else 0
                jitter = int(request_pin[:4],16)%251
                # A retry hint outside the representable clock range holds the
                # lane for operator review rather than truncating the wait.
                if hint>31_536_000:
                    ban = 1
                retry = now+max(min(60_000,1000*2**(failures-1))+jitter,
                                int(hint*1000) if not ban else 0)
                ban = int(ban or status==418)
            else:
                failures = 0
            result = dict(request_sha256=request_pin,status=state,http_status=status,
                          result_sha256=result_pin,retry_at=retry,ban=bool(ban),lost_ack=lost,
                          measurements=measurements)
            db.execute("UPDATE attempts SET state=?,result=?,seal=? WHERE id=?",
                       (state,canonical(result),digest(result),request_pin))
            db.execute("UPDATE control SET retry=?,failures=?,ban=?",(retry,failures,ban))
            return result

    def read(self, request_pin, now, weight, reader):
        """Invoke a bounded fixture reader. The callable receives a timeout."""
        state,prior = self.claim(request_pin,now,weight)
        if state!="CLAIMED":
            return state,prior
        wall,cpu = time.monotonic(),time.process_time()
        size = 0
        def metrics():
            return dict(wall_us=int((time.monotonic()-wall)*1_000_000),
                        cpu_us=int((time.process_time()-cpu)*1_000_000),payload_bytes=size)
        try:
            result = reader(timeout=1.0)
            require(type(result) is dict,"POLL_RESPONSE_BOUND")
            size = len(canonical(result))
            require(size<=MAX_BODY,"POLL_RESPONSE_BOUND")
            require(time.monotonic()-wall<=1 and time.process_time()-cpu<=0.5,"POLL_RESOURCE_BOUND")
        except HTTPError as error:
            hint = error.headers.get("Retry-After") if error.headers else None
            return "UNKNOWN",self.complete(request_pin,now,error.code,retry_after=hint,measurements=metrics())
        except (OSError,ValueError):
            return "UNKNOWN",self.complete(request_pin,now,0,measurements=metrics())
        receipt = self.complete(request_pin,now,200,result_pin=digest(result),measurements=metrics())
        return "ACK",dict(receipt=receipt,value=result)

    def health(self, now):
        with self.tx() as db:
            retry,failures,ban = self.clock(db,now)
            rows = db.execute("SELECT state,COUNT(*) FROM attempts GROUP BY state").fetchall()
            used = db.execute("SELECT COALESCE(SUM(weight),0) FROM attempts WHERE at>?",(now-self.window,)).fetchone()[0]
            return dict(states=dict(rows),used_weight=used,weight_cap=self.cap,retry_at=retry,
                        failures=failures,ban=bool(ban),queue_depth=0,fixture_only=True)
