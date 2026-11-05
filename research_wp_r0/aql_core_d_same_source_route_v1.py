"""Core D: canonical Scanner-D source proof and fail-closed strategy eligibility.

The only permission here is to validate same-source SOFTWARE TEST ONLY.
No implicit Core-C strategy approval/ack, no live Paper, no historical PIT.
"""
from __future__ import annotations
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import _sha, _check
from research_wp_r0.aql_core_d_same_source_witness_v1 import create_core_d_research_witness
from tools.strategy_service_offline.common import Frozen

SCHEMA="aql.core.d.same-source-strategy-route-gate.v1"


def verify_scanner_d_for_core_route(core_root, *, warehouse, native_price_query,
                                    local_query, identity_map, core_d_witness,
                                    scanner_d_handoff, scanner_c_request,
                                    scanner_c_approval, scanner_run,
                                    scanner_nomination, work_spec, native_policy,
                                    source_ack=None):
    """Verify byte-for-byte Scanner consumed the verified Core source projection.

    Even an actual SAME-SOURCE software projection is not a governance/PIT
    signal. Core C source-ACK is a separate durable parent. Ineligible symbol,
    denied approval or non-eligible nomination produces WAIT (not auto-queue).
    """
    from tools.scanner_strategy_c.approval_route import (
        verify_strategy_route_request, verify_test_only_approval)
    from tools.scanner_strategy_d.core_query_adapter import _project
    _sha(warehouse,"receipt_sha256")
    _sha(identity_map,"identity_map_sha256")
    w=Frozen.restore(core_d_witness)
    x=w.data
    official=create_core_d_research_witness(
        core_root,warehouse,native_price_query,local_query,identity_map,
        scanner_source_id=x["scanner_source_id"],
        scanner_generation_id=x["scanner_generation_id"],
        scanner_market=x["scanner_market"],
        research_universe_members=x["research_universe_members"],
        synthetic_available_at_ms_by_bar=x["synthetic_available_at_ms_by_bar"])
    _check(official==core_d_witness,"CORE_D_ISSUER_WITNESS_DRIFT")
    raw,manifest,universe,projection=_project(
        core_root,warehouse,native_price_query,local_query,identity_map,
        core_d_witness)
    handoff=Frozen.restore(scanner_d_handoff)
    request=verify_strategy_route_request(
        scanner_c_request,work_spec,native_policy,scanner_c_approval,
        scanner_run,scanner_nomination,
        source_custody_receipt_sha256=warehouse["receipt_sha256"],
        core245_price_query_sha256=native_price_query["price_query_sha256"],
        core253_query_local_sha256=local_query["query_sha256"],
        source_zip_sha256=warehouse["source_zip_sha256"])
    approval=verify_test_only_approval(scanner_c_approval,work_spec,native_policy)
    nomination=Frozen.restore(scanner_nomination)
    run=Frozen.restore(scanner_run)
    h=handoff.data
    _check(h.get("schema")=="aql.scanner-d.same-core-source-handoff.v1"
           and h.get("research_same_source_projection_receipt")==projection.receipt()
           and h.get("scanner_raw_sha256")==projection.data["scanner_raw_sha256"]
           and h.get("source_zip_sha256")==warehouse["source_zip_sha256"]
           and h.get("source_binding_status")==
               "CORE_QUERY_TO_SCANNER_BYTES_VERIFIED_SOFTWARE_ONLY"
           and h.get("strategy_secretary_status")=="NOT_ENQUEUED"
           and h.get("trading_authority")=="NONE"
           and h.get("orders_created")==0
           and h.get("paper_positions")==0
           and h.get("actual_fills") is None,
           "D_SCANNER_HANDOFF_NOT_SAME_SOURCE")
    service=Frozen.restore(h["scanner_c_canonical_service_receipt"])
    _check(service.data.get("scanner_run")==scanner_run
           and any(Frozen.restore(v).sha256==request.sha256
                   for v in service.data["strategy_route_requests"]),
           "D_SCANNER_CANONICAL_ROUTE_NOT_IN_CENSUS")
    _check(projection.data["scanner_raw_sha256"]==
           request.data["source_raw_sha256"]
           and projection.data["scanner_manifest_sha256"]==
           request.data["source_manifest_sha256"]
           and projection.data["scanner_universe_sha256"]==
           request.data["universe_sha256"]
           and request.data["scanner_run_sha256"]==run.sha256
           and request.data["scanner_nomination_sha256"]==nomination.sha256
           and request.data["strategy_approval_sha256"]==approval.sha256,
           "D_SCANNER_CANONICAL_SOURCE_POLICY_DRIFT")
    eligible=(request.data["strategy_route_status"]=="ROUTE_CANDIDATE_TEST_ONLY"
              and request.data["scanner_nomination_status"]=="SELECTED"
              and approval.data["governance_action"]=="APPROVE_TEST_ONLY")
    # Approval is synthetic policy, never independent external authorization.
    body={
        "schema":SCHEMA,"decision":"RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY" if eligible else "WAIT",
        "reason":"SOFTWARE_SAME_SOURCE_RESEARCH_ONLY" if eligible
                 else "WAIT_STRATEGY_POLICY_OR_UNIVERSE_INELIGIBLE",
        "core_d_witness_sha256":w.sha256,
        "scanner_d_handoff_sha256":handoff.sha256,
        "scanner_d_projection_sha256":projection.sha256,
        "scanner_c_route_sha256":request.sha256,
        "scanner_c_approval_sha256":approval.sha256,
        "scanner_c_run_sha256":run.sha256,
        "scanner_c_nomination_sha256":nomination.sha256,
        "scanner_raw_sha256":projection.data["scanner_raw_sha256"],
        "source_zip_sha256":warehouse["source_zip_sha256"],
        "manifest_integrity_sha256":warehouse["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":warehouse["receipt_sha256"],
        "core_245_price_query_sha256":native_price_query["price_query_sha256"],
        "core_253_query_local_sha256":local_query["query_sha256"],
        "cutoff_ms":warehouse["decision_cutoff_ms"],
        "strategy_id":request.data["strategy_id"],
        "strategy_version":request.data["strategy_version"],
        "config_digest":request.data["config_digest"],
        "strategy_definition_digest":request.data["definition_digest"],
        "symbol":request.data["symbol"],"timeframe":"15m",
        "nomination_status":request.data["scanner_nomination_status"],
        "strategy_secretary_state":"NOT_ENQUEUED",
        "source_ack_sha256":source_ack["receipt_sha256"] if source_ack else None,
        "approval_is_engineering_test_only":True,
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "factory_consumer_ack_sha256":None,
        "paper_execution":"NOT_ACTIVATED","trading_authority":"NONE",
        "orders_created":0,"paper_positions":0,"actual_fills":None,
    }
    return {**body,"gate_sha256":digest(body)}
