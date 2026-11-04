"""Core #253 — offline research-only Scanner→Secretary durable outbox.

This is a bounded routing seam, NOT Scanner scoring, strategy approval,
paper execution, live messaging or actual email/Telegram delivery.
Delivery is explicit caller-side handoff with acknowledged content hash.
"""
from __future__ import annotations

import hashlib
import json
import re
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import _connect, require, BackboneError

SCHEMA = "aql.core.scanner-secretary-offline-route.v1"
ACK_SCHEMA = "aql.core.secretary-offline-ack.v1"
IDENTITY = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SCANNER_CANDIDATE = re.compile(r"^[A-Za-z0-9_.:+-]{1,200}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
LANES = ("FAST", "SLOW")


def _check_identity(value, code):
    require(type(value) is str and IDENTITY.fullmatch(value), code)


def _check_sha(value, code):
    require(type(value) is str and SHA.fullmatch(value), code)


def _payload(nomination, strategy_id, strategy_version, warehouse_receipt, lane):
    require(type(nomination) is dict and
            nomination.get("schema_version") == "AQL-SCANNER-V1"
            and type(nomination.get("digest")) is str
            and SHA.fullmatch(nomination["digest"]) is not None,
            "SCANNER_V1_SCHEMA_AND_DIGEST_REQUIRED")
    scanner_body={k:v for k,v in nomination.items() if k!="digest"}
    scanner_hash=hashlib.sha256(json.dumps(
        scanner_body,sort_keys=True,separators=(",",":"),
        ensure_ascii=False,default=str,
    ).encode("utf-8")).hexdigest()
    require(scanner_hash == nomination["digest"],
            "SCANNER_ENVELOPE_DIGEST_MISMATCH")
    require(nomination.get("publishable") is False and
            nomination.get("delivery_authorized") is False and
            nomination.get("availability_class") in (
                "RETROSPECTIVE_NON_PIT", "UNKNOWN") and
            nomination.get("stage") in (
                "DISCOVERED", "SCREENED", "QUALIFIED", "NOMINATED",
                "REJECTED", "EXPIRED", "UNKNOWN"),
            "SCANNER_OFFLINE_AUTHORITY")
    for field in ("scanner_id", "profile_id"):
        _check_identity(nomination.get(field), "SCANNER_IDENTITY_REQUIRED")
    require(type(nomination.get("candidate_id")) is str and
            SCANNER_CANDIDATE.fullmatch(nomination["candidate_id"]) is not None,
            "SCANNER_CANDIDATE_ID_REQUIRED")
    require(type(nomination.get("source_manifest")) is dict
            and type(nomination.get("coverage")) is dict
            and type(nomination.get("reasons")) is list
            and type(nomination.get("feature_snapshot")) is dict,
            "SCANNER_PROVENANCE_REQUIRED")
    source_manifest = nomination["source_manifest"]
    _check_identity(source_manifest.get("dataset_id"), "SCANNER_DATASET_REQUIRED")
    _check_sha(source_manifest.get("dataset_sha"), "SCANNER_SOURCE_SHA_REQUIRED")
    require(type(warehouse_receipt) is dict
            and warehouse_receipt.get("schema") ==
                "aql.core.local-history-warehouse.v1"
            and warehouse_receipt.get("status") in (
                "OFFLINE_LOCAL_WAREHOUSE_COMMITTED","OFFLINE_LOCAL_STAGE_ONLY")
            and warehouse_receipt.get("availability") ==
                "RETROSPECTIVE_NON_PIT"
            and warehouse_receipt.get("execution") == "DISABLED"
            and type(warehouse_receipt.get("receipt_sha256")) is str
            and digest({k:v for k,v in warehouse_receipt.items()
                        if k != "receipt_sha256"}) ==
                warehouse_receipt["receipt_sha256"],
            "WAREHOUSE_RECEIPT_REQUIRED")
    require(source_manifest["dataset_id"] == warehouse_receipt["dataset_id"]
            and source_manifest["dataset_sha"] ==
                warehouse_receipt["source_zip_sha256"],
            "SCANNER_SOURCE_PARENTS_DRIFT")
    _check_identity(strategy_id, "STRATEGY_ID_REQUIRED")
    _check_identity(strategy_version, "STRATEGY_VERSION_REQUIRED")
    require(lane in LANES, "SECRETARY_LANE_INVALID")
    body = {
        "schema":SCHEMA,"lane":lane,
        "strategy_id":strategy_id,
        "strategy_version":strategy_version,
        "strategy_authority":"OFFLINE_RESEARCH_ONLY_NOT_APPROVED_PAPER",
        "scanner_nomination":nomination,
        "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "raw_vault":warehouse_receipt["vault"]["vault"],
        "source_zip_sha256":warehouse_receipt["source_zip_sha256"],
        "source_manifest_sha256":warehouse_receipt["manifest_integrity_sha256"],
        "historical_pit":"NOT_ATTESTED",
        "scanner_strategy_decision":"NOT_PERFORMED",
        "secretary_trading_authority":"NONE",
        "discoverer_dependency":"OPTIONAL",
    }
    return {**body, "payload_sha256":digest(body)}


def _append_event(con, message_id, state, payload_sha256,
                  *, attempt_count, reason=None):
    """Append a content-addressed event inside the SAME outbox transaction."""
    last=con.execute(
        "SELECT event_sha256 FROM distribution_events WHERE message_id=? "
        "ORDER BY event_seq DESC LIMIT 1",(message_id,),
    ).fetchone()
    body={
        "schema":"aql.core.secretary-event.v1",
        "message_id":message_id,"state":state,
        "payload_sha256":payload_sha256,
        "attempt_count":attempt_count,"reason":reason,
        "previous_event_sha256":last[0] if last else None,
    }
    event_sha=digest(body)
    con.execute(
        "INSERT INTO distribution_events "
        "(message_id,state,payload_sha256,prev_sha256,event_sha256,event_json) "
        "VALUES(?,?,?,?,?,?)",
        (message_id,state,payload_sha256,body["previous_event_sha256"],
         event_sha,json.dumps(body,sort_keys=True,separators=(",",":"))),
    )
    return event_sha


def _trace(con, message_id):
    rows=con.execute(
        "SELECT state,payload_sha256,prev_sha256,event_sha256,event_json "
        "FROM distribution_events WHERE message_id=? ORDER BY event_seq",
        (message_id,),
    ).fetchall()
    require(len(rows)>0 and len(rows)<=256, "SECRETARY_TRACE_MISSING_OR_TOO_LARGE")
    prior=None
    for state,payload_sha,prev,event_sha,jsontext in rows:
        body=json.loads(jsontext)
        require(body["message_id"]==message_id and
                body["state"]==state and
                body["payload_sha256"]==payload_sha and
                body["previous_event_sha256"]==prior and
                prev==prior and digest(body)==event_sha,
                "SECRETARY_TRACE_TAMPER")
        prior=event_sha
    tail=con.execute(
        "SELECT state,payload_hash,attempt_count FROM distribution_outbox "
        "WHERE message_id=?",(message_id,),
    ).fetchone()
    require(tail is not None and tail[0]==rows[-1][0] and
            tail[1]==rows[-1][1] and
            tail[2]==json.loads(rows[-1][4])["attempt_count"],
            "SECRETARY_TRACE_STATE_DRIFT")
    return [json.loads(row[4]) for row in rows]


def route_trace(root, message_id:str):
    """Safe, read-only verification of a single durable Secretary event chain."""
    _check_identity(message_id,"TRACE_MESSAGE_ID")
    con=_connect(root)
    try:
        return _trace(con,message_id)
    finally:
        con.close()


def enqueue_nomination(
    root, scanner_nomination:dict, *, strategy_id:str, strategy_version:str,
    warehouse_receipt:dict, lane:str, idempotency_key:str,
):
    """Exactly one immutable event per idempotency_key; mismatched replay DENIED."""
    _check_identity(idempotency_key,"IDEMPOTENCY_KEY_REQUIRED")
    envelope=_payload(scanner_nomination,strategy_id,strategy_version,
                      warehouse_receipt,lane)
    con=_connect(root)
    try:
        con.execute("BEGIN IMMEDIATE")
        old=con.execute(
            "SELECT payload_hash FROM distribution_outbox WHERE message_id=?",
            (idempotency_key,),
        ).fetchone()
        require(old is None or old[0]==envelope["payload_sha256"],
                "SECRETARY_IDEMPOTENCY_CONFLICT")
        if old is None:
            con.execute(
                "INSERT INTO distribution_outbox "
                "(message_id,payload_hash,lane,state,attempt_count,delivery_json,"
                "ack_sha,priority,next_attempt_ms,last_error)"
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (idempotency_key,envelope["payload_sha256"],lane,"PENDING",
                 0,json.dumps(envelope,sort_keys=True,separators=(",",":")),
                 None,0 if lane=="FAST" else 1,0,None),
            )
            _append_event(con,idempotency_key,"PENDING",envelope["payload_sha256"],
                          attempt_count=0)
        else:
            _trace(con,idempotency_key)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "schema":"aql.core.secretary-offline-queue.v1",
        "message_id":idempotency_key,"payload_sha256":envelope["payload_sha256"],
        "lane":lane,"delivery":"OFFLINE_ONLY_NO_NETWORK",
        "trading_authority":"NONE",
    }


