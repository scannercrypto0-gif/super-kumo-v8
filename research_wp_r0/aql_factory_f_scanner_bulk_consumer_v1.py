"""Factory F4 accepts exactly Scanner F3 source-preflight census into immutable store.

This is a *metadata consumer* of the actual Core F/Scanner F owner contracts,
never an authorization to execute a historical backtest. The source and
policy trust gates must separately succeed before Factory can issue ACK.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.bulk_census import historical_bulk_intake_census
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, register_experiment, read_experiment,
    ResultsStoreError, digest
)

RECEIPT="aql.factory.f.scanner-bulk-preflight-consumer.v1"
STATE={"UNKNOWN_PREFLIGHT_ONLY":"UNKNOWN",
       "UNKNOWN_RETAINED_NOT_READBACK":"UNKNOWN",
       "UNKNOWN_MISSING_SOURCE":"UNKNOWN",
       "QUARANTINED":"QUARANTINED"}


def consume_scanner_f_bulk_preflight(*, manifest,coverage_ledger,policy_draft,
                                     proposal,approval_request,work_specs,
                                     store_path,experiment_id,
                                     code_sha256,environment_sha256):
    """Rebuild Scanner F3 receipt from independent exact owner inputs.

    The existing immutable E experiment store is used; unknown source/query
    SHA stay null. The caller cannot provide a SELECTED or Lab-positive flag.
    """
    try:
        sealed=historical_bulk_intake_census(
            manifest,coverage_ledger,policy_draft,proposal,
            approval_request,work_specs)
        data=Frozen.restore(sealed).data
        policy=Frozen.restore(policy_draft)
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        raise ResultsStoreError("FACTORY_F_SCANNER_BULK_CONTRACT_INVALID") from exc
    if (data.get("schema")!="aql.scanner-f.historical-bulk-research-intake.v1"
        or data.get("source_status")!="CORE_F1_PREFLIGHT_ONLY"
        or data.get("policy_status")!="OWNER_PROVISIONAL_CONDITIONAL_A_NOT_APPROVAL_RECEIPT"
        or data.get("source_authentication")!="NOT_INDEPENDENTLY_VERIFIED"
        or data.get("decision")!="WAIT_CORE_F2_AND_INDEPENDENT_POLICY_APPROVAL"
        or data.get("research_class")!="RETROSPECTIVE_NON_PIT"
        or data.get("selected_count")!=0
        or data.get("core_245_native_query_sha256") is not None
        or data.get("core_253_local_query_sha256") is not None
        or data.get("source_ack_sha256") is not None
        or data.get("factory_consumer_ack_sha256") is not None
        or data.get("factory_lab")!="NOT_EVALUATED"
        or data.get("trading_authority")!="NONE"
        or data.get("orders")!=0):
        raise ResultsStoreError("FACTORY_F_PRE-FLIGHT_CANNOT_PROMOTE")
    trials=[]
    for sealed_attempt in data["attempts"]:
        row=Frozen.restore(sealed_attempt).data
        state=STATE.get(row["attempt_status"])
        if (state is None
            or row["source_ack_sha256"] is not None
            or row["strategy_approval_sha256"] is not None
            or row["factory_consumer_ack_sha256"] is not None
            or row["core_245_native_query_sha256"] is not None
            or row["core_253_local_query_sha256"] is not None
            or row["independent_policy_approval_sha256"] is not None):
            raise ResultsStoreError("FACTORY_F_FROZEN_ATTEMPT_PROMOTION")
        trials.append({
            "attempt_id":f"{row['strategy_id']}:{row['strategy_version']}:{row['month']}:{row['symbol']}",
            "candidate_id":f"{row['strategy_id']}:{row['strategy_version']}:{row['symbol']}",
            "state":state,
            "source_receipt_sha256":sealed_attempt["sha256"],
        })
    if len(trials)!=data["total_attempts"] or len({a["attempt_id"] for a in trials})!=len(trials):
        raise ResultsStoreError("FACTORY_F_INCOMPLETE_ATTEMPT_CENSUS")
    record=build_experiment(
        experiment_id=experiment_id,lane="HISTORICAL_SOURCE",
        source_status="HISTORICAL_SOURCE_BLOCKED",
        source_sha256=None,source_query_245_sha256=None,
        source_query_253_sha256=None,
        strategy_definition_sha256=None,config_sha256=None,
        code_sha256=code_sha256,environment_sha256=environment_sha256,
        parent_receipt_sha256=sealed["sha256"],
        attempts=trials,evidence_class="RETROSPECTIVE_NON_PIT")
    register_experiment(store_path,record)
    assert read_experiment(store_path,experiment_id)==record
    body={
        "schema":RECEIPT,
        "experiment_id":experiment_id,
        "experiment_sha256":record["sha256"],
        "scanner_bulk_receipt_sha256":sealed["sha256"],
        "core_manifest_sha256":manifest["manifest_sha256"],
        "core_coverage_sha256":coverage_ledger["coverage_ledger_sha256"],
        "scanner_policy_sha256":policy.sha256,
        "source_status":"HISTORICAL_SOURCE_BLOCKED",
        "status":"RESEARCH_CENSUS_STORED_NOT_EVALUATED",
        "month_count":data["months_censused"],
        "attempt_count":len(trials),
        "attempt_census":record["attempt_states"],
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "lab_receipt_sha256":None,
        "paper":"NOT_ACTIVATED",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
        "orders_created":0,
        "positions":0,
        "actual_fills":None,
    }
    return {**body,"receipt_sha256":digest(body)}
