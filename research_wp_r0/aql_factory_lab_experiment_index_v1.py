"""F-LAB-1: additive immutable H registry cross-reference in existing Factory v2.

No fabricated E.v1 attempt list, no second registry, warehouse or Secretary.
The *same* existing isolated Factory E SQLite v2 owns the cross-reference and
Factory H package; the Core Secretary persists in its preexisting separate root.
JOIN PREPARED -> VERIFIED_WAIT can survive a process crash and recover.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, audit_store_layout, digest,
)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE

SCHEMA="aql.factory.lab.h.experiment-index.v1"
RECEIPT="aql.factory.lab.h.index-receipt.v1"
TABLE_INDEX="factory_h_experiment_links_v1"
HEX=re.compile(r"^[0-9a-f]{64}$")
IDS=re.compile(r"^[A-Za-z0-9_.:+-]{1,160}$")
ACKS=("source_ack_sha256","strategy_approval_sha256",
      "factory_consumer_ack_sha256","research_review_ack_sha256")
SIGNALS=("ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL","UNKNOWN")
FIELDS={
    "schema","experiment_id","input_sha256","source_query_sha256",
    "source_bytes_sha256","manifest_integrity_sha256",
    "strategy_definition_sha256","strategy_plugin_sha256","config_sha256",
    "scanner_policy_sha256","scanner_evaluator_code_sha256",
    "factory_code_sha256","cost_policy_sha256","decision_cutoff_ms",
    "coverage","expected_bars","observed_bars","missing_bars",
    "decision_counts","modeled_trades","unknown_trades",
    "package_sha256","result_sha256","lab_sha256",
    "run_sha256","decision_attempt_census_sha256",
    "decision_attempt_count","attempt_scope",
    "secretary_expected_sha256","historical_pit","holdout",
    "trading_authority","sha256",
}


def require(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_LAB_1_"+reason)


def seal(value):
    return {**value,"sha256":digest(value)}


def verified(value):
    require(type(value) is dict and _sha(value.get("sha256")) and
            value["sha256"]==digest({k:v for k,v in value.items()
                                      if k!="sha256"}),"SHA_OR_SHAPE")
    return value


def _sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _db(path):
    p=Path(path)
    require(p.is_file() and p.suffix==".sqlite","EXISTING_SQLITE_REQUIRED")
    require(audit_store_layout(p)["layout_version"]==2,"LAYOUT_V2_REQUIRED")
    return p


def _con(path):
    con=sqlite3.connect(path,timeout=15)
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _load_package(con,experiment_id):
    row=con.execute(
        f"SELECT canonical_sha256,document,immutable FROM {TABLE} "
        "WHERE experiment_id=?",(experiment_id,)).fetchone()
    require(row is not None,"FACTORY_RESULT_NOT_FOUND")
    raw=json.loads(row[1])
    require(row[2]==1 and raw.get("experiment_id")==experiment_id
            and verified(raw)["sha256"]==row[0],"H_PACKAGE_MUTATED")
    return raw


def _decision_attempt_census(experiment_id,events):
    # Attempt ID means one actual Scanner closed-bar decision slot; never
    # masquerades as a strategy-family F2 attempt, fill or approved trial.
    return digest([{
        "attempt_id":digest({
            "experiment_id":experiment_id,
            "bar_open_ms":e["bar_open_ms"],
            "scanner_event_sha256":e["scanner_event_sha256"],
        }),
        "signal_state":e["signal_state"],
        "execution_state":e["execution_state"],
    } for e in events])


def build_link(packet,package,result,secretary):
    from research_wp_r0.aql_core_h_research_secretary_v1 import (
        build_generic_research_result_route)
    expected=build_generic_research_result_route(packet,package,result)
    require(secretary==expected and
            expected["state"]=="WAIT_RESEARCH_REVIEW" and
            all(expected[k] is None for k in ACKS) and
            expected["trading_authority"]=="NONE","SECRETARY_WAIT_AND_ACK")
    led=verified(package["trade_event_ledger"])
    lab=verified(package["scientific_lab"])
    cohort=led["cohort"]
    counts=led["decision_counts"]
    require(type(counts) is dict and set(counts)<=set(SIGNALS)
            and all(type(x) is int and x>=0 for x in counts.values())
            and sum(counts.values())==cohort["expected_bars"]
            and len(led["events"])==cohort["expected_bars"]
            and cohort["observed_bars"]+cohort["missing_bars"]==
                cohort["expected_bars"]
            and lab["ledger_sha256"]==led["sha256"]
            and lab["cohort"]==cohort
            and all(led["cohort"][key]>=0 for key in (
                "modeled_trades","unknown_trades")),"DENOMINATORS")
    body={
        "schema":SCHEMA,"experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "source_query_sha256":packet["source_query_sha256"],
        "source_bytes_sha256":packet["source_bytes_sha256"],
        "manifest_integrity_sha256":packet["manifest_integrity_sha256"],
        "strategy_definition_sha256":packet["strategy_definition_sha256"],
        "strategy_plugin_sha256":packet["strategy_plugin_sha256"],
        "config_sha256":packet["config_sha256"],
        "scanner_policy_sha256":packet["scanner_policy_sha256"],
        "scanner_evaluator_code_sha256":packet["scanner_evaluator_code_sha256"],
        "factory_code_sha256":packet["factory_code_sha256"],
        "cost_policy_sha256":package["factory_report"]["cost_policy_sha256"],
        "decision_cutoff_ms":packet["decision_cutoff_ms"],
        "coverage":cohort["coverage"],
        "expected_bars":cohort["expected_bars"],
        "observed_bars":cohort["observed_bars"],
        "missing_bars":cohort["missing_bars"],
        "decision_counts":{k:counts.get(k,0) for k in SIGNALS},
        "modeled_trades":cohort["modeled_trades"],
        "unknown_trades":cohort["unknown_trades"],
        "package_sha256":package["sha256"],
        "result_sha256":result["result_sha256"],
        "lab_sha256":lab["sha256"],
        "run_sha256":digest({
            "experiment_id":packet["experiment_id"],
            "input_sha256":packet["sha256"],
            "package_sha256":package["sha256"],
            "result_sha256":result["result_sha256"],
        }),
        "decision_attempt_census_sha256":_decision_attempt_census(
            packet["experiment_id"],led["events"]),
        "decision_attempt_count":len(led["events"]),
        "attempt_scope":"SCANNER_DECISION_SLOTS_NOT_F2_TRIALS",
        "secretary_expected_sha256":expected["receipt_sha256"],
        "historical_pit":"NOT_ATTESTED",
        "holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE",
    }
    return seal(body)


def _table(con):
    con.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_INDEX} (
      experiment_id TEXT PRIMARY KEY,
      link_sha256 TEXT NOT NULL,
      link_json TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('PREPARED','VERIFIED_WAIT'))
    )""")


