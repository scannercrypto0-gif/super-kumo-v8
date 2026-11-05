"""Immutable Scanner F3 policy approval *proposal* and external acceptance checklist.

This module issues only a versioned policy-approval REQUEST tied to exact
frozen Work235 strategy identities. It cannot mint or verify a trusted owner
signature; owner approvals must be authenticated out of band.
"""
from __future__ import annotations
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f.retrospective_policy import verify_retrospective_policy_draft

SCHEMA = "aql.scanner-f.historical-policy-activation-request.v1"
POLICY_ID = "btc-spot-15m-retrospective-non-pit-v1"
REQUIRED_OWNER_FIELDS = (
    "decision", "policy_id", "policy_draft_sha256",
    "strategy_identity_digest", "approved_symbol", "approved_market",
    "approved_timeframe", "approved_months", "cutoff_rule",
    "evidence_class", "historical_pit", "trading_authority",
    "holdout_state", "source_gate", "approver_identity",
    "approval_time_utc", "trusted_record_reference",
    "signature_scheme", "key_id", "signature",
)


def make_historical_activation_request(policy_draft,proposal,request,work_specs):
    """Deterministic owner-facing request; NOT an authorization."""
    p = verify_retrospective_policy_draft(
        policy_draft,proposal,request,work_specs)
    d = p.data
    identities = d["strategy_identity"]
    require(len(identities) > 0 and len({
        (x["strategy_id"],x["strategy_version"]) for x in identities
    }) == len(identities), "F3_APPROVAL_IDENTITY_CENSUS")
    strategy_digest = Frozen.build(identities).sha256
    scope = {
        "policy_id": POLICY_ID,
        "policy_draft_sha256": p.sha256,
        "strategy_identity_digest": strategy_digest,
        "approved_symbol": "BTCUSDT",
        "approved_market": "BINANCE:SPOT:USDT",
        "approved_timeframe": "15m",
        "approved_months": d["target_months"],
        "cutoff_rule": "CLOSED_15M_BAR_CLOSE_MS_LT_DECISION_CUTOFF_MS",
        "evidence_class": "RETROSPECTIVE_NON_PIT",
        "historical_pit": "NOT_ATTESTED",
        "trading_authority": "NONE",
        "holdout_state": "SEALED",
        "source_gate": "CORE_F2_INDEPENDENT_ORIGINAL_SOURCE_REQUIRED",
    }
    return Frozen.build({
        "schema": SCHEMA,
        "request_status": "PENDING_INDEPENDENT_APPROVAL",
        "owner_decision": "PROVISIONAL_CONDITIONAL_A_DORMANT",
        "scope": scope,
        "strategy_identity": identities,
        "e_proposal_sha256": d["original_e_policy_proposal_sha256"],
        "e_owner_request_sha256": d["original_e_owner_request_sha256"],
        "required_owner_receipt_fields": list(REQUIRED_OWNER_FIELDS),
        "independent_owner_approval_receipt_sha256": None,
        "independent_approval_verified": False,
        "source_authentication_verified": False,
        "core_f2_raw_warehouse_query_receipt_sha256": None,
        "historical_route_status": "WAIT_SOURCE_AND_INDEPENDENT_OWNER_APPROVAL",
        "secretary_state": "NOT_ENQUEUED",
        "factory_lab": "NOT_EVALUATED",
        "holdout_access": False,
        "paper_execution": "NOT_ACTIVATED",
        "orders": 0,
        "positions": 0,
        "fills": None,
    }).receipt()


def verify_historical_activation_request(
    activation_request, policy_draft,proposal,request,work_specs
):
    """Reject even resealed promotion, scope/config/cutoff/parent changes."""
    o = Frozen.restore(activation_request)
    expected = make_historical_activation_request(
        policy_draft,proposal,request,work_specs)
    require(o.receipt() == expected,
            "F3_ACTIVATION_REQUEST_APPROVAL_OR_PARENT_DRIFT")
    return o
