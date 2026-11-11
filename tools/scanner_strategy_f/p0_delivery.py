"""Scanner-owned fixture outbox and bounded schedule. No deployed recipients."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from .p0_slice import STEP, census, clock, decision, digest, monitor, seal, source_query, verify
from tools.strategy_service_offline.common import Frozen, require

ROUTES = {"SECRETARY":"aql.scanner.p0.decision.v1","LAB":"aql.scanner.p0.lab-monitor.v1"}


def canonical(doc):
    return json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


class Store:
    def __init__(self, root, plan, expected):
        verify(plan,expected)
        require(plan["scope"]=="TEST_ONLY" and plan["authority"]=="NONE","P0_SCOPE")
        root = Path(root).absolute()
        for part in (root,*root.parents):
            require(not part.is_symlink() and not (part.exists() and getattr(part.lstat(),"st_file_attributes",0)&0x400),
                    "P0_REPARSE")
        if not root.exists():
            root.mkdir()
            (root/"fixture-owner").write_bytes(b"scanner-p0")
        marker = root/"fixture-owner"
        require(marker.is_file() and not marker.is_symlink() and marker.read_bytes()==b"scanner-p0",
                "P0_UNOWNED")
        self.path = root/"scanner.sqlite"
        require(not self.path.is_symlink() and not (self.path.exists() and getattr(self.path.lstat(),"st_file_attributes",0)&0x400),
                "P0_REPARSE")
        self.plan = json.loads(canonical(plan))
        with self.tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), pin TEXT, "
                       "next INTEGER, clock INTEGER, bytes INTEGER)")
            db.execute("INSERT OR IGNORE INTO meta VALUES (1,?,0,0,0)",(expected,))
            require(db.execute("SELECT pin FROM meta").fetchone()[0]==expected,"P0_POLICY_DRIFT")
            db.execute("CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, slot INTEGER, raw BLOB)")
            db.execute("CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, raw BLOB)")
            db.execute("CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, route TEXT, raw BLOB, "
                       "state TEXT, attempts INTEGER, due INTEGER, ack BLOB)")

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
    def _clock(db, now):
        clock(now)
        require(now>=db.execute("SELECT clock FROM meta").fetchone()[0],"P0_CLOCK_REGRESSION")
        db.execute("UPDATE meta SET clock=?",(now,))

    def poll(self, now, plugins, sources, monitors):
        """Local reads only. No HTTP, observer or exchange client."""
        p = self.plan
        require({Frozen.restore(plugin).sha256 for plugin in plugins}==set(p["plugins"])
                and len(plugins)==len(p["plugins"]) and set(sources)==set(p["symbols"]),"P0_CONFIG_DRIFT")
        require(set(monitors)<=set(p["symbols"]),"P0_MONITOR_SYMBOL")
        wall,cpu = time.monotonic(),time.process_time()
        processed = []
        with self.tx() as db:
            self._clock(db,now)
            index,total_bytes = db.execute("SELECT next,bytes FROM meta").fetchone()
            lab_bytes = db.execute("SELECT COALESCE(SUM(length(raw)),0) FROM outbox WHERE route='LAB'").fetchone()[0]
            lab_backpressure = 0
            due = min(p["slots"],(now-p["origin"])//STEP,index+p["catchup"])
            for i in range(index,due):
                slot = p["origin"]+i*STEP
                cutoff = slot+STEP
                for symbol in p["symbols"]:
                    source,warehouse = sources[symbol]
                    source_pin = p["sources"][symbol]
                    query = None
                    try:
                        if source is not None:
                            query = source_query(source,source_pin,symbol,cutoff-p["warmup"]*STEP,cutoff,cutoff,
                                                 warehouse=warehouse)
                    except (ValueError,KeyError,TypeError,OSError,sqlite3.DatabaseError):
                        query = None
                    for plugin in plugins:
                        event,batch = decision(p,plugin,symbol,slot,now,source_pin,query,warehouse=warehouse)
                        raw = canonical(event)
                        db.execute("INSERT INTO decisions VALUES (?,?,?)",(event["id"],slot,raw))
                        total_bytes += len(raw)
                        if batch is not None:
                            braw = canonical(batch)
                            if db.execute("INSERT OR IGNORE INTO batches VALUES (?,?)",(batch["sha256"],braw)).rowcount:
                                total_bytes += len(braw)
                        if event["timing"]=="FIXTURE_ON_TIME" and event["state"] in ("ENTRY_SIGNAL","EXIT_SIGNAL"):
                            total_bytes += self._enqueue(db,"SECRETARY",event,now)
                        for req,pin in monitors.get(symbol,())[:p["max_rows"]]:
                            if not isinstance(req,dict) or req.get("plugin_sha256") != event["plugin_sha256"]:
                                continue
                            try:
                                row = monitor(req,pin,decision_doc=event,query=query)
                            except (ValueError,KeyError,TypeError):
                                row = seal(dict(schema=ROUTES["LAB"],mode="MONITOR_ONLY",authority="NONE",
                                                decision_sha256=event["sha256"],availability="UNKNOWN",
                                                reason="INVALID_MONITOR_REQUEST",value=None))
                            envelope = self._envelope("LAB",row)
                            if lab_bytes+len(canonical(envelope)) <= p["max_bytes"]:
                                lab_bytes += self._enqueue(db,"LAB",row,now)
                            else:
                                lab_backpressure += 1
                        require(total_bytes<=p["max_bytes"],"P0_STORAGE_BACKPRESSURE")
                        processed.append(event)
                db.execute("UPDATE meta SET next=?,bytes=?",(i+1,total_bytes))
        return dict(rows=processed,lab_backpressure=lab_backpressure,
                    wall_us=int((time.monotonic()-wall)*1e6),cpu_us=int((time.process_time()-cpu)*1e6))

    @staticmethod
    def _envelope(route, doc):
        return seal(dict(schema="aql.scanner.p0.handoff.v1",route=route,body=doc,
                         scope="TEST_ONLY",authority="NONE"))

    @classmethod
    def _enqueue(cls, db, route, doc, now):
        envelope = cls._envelope(route,doc)
        raw = canonical(envelope)
        existing = db.execute("SELECT raw FROM outbox WHERE id=?",(envelope["sha256"],)).fetchone()
        if existing:
            require(existing[0]==raw,"P0_OUTBOX_CONFLICT")
            return 0
        db.execute("INSERT INTO outbox VALUES (?,?,?,'READY',0,?,NULL)",(envelope["sha256"],route,raw,now))
        return len(raw)

    def deliver(self, now, receiver, *, max_attempts=3, fault=None):
        """Reserve then send one envelope. A lost ACK replays same effect key."""
        require(type(max_attempts) is int and 1<=max_attempts<=8,"P0_ATTEMPT_LIMIT")
        with self.tx() as db:
            self._clock(db,now)
            row = db.execute("SELECT id,raw,attempts,route FROM outbox WHERE state IN ('READY','PENDING') "
                             "AND due<=? ORDER BY due,id LIMIT 1",(now,)).fetchone()
            if not row:
                return "IDLE"
            key,raw,count,route = row
            try:
                doc = json.loads(raw)
                verify(doc,key)
                require(doc["route"]==route,"P0_OUTBOX_ROUTE")
            except (ValueError,KeyError,TypeError):
                db.execute("UPDATE outbox SET state='QUARANTINED' WHERE id=?",(key,))
                return "QUARANTINED"
            if route=="SECRETARY" and now-doc["body"]["cutoff"]>self.plan["lag_ms"]:
                db.execute("UPDATE outbox SET state='EXPIRED' WHERE id=?",(key,))
                return "EXPIRED"
            if count>=max_attempts:
                db.execute("UPDATE outbox SET state='QUARANTINED' WHERE id=?",(key,))
                return "QUARANTINED"
            db.execute("UPDATE outbox SET state='PENDING',attempts=?,due=? WHERE id=?",
                       (count+1,now+1000*2**count,key))
        try:
            ack = receiver(doc)
            if fault:
                fault()
            verify(ack,ack["sha256"])
            require(ack==receipt(doc),"P0_ACK_BINDING")
        except (OSError,sqlite3.OperationalError):
            return "PENDING"
        except (ValueError,KeyError,TypeError):
            with self.tx() as db:
                db.execute("UPDATE outbox SET state='QUARANTINED' WHERE id=? AND state='PENDING' AND attempts=?",
                           (key,count+1))
            return "QUARANTINED"
        with self.tx() as db:
            db.execute("UPDATE outbox SET state='ACKED',ack=? WHERE id=?",(canonical(ack),key))
        return "ACKED_FIXTURE"

    def evidence(self):
        with self.tx() as db:
            next_slot,used = db.execute("SELECT next,bytes FROM meta").fetchone()
            rows = [json.loads(raw) for raw, in db.execute("SELECT raw FROM decisions ORDER BY slot,id")]
            for row in rows:
                verify(row,row["sha256"])
            delivery = dict(db.execute("SELECT state,COUNT(*) FROM outbox GROUP BY state").fetchall())
            routes = dict(db.execute("SELECT route,COUNT(*) FROM outbox GROUP BY route").fetchall())
            batches = [row[0] for row in db.execute("SELECT id FROM batches ORDER BY id")]
        expected = next_slot*len(self.plan["symbols"])*len(self.plan["plugins"])
        return dict(slots=next_slot,expected=expected,census=census(rows,expected),rows=rows,delivery=delivery,
                    routes=routes,native_batches=batches,decision_bytes=used)


def receipt(doc):
    return seal(dict(schema="aql.scanner.p0.fixture-consumer-ack.v1",effect_sha256=doc["sha256"],
                     route=doc["route"],status="PERSISTED_FIXTURE_ONLY",authority="NONE"))


def fixture_receive(db_path, doc):
    """Rehearse independent consumer transaction, not production Secretary/Lab."""
    verify(doc,doc["sha256"])
    body = doc["body"]
    verify(body,body["sha256"])
    route = doc["route"]
    require(doc["schema"]=="aql.scanner.p0.handoff.v1" and doc["scope"]=="TEST_ONLY"
            and doc["authority"]==body["authority"]=="NONE"
            and ROUTES.get(route)==body["schema"],"P0_RECEIVER_SCOPE")
    require((route=="SECRETARY" and body["state"] in ("ENTRY_SIGNAL","EXIT_SIGNAL"))
            or (route=="LAB" and body["mode"]=="MONITOR_ONLY"),"P0_ROUTE_MISMATCH")
    db = sqlite3.connect(db_path,timeout=1)
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS effects (id TEXT PRIMARY KEY, raw BLOB)")
        key,raw = doc["sha256"],canonical(doc)
        db.execute("INSERT OR IGNORE INTO effects VALUES (?,?)",(key,raw))
        require(db.execute("SELECT raw FROM effects WHERE id=?",(key,)).fetchone()[0]==raw,"P0_EFFECT_CONFLICT")
        db.commit()
    finally:
        db.close()
    return receipt(doc)
