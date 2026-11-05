"""ATLAS D canonical Scanner Frozen → Core durable strategy Secretary (TEST ONLY).

A separate Core-D SQLite outbox binds the *actual*, independently validated
Scanner C strategy approval/request SHA parents to Core D same-source evidence.
It never rewrites the legacy Core C provisional approval schema and never
equates source ACK, explicit engineering StrategyApproval, or Factory ACK.
"""
from __future__ import annotations

import json
import re

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import _connect
from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import _sha, _check, _verify_source_ack
from research_wp_r0.aql_core_d_same_source_route_v1 import verify_scanner_d_for_core_route

SCHEMA="aql.core.d.canonical-strategy-secretary.v1"
ACK_SCHEMA="aql.factory.d.canonical-strategy-consumer-ack.v1"
EVENT_SCHEMA="aql.core.d.canonical-strategy-event.v1"
RECEIPT_SCHEMA="aql.core.d.canonical-strategy-secretary-snapshot.v1"
ID=re.compile(r"^[A-Za-z0-9_.:+-]{1,160}$")


def _create(con):
    con.executescript("""
       CREATE TABLE IF NOT EXISTS d_canonical_strategy_routes (
           route_id TEXT PRIMARY KEY, gate_sha TEXT NOT NULL UNIQUE,
           gate_json TEXT NOT NULL, source_ack_sha TEXT NOT NULL,
           source_ack_json TEXT NOT NULL, state TEXT NOT NULL,
           consumer_ack_sha TEXT, consumer_ack_json TEXT,
           expires_at_ms INTEGER NOT NULL, attempts INTEGER NOT NULL,
           next_retry_ms INTEGER NOT NULL
       );
       CREATE TABLE IF NOT EXISTS d_canonical_strategy_events (
           seq INTEGER PRIMARY KEY AUTOINCREMENT, route_id TEXT NOT NULL,
           event_json TEXT NOT NULL, event_sha TEXT NOT NULL
       );
       CREATE INDEX IF NOT EXISTS idx_d_canonical_events
           ON d_canonical_strategy_events(route_id,seq);
    """)


def _tail(con,route_id):
    rows=con.execute("SELECT event_json,event_sha FROM d_canonical_strategy_events "
                     "WHERE route_id=? ORDER BY seq",(route_id,)).fetchall()
    _check(0<len(rows)<=256,"D_EVENT_CHAIN_REQUIRED")
    prev=None
    for txt,sha in rows:
        event=json.loads(txt)
        _check(event.get("schema")==EVENT_SCHEMA
               and event.get("route_id")==route_id
               and event.get("previous_event_sha256")==prev
               and digest(event)==sha,"D_EVENT_CHAIN_TAMPER")
        prev=sha
    return [json.loads(x[0]) for x in rows]


def _event(con,route_id,*,state,gate_sha,source_sha,consumer_sha,reason,attempts):
    last=con.execute("SELECT event_sha FROM d_canonical_strategy_events "
                     "WHERE route_id=? ORDER BY seq DESC LIMIT 1",
                     (route_id,)).fetchone()
    body={"schema":EVENT_SCHEMA,"route_id":route_id,
          "gate_sha256":gate_sha,"source_ack_sha256":source_sha,
          "consumer_ack_sha256":consumer_sha,
          "state":state,"attempts":attempts,"reason":reason,
          "previous_event_sha256":last[0] if last else None}
    con.execute("INSERT INTO d_canonical_strategy_events(route_id,event_json,event_sha) "
                "VALUES(?,?,?)",(route_id,json.dumps(body,sort_keys=True),digest(body)))


