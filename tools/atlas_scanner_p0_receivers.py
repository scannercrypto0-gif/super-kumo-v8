"""Integration-owned research read-side for pinned Scanner P0 fixture transport."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from tools.scanner_strategy_f.p0_delivery import ROUTES, canonical, receipt
from tools.scanner_strategy_f.p0_slice import STEP, clock, digest, require, seal, verify


STATES = {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL", "UNKNOWN"}
TIMING = {"FIXTURE_ON_TIME", "LATE_RESEARCH_ONLY"}
MONITOR_FIELDS = {
    "schema", "mode", "request_sha256", "decision_sha256", "symbol", "plugin_sha256",
    "strategy_version", "indicator", "parameters", "version", "library_sha256",
    "cutoff", "source_query_sha256", "known_at", "timing", "warmup_bars",
    "availability", "reason", "value", "authority", "sha256",
}
INVALID_MONITOR_FIELDS = {
    "schema", "mode", "authority", "decision_sha256", "availability", "reason", "value", "sha256",
}


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


class ResearchReceivers:
    """Use the Scanner outbox unchanged and separate local, bounded receiver custody."""

    def __init__(self, root, scanner, plan_pin):
        self.root = Path(root).absolute()
        for path in (self.root, *self.root.parents):
            require(not path.is_symlink()
                    and not (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400),
                    "RECEIVER_REPARSE")
        self.scanner = scanner
        self.plan = scanner.plan
        verify(self.plan, plan_pin)
        require(self.plan["scope"] == "TEST_ONLY" and self.plan["authority"] == "NONE", "RECEIVER_SCOPE")
        marker = self.root / "receiver-plan"
        if not self.root.exists():
            self.root.mkdir()
            marker.write_text(plan_pin, encoding="ascii")
        require(marker.is_file() and not marker.is_symlink()
                and marker.read_text(encoding="ascii") == plan_pin, "RECEIVER_UNOWNED")

    def _decision(self, row):
        verify(row, row["sha256"])
        require(row["schema"] == ROUTES["SECRETARY"] and row["authority"] == "NONE"
                and row["known_at"] is None and row["state"] in STATES and row["timing"] in TIMING,
                "RECEIVER_DECISION_SCOPE")
        slot = clock(row["slot"])
        delta = slot - self.plan["origin"]
        require(row["plan_sha256"] == self.plan["sha256"] and row["plugin_sha256"] in self.plan["plugins"]
                and row["symbol"] in self.plan["symbols"] and self.plan["sources"][row["symbol"]] == row["source_sha256"]
                and row["cutoff"] == slot + STEP and delta % STEP == 0
                and 0 <= delta // STEP < self.plan["slots"]
                and row["id"] == digest([self.plan["sha256"], row["symbol"], row["plugin_sha256"], slot]),
                "RECEIVER_FROZEN_IDENTITY")
        return row

    def _monitor(self, body, parent):
        require(body["mode"] == "MONITOR_ONLY" and body["decision_sha256"] == parent["sha256"],
                "RECEIVER_MONITOR_SCOPE")
        if set(body) == INVALID_MONITOR_FIELDS:
            require(body["availability"] == "UNKNOWN" and body["reason"] == "INVALID_MONITOR_REQUEST"
                    and body["value"] is None, "RECEIVER_MONITOR_UNKNOWN")
            return
        require(set(body) == MONITOR_FIELDS and body["known_at"] is None
                and all(sha(body[field]) for field in ("request_sha256", "library_sha256"))
                and all(body[field] == parent[field] for field in
                        ("symbol", "plugin_sha256", "strategy_version", "cutoff", "timing"))
                and (body["source_query_sha256"] is None
                     or body["source_query_sha256"] == parent["source_query_sha256"])
                and isinstance(body["version"], str) and bool(body["version"])
                and isinstance(body["indicator"], str) and bool(body["indicator"])
                and isinstance(body["parameters"], dict), "RECEIVER_MONITOR_PROVENANCE")
        require((body["availability"] == "UNKNOWN" and body["value"] is None and bool(body["reason"]))
                or (body["availability"] == "AVAILABLE" and isinstance(body["value"], dict)
                    and body["reason"] is None and sha(body["source_query_sha256"])),
                "RECEIVER_MONITOR_AVAILABILITY")

    def _persist(self, route, key, body, disposition):
        proof = seal(dict(schema="aql.integration.scanner-p0.receiver-receipt.v1", route=route,
                          effect_sha256=key, body_sha256=body["sha256"], disposition=disposition,
                          scope="TEST_ONLY", authority="NONE"))
        payload, raw = canonical(body), canonical(proof)
        path = self.root / (route.lower() + ".sqlite")
        require(not path.is_symlink()
                and not (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400),
                "RECEIVER_REPARSE")
        with closing(sqlite3.connect(path, timeout=1)) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS receiver_meta (id INTEGER PRIMARY KEY, pin TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO receiver_meta VALUES (1,?)", (self.plan["sha256"],))
            require(db.execute("SELECT pin FROM receiver_meta WHERE id=1").fetchone() == (self.plan["sha256"],),
                    "RECEIVER_PLAN_DRIFT")
            db.execute("CREATE TABLE IF NOT EXISTS effects (id TEXT PRIMARY KEY, body BLOB, receipt BLOB)")
            saved = db.execute("SELECT body,receipt FROM effects WHERE id=?", (key,)).fetchone()
            if saved is None:
                used = db.execute("SELECT COALESCE(SUM(length(body)+length(receipt)),0) FROM effects").fetchone()[0]
                require(used + len(payload) + len(raw) <= self.plan["max_bytes"], "RECEIVER_BACKPRESSURE")
                db.execute("INSERT INTO effects VALUES (?,?,?)", (key, payload, raw))
            else:
                require(saved == (payload, raw), "RECEIVER_EFFECT_CONFLICT")
            db.commit()
        return proof

    def _source(self):
        return closing(sqlite3.connect(self.scanner.path.resolve().as_uri() + "?mode=ro", uri=True))

    def receive(self, doc, now):
        verify(doc, doc["sha256"])
        route, body = doc["route"], doc["body"]
        verify(body, body["sha256"])
        require(set(doc) == {"schema", "route", "body", "scope", "authority", "sha256"}
                and doc["schema"] == "aql.scanner.p0.handoff.v1" and doc["scope"] == "TEST_ONLY"
                and doc["authority"] == body["authority"] == "NONE" and ROUTES.get(route) == body["schema"],
                "RECEIVER_ENVELOPE_SCOPE")
        # Bind to the pinned Scanner's persisted outbox and decision, not a caller's self-sealed claim.
        with self._source() as db:
            saved = db.execute("SELECT raw,state FROM outbox WHERE id=? AND route=?",
                               (doc["sha256"], route)).fetchone()
            require(saved is not None and saved[0] == canonical(doc) and saved[1] in ("PENDING", "ACKED"),
                    "RECEIVER_UNBOUND_OUTBOX")
            if route == "SECRETARY":
                row = db.execute("SELECT raw FROM decisions WHERE id=?", (body["id"],)).fetchone()
            else:
                rows = db.execute("SELECT raw FROM decisions WHERE json_extract(raw,'$.sha256')=? LIMIT 2",
                                  (body["decision_sha256"],)).fetchall()
                row = rows[0] if len(rows) == 1 else None
        require(row is not None, "RECEIVER_UNBOUND_DECISION")
        parent = self._decision(json.loads(row[0]))
        if route == "SECRETARY":
            require(parent == body and body["state"] in ("ENTRY_SIGNAL", "EXIT_SIGNAL")
                    and body["timing"] == "FIXTURE_ON_TIME"
                    and 0 <= clock(now) - body["cutoff"] <= self.plan["lag_ms"], "RECEIVER_EXPIRED_OR_NOT_SIGNAL")
        else:
            self._monitor(body, parent)
            require(clock(now) >= parent["cutoff"], "RECEIVER_MONITOR_FUTURE")
        self._persist(route, doc["sha256"], body, "RESEARCH_ONLY" if route == "SECRETARY" else "MONITOR_ONLY")
        return receipt(doc)  # Exact pinned wire ACK, emitted only after independent COMMIT.

    def record_census(self):
        """Read-side for all immutable decisions, including events Scanner never dispatches."""
        with self._source() as db:
            rows = [json.loads(raw) for raw, in db.execute("SELECT raw FROM decisions ORDER BY slot,id")]
            expired = {
                json.loads(raw)["body"]["sha256"]
                for raw, in db.execute("SELECT raw FROM outbox WHERE route='SECRETARY' AND state='EXPIRED'")
            }
        proofs = []
        for row in rows:
            row = self._decision(row)
            proofs.append(self._persist("SECRETARY", digest(["CENSUS", row["id"]]), row, "RESEARCH_CENSUS"))
            if row["sha256"] in expired or row["timing"] == "LATE_RESEARCH_ONLY":
                proofs.append(self._persist("SECRETARY", digest(["EXPIRY", row["id"]]), row, "EXPIRED_RESEARCH_ONLY"))
        return proofs
