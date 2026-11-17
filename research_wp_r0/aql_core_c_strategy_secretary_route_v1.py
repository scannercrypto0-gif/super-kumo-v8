"""ATLAS Package C — Core-owned research-only strategy Secretary route (v1).

Separate SOURCE_ACK, STRATEGY_APPROVAL and CONSUMER_ACK.  No source-only
receipt, synthetic scanner SELECTED or historical UNKNOWN creates approval.
This is a durable, restartable SQLite state machine co-located with, but
isolated from, the existing Core #226 source outbox; it never sends an order.
"""
from __future__ import annotations

import json
import re
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import _connect, require
from research_wp_r0.aql_core_dual_query_identity_map_v1 import SCHEMA as MAP_SCHEMA
from research_wp_r0.aql_core_secretary_routing_v1 import _trace as _source_trace

REQUEST_SCHEMA = "aql.core.c.strategy-route-request.v1"
APPROVAL_SCHEMA = "aql.scanner.c.strategy-approval.v1"
POLICY_SCHEMA = "aql.scanner.native15m-policy.v1"
RECEIPT_SCHEMA = "aql.core.c.strategy-secretary-route.v1"
EVENT_SCHEMA = "aql.core.c.strategy-route-event.v1"
SOURCE_ACK_SCHEMA = "aql.core.secretary-offline-ack.v1"
STATES = ("WAIT_APPROVAL", "PENDING_CONSUMER", "RETRY",
          "ACKED_CONSUMER", "QUARANTINED", "EXPIRED")
HEX = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9_.:+-]{1,180}$")


def _check(condition, code):
    require(condition, "CORE_C_"+code)


def _sha(obj, key):
    _check(type(obj) is dict and type(obj.get(key)) is str
           and HEX.fullmatch(obj[key]) is not None,
           "SIGNED_PARENT_REQUIRED")
    _check(digest({k:v for k,v in obj.items() if k!=key})==obj[key],
           "SIGNED_PARENT_TAMPER")


def _identity(row):
    return (row.get("strategy_id"), row.get("strategy_version"),
            row.get("config_digest"))


