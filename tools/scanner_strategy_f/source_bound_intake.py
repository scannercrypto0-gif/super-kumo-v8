"""Scanner F3: non-PIT Core F2 source-bound research bridge.

This is a custody + *independently signed policy* authorization boundary,
NOT a trading authorization. Its output is a bounded, complete historical
strategy×month×symbol census for Factory/Secretary, with admitted months
marked PENDING_RESEARCH_EVALUATION (not SELECTED). A missing or forged
Core F2 report never becomes a positive screening result.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
import re
from research_wp_r0.aql_core_f_bulk_source_v1 import verify_manifest,verify_coverage_ledger
from research_wp_r0.aql_core_f_private_f2_v1 import digest as core_digest
from tools.strategy_service_offline.common import Frozen,require
from tools.scanner_strategy_f.bulk_census import historical_bulk_intake_census
from tools.scanner_strategy_f.independent_policy_verification import verify_external_policy_approval

SCHEMA="aql.scanner-f.historical-source-bound-research-intake.v1"
ATTEMPT_SCHEMA="aql.scanner-f.historical-source-bound-research-attempt.v1"
SOURCE_SCHEMA="aql.core.f.private-raw-warehouse-dual-query-report.v1"
MONTHS=tuple(f"2024-{i:02d}" for i in range(1,13))
RETAINED=frozenset(("2024-02","2024-08"))
SHA=re.compile(r"^[0-9a-f]{64}$")


def verify_core_f2_report(report,manifest,coverage, *,
                          expected_report_sha256,external_source_authorization_sha256):
    """Verify canonical F2 source graph; separate independent source witness.

    Caller MUST pin source authority and expected F2 report SHA via a trusted
    channel distinct from report bytes. This function validates source graph,
    not publisher digital signature or the external custodian's identity.
    """
    require(type(report) is dict and report.get("schema")==SOURCE_SCHEMA
            and type(report.get("report_sha256")) is str
            and SHA.fullmatch(report["report_sha256"])
            and report["report_sha256"]==expected_report_sha256
            and core_digest({k:v for k,v in report.items()
                             if k!="report_sha256"})==report["report_sha256"],
            "F3_CORE_F2_REPORT_SHA_OR_SCHEMA")
    require(verify_manifest(manifest) and verify_coverage_ledger(manifest,coverage)
            and report.get("manifest_sha256")==manifest["manifest_sha256"]
            and report.get("f1_coverage_ledger_sha256")==coverage["coverage_ledger_sha256"]
            and type(external_source_authorization_sha256) is str
            and SHA.fullmatch(external_source_authorization_sha256)
            and report.get("authorization_document_sha256")
                ==external_source_authorization_sha256
            and report.get("provenance")
                =="CURRENT_PUBLISHER_TLS_CHECKSUM_OPERATOR_ATTESTED_NOT_HISTORICAL_ISSUER_SIGNATURE"
            and report.get("strategy_policy_approval")=="NOT_ATTESTED_BY_CORE"
            and report.get("secretary_historical_strategy_route")=="NOT_AUTHORIZED"
            and report.get("factory_consumer_ack") is None
            and report.get("historical_pit")=="NOT_ATTESTED"
            and report.get("trading_authority")=="NONE"
            and report.get("f2_new_admitted_count")==10
            and report.get("f2_previous_retained_inventory_only_count")==2,
            "F3_CORE_F2_SOURCE_AUTHORIZATION_AND_COVERAGE")
    entries=report.get("entries")
    require(type(entries) is list and len(entries)==10,
            "F3_CORE_F2_MISSING_NEW_MONTHS")
    expected=[m for m in MONTHS if m not in RETAINED]
    states={x["month"]:x["status"] for x in coverage["entries"]}
    require(all(states[m]=="ACCEPTED_PREFLIGHT" for m in expected)
            and all(states[m]=="RETAINED_PREVIOUSLY_PINNED" for m in RETAINED),
            "F3_CORE_F1_RETENTION_OR_COVERAGE")
    actual=[]
    for entry in entries:
        require(type(entry) is dict
                and set(entry)=={"month","state","source_sha256",
                    "checksum_file_sha256","csv_member_sha256",
                    "warehouse_receipt_sha256","core_245_native_price_query_sha256",
                    "core_253_local_query_sha256","dual_query_map_sha256",
                    "bars","historical_pit"},
                "F3_CORE_F2_ENTRY_FIELDS")
        month=entry["month"]
        require(month in expected and month not in actual
                and entry["state"]=="RAW_AND_DUAL_QUERY_READBACK"
                and entry["historical_pit"]=="NOT_ATTESTED"
                and entry["bars"]==monthrange(2024,int(month[-2:]))[1]*96
                and all(type(entry[k]) is str and SHA.fullmatch(entry[k])
                    for k in ("source_sha256","checksum_file_sha256",
                        "csv_member_sha256","warehouse_receipt_sha256",
                        "core_245_native_price_query_sha256",
                        "core_253_local_query_sha256","dual_query_map_sha256"))
                and entry["core_245_native_price_query_sha256"]
                    !=entry["core_253_local_query_sha256"],
                "F3_CORE_F2_SOURCE_DUAL_QUERY_OR_BAR_DRIFT")
        original=next(x for x in coverage["entries"] if x["month"]==month)
        require(entry["source_sha256"]==original["archive_sha256"]
                and entry["checksum_file_sha256"]==original["checksum_file_sha256"],
                "F3_CORE_F1_F2_ORIGINAL_SHA_DRIFT")
        actual.append(month)
    require(actual==expected,"F3_CORE_F2_MONTH_ORDER_OR_DENOMINATOR")
    return {e["month"]:e for e in entries}


def bind_original_research_census(
    manifest,coverage,policy_draft,proposal,approval_request,work_specs, *,
    core_f2_report,expected_core_f2_sha256,
    external_source_authorization_sha256,
    signed_owner_policy_approval, trusted_policy_keyring,observed_at_utc,
):
    """Exact F2 + independently signed policy, still no strategy SELECTED.

    A successful match is READY_FOR_INDEPENDENT_RESEARCH_SCREENING only.
    Scanner owner must next validate actual Core query bars, indicator/rule
    evaluation and strategy-specific historical approval before Secretary
    can enqueue a selected attempt. No acceptance by a metadata hash alone.
    """
    preflight=historical_bulk_intake_census(
        manifest,coverage,policy_draft,proposal,approval_request,work_specs)
    d=Frozen.restore(preflight).data
    from tools.scanner_strategy_f.policy_activation_request import make_historical_activation_request
    activation=make_historical_activation_request(
        policy_draft,proposal,approval_request,work_specs)
    approved=verify_external_policy_approval(
        signed_owner_policy_approval,activation,policy_draft,
        proposal,approval_request,work_specs,
        trusted_keyring=trusted_policy_keyring,observed_at_utc=observed_at_utc)
    original=verify_core_f2_report(
        core_f2_report,manifest,coverage,
        expected_report_sha256=expected_core_f2_sha256,
        external_source_authorization_sha256=external_source_authorization_sha256)
    attempts=[]
    for item in d["attempts"]:
        old=Frozen.restore(item).data
        month=old["month"]
        row=original.get(month)
        # Even an independently approved policy and proven F2 custody
        # do not by themselves constitute strategy selection.
        attempts.append(Frozen.build({
            "schema":ATTEMPT_SCHEMA,
            "month":month,
            "strategy_id":old["strategy_id"],
            "strategy_version":old["strategy_version"],
            "symbol":"BTCUSDT",
            "market":"BINANCE:SPOT:USDT",
            "timeframe":"15m",
            "source_manifest_sha256":manifest["manifest_sha256"],
            "f1_coverage_sha256":coverage["coverage_ledger_sha256"],
            "core_f2_report_sha256":core_f2_report["report_sha256"] if row else None,
            "original_source_sha256":row["source_sha256"] if row else None,
            "warehouse_receipt_sha256":row["warehouse_receipt_sha256"] if row else None,
            "core245_native_query_sha256":row["core_245_native_price_query_sha256"] if row else None,
            "core253_local_query_sha256":row["core_253_local_query_sha256"] if row else None,
            "dual_query_map_sha256":row["dual_query_map_sha256"] if row else None,
            "policy_approval_sha256":approved["sha256"],
            "work235_config_digest":old["work235_config_digest"],
            "native15m_config_digest":old["native15m_config_digest"],
            "strategy_definition_digest":old["strategy_definition_digest"],
            "dna_digest":old["dna_digest"],
            "expected_bar_count":old["expected_bar_count"],
            "status":"PENDING_RESEARCH_EVALUATION" if row else "UNKNOWN_RETAINED_NOT_READBACK",
            "historical_pit":"NOT_ATTESTED",
            "source_ack_sha256":None,
            "strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None,
            "trading_authority":"NONE",
        }).receipt())
    require(len(attempts)==24
            and sum(x["payload"]["status"]=="PENDING_RESEARCH_EVALUATION"
                    for x in attempts)==20
            and sum(x["payload"]["status"]=="UNKNOWN_RETAINED_NOT_READBACK"
                    for x in attempts)==4,
            "F3_SOURCE_BOUND_ATTEMPT_CENSUS")
    return Frozen.build({
        "schema":SCHEMA,
        "source_manifest_sha256":manifest["manifest_sha256"],
        "f1_coverage_sha256":coverage["coverage_ledger_sha256"],
        "core_f2_report_sha256":core_f2_report["report_sha256"],
        "external_source_authorization_sha256":external_source_authorization_sha256,
        "verified_owner_policy_receipt_sha256":approved["sha256"],
        "policy_draft_sha256":Frozen.restore(policy_draft).sha256,
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "strategy_count":d["strategy_count"],
        "month_count":12,
        "attempt_count":24,
        "ready_for_independent_research_screening":20,
        "unknown_retained":4,
        "selected":0,
        "attempts":attempts,
        "secretary_state":"NOT_ENQUEUED",
        "factory_consumer_ack_sha256":None,
        "factory_lab":"NOT_EVALUATED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    }).receipt()