def _verified(con,route_id):
    row=con.execute("SELECT gate_sha,gate_json,source_ack_sha,source_ack_json,"
                    "state,consumer_ack_sha,consumer_ack_json,expires_at_ms,"
                    "attempts,next_retry_ms FROM d_canonical_strategy_routes "
                    "WHERE route_id=?",(route_id,)).fetchone()
    _check(row is not None,"D_ROUTE_NOT_FOUND")
    gate=json.loads(row[1])
    _sha(gate,"gate_sha256")
    _check(gate["schema"]=="aql.core.d.same-source-strategy-route-gate.v1"
           and gate["decision"]=="RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY"
           and gate["nomination_status"]=="SELECTED"
           and gate["scanner_c_governance_action"]=="APPROVE_TEST_ONLY"
           and gate["scanner_c_scope"]=="SYNTHETIC_OFFLINE_ENGINEERING_ONLY"
           and gate["historical_pit"]=="NOT_ATTESTED"
           and gate["historical_known_at_ms"] is None
           and gate["trading_authority"]=="NONE"
           and gate["gate_sha256"]==row[0]
           and row[2]==gate["source_ack_sha256"],"D_CANONICAL_GATE_SCOPE_DRIFT")
    source=json.loads(row[3])
    _verify_source_ack(con,{
        "source_ack_sha256":gate["source_ack_sha256"],
        "strategy_id":gate["strategy_id"],
        "strategy_version":gate["strategy_version"],
        "source_zip_sha256":gate["source_zip_sha256"],
        "manifest_integrity_sha256":gate["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":gate["warehouse_receipt_sha256"],
        "scanner_nomination_sha256":source["source_nomination_sha256"],
    },source["receipt"])
    _check(source["receipt"]["receipt_sha256"]==row[2]
           and source["scanner_c_nomination_sha256"]==
               gate["scanner_c_nomination_sha256"]
           and source["scanner_c_approval_sha256"]==
               gate["scanner_c_approval_sha256"]
           and source["scanner_d_handoff_sha256"]==
               gate["scanner_d_handoff_sha256"]
           and source["core_d_witness_sha256"]==
               gate["core_d_witness_sha256"],"D_SOURCE_ACK_BINDING_DRIFT")
    ack=json.loads(row[6]) if row[6] else None
    if ack is not None:
        _sha(ack,"consumer_ack_sha256")
        _check(ack["consumer_ack_sha256"]==row[5]
               and ack["schema"]==ACK_SCHEMA
               and ack["strategy_gate_sha256"]==row[0]
               and ack["source_ack_sha256"]==row[2]
               and ack["scanner_c_approval_sha256"]==
                   gate["scanner_c_approval_sha256"]
               and ack["trading_authority"]=="NONE"\n           and ack.get("paper_authority")=="NONE"\n           and ack.get("orders_created")==0\n           and ack.get("paper_positions")==0\n           and ack.get("actual_fills") is None\n           and ack.get("route_id")==route_id\n           and ack.get("decision")=="ACCEPTED_TEST_ONLY_RESEARCH"\n           and ack.get("strategy_id")==gate["strategy_id"]\n           and ack.get("strategy_version")==gate["strategy_version"]\n           and ack.get("config_digest")==gate["config_digest"]\n           and ack.get("source_zip_sha256")==gate["source_zip_sha256"]\n           and ack.get("core_245_price_query_sha256")==gate["core_245_price_query_sha256"]\n           and ack.get("core_253_query_local_sha256")==gate["core_253_query_local_sha256"]\n           and ack.get("cutoff_ms")==gate["cutoff_ms"]\n           and type(ack.get("accepted_at_ms")) is int\n           and gate["cutoff_ms"]<=ack["accepted_at_ms"]<row[7],
               "D_CONSUMER_ACK_PARENT_DRIFT")
    trace=_tail(con,route_id)
    _check(trace[-1]["state"]==row[4]
           and trace[-1]["gate_sha256"]==row[0]
           and trace[-1]["source_ack_sha256"]==row[2]
           and trace[-1]["consumer_ack_sha256"]==row[5]
           and trace[-1]["attempts"]==row[8],
           "D_EVENT_TAIL_PARENT_DRIFT")
    return row,gate,ack,trace


def _snapshot(root,route_id,*,now_ms):
    con=_connect(root)
    try:
        _create(con)
        row,gate,ack,trace=_verified(con,route_id)
        state=row[4]
        if now_ms>=row[7]:
            state="EXPIRED" if state!="QUARANTINED" else "QUARANTINED"
        body={
            "schema":RECEIPT_SCHEMA,"route_id":route_id,
            "state":state,"gate_sha256":gate["gate_sha256"],
            "scanner_c_approval_sha256":gate["scanner_c_approval_sha256"],
            "scanner_c_nomination_sha256":gate["scanner_c_nomination_sha256"],
            "scanner_d_handoff_sha256":gate["scanner_d_handoff_sha256"],
            "core_d_witness_sha256":gate["core_d_witness_sha256"],
            "source_ack_sha256":row[2],
            "consumer_ack_sha256":row[5],
            "source_ack_is_strategy_approval":False,
            "strategy_id":gate["strategy_id"],
            "strategy_version":gate["strategy_version"],
            "config_digest":gate["config_digest"],
            "strategy_definition_digest":gate["strategy_definition_digest"],
            "source_zip_sha256":gate["source_zip_sha256"],
            "core_245_price_query_sha256":gate["core_245_price_query_sha256"],
            "core_253_query_local_sha256":gate["core_253_query_local_sha256"],
            "cutoff_ms":gate["cutoff_ms"],
            "symbol":gate["symbol"],"timeframe":"15m",
            "event_tail_sha256":digest(trace[-1]),
            "route_ready_for_factory_test_only":state=="ACKED_CONSUMER",
            "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
            "paper_execution":"NOT_ACTIVATED",
            "trading_authority":"NONE",
            "orders_created":0,"paper_positions":0,"actual_fills":None,
        }
        return {**body,"route_receipt_sha256":digest(body)}
    finally:con.close()


def enqueue_scanner_d_strategy(root,*,gate,source_ack,source_nomination_sha256,
                              route_id,now_ms,expires_at_ms):
    """No enqueue without separately validated canonical Scanner and source ACK.

    The gate must be produced by verify_scanner_d_for_core_route for the same
    pinned Core + Scanner receipts; this API never mints strategy approval.
    """
    _sha(gate,"gate_sha256")
    _check(gate["schema"]=="aql.core.d.same-source-strategy-route-gate.v1"
           and gate["decision"]=="RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY"
           and gate["nomination_status"]=="SELECTED"
           and gate["scanner_c_governance_action"]=="APPROVE_TEST_ONLY"
           and gate["scanner_c_scope"]=="SYNTHETIC_OFFLINE_ENGINEERING_ONLY"
           and gate["trading_authority"]=="NONE"
           and gate["historical_pit"]=="NOT_ATTESTED"
           and type(route_id) is str and ID.fullmatch(route_id)
           and type(now_ms) is int and type(expires_at_ms) is int
           and gate["cutoff_ms"]<=now_ms<expires_at_ms
           and expires_at_ms-now_ms<=600_000,
           "D_GATE_ENQUEUE_POLICY_OR_EXPIRY")
    _check(type(source_nomination_sha256) is str
           and len(source_nomination_sha256)==64
           and gate["source_ack_sha256"]==source_ack["receipt_sha256"],
           "D_SOURCE_ACK_NOT_STRATEGY_APPROVAL")
    source={
        "receipt":source_ack,
        "source_nomination_sha256":source_nomination_sha256,
        "scanner_c_nomination_sha256":gate["scanner_c_nomination_sha256"],
        "scanner_c_approval_sha256":gate["scanner_c_approval_sha256"],
        "scanner_d_handoff_sha256":gate["scanner_d_handoff_sha256"],
        "core_d_witness_sha256":gate["core_d_witness_sha256"],
    }
    con=_connect(root)
    try:
        _create(con)
        con.execute("BEGIN IMMEDIATE")
        _verify_source_ack(con,{
            "source_ack_sha256":source_ack["receipt_sha256"],
            "strategy_id":gate["strategy_id"],
            "strategy_version":gate["strategy_version"],
            "source_zip_sha256":gate["source_zip_sha256"],
            "manifest_integrity_sha256":gate["manifest_integrity_sha256"],
            "warehouse_receipt_sha256":gate["warehouse_receipt_sha256"],
            "scanner_nomination_sha256":source_nomination_sha256,
        },source_ack)
        old=con.execute("SELECT route_id FROM d_canonical_strategy_routes WHERE gate_sha=?",
                        (gate["gate_sha256"],)).fetchone()
        _check(old is None or old[0]==route_id,"D_DUPLICATE_GATE_DIFFERENT_ROUTE")
        prior=con.execute("SELECT gate_sha,source_ack_sha,expires_at_ms "
                          "FROM d_canonical_strategy_routes WHERE route_id=?",
                          (route_id,)).fetchone()
        _check(prior is None or prior==(gate["gate_sha256"],
                 source_ack["receipt_sha256"],expires_at_ms),
               "D_ROUTE_IDEMPOTENCY_CONFLICT")
        if prior is None:
            con.execute("INSERT INTO d_canonical_strategy_routes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (route_id,gate["gate_sha256"],json.dumps(gate,sort_keys=True),
                         source_ack["receipt_sha256"],json.dumps(source,sort_keys=True),
                         "PENDING_CONSUMER",None,None,expires_at_ms,0,0))
            _event(con,route_id,state="PENDING_CONSUMER",
                   gate_sha=gate["gate_sha256"],source_sha=source_ack["receipt_sha256"],
                   consumer_sha=None,reason="EXPLICIT_SCANNER_TEST_ONLY_APPROVAL",
                   attempts=0)
        else:_verified(con,route_id)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:con.close()
    return _snapshot(root,route_id,now_ms=now_ms)


