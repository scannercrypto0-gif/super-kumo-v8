"""Factory owner F2_RECOVERY_EVIDENCE.v1: diagnostic-only original-source gate.

Does not synthesize missing canonical F2 report or bypass signed F5 gates.
Core #275 independently re-reads existing owner-local RawVault, stage,
warehouse, #245 native and #253 local month coverage. This consumer checks
the returned Core read-only receipts and one real monthly bar identity.
"""
from __future__ import annotations

import json
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError,digest,_sha
)
from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
    MONTHS,SCHEMA as LEGACY,validate_diagnostic_input,run_diagnostic,need
)

SCHEMA="aql.factory.f.f2-recovery-evidence-diagnostic-input.v1"
REPORT="aql.factory.f.f2-recovery-evidence-diagnostic-report.v1"
RECOVERY_SHA="0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"
CORE_SCHEMA="aql.core.f2-recovery-readonly-source.v1"
RECEIPT_FIELDS={
    "schema","month","dataset_id","status","recovery_file_sha256",
    "original_f2_report_sha256","source_zip_sha256",
    "manifest_integrity_sha256","warehouse_receipt_sha256",
    "core245_native_query_sha256","core253_local_query_sha256",
    "dual_map_sha256","bar_count","start_ms","end_exclusive_ms",
    "decision_cutoff_ms","no_write_tree_fingerprint_sha256",
    "historical_pit","source_ack_sha256","strategy_approval_sha256",
    "factory_consumer_ack_sha256","secretary_state","trading_authority",
    "receipt_sha256"
}


def verified_core_receipts(recovery):
    """Return SHA ancestry only for 10 Core-owned read-only verified receipts.

    A sealed local mapping alone never suffices. Owner must use actual Core
    read_original_recovery(...)/read_recovered_diagnostic private source
    readback with protected E: root. This check does NOT claim issuer rights.
    """
    need(type(recovery) is dict and set(recovery)=={
         "schema","original_f2_report_sha256",
         "recovery_evidence_file_sha256","source_rights",
         "readback_receipts"} and
         recovery["schema"]=="F2_RECOVERY_EVIDENCE.v1" and
         recovery["original_f2_report_sha256"] is None and
         recovery["recovery_evidence_file_sha256"]==RECOVERY_SHA and
         recovery["source_rights"]=="OWNER_LOCAL_NOT_INDEPENDENT",
         "RECOVERY_CONTRACT_OR_F2_IMPERSONATION")
    docs=recovery["readback_receipts"]
    need(type(docs) is list and len(docs)==10 and
         {row.get("month") for row in docs if type(row) is dict}==set(MONTHS),
         "RECOVERY_EXACT_TEN_MONTHS")
    parents={}
    count=0
    for receipt in docs:
        need(type(receipt) is dict and set(receipt)==RECEIPT_FIELDS,
             "RECOVERY_CORE_RECEIPT_FIELDS")
        month=receipt["month"]
        source=receipt["source_zip_sha256"]
        native=receipt["core245_native_query_sha256"]
        local=receipt["core253_local_query_sha256"]
        manifest=receipt["manifest_integrity_sha256"]
        stage=receipt["warehouse_receipt_sha256"]
        dual=receipt["dual_map_sha256"]
        need(receipt["schema"]==CORE_SCHEMA
             and receipt["status"]=="SOURCE_BACKED_RECOVERY_READBACK_ONLY"
             and receipt["recovery_file_sha256"]==RECOVERY_SHA
             and receipt["original_f2_report_sha256"] is None
             and receipt["historical_pit"]=="NOT_ATTESTED"
             and receipt["secretary_state"]=="NOT_ENQUEUED"
             and receipt["trading_authority"]=="NONE"
             and receipt["source_ack_sha256"] is None
             and receipt["strategy_approval_sha256"] is None
             and receipt["factory_consumer_ack_sha256"] is None
             and all(_sha(v) for v in
                     (source,native,local,manifest,stage,dual,
                      receipt["no_write_tree_fingerprint_sha256"]))
             and native!=local and
             _sha(receipt["receipt_sha256"]) and
             digest({k:v for k,v in receipt.items()
                     if k!="receipt_sha256"})==receipt["receipt_sha256"],
             "RECOVERY_CORE_READBACK_SEAL_OR_AUTHORITY_DRIFT")
        from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
            _month_boundaries
        )
        start,end=_month_boundaries(month)
        need(receipt["dataset_id"]=="BINANCE-SPOT-BTCUSDT-15M-"+month+"-F-v1"
             and receipt["start_ms"]==start
             and receipt["end_exclusive_ms"]==end
             and type(receipt["decision_cutoff_ms"]) is int
             and receipt["decision_cutoff_ms"]>=end
             and receipt["bar_count"]==(end-start)//900000,
             "RECOVERY_SOURCE_MONTH_AND_CUTOFF")
        count+=receipt["bar_count"]
        parents[month]={"source_sha256":source,"native_sha256":native,
                        "local_sha256":local,"manifest_sha256":manifest,
                        "warehouse_receipt_sha256":stage,
                        "dual_map_sha256":dual,
                        "readback_receipt_sha256":receipt["receipt_sha256"]}
    need(count==29376,"RECOVERY_TOTAL_29376")
    return parents