def _index_required(con):
    require(con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE_INDEX,)).fetchone() is not None,"INDEX_NOT_INITIALIZED")


def _existing(con,experiment_id):
    row=con.execute(f"SELECT link_sha256,link_json,status FROM {TABLE_INDEX} "
                    "WHERE experiment_id=?",(experiment_id,)).fetchone()
    if row is None:
        return None
    value=json.loads(row[1])
    require(set(value)==FIELDS and value["experiment_id"]==experiment_id
            and verified(value)["sha256"]==row[0] and
            row[2] in ("PREPARED","VERIFIED_WAIT"),"INDEX_MUTATED")
    return value,row[2]


def _validate_link(con,link):
    require(set(link)==FIELDS and type(link["experiment_id"]) is str
            and IDS.fullmatch(link["experiment_id"]) is not None
            and link["experiment_id"].startswith("RESEARCH-H-GENERIC-")
            and all(_sha(link[k]) for k in (
                "input_sha256","source_query_sha256","source_bytes_sha256",
                "manifest_integrity_sha256","strategy_definition_sha256",
                "strategy_plugin_sha256","config_sha256",
                "scanner_policy_sha256","scanner_evaluator_code_sha256",
                "factory_code_sha256","cost_policy_sha256",
                "package_sha256","result_sha256","lab_sha256",
                "run_sha256","decision_attempt_census_sha256",
                "secretary_expected_sha256"))
            and type(link["decision_cutoff_ms"]) is int
            and link["decision_cutoff_ms"]>=0
            and link["coverage"] in ("COMPLETE","PARTIAL","UNKNOWN")
            and link["historical_pit"]=="NOT_ATTESTED"
            and link["holdout"]=="SEALED_UNOPENED"
            and link["trading_authority"]=="NONE"
            and link["attempt_scope"]=="SCANNER_DECISION_SLOTS_NOT_F2_TRIALS"
            and type(link["decision_attempt_count"]) is int
            and link["decision_attempt_count"]>=1,"LINK_SCOPE")
    package=_load_package(con,link["experiment_id"])
    report=verified(package["factory_report"])
    led=verified(package["trade_event_ledger"])
    lab=verified(package["scientific_lab"])
    review=verified(package["secretary_research_receipt"])
    require(package["sha256"]==link["package_sha256"]
            and package["input_sha256"]==link["input_sha256"]
            and report["input_sha256"]==link["input_sha256"]
            and review["experiment_input_sha256"]==link["input_sha256"]
            and led["source_query_sha256"]==report["source_query_sha256"]==
                review["source_query_sha256"]==link["source_query_sha256"]
            and led["source_bytes_sha256"]==report["source_bytes_sha256"]==
                review["source_bytes_sha256"]==link["source_bytes_sha256"]
            and review["manifest_integrity_sha256"]==
                link["manifest_integrity_sha256"]
            and report["strategy_definition_sha256"]==
                review["strategy_definition_sha256"]==
                led["strategy_digest"]==link["strategy_definition_sha256"]
            and review["strategy_plugin_sha256"]==
                led["scanner_plugin_sha256"]==
                link["strategy_plugin_sha256"]
            and report["config_sha256"]==review["config_sha256"]==
                led["config_sha256"]==link["config_sha256"]
            and led["scanner_policy_sha256"]==
                review["scanner_signal_policy_sha256"]==
                link["scanner_policy_sha256"]
            and review["scanner_evaluator_code_sha256"]==
                link["scanner_evaluator_code_sha256"]
            and report["factory_code_sha256"]==
                review["factory_code_sha256"]==
                led["code_sha256"]==link["factory_code_sha256"]
            and report["cost_policy_sha256"]==
                review["cost_policy_sha256"]==
                led["policy_sha256"]==link["cost_policy_sha256"]
            and report["decision_cutoff_ms"]==
                review["decision_cutoff_ms"]==link["decision_cutoff_ms"]
            and report["result_sha256"]==review["result_sha256"]==
                link["result_sha256"]
            and report["lab_sha256"]==review["lab_sha256"]==
                lab["sha256"]==link["lab_sha256"]
            and lab["ledger_sha256"]==led["sha256"]
            and review["ledger_sha256"]==led["sha256"]
            and link["run_sha256"]==digest({
                "experiment_id":link["experiment_id"],
                "input_sha256":link["input_sha256"],
                "package_sha256":link["package_sha256"],
                "result_sha256":link["result_sha256"],
            })
            and link["decision_attempt_count"]==len(led["events"])
            and link["decision_attempt_census_sha256"]==
                _decision_attempt_census(link["experiment_id"],led["events"]),
            "H_PARENT_DRIFT")
    require(led["cohort"]["coverage"]==link["coverage"]
            and led["cohort"]["expected_bars"]==link["expected_bars"]
            and led["cohort"]["observed_bars"]==link["observed_bars"]
            and led["cohort"]["missing_bars"]==link["missing_bars"]
            and led["cohort"]["modeled_trades"]==link["modeled_trades"]
            and led["cohort"]["unknown_trades"]==link["unknown_trades"]
            and {k:led["decision_counts"].get(k,0) for k in SIGNALS}==
                link["decision_counts"]
            and lab["ledger_sha256"]==led["sha256"],"H_COHORT_DRIFT")
    return package


