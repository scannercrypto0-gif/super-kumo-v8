"""Scanner E historical research policy: independently reviewable approval REQUEST.

This contract can describe owner/issuer evidence REQUIREMENTS and accept
independently signed source proof as immutable opaque SHA references. It does
NOT mint a policy approval, claim trusted issuer signatures or route trading.

The final approval authority must live outside Scanner; a locally sealed
request, fixture identity, Core custody-only checksum, or historical
retrospective observation is never an authorization to SELECTED/Secretary.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_e.historical_research_policy import (
    validate_historical_policy_proposal,
)

SCHEMA="aql.scanner-e.historical-policy-approval-request.v1"
CONDITION_SCHEMA="aql.scanner-e.historical-approval-preconditions.v1"


def prepare_historical_policy_approval_request(
    policy_proposal, frozen_work_specs, *,
    owner_review_ticket="ATLAS-273",
    source_authentication_receipt=None,
    core_245_query_receipt=None,
    core_253_query_receipt=None,
    issuer_historical_known_at_receipt=None,
):
    """Issue an unapproved governance request carrying exact evidence gaps.

    This is safe with optional third-party receipts because the checker below
    intentionally does not accept arbitrary supplied objects as independent
    authentication. The owner reviews originals via Core private custody.
    """
    policy=validate_historical_policy_proposal(
        policy_proposal,frozen_work_specs)
    require(type(owner_review_ticket) is str
            and owner_review_ticket=="ATLAS-273",
            "E_HISTORICAL_REVIEW_TICKET_INVALID")
    parents=(source_authentication_receipt,
             core_245_query_receipt,core_253_query_receipt,
             issuer_historical_known_at_receipt)
    require(all(v is None for v in parents),
            "E_NO_CALLER_SELF_ATTESTED_HISTORICAL_EVIDENCE")
    return Frozen.build({
        "schema":SCHEMA,
        "request_version":"historical-research-approval-request-v1",
        "governance_issue":"273",
        "owner_review_ticket":owner_review_ticket,
        "policy_proposal_sha256":policy.sha256,
        "policy_schema":policy.data["schema"],
        "strategy_contracts":[{
            "strategy_id":x["strategy_id"],
            "strategy_version":x["strategy_version"],
            "work235_spec_sha256":x["work235_spec_sha256"],
            "work235_config_digest":x["work235_config_digest"],
            "scanner_native15m_policy_sha256":
                x["scanner_native15m_policy_sha256"],
            "scanner_native15m_config_digest":
                x["scanner_native15m_config_digest"],
            "definition_digest":x["definition_digest"],
            "dna_digest":x["dna_digest"],
        } for x in policy.data["strategies"]],
        "target_symbols":policy.data["target_symbols"],
        "market":policy.data["research_venue"],
        "timeframe":policy.data["timeframe"],
        "source_type":"ORIGINAL_PUBLISHER",
        "required_external_evidence":[
            "OWNER_AUTHORIZED_ORIGINAL_PUBLISHER_ARCHIVE",
            "INDEPENDENTLY_AUTHENTICATED_PUBLISHER_CHECKSUM",
            "CORE_IMMUTABLE_RAW_AND_WAREHOUSE_READBACK",
            "CORE_245_AND_CORE_253_DISTINCT_QUERY_SHAS",
            "INDEPENDENT_ISSUER_KNOWN_AT_FOR_PIT_CLAIMS",
            "INDEPENDENT_RESEARCH_POLICY_OWNER_APPROVAL",
        ],
        "source_authentication_receipt_sha256":None,
        "core_245_query_sha256":None,
        "core_253_query_sha256":None,
        "issuer_known_at_receipt_sha256":None,
        "independent_policy_approval_receipt_sha256":None,
        "source_authorization":"NOT_ATTESTED",
        "issuer_known_at_status":"NOT_ATTESTED",
        "historical_pit":"NOT_ATTESTED",
        "policy_approval_status":"PENDING_INDEPENDENT_OWNER",
        "scanner_historical_screening":"WAIT",
        "core_secretary_historical_route":"NOT_AUTHORIZED",
        "factory_historical_lab":"NOT_AUTHORIZED",
        "paper_execution":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "orders_created":0,
        "paper_positions":0,
        "actual_fills":None,
        "decision":"WAIT_SOURCE_ACCESS_AND_POLICY_APPROVAL",
    }).receipt()


def verify_historical_policy_approval_request(
    approval_request, policy_proposal, frozen_work_specs
):
    """Canonical replay denies a resealed approval/source/PIT forgery."""
    obj=Frozen.restore(approval_request)
    require(obj.data.get("schema")==SCHEMA
            and obj.data.get("policy_approval_status")
                =="PENDING_INDEPENDENT_OWNER"
            and obj.data.get("trading_authority")=="NONE"
            and obj.data.get("source_authorization")=="NOT_ATTESTED"
            and obj.data.get("issuer_known_at_status")=="NOT_ATTESTED"
            and obj.data.get("core_secretary_historical_route")
                =="NOT_AUTHORIZED"
            and obj.data.get("independent_policy_approval_receipt_sha256")
                is None,
            "E_HISTORICAL_OWNER_APPROVAL_NOT_AVAILABLE")
    require(obj.receipt()==prepare_historical_policy_approval_request(
        policy_proposal,frozen_work_specs),
        "E_OWNER_APPROVAL_REQUEST_PARENT_OR_SCOPE_DRIFT")
    return obj