def poll_nomination(root, *, now_ms:int, lane:str|None=None):
    """Durable, strictly read-only poll. Consumers explicitly ACK or retry."""
    require(type(now_ms) is int and now_ms>=0 and
            (lane is None or lane in LANES), "SECRETARY_POLL_ARGUMENT")
    con=_connect(root)
    try:
        sql=("SELECT message_id,payload_hash,delivery_json,attempt_count,"
             "lane,state FROM distribution_outbox WHERE "
             "state IN ('PENDING','RETRY') AND next_attempt_ms<=?")
        params=[now_ms]
        if lane is not None:
            sql+=" AND lane=?"
            params.append(lane)
        sql+=" ORDER BY priority ASC,created_sequence ASC LIMIT 1"
        found=con.execute(sql,params).fetchone()
        if found is None:
            return None
        mid,sha,payload,attempts,selected,state=found
        _trace(con,mid)
        body=json.loads(payload)
        require(body["payload_sha256"] == sha
                and digest({k:v for k,v in body.items()
                            if k != "payload_sha256"}) == sha,
                "SECRETARY_QUEUE_TAMPER")
        return {"message_id":mid,"envelope":body,"lane":selected,
                "attempt_count":attempts,"state":state}
    finally:
        con.close()


def acknowledge_nomination(root, *, message_id:str, payload_sha256:str,
                            acknowledgement_sha256:str):
    """Caller explicitly acknowledges offline research handoff; no trade occurs."""
    _check_identity(message_id,"ACK_MESSAGE_ID")
    _check_sha(payload_sha256,"ACK_PAYLOAD_SHA")
    _check_sha(acknowledgement_sha256,"ACK_EVIDENCE_SHA")
    con=_connect(root)
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute(
            "SELECT payload_hash,state,ack_sha FROM distribution_outbox "
            "WHERE message_id=?",(message_id,),
        ).fetchone()
        require(row is not None and row[0]==payload_sha256,
                "ACK_SOURCE_MISMATCH")
        _trace(con,message_id)
        require(row[1]!="QUARANTINED","ACK_QUARANTINED")
        if row[1]=="ACKED":
            require(row[2]==acknowledgement_sha256,"ACK_REWRITE_DENIED")
        else:
            con.execute(
                "UPDATE distribution_outbox SET state='ACKED',ack_sha=?,"
                "last_error=NULL WHERE message_id=?",
                (acknowledgement_sha256,message_id),
            )
            attempts=con.execute(
                "SELECT attempt_count FROM distribution_outbox "
                "WHERE message_id=?",(message_id,),
            ).fetchone()[0]
            _append_event(con,message_id,"ACKED",payload_sha256,
                          attempt_count=attempts,reason=acknowledgement_sha256)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    body={
        "schema":ACK_SCHEMA,"message_id":message_id,
        "payload_sha256":payload_sha256,
        "acknowledgement_sha256":acknowledgement_sha256,
        "state":"ACKED","authority":"OFFLINE_RESEARCH_ONLY",
    }
    return {**body,"receipt_sha256":digest(body)}