def prepare_experiment_link(path,link):
    """Atomic idempotent PREPARE after Factory immutable H has been stored.

    Separately durable Core Secretary write may crash; retry finalize with
    same signed expected parent SHA, never duplicate/overwrite.
    """
    p=_db(path)
    verified(link)
    con=_con(p)
    try:
        con.execute("BEGIN IMMEDIATE")
        _table(con)
        require(set(link)==FIELDS,"LINK_FIELDS")
        _validate_link(con,link)
        prior=_existing(con,link["experiment_id"])
        require(prior is None or prior[0]==link,"IMMUTABLE_CONFLICT")
        if prior is None:
            con.execute(f"INSERT INTO {TABLE_INDEX} VALUES(?,?,?,?)",
                        (link["experiment_id"],link["sha256"],
                         json.dumps(link,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True,allow_nan=False),
                         "PREPARED"))
        con.commit()
        status="PREPARED" if prior is None else prior[1]
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return seal({"schema":RECEIPT,"experiment_id":link["experiment_id"],
                 "link_sha256":link["sha256"],"status":status,
                 "trading_authority":"NONE"})


def finalize_experiment_link(path,secretary_root,experiment_id):
    """Only Core-owned durable WAIT readback can advance the local link."""
    p=_db(path)
    con=_con(p)
    try:
        con.execute("BEGIN IMMEDIATE")
        _index_required(con)
        old=_existing(con,experiment_id)
        require(old is not None,"JOIN_NOT_PREPARED")
        link,status=old
        _validate_link(con,link)
        from research_wp_r0.aql_core_h_research_secretary_v1 import (
            read_generic_research_result_route)
        route=read_generic_research_result_route(
            secretary_root,experiment_id)
        require(route["receipt_sha256"]==link["secretary_expected_sha256"]
                and route["experiment_id"]==experiment_id
                and route["factory_package_sha256"]==link["package_sha256"]
                and route["scientific_lab_sha256"]==link["lab_sha256"]
                and route["state"]=="WAIT_RESEARCH_REVIEW"
                and all(route[k] is None for k in ACKS)
                and route["trading_authority"]=="NONE","SECRETARY_DRIFT")
        if status=="PREPARED":
            con.execute(f"UPDATE {TABLE_INDEX} SET status='VERIFIED_WAIT' "
                        "WHERE experiment_id=? AND status='PREPARED'",
                        (experiment_id,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return get_experiment_link(p,experiment_id,secretary_root=secretary_root)


def get_experiment_link(path,experiment_id,*,secretary_root=None):
    p=_db(path)
    con=_con(p)
    try:
        _index_required(con)
        old=_existing(con,experiment_id)
        require(old is not None,"JOIN_NOT_FOUND")
        link,status=old
        _validate_link(con,link)
    finally:
        con.close()
    if status=="VERIFIED_WAIT":
        require(secretary_root is not None,"SECRETARY_ROOT_REQUIRED")
        from research_wp_r0.aql_core_h_research_secretary_v1 import (
            read_generic_research_result_route)
        route=read_generic_research_result_route(secretary_root,experiment_id)
        require(route["receipt_sha256"]==link["secretary_expected_sha256"]
                and route["factory_package_sha256"]==link["package_sha256"]
                and route["scientific_lab_sha256"]==link["lab_sha256"]
                and route["state"]=="WAIT_RESEARCH_REVIEW"
                and all(route[k] is None for k in ACKS),"SECRETARY_READBACK")
    body={"schema":RECEIPT,"experiment_id":experiment_id,
          "link_sha256":link["sha256"],"status":status,
          "trading_authority":"NONE"}
    return {**body,"sha256":digest(body),"link":link}


def list_experiment_links(path,*,secretary_root=None):
    p=_db(path)
    con=_con(p)
    try:
        _index_required(con)
        ids=[x[0] for x in con.execute(
            f"SELECT experiment_id FROM {TABLE_INDEX} ORDER BY experiment_id"
        ).fetchall()]
    finally:
        con.close()
    return [get_experiment_link(p,experiment_id,secretary_root=secretary_root)
            for experiment_id in ids]
