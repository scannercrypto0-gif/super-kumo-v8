"""ATLAS Factory F4 resumable historical research attempt accounting.

This is a durable *batch attempt ledger*, not a substitute for Core custody,
Scanner research-policy authorization, historical Secretary, or actual Lab.
No source-less request can be upgraded to historical success here.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, digest, _sha
)

SCHEMA="aql.factory.f.research-batch.v1"
RECEIPT_SCHEMA="aql.factory.f.research-batch-census.v1"
STATES=("SELECTED","DENIED","UNKNOWN")
SOURCE="HISTORICAL_SOURCE_BLOCKED"
_SAFE=re.compile(r"^[A-Za-z0-9_.:+-]{1,160}$")


def _need(condition,why):
    if not condition:
        raise ResultsStoreError("FACTORY_F_"+why)


def _check(record):
    _need(type(record) is dict and _sha(record.get("receipt_sha256"))
          and digest({k:v for k,v in record.items()
                      if k!="receipt_sha256"})==record["receipt_sha256"],
          "RECEIPT_TAMPER")


def _connect(path):
    p=Path(path)
    _need(p.suffix==".sqlite" and p.parent.is_dir(),"PATH")
    db=sqlite3.connect(p,timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA busy_timeout=15000")
    db.executescript("""
       CREATE TABLE IF NOT EXISTS f_batches(
          batch_id TEXT PRIMARY KEY, header_sha TEXT NOT NULL,
          header_json TEXT NOT NULL
       );
       CREATE TABLE IF NOT EXISTS f_attempts(
          batch_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
          candidate_id TEXT NOT NULL, state TEXT NOT NULL,
          receipt_sha TEXT NOT NULL, receipt_json TEXT NOT NULL,
          PRIMARY KEY(batch_id, attempt_id),
          FOREIGN KEY(batch_id) REFERENCES f_batches(batch_id)
       );
    """)
    return db


def start_blocked_batch(path,*,batch_id,
                        source_status_sha256,
                        policy_request_sha256,policy_proposal_sha256,
                        attempt_manifest):
    """Persist expected complete candidate population, all UNKNOWN only.

    No imaginary source IDs, source ACKs, approvals, query digests, or results
    are generated. The manifest is a deterministic explicit denominator.
    """
    _need(type(batch_id) is str and _SAFE.fullmatch(batch_id)
          and all(_sha(s) for s in (source_status_sha256,
                                   policy_request_sha256,
                                   policy_proposal_sha256)), "IDENTITY")
    _need(type(attempt_manifest) is list
          and 0<len(attempt_manifest)<=10000, "DENOMINATOR")
    seen=set()
    expected=[]
    for row in attempt_manifest:
        _need(type(row) is dict
              and set(row)=={"attempt_id","candidate_id"}
              and type(row["attempt_id"]) is str
              and _SAFE.fullmatch(row["attempt_id"])
              and row["attempt_id"] not in seen
              and type(row["candidate_id"]) is str
              and _SAFE.fullmatch(row["candidate_id"]),
              "ATTEMPT_IDENTITY")
        seen.add(row["attempt_id"])
        expected.append(row)
    expected.sort(key=lambda v:v["attempt_id"])
    base=dict(schema=SCHEMA,batch_id=batch_id,
              status=SOURCE,evidence_class="RETROSPECTIVE_NON_PIT",
              source_status_sha256=source_status_sha256,
              policy_request_sha256=policy_request_sha256,
              policy_proposal_sha256=policy_proposal_sha256,
              manifest=expected,denominator=len(expected),
              source_ack_sha256=None,strategy_approval_sha256=None,
              factory_consumer_ack_sha256=None,
              core_245_query_sha256=None,core_253_query_sha256=None,
              lab_sha256=None,result_sha256=None,
              paper="NOT_ACTIVATED",trading_authority="NONE",
              orders_created=0,paper_positions=0,actual_fills=None)
    header={**base,"receipt_sha256":digest(base)}
    encoded=json.dumps(header,sort_keys=True,separators=(",",":"))
    db=_connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        old=db.execute("SELECT header_sha,header_json FROM f_batches WHERE batch_id=?",
                       (batch_id,)).fetchone()
        _need(old is None or old==(header["receipt_sha256"],encoded),
              "IMMUTABLE_BATCH_ID_CONFLICT")
        if old is None:
            db.execute("INSERT INTO f_batches VALUES(?,?,?)",
                       (batch_id,header["receipt_sha256"],encoded))
            for item in expected:
                b=dict(schema="aql.factory.f.research-attempt.v1",
                       batch_id=batch_id,attempt_id=item["attempt_id"],
                       candidate_id=item["candidate_id"],
                       state="UNKNOWN",
                       reason="WAIT_ORIGINAL_SOURCE_AND_RESEARCH_POLICY",
                       source_status_sha256=source_status_sha256,
                       policy_request_sha256=policy_request_sha256,
                       policy_proposal_sha256=policy_proposal_sha256,
                       source_ack_sha256=None,strategy_approval_sha256=None,
                       factory_consumer_ack_sha256=None,
                       core_245_query_sha256=None,core_253_query_sha256=None,
                       config_sha256=None,strategy_sha256=None,
                       lab_sha256=None,result_sha256=None,
                       paper="NOT_ACTIVATED",orders_created=0,
                       paper_positions=0,actual_fills=None,
                       trading_authority="NONE")
                v={**b,"receipt_sha256":digest(b)}
                db.execute("INSERT INTO f_attempts VALUES(?,?,?,?,?,?)",
                           (batch_id,item["attempt_id"],item["candidate_id"],
                            "UNKNOWN",v["receipt_sha256"],
                            json.dumps(v,sort_keys=True,separators=(",",":"))))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return batch_snapshot(path,batch_id)


def batch_snapshot(path,batch_id):
    db=_connect(path)
    try:
        header_row=db.execute("SELECT header_sha,header_json FROM f_batches WHERE batch_id=?",
                              (batch_id,)).fetchone()
        _need(header_row is not None,"NOT_FOUND")
        header=json.loads(header_row[1])
        _check(header)
        _need(header_row[0]==header["receipt_sha256"]
              and header["batch_id"]==batch_id
              and header["status"]==SOURCE
              and header["source_ack_sha256"] is None
              and header["strategy_approval_sha256"] is None
              and header["factory_consumer_ack_sha256"] is None,
              "HEADER_DRIFT")
        rows=db.execute(
            "SELECT attempt_id,candidate_id,state,receipt_sha,receipt_json FROM f_attempts WHERE batch_id=? ORDER BY attempt_id",
            (batch_id,)).fetchall()
        _need(len(rows)==header["denominator"]
              and [x["attempt_id"] for x in header["manifest"]]
                  ==[row[0] for row in rows],"ATTEMPT_CENSUS_DRIFT")
        evidence=[]
        for identifier,candidate,state,sha,raw in rows:
            obj=json.loads(raw)
            _check(obj)
            _need(sha==obj["receipt_sha256"]
                  and identifier==obj["attempt_id"]
                  and candidate==obj["candidate_id"]
                  and state==obj["state"]=="UNKNOWN"
                  and obj["source_status_sha256"]==header["source_status_sha256"]
                  and obj["policy_request_sha256"]==header["policy_request_sha256"]
                  and obj["policy_proposal_sha256"]==header["policy_proposal_sha256"]
                  and obj["source_ack_sha256"] is None
                  and obj["strategy_approval_sha256"] is None
                  and obj["factory_consumer_ack_sha256"] is None
                  and obj["lab_sha256"] is None
                  and obj["result_sha256"] is None
                  and obj["trading_authority"]=="NONE"
                  and obj["orders_created"]==0
                  and obj["paper_positions"]==0
                  and obj["actual_fills"] is None,
                  "ATTEMPT_TAMPER_OR_PROMOTION")
            evidence.append(obj["receipt_sha256"])
        body=dict(schema=RECEIPT_SCHEMA,batch_id=batch_id,
                  batch_header_sha256=header["receipt_sha256"],
                  attempt_count=len(rows),selected=0,denied=0,
                  unknown=len(rows),
                  attempt_receipt_shas=evidence,
                  attempt_set_sha256=digest(evidence),
                  status=SOURCE,source_ack_sha256=None,
                  strategy_approval_sha256=None,
                  factory_consumer_ack_sha256=None,
                  lab_sha256=None,result_sha256=None,
                  paper="NOT_ACTIVATED",trading_authority="NONE",
                  orders_created=0,paper_positions=0,actual_fills=None)
        return {**body,"receipt_sha256":digest(body)}
    finally:
        db.close()
