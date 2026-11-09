"""Synthetic-only durable link from eligible G1 bar + explicit Scanner opportunity to G2.

Separate append-only SQLite events; no live collector, paper, F5, or original E:.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3
from pathlib import Path

from aql.g1_integrity import content, fingerprint
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.models.bar import MarketBar
from aql.observation.contracts import (
    CONTEXT_KEYS, HORIZONS_MS, ContextValue, DecisionSnapshot, Observation,
    canonical, digest,
)

SCANNER_SCHEMA = "aql.scanner.g1.explicit-opportunity-test-only.v1"
EVENT_SCHEMA = "aql.core.g1-g2.durable-observation.v1"


class BridgeStop(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise BridgeStop(code)


def sha(x):
    return isinstance(x, str) and len(x) == 64 and all(
        c in "0123456789abcdef" for c in x)


class DurableG2Bridge:
    """Owner-independent event DB. Original G1 journal/market store unchanged."""
    def __init__(self, db):
        self.db = Path(db)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        try:
            with con:
                con.execute("""CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY, kind TEXT NOT NULL,
                    identity TEXT NOT NULL, payload TEXT NOT NULL,
                    prev_sha TEXT NOT NULL, event_sha TEXT NOT NULL,
                    UNIQUE(kind, identity))""")
                self._replay(con)
        finally:
            con.close()

    def _connect(self):
        con = sqlite3.connect(self.db, timeout=5)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def _replay(self, con):
        previous = "0" * 64
        snapshots, outcomes = {}, {}
        for seq, kind, identity, raw, parent, seal in con.execute(
            "SELECT seq,kind,identity,payload,prev_sha,event_sha FROM events ORDER BY seq"):
            require(parent == previous, "CHAIN_PARENT")
            data = json.loads(raw)
            require(raw == canonical(data), "NONCANONICAL_RECORD")
            require(digest(dict(seq=seq,kind=kind,identity=identity,
                                payload=data,prev_sha=parent)) == seal, "CHAIN_SHA")
            if kind == "snapshot":
                snap = data["snapshot"]
                require(identity == snap["snapshot_id"] and identity ==
                        digest({k:v for k,v in snap.items() if k!="snapshot_id"}),
                        "SNAPSHOT_SHA")
                require(data["commit_return_ms"] <= snap["decision_ms"] and
                        sha(data["g1_content_sha256"]) and
                        sha(data["scanner_sha256"]), "PARENT_DRIFT")
                require(identity not in snapshots, "DUPLICATE_SNAPSHOT")
                snapshots[identity] = data
            elif kind == "observation":
                require(data["snapshot_id"] in snapshots, "UNKNOWN_PARENT")
                observation = Observation(**data)
                observation.validate(snapshots[data["snapshot_id"]]["snapshot"]["decision_ms"])
                key = (data["snapshot_id"],data["horizon_ms"])
                require(identity == f"{key[0]}:{key[1]}" and key not in outcomes,
                        "DUPLICATE_OBSERVATION")
                outcomes[key] = data
            else:
                raise BridgeStop("INVALID_KIND")
            previous = seal
        return snapshots, outcomes, previous

    def _append(self, con, kind, identity, data, previous):
        seq = con.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events").fetchone()[0]
        seal = digest(dict(seq=seq,kind=kind,identity=identity,
                           payload=data,prev_sha=previous))
        con.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                    (seq,kind,identity,canonical(data),previous,seal))
        return seal

    def accept(self, journal, store, bar, opportunity, *, now_ms):
        """Explicit Scanner event required; no auto-opportunity per candle."""
        require(isinstance(journal,DurableJournal) and
                isinstance(store,OperationalStore) and
                isinstance(bar,MarketBar), "G1_TYPES")
        o = opportunity
        require(type(o) is dict and o.get("schema")==SCANNER_SCHEMA and
                o.get("policy")=="TEST_ONLY" and o.get("decision")=="OPPORTUNITY"
                and o.get("authority")=="NONE" and
                o.get("origin")=="SCANNER_EXPLICIT", "SCANNER_AUTHORITY")
        required = ("strategy_definition_sha256","strategy_config_sha256",
                    "scanner_policy_sha256","decision_receipt_sha256")
        require(all(sha(o.get(k)) for k in required) and sha(o.get("sha256"))
                and o["sha256"]==digest({k:v for k,v in o.items() if k!="sha256"}),
                "SCANNER_SHA")
        require(type(o.get("opportunity_key")) is str and o["opportunity_key"]
                and type(now_ms) is int and
                all(type(o.get(k)) is int for k in
                    ("decision_ms","bar_available_ms","bar_close_ms")),
                "TIME_OR_ID")
        require(bar.is_final is True and bar.source=="binance_ws" and
                bar.checksum==bar.compute_checksum() and
                o.get("bar_key")==bar.stable_key() and
                o.get("bar_checksum")==bar.checksum and
                o.get("symbol")==bar.symbol and o.get("interval")==bar.interval and
                o["bar_close_ms"]==bar.bar_close, "NONFINAL_OR_PARENT")
        journal.require_eligible(bar.stable_key())
        store.require_eligible(bar.stable_key())
        receipt=journal.commit_receipt(bar.stable_key())
        require(receipt.get("status")=="SQLITE_COMMIT_RETURN_OBSERVED" and
                receipt.get("version")==1 and
                receipt.get("content_digest")==fingerprint(content(bar)), "NO_G1_COMMIT_RECEIPT")
        committed=receipt["commit_return_observed_at_ms"]
        require(bar.bar_close<=bar.ingested_at<=committed<=o["bar_available_ms"]
                <=o["decision_ms"]<=now_ms and
                o["decision_ms"]-committed<=5000, "FUTURE_OR_STALE_CLOCK")
        # OperationalStore.get_range returns (min_open,max_open), not bar rows.
        # Reuse its existing exact stable-key readback under read-only query.
        store_con=store._connect()
        try:
            stored=store._original_bar(store_con,bar.stable_key())
        finally:
            store_con.close()
        require(stored is not None and stored.is_final is True and
                stored.checksum==bar.checksum and
                stored.compute_checksum()==bar.checksum, "G1_STORE_DRIFT")
        context={k:ContextValue(None,None,None,None,"NOT_SUPPLIED_TEST_ONLY")
                 for k in CONTEXT_KEYS}
        snap=DecisionSnapshot(opportunity_key=o["opportunity_key"],source=SCANNER_SCHEMA,
             event_ms=bar.bar_close,receipt_ms=committed,
             decision_ms=o["decision_ms"],disposition="observed",
             context=context,freshness_limit_ms=5000)
        data=dict(snapshot=json.loads(snap.serialized()),scanner_sha256=o["sha256"],
                  g1_content_sha256=receipt["content_digest"],
                  bar_key=bar.stable_key(),commit_return_ms=committed,
                  strategy_definition_sha256=o[required[0]],
                  strategy_config_sha256=o[required[1]],
                  scanner_policy_sha256=o[required[2]],
                  decision_receipt_sha256=o[required[3]],
                  horizons_ms=list(HORIZONS_MS),trading_authority="NONE")
        con=self._connect()
        try:
            with con:
                snapshots, _, tail=self._replay(con)
                matching=[v for v in snapshots.values()
                          if v["snapshot"]["opportunity_key"]==o["opportunity_key"]]
                if matching:
                    require(len(matching)==1 and matching[0]==data,
                            "OPPORTUNITY_CONFLICT")
                    return snap.snapshot_id,"REPLAY_IDENTICAL"
                self._append(con,"snapshot",snap.snapshot_id,data,tail)
            return snap.snapshot_id,"STORED_DURABLE"
        finally:
            con.close()

    def observe(self, snapshot_id, horizon_ms, *, observed_ms, received_ms,
                source, evidence_id, value=None, missing_reason=None):
        require(sha(snapshot_id) and horizon_ms in HORIZONS_MS,"OBSERVATION_SCOPE")
        obs=Observation(snapshot_id,horizon_ms,observed_ms,received_ms,
                        source,evidence_id,value,missing_reason)
        con=self._connect()
        try:
            with con:
                snaps, outcomes, tail=self._replay(con)
                require(snapshot_id in snaps,"UNKNOWN_SNAPSHOT")
                obs.validate(snaps[snapshot_id]["snapshot"]["decision_ms"])
                key=(snapshot_id,horizon_ms)
                body=asdict(obs)
                if key in outcomes:
                    require(outcomes[key]==body,"OBSERVATION_CONFLICT")
                    return "REPLAY_IDENTICAL"
                self._append(con,"observation",f"{snapshot_id}:{horizon_ms}",body,tail)
            return "STORED_DURABLE"
        finally:
            con.close()

    def horizon_state(self, snapshot_id, horizon_ms, as_of_ms):
        require(type(as_of_ms) is int, "INVALID_TIME")
        con=self._connect()
        try:
            snaps, outcomes, _=self._replay(con)
        finally:
            con.close()
        require(snapshot_id in snaps and horizon_ms in HORIZONS_MS,"UNKNOWN_SCOPE")
        o=outcomes.get((snapshot_id,horizon_ms))
        if o is None or o["received_ms"]>as_of_ms:
            return "pending"
        return "missing" if o["value"] is None else "mature"

    def readback(self):
        con=self._connect()
        try:
            snaps, obs, tail=self._replay(con)
        finally:
            con.close()
        return dict(schema=EVENT_SCHEMA,snapshots=len(snaps),observations=len(obs),
                    tail_sha256=tail,trading_authority="NONE")