def validate_recovery_input(packet):
    need(type(packet) is dict and packet.get("schema")==SCHEMA and
         _sha(packet.get("sha256")) and
         digest({k:v for k,v in packet.items() if k!="sha256"})
         ==packet["sha256"],"RECOVERY_INPUT_SEAL")
    need(set(packet)=={
        "schema","sha256","experiment_id","local_source_mode","purpose",
        "original_f2_report_sha256","recovery_evidence_file_sha256",
        "recovery_core_receipts","source_manifest_sha256",
        "core_245_query_sha256","core_253_query_sha256",
        "operator_local_source_readback_sha256","strategy_definition_sha256",
        "config_sha256","code_sha256","environment_sha256",
        "strategy","admitted_months","attempts","trial_packet",
        "source_coverage","market","symbol","timeframe"},
         "RECOVERY_INPUT_FIELDS")
    need(packet["original_f2_report_sha256"] is None
         and packet["recovery_evidence_file_sha256"]==RECOVERY_SHA
         and type(packet["experiment_id"]) is str
         and packet["experiment_id"].startswith("DIAG-F4-RECOVERY-"),
         "RECOVERY_IDENTITY_NOT_F2_OR_F5")
    parents=verified_core_receipts({
        "schema":"F2_RECOVERY_EVIDENCE.v1",
        "original_f2_report_sha256":None,
        "recovery_evidence_file_sha256":packet["recovery_evidence_file_sha256"],
        "source_rights":"OWNER_LOCAL_NOT_INDEPENDENT",
        "readback_receipts":packet["recovery_core_receipts"]})
    # Cohort SHA names are *separate*, deterministic from actual Core receipts.
    native=digest([[month,parents[month]["native_sha256"]] for month in MONTHS])
    local=digest([[month,parents[month]["local_sha256"]] for month in MONTHS])
    manifest=digest([[month,parents[month]["manifest_sha256"]] for month in MONTHS])
    need(packet["core_245_query_sha256"]==native and
         packet["core_253_query_sha256"]==local and native!=local
         and packet["source_manifest_sha256"]==manifest,
         "RECOVERY_ACTUAL_CORE_RECEIPT_GRAPH")
    # Explicitly bind all source-derived census month rows to their own
    # owner-local recomputed source parent before a diagnostic Lab is allowed.
    need(type(packet["attempts"]) is list and
         all(type(row) is dict and
             (row.get("month") not in parents or
              row.get("source_receipt_sha256")==
                  parents[row["month"]]["source_sha256"])
             for row in packet["attempts"]),
         "RECOVERY_ATTEMPT_SOURCE_RECEIPT_SWAP")
    trial=packet["trial_packet"]
    need(type(trial) is dict and
         trial.get("diagnostic_month") in parents,
         "RECOVERY_FOCUS_MONTH")
    month=trial["diagnostic_month"]
    # Every eligible original-month attempt must refer to exactly the
    # checked Core source object for its own month; inventory-only receipts
    # remain locally marked UNKNOWN and are never treated as source files.
    need(trial.get("source_bytes_sha256")==parents[month]["source_sha256"]
         and packet["operator_local_source_readback_sha256"]==
             parents[month]["source_sha256"],
         "RECOVERY_FOCUS_ORIGINAL_BYTES")
    # Reuse every existing causal, cutoff, definition, 24-attempt, Feb/Aug and
    # trading-denial constraint. Never edit the strict legacy original F2 gate.
    legacy={k:v for k,v in packet.items()
            if k not in ("original_f2_report_sha256",
                         "recovery_evidence_file_sha256","recovery_core_receipts",
                         "sha256")}
    legacy["schema"]=LEGACY
    # This is solely an internal compatibility validation; it never becomes
    # an exported original F2 approval or canonical F2 source receipt.
    # Legacy structural validator's nonnull field is NEVER an F2 report pin:
    # this internal type adapter binds a derived, domain-separated diagnostic
    # graph hash. It is not emitted as a Core F2 report, and cannot be passed
    # to F5 validation.
    legacy["core_f2_report_sha256"]=digest({
        "schema":"aql.factory.f.internal-recovery-compatibility-parent.v1",
        "recovery_file_sha256":RECOVERY_SHA,
        "core_receipt_graph_sha256":digest(parents),
        "diagnostic_input_sha256":packet["sha256"]})
    legacy["sha256"]=digest(legacy)
    validate_diagnostic_input(legacy)
    return legacy,parents


def run_recovery_diagnostic(packet,store_path):
    legacy,parents=validate_recovery_input(packet)
    # Distinct experiment namespace and separate local-trust evidence body.
    result=run_diagnostic(legacy,store_path)
    body={
        "schema":REPORT,"status":"RECOVERY_DIAGNOSTIC_ONLY_NOT_F5",
        "experiment_id":packet["experiment_id"],
        "recovery_evidence_file_sha256":RECOVERY_SHA,
        "original_f2_report_sha256":None,
        "core_receipt_graph_sha256":digest(parents),
        "input_sha256":packet["sha256"],
        "lab_sha256":result["lab_sha256"],
        "experiment_sha256":result["experiment_sha256"],
        "result_sha256":result["result_sha256"],
        "attempt_count":result["attempt_count"],
        "feb_aug_inventory_unknown":result["feb_aug_inventory_unknown"],
        "modeled_count":result["modeled_count"],
        "unknown_count":result["unknown_count"],
        "costs":result["costs"],
        "store_status":result["store_status"],
        "factory_consumer_ack_sha256":None,
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "historical_pit":"NOT_ATTESTED",
        "independent_attestation":"NOT_ATTESTED",
        "trading_authority":"NONE","paper":"NOT_ACTIVATED",
        "orders_created":0,"positions":0,
        "holdout":"SEALED_UNOPENED"
    }
    return {**body,"receipt_sha256":digest(body)}