def ack_scanner_d_strategy_consumer(root,route_id,consumer_ack,*,now_ms):
    """Only genuine caller-supplied Factory TEST_ONLY consumer ACK changes state."""
    _sha(consumer_ack,"consumer_ack_sha256")
    con=_connect(root)
    try:
        _create(con)
        con.execute("BEGIN IMMEDIATE")
        row,gate,prior,trace=_verified(con,route_id)
        _check(type(now_ms) is int and now_ms<row[7]
               and row[4] in ("PENDING_CONSUMER","ACKED_CONSUMER"),
               "D_CONSUMER_ACK_EXPIRED_OR_INVALID_STATE")
        a=consumer_ack
        _check(a.get("schema")==ACK_SCHEMA
               and a.get("route_id")==route_id
               and a.get("decision")=="ACCEPTED_TEST_ONLY_RESEARCH"
               and a.get("strategy_gate_sha256")==gate["gate_sha256"]
               and a.get("scanner_c_approval_sha256")==gate["scanner_c_approval_sha256"]
               and a.get("source_ack_sha256")==row[2]
               and a.get("strategy_id")==gate["strategy_id"]
               and a.get("strategy_version")==gate["strategy_version"]
               and a.get("config_digest")==gate["config_digest"]
               and a.get("source_zip_sha256")==gate["source_zip_sha256"]
               and a.get("core_245_price_query_sha256")==gate["core_245_price_query_sha256"]
               and a.get("core_253_query_local_sha256")==gate["core_253_query_local_sha256"]
               and a.get("cutoff_ms")==gate["cutoff_ms"]
               and a.get("trading_authority")=="NONE"
               and a.get("paper_authority")=="NONE"
               and a.get("orders_created")==0 and a.get("paper_positions")==0
               and a.get("actual_fills") is None
               and type(a.get("accepted_at_ms")) is int
               and gate["cutoff_ms"]<=a["accepted_at_ms"]<=now_ms,
               "D_FACTORY_CONSUMER_ACK_PARENT_SCOPE")
        if row[4]=="ACKED_CONSUMER":
            _check(prior==a,"D_CONSUMER_ACK_REPLAY_CONFLICT")
        else:
            con.execute("UPDATE d_canonical_strategy_routes SET state=?,consumer_ack_sha=?,"
                        "consumer_ack_json=? WHERE route_id=?",
                        ("ACKED_CONSUMER",a["consumer_ack_sha256"],
                         json.dumps(a,sort_keys=True),route_id))
            _event(con,route_id,state="ACKED_CONSUMER",gate_sha=gate["gate_sha256"],
                   source_sha=row[2],consumer_sha=a["consumer_ack_sha256"],
                   reason="FACTORY_EXPLICIT_TEST_ONLY_CONSUMER_ACK",attempts=row[8])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:con.close()
    return _snapshot(root,route_id,now_ms=now_ms)


def strategy_d_snapshot(root,route_id,*,now_ms):
    return _snapshot(root,route_id,now_ms=now_ms)