def _create(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS c_strategy_routes (
        route_id TEXT PRIMARY KEY, request_sha TEXT NOT NULL,
        request_json TEXT NOT NULL, approval_sha TEXT,
        source_ack_json TEXT NOT NULL, consumer_ack_json TEXT,
        policy_sha TEXT NOT NULL, policy_json TEXT NOT NULL,
        approval_json TEXT, source_ack_sha TEXT NOT NULL,
        state TEXT NOT NULL, attempts INTEGER NOT NULL,
        consumer_ack_sha TEXT, next_attempt_ms INTEGER NOT NULL
      );
      CREATE UNIQUE INDEX IF NOT EXISTS idx_c_strategy_unique_request
        ON c_strategy_routes(request_sha);
      CREATE TABLE IF NOT EXISTS c_strategy_events (
        event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
        route_id TEXT NOT NULL, state TEXT NOT NULL,
        event_json TEXT NOT NULL, event_sha TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_c_strategy_events
        ON c_strategy_events(route_id,event_seq);
    """)


def _trace(con, route_id):
    rows=con.execute("SELECT state,event_json,event_sha FROM c_strategy_events "
                     "WHERE route_id=? ORDER BY event_seq",(route_id,)).fetchall()
    _check(bool(rows) and len(rows)<=256,"TRACE_MISSING_OR_TOO_LONG")
    previous=None
    for state,encoded,sha in rows:
        event=json.loads(encoded)
        _check(event.get("state")==state and
               event.get("route_id")==route_id and
               event.get("previous_sha256")==previous and
               digest(event)==sha,"TRACE_TAMPER")
        previous=sha
    current=con.execute("SELECT state,request_sha,approval_sha,"
                        "source_ack_sha,consumer_ack_sha,attempts,policy_sha "
                        "FROM c_strategy_routes WHERE route_id=?",
                        (route_id,)).fetchone()
    _check(current is not None and current[0]==rows[-1][0],"TRACE_STATE_DRIFT")
    tail=json.loads(rows[-1][1])
    _check(tail["request_sha256"]==current[1]
           and tail["policy_receipt_sha256"]==current[6]
           and tail["approval_sha256"]==current[2]
           and tail["source_ack_sha256"]==current[3]
           and tail["consumer_ack_sha256"]==current[4]
           and tail["attempts"]==current[5],"TRACE_PARENT_DRIFT")
    return [json.loads(x[1]) for x in rows]


def _event(con, route_id, state, *, request_sha, policy_sha, approval_sha,
           source_ack_sha, consumer_ack_sha, attempts, reason):
    prev=con.execute("SELECT event_sha FROM c_strategy_events WHERE route_id=? "
                     "ORDER BY event_seq DESC LIMIT 1",(route_id,)).fetchone()
    body={"schema":EVENT_SCHEMA,"route_id":route_id,"state":state,
          "request_sha256":request_sha,"policy_receipt_sha256":policy_sha,
          "approval_sha256":approval_sha,
          "source_ack_sha256":source_ack_sha,
          "consumer_ack_sha256":consumer_ack_sha,"attempts":attempts,
          "reason":reason,"previous_sha256":prev[0] if prev else None}
    con.execute("INSERT INTO c_strategy_events(route_id,state,event_json,event_sha) "
                "VALUES(?,?,?,?)",(route_id,state,json.dumps(body,sort_keys=True,
                separators=(",",":")),digest(body)))


def _verify_policy(policy_receipt,request):
    """Read-only verification of the existing Scanner B native15m TEST_ONLY policy.

    This is a SHA-sealed identity/contract, not a grant of production or
    trading authority. Scanner owns validating the policy against frozen
    Work235 / StrategyDefinition; Core cannot infer that from a source ACK.
    """
    _check(type(policy_receipt) is dict
           and type(policy_receipt.get("payload")) is dict
           and type(policy_receipt.get("sha256")) is str
           and HEX.fullmatch(policy_receipt["sha256"]) is not None,
           "POLICY_RECEIPT_REQUIRED")
    policy=policy_receipt["payload"]
    _check(digest(policy)==policy_receipt["sha256"],
           "POLICY_SEAL_TAMPER")
    _check(policy.get("schema")==POLICY_SCHEMA
           and policy.get("timeframe")=="15m"
           and policy.get("override_is_explicit") is True
           and policy.get("evidence_class")=="TEST_ONLY"
           and policy.get("operational_work235_15m")==
               "NOT_CONNECTED_15M_UNSUPPORTED"
           and policy.get("approved_paper_registry")=="NOT_CONNECTED"
           and policy.get("trading_authority")=="NONE",
           "POLICY_NOT_TEST_ONLY")
    config=policy.get("config_digest")
    _check(type(config) is str and HEX.fullmatch(config) is not None
           and digest({k:v for k,v in policy.items() if k!="config_digest"})==config,
           "POLICY_CONFIG_DIGEST_DRIFT")
    definition=policy.get("definition")
    _check(type(definition) is dict
           and type(definition.get("digest")) is str
           and HEX.fullmatch(definition["digest"]) is not None,
           "POLICY_DEFINITION_REQUIRED")
    _check(request.get("policy_receipt_sha256")==policy_receipt["sha256"]
           and request.get("config_digest")==config
           and request.get("strategy_definition_digest")==definition["digest"]
           and request.get("strategy_id")==policy.get("strategy_id")
           and request.get("strategy_version")==policy.get("strategy_version"),
           "POLICY_REQUEST_IDENTITY_DRIFT")
    return policy


def _verify_source_ack(con, request, source_ack, nomination=None):
    """Validate actual durable Core #226 source ACK, not a resealed dict."""
    _sha(source_ack,"receipt_sha256")
    _check(source_ack.get("schema")==SOURCE_ACK_SCHEMA
           and source_ack.get("state")=="ACKED"
           and source_ack.get("authority")=="OFFLINE_RESEARCH_ONLY"
           and request.get("source_ack_sha256")==source_ack["receipt_sha256"],
           "SOURCE_ACK_SIGNED_PARENT")
    mid=source_ack.get("message_id")
    _check(type(mid) is str and IDENT.fullmatch(mid) is not None,
           "SOURCE_ACK_MESSAGE_ID")
    row=con.execute("SELECT payload_hash,state,ack_sha,delivery_json "
                    "FROM distribution_outbox WHERE message_id=?",
                    (mid,)).fetchone()
    _check(row is not None and row[1]=="ACKED"
           and row[0]==source_ack.get("payload_sha256")
           and row[2]==source_ack.get("acknowledgement_sha256"),
           "SOURCE_ACK_NOT_DURABLE")
    trace=_source_trace(con,mid)
    _check(trace[-1]["state"]=="ACKED"
           and trace[-1]["reason"]==source_ack["acknowledgement_sha256"]
           and trace[-1]["payload_sha256"]==row[0],
           "SOURCE_ACK_TRACE_DRIFT")
    delivery=json.loads(row[3])
    _sha(delivery,"payload_sha256")
    _check(delivery["payload_sha256"]==row[0]
           and delivery.get("schema")=="aql.core.scanner-secretary-offline-route.v1"
           and delivery.get("strategy_id")==request.get("strategy_id")
           and delivery.get("strategy_version")==request.get("strategy_version")
           and delivery.get("source_zip_sha256")==request.get("source_zip_sha256")
           and delivery.get("source_manifest_sha256")==
                request.get("manifest_integrity_sha256")
           and delivery.get("warehouse_receipt_sha256")==
                request.get("warehouse_receipt_sha256")
           and delivery.get("scanner_nomination",{}).get("digest")==
                request.get("scanner_nomination_sha256")
           and delivery.get("secretary_trading_authority")=="NONE",
           "SOURCE_ACK_OUTBOX_PARENT_DRIFT")
    if nomination is not None:
        _check(delivery["scanner_nomination"]==nomination,
               "SOURCE_ACK_NOMINATION_BODY_DRIFT")


def _verify_request(request, identity_map, warehouse, nomination, source_ack,
                    *, now_ms):
    _sha(request,"request_sha256")
    _sha(identity_map,"identity_map_sha256")
    _sha(warehouse,"receipt_sha256")
    _sha(nomination,"digest")
    _sha(source_ack,"receipt_sha256")
    _check(request.get("schema")==REQUEST_SCHEMA
           and identity_map.get("schema")==MAP_SCHEMA
           and warehouse.get("schema")=="aql.core.local-history-warehouse.v1"
           and nomination.get("schema_version")=="AQL-SCANNER-V1"
           and source_ack.get("schema")==SOURCE_ACK_SCHEMA,
           "SOURCE_PARENT_SCHEMA")
    _check(type(now_ms) is int and now_ms>=0,"CLOCK_TYPE")
    _check(request.get("timeframe")=="15m"
           and warehouse.get("interval")=="15m"
           and request.get("symbol")==warehouse.get("symbol")
           and request.get("market")=="BINANCE:SPOT:USDT"
           and warehouse.get("exchange")=="BINANCE"
           and warehouse.get("market")=="SPOT","SOURCE_SCOPE")
    for name in ("strategy_id","strategy_version"):
        _check(type(request.get(name)) is str
               and IDENT.fullmatch(request[name]) is not None,
               "STRATEGY_IDENTITY")
    for name in ("config_digest","strategy_definition_digest",
                 "source_zip_sha256","manifest_integrity_sha256",
                 "core_245_price_query_sha256","core_253_query_local_sha256",
                 "warehouse_receipt_sha256","identity_map_sha256",
                 "scanner_nomination_sha256","source_ack_sha256",
                 "policy_receipt_sha256"):
        _check(type(request.get(name)) is str and
               HEX.fullmatch(request[name]) is not None,
               "REQUEST_SHA_FIELDS")
    _check(type(request.get("cutoff_ms")) is int
           and type(request.get("expires_at_ms")) is int
           and request["cutoff_ms"]<request["expires_at_ms"],
           "REQUEST_TIME_WINDOW")
    _check(request.get("historical_known_at_ms") is None
           and request.get("historical_pit")=="NOT_ATTESTED"
           and request.get("operational_scanner_status")=="UNKNOWN"
           and request.get("trading_authority")=="NONE"
           and request.get("paper_authority")=="NONE"
           and request.get("source_ack_is_approval") is False,
           "REQUEST_FALSE_AUTHORITY")
    fields={
       "source_zip_sha256":"source_zip_sha256",
       "manifest_integrity_sha256":"manifest_integrity_sha256",
       "core_245_price_query_sha256":"core_245_native_price_query_sha256",
       "core_253_query_local_sha256":"core_253_query_local_sha256",
       "warehouse_receipt_sha256":"warehouse_receipt_sha256",
       "identity_map_sha256":"identity_map_sha256",
       "cutoff_ms":"decision_cutoff_ms",
    }
    _check(all(request[k]==identity_map[v] for k,v in fields.items())
           and identity_map.get("historical_known_at_ms") is None
           and identity_map.get("trading_authority")=="NONE"
           and identity_map.get("operational_scanner_status")=="UNKNOWN"
           and identity_map.get("work235_native_15m")==
               "NOT_CONNECTED_15M_UNSUPPORTED"
           and identity_map.get("dataset_id")==warehouse.get("dataset_id")
           and identity_map.get("source_version")==warehouse.get("version"),
           "DUAL_QUERY_PARENT_DRIFT")
    _check(request["source_zip_sha256"]==warehouse.get("source_zip_sha256")
           and request["manifest_integrity_sha256"]==
                warehouse.get("manifest_integrity_sha256")
           and request["warehouse_receipt_sha256"]==warehouse["receipt_sha256"]
           and request["cutoff_ms"]==warehouse.get("decision_cutoff_ms")
           and warehouse.get("status")=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
           and warehouse.get("vault",{}).get("vault")==
                "EXISTING_PINNED_RAW_VAULT"
           and warehouse.get("historical_known_at")=="NOT_ATTESTED"
           and warehouse.get("availability")=="RETROSPECTIVE_NON_PIT",
           "WAREHOUSE_SOURCE_AUTHORITY_DRIFT")
    _check(request["scanner_nomination_sha256"]==nomination["digest"]
           and nomination.get("stage")=="UNKNOWN"
           and nomination.get("availability_class")=="RETROSPECTIVE_NON_PIT"
           and nomination.get("publishable") is False
           and nomination.get("delivery_authorized") is False
           and nomination.get("source_manifest",{}).get("dataset_sha")==
                request["source_zip_sha256"]
           and nomination.get("source_manifest",{}).get("dataset_id")==
                warehouse.get("dataset_id"),
           "SCANNER_NOMINATION_NOT_SOURCE_LOCKED")
    _check(request["source_ack_sha256"]==source_ack["receipt_sha256"]
           and source_ack.get("state")=="ACKED"
           and source_ack.get("authority")=="OFFLINE_RESEARCH_ONLY",
           "SOURCE_ACK_NOT_APPROVAL")
    _check(request["expires_at_ms"]>now_ms,"ROUTE_EXPIRED")
    return request


def make_strategy_route_request(*, identity_map, warehouse, nomination,
                                source_ack, strategy_policy_receipt,
                                strategy_id, strategy_version,
                                config_digest, strategy_definition_digest,
                                expires_at_ms):
    body={
       "schema":REQUEST_SCHEMA,
       "strategy_id":strategy_id,"strategy_version":strategy_version,
       "config_digest":config_digest,
       "strategy_definition_digest":strategy_definition_digest,
       "symbol":warehouse["symbol"],"timeframe":"15m",
       "market":"BINANCE:SPOT:USDT",
       "source_zip_sha256":identity_map["source_zip_sha256"],
       "manifest_integrity_sha256":identity_map["manifest_integrity_sha256"],
       "core_245_price_query_sha256":
            identity_map["core_245_native_price_query_sha256"],
       "core_253_query_local_sha256":
            identity_map["core_253_query_local_sha256"],
       "identity_map_sha256":identity_map["identity_map_sha256"],
       "warehouse_receipt_sha256":warehouse["receipt_sha256"],
       "cutoff_ms":identity_map["decision_cutoff_ms"],
       "expires_at_ms":expires_at_ms,
       "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
       "operational_scanner_status":"UNKNOWN",
       "scanner_nomination_sha256":nomination["digest"],
       "source_ack_sha256":source_ack["receipt_sha256"],
       "policy_receipt_sha256":strategy_policy_receipt["sha256"],
       "source_ack_is_approval":False,
       "paper_authority":"NONE","trading_authority":"NONE",
    }
    request={**body,"request_sha256":digest(body)}
    _verify_policy(strategy_policy_receipt,request)
    return request


def _approval(approval, request, *, now_ms):
    if approval is None:
        return None
    _sha(approval,"approval_sha256")
    _check(approval.get("schema")==APPROVAL_SCHEMA
           and approval.get("decision")=="APPROVED_TEST_ONLY"
           and approval.get("scope")=="TEST_ONLY"
           and approval.get("paper_authority")=="NONE"
           and approval.get("trading_authority")=="NONE"
           and approval.get("historical_pit")=="NOT_ATTESTED"
           and approval.get("historical_known_at_ms") is None
           and approval.get("source_ack_is_approval") is False
           and approval.get("approved_by")=="EXPLICIT_RESEARCH_POLICY_GATE",
           "APPROVAL_POLICY_NOT_AUTHORIZED")
    _check(_identity(approval)==_identity(request)
           and approval.get("strategy_definition_digest")==
                request["strategy_definition_digest"]
           and approval.get("timeframe")=="15m"
           and approval.get("symbol")==request["symbol"]
           and approval.get("source_zip_sha256")==request["source_zip_sha256"]
           and approval.get("manifest_integrity_sha256")==
                request["manifest_integrity_sha256"]
           and approval.get("core_245_price_query_sha256")==
                request["core_245_price_query_sha256"]
           and approval.get("core_253_query_local_sha256")==
                request["core_253_query_local_sha256"]
           and approval.get("scanner_nomination_sha256")==
                request["scanner_nomination_sha256"]
           and approval.get("source_ack_sha256")==
                request["source_ack_sha256"]
           and approval.get("request_sha256")==request["request_sha256"]
           and approval.get("policy_receipt_sha256")==
                request["policy_receipt_sha256"]
           and approval.get("cutoff_ms")==request["cutoff_ms"],
           "APPROVAL_IDENTITY_OR_PARENT_DRIFT")
    _check(type(approval.get("issued_at_ms")) is int
           and type(approval.get("expires_at_ms")) is int
           and approval["issued_at_ms"]<=now_ms<
               min(approval["expires_at_ms"],request["expires_at_ms"])
           and approval["issued_at_ms"]>=request["cutoff_ms"],
           "APPROVAL_EXPIRED_OR_TIME_DRIFT")
    return approval


def _verify_stored(con, route_id):
    row=con.execute("SELECT request_sha,request_json,approval_sha,approval_json,"
                    "source_ack_sha,state,attempts,consumer_ack_sha,next_attempt_ms,"
                    "source_ack_json,consumer_ack_json,policy_sha,policy_json "
                    "FROM c_strategy_routes WHERE route_id=?",(route_id,)).fetchone()
    _check(row is not None,"ROUTE_NOT_FOUND")
    request=json.loads(row[1])
    _sha(request,"request_sha256")
    _check(request["request_sha256"]==row[0]
           and request["source_ack_sha256"]==row[4],"STORED_SOURCE_DRIFT")
    approval=json.loads(row[3]) if row[3] is not None else None
    _check((approval is None)==(row[2] is None),"STORED_APPROVAL_DRIFT")
    if approval is not None:
        _sha(approval,"approval_sha256")
        _check(approval["approval_sha256"]==row[2]
               and approval["request_sha256"]==row[0],
               "STORED_APPROVAL_PARENT")
    policy=json.loads(row[12])
    _check(row[11]==policy["sha256"],"STORED_POLICY_PARENT_DRIFT")
    _verify_policy(policy,request)
    source_ack=json.loads(row[9])
    _verify_source_ack(con,request,source_ack)
    if row[10] is not None:
        consumed=json.loads(row[10])
        _sha(consumed,"consumer_ack_sha256")
        _check(row[7]==consumed["consumer_ack_sha256"]
               and approval is not None
               and consumed.get("approval_sha256")==approval["approval_sha256"]
               and consumed.get("request_sha256")==request["request_sha256"],
               "STORED_CONSUMER_ACK_DRIFT")
    else:
        _check(row[7] is None,"STORED_CONSUMER_ACK_MISSING")
    trace=_trace(con,route_id)
    return row,request,approval,trace


def enqueue_strategy_route(root, request, identity_map, warehouse,
                           nomination, source_ack, strategy_policy_receipt, *,
                           approval=None, now_ms, route_id):
    """Create-once strategy route, or replay same immutable decision.

    No approval -> WAIT_APPROVAL. Source-only ACK NEVER promotes this state.
    Approval is external signed explicit research TEST_ONLY input, not created
    here. Every route remains non-operational, even with a valid approval.
    """
    _check(type(route_id) is str and IDENT.fullmatch(route_id) is not None,
           "ROUTE_ID")
    _verify_request(request,identity_map,warehouse,nomination,source_ack,now_ms=now_ms)
    _verify_policy(strategy_policy_receipt,request)
    source_con=_connect(root)
    try:
        _verify_source_ack(source_con,request,source_ack,nomination)
    finally:
        source_con.close()
    valid=_approval(approval,request,now_ms=now_ms)
    state="PENDING_CONSUMER" if valid is not None else "WAIT_APPROVAL"
    con=_connect(root)
    try:
        _create(con)
        con.execute("BEGIN IMMEDIATE")
        other=con.execute(
            "SELECT route_id FROM c_strategy_routes WHERE request_sha=?",
            (request["request_sha256"],)).fetchone()
        _check(other is None or other[0]==route_id,
               "AMBIGUOUS_DUPLICATE_REQUEST_ROUTE")
        existing=con.execute(
            "SELECT request_sha,approval_sha FROM c_strategy_routes WHERE route_id=?",
            (route_id,)).fetchone()
        if existing:
            _verify_stored(con,route_id)
            _check(existing==(request["request_sha256"],
                              valid["approval_sha256"] if valid else None),
                   "IDEMPOTENCY_CONFLICT")
        else:
            con.execute("INSERT INTO c_strategy_routes("
                "route_id,request_sha,request_json,approval_sha,approval_json,"
                "source_ack_sha,state,attempts,consumer_ack_sha,next_attempt_ms,"
                "source_ack_json,consumer_ack_json,policy_sha,policy_json)"
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (route_id,request["request_sha256"],json.dumps(request,sort_keys=True),
                 valid["approval_sha256"] if valid else None,
                 json.dumps(valid,sort_keys=True) if valid else None,
                 source_ack["receipt_sha256"],state,0,None,0,
                 json.dumps(source_ack,sort_keys=True),None,
                 strategy_policy_receipt["sha256"],
                 json.dumps(strategy_policy_receipt,sort_keys=True)))
            _event(con,route_id,state,request_sha=request["request_sha256"],
                   policy_sha=strategy_policy_receipt["sha256"],
                   approval_sha=valid["approval_sha256"] if valid else None,
                   source_ack_sha=source_ack["receipt_sha256"],
                   consumer_ack_sha=None,attempts=0,reason="CREATED")
        con.commit()
        return strategy_route_snapshot(root,route_id,now_ms=now_ms)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _transition(root, route_id, *, now_ms, action, approval=None,
                consumer_ack=None, retry_reason=None, max_attempts=3):
    con=_connect(root)
    try:
        _create(con)
        con.execute("BEGIN IMMEDIATE")
        row,request,prior,trace=_verify_stored(con,route_id)
        _check(type(now_ms) is int and now_ms>=0,"CLOCK_TYPE")
        if row[5] in ("ACKED_CONSUMER","QUARANTINED","EXPIRED"):
            _check(action=="ACK" and row[5]=="ACKED_CONSUMER" and
                   consumer_ack is not None
                   and row[7]==consumer_ack.get("consumer_ack_sha256"),
                   "TERMINAL_STATE")
            _check(now_ms < request["expires_at_ms"],"ROUTE_EXPIRED")
            _verify_consumer_ack(consumer_ack,request,prior,now_ms)
            con.commit()
            return strategy_route_snapshot(root,route_id,now_ms=now_ms)
        if now_ms>=request["expires_at_ms"]:
            state="EXPIRED"
            app=prior
            ack=None
            attempts=row[6]
            reason="REQUEST_EXPIRED"
        elif action=="APPROVE":
            _check(row[5]=="WAIT_APPROVAL","INVALID_APPROVAL_TRANSITION")
            app=_approval(approval,request,now_ms=now_ms)
            _check(app is not None,"MISSING_EXPLICIT_APPROVAL")
            state="PENDING_CONSUMER"
            ack=None
            attempts=row[6]
            reason="EXPLICIT_APPROVAL"
        elif action=="RETRY":
            _check(row[5] in ("PENDING_CONSUMER","RETRY"),"RETRY_NOT_ALLOWED")
            _check(row[5]!="RETRY" or now_ms>=row[8],
                   "RETRY_BACKOFF_NOT_ELAPSED")
            _check(type(retry_reason) is str and IDENT.fullmatch(retry_reason) is not None
                   and type(max_attempts) is int and 1<=max_attempts<=10,
                   "RETRY_PARAMETERS")
            _check(prior is not None,"RETRY_REQUIRES_APPROVAL")
            attempts=row[6]+1
            state="QUARANTINED" if attempts>=max_attempts else "RETRY"
            app=prior;ack=None;reason=retry_reason
        elif action=="ACK":
            _check(row[5] in ("PENDING_CONSUMER","RETRY"),"ACK_NOT_ALLOWED")
            _check(row[5]!="RETRY" or now_ms>=row[8],
                   "CONSUMER_BACKOFF_NOT_ELAPSED")
            _check(consumer_ack is not None
                   and consumer_ack.get("route_id")==route_id,
                   "CONSUMER_ROUTE_ID_DRIFT")
            _check(prior is not None,"MISSING_EXPLICIT_APPROVAL")
            _approval(prior,request,now_ms=now_ms)
            _verify_consumer_ack(consumer_ack,request,prior,now_ms)
            state="ACKED_CONSUMER";app=prior
            ack=consumer_ack["consumer_ack_sha256"]
            attempts=row[6];reason="EXPLICIT_CONSUMER_ACK"
        else:
            _check(False,"UNKNOWN_TRANSITION")
        next_ms=(now_ms+min(3600,2**max(0,attempts-1))*1000
                 if state=="RETRY" else 0)
        con.execute("UPDATE c_strategy_routes SET approval_sha=?,approval_json=?,"
                    "state=?,attempts=?,consumer_ack_sha=?,next_attempt_ms=?,"
                    "consumer_ack_json=? WHERE route_id=?",
                    (app["approval_sha256"] if app else None,
                     json.dumps(app,sort_keys=True) if app else None,
                     state,attempts,ack,next_ms,
                     json.dumps(consumer_ack,sort_keys=True)
                        if state=="ACKED_CONSUMER" else None,route_id))
        _event(con,route_id,state,request_sha=request["request_sha256"],
               policy_sha=request["policy_receipt_sha256"],
               approval_sha=app["approval_sha256"] if app else None,
               source_ack_sha=row[4],consumer_ack_sha=ack,
               attempts=attempts,reason=reason)
        con.commit()
        return strategy_route_snapshot(root,route_id,now_ms=now_ms)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _verify_consumer_ack(ack, request, approval, now_ms):
    _sha(ack,"consumer_ack_sha256")
    _check(ack.get("schema")=="aql.factory.c.strategy-consumer-ack.v1"
           and ack.get("decision")=="ACCEPTED_TEST_ONLY_RESEARCH"
           and ack.get("trading_authority")=="NONE"
           and ack.get("paper_authority")=="NONE"
           and ack.get("request_sha256")==request["request_sha256"]
           and ack.get("approval_sha256")==approval["approval_sha256"]
           and _identity(ack)==_identity(request)
           and ack.get("source_zip_sha256")==request["source_zip_sha256"]
           and ack.get("core_245_price_query_sha256")==
                request["core_245_price_query_sha256"]
           and ack.get("core_253_query_local_sha256")==
                request["core_253_query_local_sha256"]
           and ack.get("cutoff_ms")==request["cutoff_ms"]
           and ack.get("route_id") is not None
           and ack.get("source_ack_sha256")==request["source_ack_sha256"]
           and ack.get("policy_receipt_sha256")==request["policy_receipt_sha256"]
           and ack.get("scanner_nomination_sha256")==
                request["scanner_nomination_sha256"]
           and ack.get("manifest_integrity_sha256")==
                request["manifest_integrity_sha256"]
           and ack.get("warehouse_receipt_sha256")==
                request["warehouse_receipt_sha256"]
           and type(ack.get("accepted_at_ms")) is int
           and request["cutoff_ms"]<=ack["accepted_at_ms"]<=now_ms
           and ack["accepted_at_ms"]<request["expires_at_ms"],
           "CONSUMER_ACK_PARENT_OR_AUTHORITY")
    _approval(approval,request,now_ms=now_ms)


def approve_strategy_route(root,route_id,approval,*,now_ms):
    return _transition(root,route_id,now_ms=now_ms,action="APPROVE",
                       approval=approval)


def acknowledge_strategy_consumer(root,route_id,consumer_ack,*,now_ms):
    return _transition(root,route_id,now_ms=now_ms,action="ACK",
                       consumer_ack=consumer_ack)


def retry_strategy_route(root,route_id,*,reason,now_ms,max_attempts=3):
    return _transition(root,route_id,now_ms=now_ms,action="RETRY",
                       retry_reason=reason,max_attempts=max_attempts)


def strategy_route_snapshot(root,route_id,*,now_ms):
    _check(type(now_ms) is int and now_ms>=0,"CLOCK_TYPE")
    con=_connect(root)
    try:
        _create(con)
        row,request,approval,trace=_verify_stored(con,route_id)
        state=row[5]
        if now_ms>=request["expires_at_ms"] and state not in (
             "ACKED_CONSUMER","QUARANTINED","EXPIRED"):
            state="EXPIRED"  # read-only projection, not a committed transition
        approval_valid_at_now=False
        if approval is not None:
            try:
                _approval(approval,request,now_ms=now_ms)
                approval_valid_at_now=True
            except ValueError:
                if state not in ("ACKED_CONSUMER","QUARANTINED","EXPIRED"):
                    state="WAIT_APPROVAL"
        receipt={
           "schema":RECEIPT_SCHEMA,"route_id":route_id,
           "request_sha256":request["request_sha256"],
           "source_ack_sha256":row[4],
           "policy_receipt_sha256":request["policy_receipt_sha256"],
           "approval_sha256":row[2],
           "consumer_ack_sha256":row[7],
           "state":state,"event_tail_sha256":digest(trace[-1]),
           "attempt_count":row[6],
           "strategy_id":request["strategy_id"],
           "strategy_version":request["strategy_version"],
           "config_digest":request["config_digest"],
           "strategy_definition_digest":request["strategy_definition_digest"],
           "symbol":request["symbol"],"timeframe":request["timeframe"],
           "source_zip_sha256":request["source_zip_sha256"],
           "manifest_integrity_sha256":request["manifest_integrity_sha256"],
           "core_245_price_query_sha256":request["core_245_price_query_sha256"],
           "core_253_query_local_sha256":request["core_253_query_local_sha256"],
           "identity_map_sha256":request["identity_map_sha256"],
           "warehouse_receipt_sha256":request["warehouse_receipt_sha256"],
           "scanner_nomination_sha256":request["scanner_nomination_sha256"],
           "cutoff_ms":request["cutoff_ms"],
           "historical_known_at_ms":None,
           "historical_pit":"NOT_ATTESTED","operational_scanner_status":"UNKNOWN",
           "paper_authority":"NONE","trading_authority":"NONE",
           "paper_execution":"NOT_ACTIVATED",
           "route_ready_for_isolated_lab":(
               state=="ACKED_CONSUMER" and approval_valid_at_now
               and now_ms<request["expires_at_ms"]),
           "strategy_policy_approved_test_only":row[2] is not None,
           "approval_valid_at_now":approval_valid_at_now,
        }
        return {**receipt,"route_receipt_sha256":digest(receipt)}
    finally:
        con.close()


def strategy_route_trace(root,route_id):
    con=_connect(root)
    try:
        _create(con)
        _verify_stored(con,route_id)
        return _trace(con,route_id)
    finally:
        con.close()
