"""Package H Factory/Lab integrated research-only build and immutable replay.

The canonical Factory v2 module still computes validated causal rules and owns
the sealed store. This adapter binds its *same* input/results to a trace ledger,
descriptive Lab report and non-operational Secretary-ready envelope. No E: I/O.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest,ResultsStoreError,audit_store_layout,
)
from research_wp_r0.aql_factory_h_scientific_lab_v1 import (
    evaluate_immutable_ledger,secretary_research_receipt,
)

SCHEMA="aql.factory.h.research-package.v1"
TABLE="factory_h_research_results_v1"


def _need(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_H_"+reason)


def _bind(packet,factory,ledger,lab,secretary):
    _need(factory["input_sha256"]==packet["sha256"]
          and ledger["input_sha256"]==packet["sha256"]
          and lab["ledger_sha256"]==ledger["sha256"]
          and secretary["experiment_sha256"]==factory["experiment_sha256"]
          and secretary["lab_sha256"]==lab["sha256"]
          and secretary["result_sha256"]==factory["result_sha256"]
          and secretary["source_ack_sha256"] is None
          and secretary["strategy_approval_sha256"] is None
          and secretary["factory_consumer_ack_sha256"] is None
          and secretary["trading_authority"]=="NONE",
          "SOURCE_RESULT_RESEARCH_AUTHORITY_DRIFT")


def _store_package(path, body):
    """Single isolated v2 SQLite transaction; immutable SHA+bytes replay."""
    doc={**body,"sha256":digest(body)}
    encoded=json.dumps(doc,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)
    conn=sqlite3.connect(path,timeout=15)
    try:
        conn.execute("PRAGMA busy_timeout=15000")
        _need(conn.execute("PRAGMA user_version").fetchone()[0]==2,
              "EXISTING_LAYOUT_V2_REQUIRED")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
            experiment_id TEXT PRIMARY KEY, canonical_sha256 TEXT NOT NULL,
            document TEXT NOT NULL, immutable INTEGER NOT NULL CHECK(immutable=1)
        )""")
        old=conn.execute(
            f"SELECT canonical_sha256,document,immutable FROM {TABLE} "
            "WHERE experiment_id=?",
            (doc["experiment_id"],)).fetchone()
        _need(old is None or old==(doc["sha256"],encoded,1),
              "IMMUTABLE_PACKAGE_CONFLICT")
        if old is None:
            conn.execute(f"INSERT INTO {TABLE} VALUES(?,?,?,1)",
                         (doc["experiment_id"],doc["sha256"],encoded))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    reader=sqlite3.connect(path,timeout=15)
    try:
        db=reader.execute(
            f"SELECT canonical_sha256,document,immutable FROM {TABLE} "
            "WHERE experiment_id=?",(doc["experiment_id"],)).fetchone()
        _need(db==(doc["sha256"],encoded,1) and
              digest(json.loads(db[1]))==digest(doc),
              "IMMUTABLE_PACKAGE_READBACK")
    finally:
        reader.close()
    return doc["sha256"],("STORED_IMMUTABLE" if old is None
                          else "REPLAY_IDENTICAL")


def run_factory_h_research(packet, store_path):
    """One complete Factory/Lab research slice; store must be pre-initialized."""
    from research_wp_r0.aql_factory_h_trade_event_ledger_v1 import (
        build_trade_event_ledger,verify_trade_event_ledger,
    )
    from research_wp_r0.aql_factory_f_f2_recovery_research_v2 import (
        validate_recovery_research_input,run_recovery_research_v2,
    )
    validate_recovery_research_input(packet)
    path=Path(store_path)
    _need(path.is_file() and path.suffix==".sqlite" and
          audit_store_layout(path)["layout_version"]==2,
          "ISOLATED_LAYOUT_V2_REQUIRED")
    factory=run_recovery_research_v2(packet,path)
    ledger=build_trade_event_ledger(packet)
    lab=evaluate_immutable_ledger(ledger)
    secretary=secretary_research_receipt(
        packet=packet,factory_report=factory,ledger=ledger,lab=lab)
    _bind(packet,factory,ledger,lab,secretary)
    body={
        "schema":SCHEMA,"experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "factory_experiment_sha256":factory["experiment_sha256"],
        "factory_result_sha256":factory["result_sha256"],
        "factory_lab_sha256":factory["lab_sha256"],
        "trade_event_ledger":ledger,
        "scientific_lab":lab,
        "secretary_research_receipt":secretary,
        "source_graph_sha256":ledger["source_graph_sha256"],
        "policy_sha256":ledger["policy_sha256"],
        "zero_cost_diagnostic":all(
            __import__("decimal").Decimal(v)==0
            for v in packet["operator_policy"]["costs"].values()),
        "trading_authority":"NONE",
        "holdout":"SEALED_UNOPENED",
        "historical_pit":"NOT_ATTESTED",
        "f5":"BLOCKED_EXTERNAL_INPUT",
    }
    identity,status=_store_package(path,body)
    reply={
        "schema":"aql.factory.h.research-package-result.v1",
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "package_sha256":identity,
        "trade_ledger_sha256":ledger["sha256"],
        "scientific_lab_sha256":lab["sha256"],
        "secretary_receipt_sha256":secretary["sha256"],
        "factory_experiment_sha256":factory["experiment_sha256"],
        "factory_result_sha256":factory["result_sha256"],
        "factory_lab_sha256":factory["lab_sha256"],
        "zero_cost_diagnostic":body["zero_cost_diagnostic"],
        "store_status":status,
        "factory_store_status":factory["store_status"],
        "trading_authority":"NONE",
        "f5":"BLOCKED_EXTERNAL_INPUT",
        "paper":"NOT_ACTIVATED",
        "holdout":"SEALED_UNOPENED",
    }
    return {**reply,"receipt_sha256":digest(reply)}
