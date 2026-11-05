"""Scanner F3 -> Factory F4 fail-closed bulk historical intake census.

The available source records are Core F0/F1 PRIVATE PREFLIGHT ONLY, never
independent publisher authority, RAW admission or strategy approval. No
historical selected-positive or Secretary enqueue can be issued by this API.
"""
from __future__ import annotations

from research_wp_r0.aql_core_f_bulk_source_v1 import verify_manifest, verify_coverage_ledger
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f.retrospective_policy import (
    historical_route_gate, verify_retrospective_policy_draft,
)

SCHEMA="aql.scanner-f.historical-bulk-research-intake.v1"
ATTEMPT_SCHEMA="aql.scanner-f.historical-bulk-attempt.v1"
COMPLETE_SET=tuple(f"2024-{i:02d}" for i in range(1,13))
STATES=("ACCEPTED_PREFLIGHT","REJECTED_QUARANTINED",
        "MISSING_SOURCE","RETAINED_PREVIOUSLY_PINNED")


def historical_bulk_intake_census(
    manifest,coverage_ledger,policy_draft,proposal,approval_request,work_specs,
    *, core_custody=None, core_245_query=None, core_253_query=None,
    independent_policy_approval=None, source_ack=None,
):
    """Read-only sanitized F3/Factory receipt; 1 attempt per strategy × month × symbol.

    Missing/retained/rejected and accepted-prefight-only never become SELECTED.
    Caller-supplied opaque evidence is refused until independently authenticated
    Core F2/PM policy approval verifier is available.
    """
    p=verify_retrospective_policy_draft(
        policy_draft,proposal,approval_request,work_specs)
    historical_route_gate(
        policy_draft,proposal,approval_request,work_specs,
        core_source_authentication=core_custody,
        core_245_query=core_245_query,core_253_query=core_253_query,
        owner_policy_approval=independent_policy_approval,source_ack=source_ack,
    )
    require(verify_manifest(manifest)
            and verify_coverage_ledger(manifest,coverage_ledger),
            "F_CORE_MANIFEST_OR_COVERAGE_TAMPER")
    d=p.data
    require(manifest["source"]=="BINANCE_SPOT_BTCUSDT_NATIVE_15M"
            and manifest["interval_ms"]==900000
            and manifest["target_first"]=="2024-01"
            and manifest["target_last"]=="2024-12"
            and [x["month"] for x in manifest["rows"]]==list(COMPLETE_SET)
            and set(d["target_months"])==set(COMPLETE_SET)
            and coverage_ledger["manifest_sha256"]==manifest["manifest_sha256"]
            and coverage_ledger["raw_admission"]=="NOT_CLAIMED"
            and coverage_ledger["warehouse_query"]=="NOT_CLAIMED"
            and coverage_ledger["core_245_native_query_sha256"] is None
            and coverage_ledger["core_253_local_query_sha256"] is None
            and coverage_ledger["secretary_historical_route"]=="NOT_AUTHORIZED"
            and coverage_ledger["historical_pit"]=="NOT_ATTESTED",
            "F_UNVERIFIED_SOURCE_OR_GRID")
    # Verify each row really belongs to the immutable original Core F month
    # and that retained Feb/Aug cannot be impersonated as a new source.
    require(len(coverage_ledger["entries"])==len(manifest["rows"])
            and all(entry["month"]==row["month"]
                    and (row["inventory_status"]!="RETAINED_PREVIOUSLY_PINNED"
                         or entry["status"]=="RETAINED_PREVIOUSLY_PINNED")
                    for entry,row in zip(coverage_ledger["entries"],manifest["rows"])),
            "F_CORE_COVERAGE_ROW_IDENTITY_DRIFT")
    expected_status={"ACCEPTED_PREFLIGHT":"UNKNOWN_PREFLIGHT_ONLY",
                     "REJECTED_QUARANTINED":"QUARANTINED",
                     "MISSING_SOURCE":"UNKNOWN_MISSING_SOURCE",
                     "RETAINED_PREVIOUSLY_PINNED":"UNKNOWN_RETAINED_NOT_READBACK"}
    attempts=[]
    for s in d["strategy_identity"]:
        for row in coverage_ledger["entries"]:
            month=row["month"]
            state=row["status"]
            require(month in d["target_months"] and state in STATES,
                    "F_MONTH_OR_CENSUS_SCOPE")
            attempts.append(Frozen.build({
                "schema":ATTEMPT_SCHEMA,
                "strategy_id":s["strategy_id"],
                "strategy_version":s["strategy_version"],
                "work235_spec_sha256":s["work235_spec_sha256"],
                "work235_config_digest":s["work235_config_digest"],
                "native15m_policy_sha256":s["scanner_native15m_policy_sha256"],
                "native15m_config_digest":s["scanner_native15m_config_digest"],
                "strategy_definition_digest":s["definition_digest"],
                "dna_digest":s["dna_digest"],
                "symbol":"BTCUSDT","market":"BINANCE:SPOT:USDT",
                "timeframe":"15m","month":month,
                "expected_bar_count":row["expected_native_15m_bars"],
                "core_source_manifest_sha256":manifest["manifest_sha256"],
                "core_source_coverage_sha256":coverage_ledger["coverage_ledger_sha256"],
                "prefight_source_status":state,
                "source_archive_sha256":row["archive_sha256"],
                "source_checksum_file_sha256":row["checksum_file_sha256"],
                "source_preflight_sha256":row["preflight_receipt_sha256"],
                "independently_authenticated_issuer":False,
                "core_raw_readback_receipt_sha256":None,
                "core_245_native_query_sha256":None,
                "core_253_local_query_sha256":None,
                "independent_policy_approval_sha256":None,
                "source_ack_sha256":None,
                "strategy_approval_sha256":None,
                "factory_consumer_ack_sha256":None,
                "attempt_status":expected_status[state],
                "historical_pit":"NOT_ATTESTED",
                "trading_authority":"NONE",
            }).receipt())
    statuses={status:sum(x["payload"]["attempt_status"]==status for x in attempts)
              for status in expected_status.values()}
    total=len(attempts)
    require(total==len(d["strategy_identity"])*manifest["month_count"]
            and sum(statuses.values())==total,
            "F_INCOMPLETE_STRATEGY_MONTH_CENSUS")
    return Frozen.build({
        "schema":SCHEMA,
        "policy_draft_sha256":p.sha256,
        "core_manifest_sha256":manifest["manifest_sha256"],
        "core_coverage_ledger_sha256":coverage_ledger["coverage_ledger_sha256"],
        "source_status":"CORE_F1_PREFLIGHT_ONLY",
        "source_authentication":"NOT_INDEPENDENTLY_VERIFIED",
        "policy_status":"OWNER_PROVISIONAL_CONDITIONAL_A_NOT_APPROVAL_RECEIPT",
        "research_class":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "strategy_count":len(d["strategy_identity"]),
        "symbol_count":1,
        "months_censused":manifest["month_count"],
        "total_attempts":total,
        "attempt_status_census":statuses,
        "attempts":attempts,
        "selected_count":0,
        "core_245_native_query_sha256":None,
        "core_253_local_query_sha256":None,
        "independent_owner_approval_sha256":None,
        "source_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "factory_consumer_ack_sha256":None,
        "factory_lab":"NOT_EVALUATED",
        "paper_execution":"NOT_ACTIVATED",
        "holdout":"SEALED",
        "orders":0,"positions":0,"fills":None,
        "trading_authority":"NONE",
        "decision":"WAIT_CORE_F2_AND_INDEPENDENT_POLICY_APPROVAL",
    }).receipt()
