"""F-LAB-3: restartable synthetic research lifecycle orchestration.

This is a thin checkpoint adapter, not a new research evaluator or datastore.
The preexisting Factory E v2/Factory H index and Core Secretary are authoritative.
No source acquisition, rights decisions, broker, PIT promotion or external retry.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import (
    run_factory_h_generic_research,
)
from research_wp_r0.aql_factory_lab_experiment_index_v1 import (
    build_link, prepare_experiment_link, finalize_experiment_link,
    get_experiment_link,
)
from research_wp_r0.aql_factory_lab_generic_paired_v1 import (
    build_generic_paired_lab,
)
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    build_generic_research_result_route, route_generic_research_result,
    read_generic_research_result_route,
)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
import sqlite3

SCHEMA="aql.integration.f-lab-3.lifecycle.v1"
STATES=("PLANNED","SOURCE_VERIFIED_SYNTHETIC","SCANNER_VERIFIED",
        "FACTORY_IMMUTABLE","LAB_EVALUATED","SECRETARY_WAIT")
ACKS=("source_ack_sha256","strategy_approval_sha256",
      "factory_consumer_ack_sha256","research_review_ack_sha256")

class LifecycleStop(ValueError):
    pass

def ensure(ok,reason):
    if not ok:
        raise LifecycleStop("F_LAB_3_"+reason)

def seal(value):
    return {**value,"sha256":digest(value)}

def verified(value):
    ensure(type(value) is dict and value.get("sha256")==digest(
        {k:v for k,v in value.items() if k!="sha256"}),"CHECKPOINT_TAMPER")
    return value

def _safe_dir(root, store_path, secretary_root):
    root=Path(root).resolve()
    store=Path(store_path).resolve()
    secretary=Path(secretary_root).resolve()
    ensure(root.is_dir() and not root.is_symlink(),"CHECKPOINT_ROOT_MISSING")
    ensure(root!=store and root!=secretary and
           root not in store.parents and root not in secretary.parents and
           secretary not in root.parents and store not in root.parents,
           "CHECKPOINT_OUTPUT_OVERLAP")
    return root

def identity(packet):
    ensure(type(packet) is dict and packet.get("sha256")==digest({
        k:v for k,v in packet.items() if k!="sha256"}),"SCANNER_PACKET_UNSEALED")
    ensure(packet.get("historical_pit")=="NOT_ATTESTED" and
           packet.get("trading_authority") in (None,"NONE") and
           packet.get("experiment_id","").startswith("RESEARCH-H-GENERIC-"),
           "RESEARCH_ONLY_SCOPE")
    query=packet.get("core_query")
    ensure(type(query) is dict and query.get("historical_pit")=="NOT_ATTESTED"
           and query.get("source_bytes_sha256")==packet.get("source_bytes_sha256")
           and query.get("query_sha256")==packet.get("source_query_sha256")
           and query.get("decision_cutoff_ms")==packet.get("decision_cutoff_ms"),
           "CORE_QUERY_LINEAGE")
    return digest({
        "experiment_id":packet["experiment_id"],
        "packet_sha256":packet["sha256"],
        "source_sha256":packet["source_bytes_sha256"],
        "query_sha256":packet["source_query_sha256"],
        "strategy_sha256":packet["strategy_definition_sha256"],
        "cost_sha256":packet["operator_cost_policy"]["sha256"],
        "cutoff_ms":packet["decision_cutoff_ms"],
    })

def _path(directory, experiment_id):
    ensure(all(c.isalnum() or c in "-_." for c in experiment_id)
           and len(experiment_id)<=160 and experiment_id.startswith(
               "RESEARCH-H-GENERIC-"),"EXPERIMENT_ID_UNSAFE")
    return directory/(experiment_id+".json")

def _read(path,run_id):
    if not path.exists():
        return None
    ensure(path.is_file() and not path.is_symlink(),"CHECKPOINT_NOT_FILE")
    saved=verified(json.loads(path.read_text("utf-8")))
    ensure(saved.get("schema")==SCHEMA and
           saved.get("run_sha256")==run_id and
           saved.get("experiment_id")==path.stem and
           saved.get("state") in STATES and
           saved.get("trading_authority")=="NONE" and
           saved.get("historical_pit")=="NOT_ATTESTED" and
           saved.get("source_type")=="SYNTHETIC_ONLY",
           "CHECKPOINT_IDENTITY_CONFLICT")
    return saved

def _advance(path,run_id,experiment_id,state,refs):
    prior=_read(path,run_id)
    if prior:
        ensure(STATES.index(state)>=STATES.index(prior["state"]),
               "CHECKPOINT_STATE_REGRESSION")
        merged=dict(prior["receipts"])
        for k,v in refs.items():
            ensure(k not in merged or merged[k]==v,"CHECKPOINT_RECEIPT_CONFLICT")
            merged[k]=v
    else:
        merged=dict(refs)
    body={
        "schema":SCHEMA,"run_sha256":run_id,"experiment_id":experiment_id,
        "state":state,"receipts":merged,
        "source_type":"SYNTHETIC_ONLY","historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE","holdout":"SEALED_UNOPENED",
    }
    completed=seal(body)
    if prior==completed:
        return completed
    scratch=path.with_suffix(".pending")
    # Refuse orphaned/inconsistent pending stage; a genuine crash before the
    # atomic replace can be retried only when pending bytes match desired state.
    if scratch.exists():
        pending=verified(json.loads(scratch.read_text("utf-8")))
        ensure(pending==completed or pending==prior,
               "CRASH_PENDING_CONFLICT")
        scratch.unlink()
    fd=os.open(scratch,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(completed,stream,sort_keys=True,separators=(",",":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch,path)
    finally:
        if scratch.exists():
            scratch.unlink()
    return completed

def _stored_package(db,experiment_id):
    with sqlite3.connect(db) as con:
        row=con.execute(
            f"SELECT document,canonical_sha256,immutable FROM {TABLE} WHERE experiment_id=?",
            (experiment_id,)).fetchone()
    ensure(row is not None and row[2]==1,"FACTORY_STORE_NOT_FOUND")
    package=json.loads(row[0])
    verified(package)
    ensure(package["sha256"]==row[1],"FACTORY_STORE_SHA_DRIFT")
    return package

def run_synthetic(*,packet,store_path,secretary_root,checkpoint_root,
                  stop_after=None):
    """Actual Factory H + Factory Lab + Core Secretary, no mocked stage APIs.

    Re-execution uses immutable Factory replay and Secretary/index idempotence.
    stop_after injects deterministic crash-boundary simulation for CI only.
    """
    ensure(stop_after is None or stop_after in STATES,
           "INVALID_STOP_BOUNDARY")
    root=_safe_dir(checkpoint_root,store_path,secretary_root)
    run_id=identity(packet)
    eid=packet["experiment_id"]
    path=_path(root,eid)
    prior=_read(path,run_id)
    if prior and prior["state"]=="SECRETARY_WAIT":
        item=get_experiment_link(store_path,eid,secretary_root=secretary_root)
        secretary=read_generic_research_result_route(secretary_root,eid)
        ensure(item["status"]=="VERIFIED_WAIT" and
               item["link"]["sha256"]==prior["receipts"]["factory_index_sha256"]
               and secretary["receipt_sha256"]==prior["receipts"]["secretary_sha256"]
               and secretary["state"]=="WAIT_RESEARCH_REVIEW" and
               all(secretary[a] is None for a in ACKS),
               "COMPLETED_READBACK_DRIFT")
        return prior

    def mark(state,refs=None):
        receipt=_advance(path,run_id,eid,state,refs or {})
        if state==stop_after:
            raise LifecycleStop("F_LAB_3_SIMULATED_CRASH_AT_"+state)
        return receipt

    if prior is None:
        mark("PLANNED",{"packet_sha256":packet["sha256"]})
    mark("SOURCE_VERIFIED_SYNTHETIC",
         {"source_query_sha256":packet["source_query_sha256"],
          "source_bytes_sha256":packet["source_bytes_sha256"]})
    mark("SCANNER_VERIFIED",{"scanner_packet_sha256":packet["sha256"]})

    # Factory H itself is immutable, replay must preserve the real package SHA.
    result=run_factory_h_generic_research(packet,store_path)
    package=_stored_package(store_path,eid)
    ensure(result["package_sha256"]==package["sha256"],
           "FACTORY_PACKAGE_MISMATCH")
    mark("FACTORY_IMMUTABLE",
         {"factory_package_sha256":package["sha256"],
          "factory_result_sha256":result["result_sha256"]})
    lab=package["scientific_lab"]
    verified(lab)
    ensure(lab["ledger_sha256"]==package["trade_event_ledger"]["sha256"],
           "SCIENTIFIC_LAB_LEDGER_DRIFT")
    mark("LAB_EVALUATED",{"lab_sha256":lab["sha256"]})

    expected=build_generic_research_result_route(packet,package,result)
    link=build_link(packet,package,result,expected)
    prepared=prepare_experiment_link(store_path,link)
    ensure(prepared["status"] in ("PREPARED","VERIFIED_WAIT"),
           "FACTORY_INDEX_PREPARE")
    secretary=route_generic_research_result(
        secretary_root,packet,package,result)
    ensure(secretary["receipt_sha256"]==expected["receipt_sha256"] and
           secretary["state"]=="WAIT_RESEARCH_REVIEW" and
           all(secretary[a] is None for a in ACKS),
           "SECRETARY_NOT_WAIT")
    done=finalize_experiment_link(store_path,secretary_root,eid)
    ensure(done["status"]=="VERIFIED_WAIT" and
           done["link_sha256"]==link["sha256"],
           "FACTORY_INDEX_FINALIZE")
    return mark("SECRETARY_WAIT",{
        "factory_index_sha256":link["sha256"],
        "secretary_sha256":secretary["receipt_sha256"],
    })

def run_paired(*,packet,package,result,store_path,secretary_root,
               checkpoint_root,observation_windows,
               comparison_definition_sha256,protocol_sha256,
               evaluation_asof_ms):
    """F-LAB-2 uses true pre-existing paired Lab, not new observation logic."""
    root=_safe_dir(checkpoint_root,store_path,secretary_root)
    run_id=identity(packet)
    done=_read(_path(root,packet["experiment_id"]),run_id)
    ensure(done is not None and done["state"]=="SECRETARY_WAIT",
           "PAIRED_REQUIRES_DURABLE_WAIT")
    paired=build_generic_paired_lab(
        store_path=store_path,secretary_root=secretary_root,
        experiment_id=packet["experiment_id"],packet=packet,
        package=package,base_result=result,
        observation_windows=observation_windows,
        comparison_definition_sha256=comparison_definition_sha256,
        protocol_sha256=protocol_sha256,
        evaluation_asof_ms=evaluation_asof_ms)
    ensure(paired["trading_authority"]=="NONE" and
           paired["observed_outcome_scope"]=="TEST_ONLY_DESCRIPTIVE_NO_ALPHA",
           "PAIRED_AUTHORITY_LEAK")
    return paired
