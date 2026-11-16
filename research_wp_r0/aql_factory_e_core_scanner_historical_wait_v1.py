"""Factory E binds Core E and Scanner E sealed status without claiming history.

This is a cross-owner blocker receipt for the final #272 integrated gate.
No historical Lab or Secretary authorization may be derived from proposal.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, register_experiment, ResultsStoreError, digest,
)
from research_wp_r0.aql_core_e_status_evidence_v1 import verify_core_e_status
from tools.scanner_strategy_e.historical_research_policy import (
    validate_historical_policy_proposal,
)
from tools.scanner_strategy_e.historical_policy_approval_request import (
    verify_historical_policy_approval_request,
)
from tools.strategy_service_offline.common import Frozen

def record_historical_core_scanner_wait(*, store_path, experiment_id,
                                        core_preflight, core_status,
                                        scanner_policy_proposal, approval_request,
                                        frozen_work_specs,
                                        code_sha256, environment_sha256):
    if not verify_core_e_status(core_status, core_preflight):
        raise ResultsStoreError("FACTORY_E_CORE_E_STATUS_UNTRUSTED")
    try:
        policy=validate_historical_policy_proposal(
            scanner_policy_proposal,frozen_work_specs).data
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ResultsStoreError("FACTORY_E_HISTORICAL_POLICY_INVALID") from exc
    try:
        approval = verify_historical_policy_approval_request(
            approval_request,scanner_policy_proposal,frozen_work_specs).data
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        raise ResultsStoreError("FACTORY_E_RESEARCH_POLICY_REQUEST_INVALID") from exc
    if (approval.get("policy_approval_status") != "PENDING_INDEPENDENT_OWNER"
        or approval.get("source_authentication_receipt_sha256") is not None
        or approval.get("independent_policy_approval_receipt_sha256") is not None
        or approval.get("core_secretary_historical_route") != "NOT_AUTHORIZED"
        or core_status["status"] != "SOURCE_BLOCKED"
        or core_status["source_sha256"] is not None
        or core_status["warehouse_receipt_sha256"] is not None
        or core_status["core_245_native_price_query_sha256"] is not None
        or core_status["core_253_local_query_sha256"] is not None
        or core_status["historical_policy_approval"] != "NOT_APPROVED"
        or core_status["historical_pit"] != "NOT_ATTESTED"
        or core_status["secretary_historical_route"] != "NOT_AUTHORIZED"
        or policy["policy_status"] != "PROPOSED_NOT_APPROVED"
        or policy["historical_route_status"] != "WAIT"
        or policy["independent_approval_receipt_sha256"] is not None
        or policy["actual_historical_source_receipt_sha256"] is not None
        or policy["historical_pit"] != "NOT_ATTESTED"
        or policy["trading_authority"] != "NONE"):
        raise ResultsStoreError("FACTORY_E_UNAUTHORIZED_HISTORICAL_PROMOTION")
    attempts=[]
    for i,entry in enumerate(policy["strategies"]):
        for symbol in policy["target_symbols"]:
            attempts.append(dict(
                attempt_id=f"historical:{i}:{symbol}",
                candidate_id=f"{entry['strategy_id']}:{entry['strategy_version']}:{symbol}",
                state="UNKNOWN",
                source_receipt_sha256=scanner_policy_proposal["sha256"],
            ))
    record=build_experiment(
        experiment_id=experiment_id, lane="HISTORICAL_SOURCE",
        source_status="HISTORICAL_SOURCE_BLOCKED",
        source_sha256=None,source_query_245_sha256=None,
        source_query_253_sha256=None,
        strategy_definition_sha256=None,config_sha256=None,
        code_sha256=code_sha256,environment_sha256=environment_sha256,
        parent_receipt_sha256=core_status["receipt_sha256"],
        attempts=attempts,evidence_class="RETROSPECTIVE_NON_PIT")
    stored=register_experiment(store_path,record)
    body=dict(
        schema="aql.factory.e.core-scanner-historical-wait.v1",
        experiment_sha256=record["sha256"],
        core_e_status_sha256=core_status["receipt_sha256"],
        scanner_policy_proposal_sha256=scanner_policy_proposal["sha256"],
        scanner_approval_request_sha256=approval_request["sha256"],
        strategy_count=len(policy["strategies"]),
        symbol_count=len(policy["target_symbols"]),
        attempt_count=len(attempts),
        selected_count=0,
        unknown_count=len(attempts),
        historical_source="HISTORICAL_SOURCE_BLOCKED",
        historical_policy="PROPOSED_NOT_APPROVED",
        historical_pit="NOT_ATTESTED",
        lab="NOT_EVALUATED",
        paper="NOT_ACTIVATED",
        trading_authority="NONE",
        orders_created=0,
        paper_positions=0,
        actual_fills=None,
    )
    return {**body,"receipt_sha256":digest(body)}