def retry_or_quarantine(root, *, message_id:str, payload_sha256:str,
                        reason:str, now_ms:int, max_attempts:int=3):
    """Bounded exponential retry; terminal quarantine rather than silent drop."""
    _check_identity(message_id,"RETRY_MESSAGE_ID")
    _check_sha(payload_sha256,"RETRY_PAYLOAD_SHA")
    require(type(reason) is str and IDENTITY.fullmatch(reason)
            and type(now_ms) is int and now_ms>=0
            and type(max_attempts) is int and 1<=max_attempts<=10,
            "RETRY_PARAMETERS")
    con=_connect(root)
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute(
            "SELECT payload_hash,state,attempt_count FROM distribution_outbox "
            "WHERE message_id=?",(message_id,),
        ).fetchone()
        require(row is not None and row[0]==payload_sha256,
                "RETRY_SOURCE_MISMATCH")
        require(row[1] in ("PENDING","RETRY"),
                "RETRY_TERMINAL")
        _trace(con,message_id)
        attempts=row[2]+1
        state="QUARANTINED" if attempts>=max_attempts else "RETRY"
        next_ms=now_ms+(min(3600,2**(attempts-1))*1000)
        con.execute(
            "UPDATE distribution_outbox SET state=?,attempt_count=?,"
            "next_attempt_ms=?,last_error=? WHERE message_id=?",
            (state,attempts,next_ms,reason,message_id),
        )
        _append_event(con,message_id,state,payload_sha256,
                      attempt_count=attempts,reason=reason)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    body={"schema":"aql.core.secretary-offline-retry.v1",
          "message_id":message_id,"state":state,
          "attempt_count":attempts,"reason":reason,
          "next_attempt_ms":None if state=="QUARANTINED" else next_ms}
    return {**body,"receipt_sha256":digest(body)}
