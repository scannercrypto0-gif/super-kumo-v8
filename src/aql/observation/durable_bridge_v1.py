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

SCANNER_SCHEMA = "aql.scanner.g1-g2.test-only-opportunity.v1"
DECISION_SCHEMA = "aql.scanner.g1-g2.explicit-test-decision.v1"
SCANNER_FIELDS = frozenset(("schema","opportunity_key","symbol","interval","source",
    "source_bar_open_ms","source_bar_close_ms","bar_checksum","g1_stable_key",
    "g1_content_digest","g1_receipt_sha256","g1_receipt_ms",
    "decision_cutoff_ms","decision_ms","strategy_id","strategy_version",
    "strategy_definition_sha256","strategy_config_sha256",
    "strategy_evaluator_sha256","strategy_decision_sha256","decision_state",
    "policy_sha256","source_availability","test_only","historical_pit",
    "source_ack_sha256","strategy_approval_sha256","factory_consumer_ack_sha256",
    "trading_authority","orders_enabled","sha256"))
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
        require(type(o) is dict and set(o) == SCANNER_FIELDS and
                o.get("schema") == SCANNER_SCHEMA and
                o.get("test_only") is True and
                o.get("decision_state") in ("ENTRY_SIGNAL", "EXIT_SIGNAL") and
                o.get("source") == "binance_ws" and
                o.get("source_availability") ==
                    "G1_COMMIT_RECEIPT_OBSERVED_TEST_ONLY" and
                o.get("historical_pit") == "NOT_ATTESTED" and
                o.get("trading_authority") == "NONE" and
                o.get("orders_enabled") is False and
                all(o.get(k) is None for k in ("source_ack_sha256",
                    "strategy_approval_sha256", "factory_consumer_ack_sha256")),
                "SCANNER_AUTHORITY_OR_SCHEMA")
        hash_fields = ("opportunity_key", "bar_checksum", "g1_content_digest",
            "g1_receipt_sha256", "strategy_definition_sha256",
            "strategy_config_sha256", "strategy_evaluator_sha256",
            "strategy_decision_sha256", "policy_sha256", "sha256")
        require(all(sha(o.get(k)) for k in hash_fields) and
                o["sha256"] == digest({k:v for k,v in o.items()
                                      if k != "sha256"}), "SCANNER_SHA")
        require(all(type(o.get(k)) is int and o[k] >= 0 for k in (
                "source_bar_open_ms","source_bar_close_ms","g1_receipt_ms",
                "decision_cutoff_ms","decision_ms")) and
                o["decision_ms"] == o["decision_cutoff_ms"] and
                all(type(o.get(k)) is str and bool(o[k]) for k in (
                "strategy_id","strategy_version","symbol","interval",
                "g1_stable_key")), "SCANNER_TIME_OR_ID")
        key_material = dict(schema=SCANNER_SCHEMA,
            g1_stable_key=o["g1_stable_key"], strategy_id=o["strategy_id"],
            strategy_version=o["strategy_version"],
            strategy_definition_sha256=o["strategy_definition_sha256"],
            strategy_config_sha256=o["strategy_config_sha256"],
            strategy_evaluator_sha256=o["strategy_evaluator_sha256"],
            policy_sha256=o["policy_sha256"])
        require(o["opportunity_key"] == digest(key_material), "SCANNER_OPPORTUNITY_KEY")
        decision_material = dict(schema=DECISION_SCHEMA,
            strategy_id=o["strategy_id"],strategy_version=o["strategy_version"],
            strategy_definition_sha256=o["strategy_definition_sha256"],
            strategy_config_sha256=o["strategy_config_sha256"],
            strategy_evaluator_sha256=o["strategy_evaluator_sha256"],
            symbol=o["symbol"],interval=o["interval"],
            bar_close_ms=o["source_bar_close_ms"],
            decision_cutoff_ms=o["decision_cutoff_ms"],
            decision_state=o["decision_state"],test_only=True)
        require(o["strategy_decision_sha256"] == digest(decision_material),
                "SCANNER_DECISION_LINK")
        require(bar.is_final is True and bar.source == "binance_ws" and
                bar.checksum == bar.compute_checksum() and
                o["g1_stable_key"] == bar.stable_key() and
                o["bar_checksum"] == bar.checksum and
                o["symbol"] == bar.symbol and o["interval"] == bar.interval and
                o["source_bar_open_ms"] == bar.bar_open and
                o["source_bar_close_ms"] == bar.bar_close, "NONFINAL_OR_PARENT")
        journal.require_eligible(bar.stable_key())
        store.require_eligible(bar.stable_key())
        receipt=journal.commit_receipt(bar.stable_key())
        require(receipt.get("status")=="SQLITE_COMMIT_RETURN_OBSERVED" and
                receipt.get("version")==1 and
                receipt.get("content_digest")==fingerprint(content(bar)), "NO_G1_COMMIT_RECEIPT")
        committed=receipt["commit_return_observed_at_ms"]
        require(o["g1_content_digest"] == receipt["content_digest"] and
                o["g1_receipt_sha256"] == digest(receipt) and
                o["g1_receipt_ms"] == committed, "SCANNER_G1_RECEIPT_DRIFT")
        require(bar.bar_close < bar.ingested_at <= committed <=
                o["decision_ms"] <= now_ms and
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
                  strategy_definition_sha256=o["strategy_definition_sha256"],
                  strategy_config_sha256=o["strategy_config_sha256"],
                  scanner_policy_sha256=o["policy_sha256"],
                  decision_receipt_sha256=o["strategy_decision_sha256"],
                  scanner_evaluator_sha256=o["strategy_evaluator_sha256"],
                  scanner_g1_receipt_sha256=o["g1_receipt_sha256"],
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

    def _connect_readonly(self):
        """Read an existing G2 WAL DB without migration, checkpoint or writes."""
        from urllib.parse import quote
        require(self.db.is_file(), "G2_SOURCE_MISSING")
        uri = "file:" + quote(str(self.db.resolve()).replace("\\\\", "/"), safe="/:") + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            con.execute("PRAGMA query_only=ON")
            return con
        except Exception:
            con.close()
            raise

    def read_verified_opportunity(self, snapshot_id, *, as_of_ms):
        """Pure read-only, fully replay-verified per-opportunity G2 snapshot + horizons.

        UNKNOWN after a due horizon with no eligible evidence is not an invented
        missing/mature observation. Receipt time controls visibility.
        """
        require(sha(snapshot_id) and type(as_of_ms) is int and as_of_ms >= 0,
                "READ_SCOPE")
        con = self._connect_readonly()
        try:
            snaps, outcomes, tail = self._replay(con)
        finally:
            con.close()
        require(snapshot_id in snaps, "READ_SNAPSHOT_NOT_FOUND")
        parent = snaps[snapshot_id]
        snap = parent["snapshot"]
        require(as_of_ms >= snap["decision_ms"], "READ_BEFORE_DECISION")
        require(parent["horizons_ms"] == list(HORIZONS_MS) and
                parent["trading_authority"] == "NONE" and
                sha(parent["scanner_sha256"]) and
                sha(parent["scanner_g1_receipt_sha256"]) and
                sha(parent["decision_receipt_sha256"]) and
                sha(parent["scanner_policy_sha256"]) and
                sha(parent["strategy_definition_sha256"]) and
                sha(parent["strategy_config_sha256"]) and
                sha(parent["scanner_evaluator_sha256"]) and
                sha(parent["g1_content_sha256"]) and
                parent["commit_return_ms"] == snap["receipt_ms"],
                "READ_PARENT_DRIFT")
        horizons = []
        for h in HORIZONS_MS:
            event = outcomes.get((snapshot_id, h))
            due = snap["decision_ms"] + h
            if event is not None and event["received_ms"] <= as_of_ms:
                state = "missing" if event["value"] is None else "mature"
                visible = dict(event)
            else:
                state = "pending" if as_of_ms < due else "UNKNOWN"
                visible = None
            horizons.append(dict(
                horizon_ms=h, identity=f"{snapshot_id}:{h}",
                due_ms=due, state=state, observation=visible))
        doc = dict(schema="aql.core.g1-g2.verified-opportunity-read.v1",
                   snapshot_id=snapshot_id, snapshot=dict(snap),
                   g1_content_sha256=parent["g1_content_sha256"],
                   g1_receipt_sha256=parent["scanner_g1_receipt_sha256"],
                   scanner_opportunity_sha256=parent["scanner_sha256"],
                   scanner_decision_sha256=parent["decision_receipt_sha256"],
                   scanner_policy_sha256=parent["scanner_policy_sha256"],
                   strategy_definition_sha256=parent["strategy_definition_sha256"],
                   strategy_config_sha256=parent["strategy_config_sha256"],
                   scanner_evaluator_sha256=parent["scanner_evaluator_sha256"],
                   commit_return_ms=parent["commit_return_ms"],
                   as_of_ms=as_of_ms, horizons=horizons,
                   event_chain_tail_sha256=tail, test_only=True,
                   historical_pit="NOT_ATTESTED",
                   trading_authority="NONE", orders_enabled=False)
        return {**doc, "sha256": digest(doc)}

    def readback(self):
        con=self._connect()
        try:
            snaps, obs, tail=self._replay(con)
        finally:
            con.close()
        return dict(schema=EVENT_SCHEMA,snapshots=len(snaps),observations=len(obs),
                    tail_sha256=tail,trading_authority="NONE")
