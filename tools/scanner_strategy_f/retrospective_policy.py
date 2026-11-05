"""ATLAS Scanner F3 — versioned BTCUSDT historical RESEARCH_ONLY NON_PIT policy.

Draft policy is never owner approval. Independent approval has a *different*
issuer/trust root; a bare Scanner Frozen SHA is not an authority signature.
No Work235 mutation, Paper, actual source creation, or Secretary enqueue.
"""
from __future__ import annotations
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_e.historical_research_policy import (
    validate_historical_policy_proposal,
)
from tools.scanner_strategy_e.historical_policy_approval_request import (
    verify_historical_policy_approval_request,
)

POLICY_SCHEMA="aql.scanner-f.historical-retrospective-research-policy.v1"
GATE_SCHEMA="aql.scanner-f.historical-route-authorization-gate.v1"
MONTHS=("2024-01","2024-02","2024-03","2024-04","2024-05","2024-06",
        "2024-07","2024-08","2024-09","2024-10","2024-11","2024-12")


def create_retrospective_policy_draft(proposal,approval_request,work_specs, *,
                                     target_months=MONTHS):
    """Version and pin strategy lineage without silently granting BTC approval."""
    p=validate_historical_policy_proposal(proposal,work_specs)
    a=verify_historical_policy_approval_request(approval_request,proposal,work_specs)
    require(type(target_months) in (tuple,list)
            and 0<len(target_months)<=12
            and len(set(target_months))==len(target_months)
            and all(type(m) is str and m in MONTHS for m in target_months),
            "F_HISTORICAL_MONTH_SCOPE")
    d=p.data
    require(d["target_symbols"]==["BTCUSDT"]
            and d["research_venue"]=="BINANCE:SPOT:USDT"
            and d["timeframe"]=="15m"
            and d["historical_pit"]=="NOT_ATTESTED"
            and a.data["policy_approval_status"]=="PENDING_INDEPENDENT_OWNER",
            "F_HISTORICAL_POLICY_SCOPE")
    return Frozen.build({
        "schema":POLICY_SCHEMA,
        "policy_version":"btc-spot-15m-retrospective-non-pit-v1",
        "policy_status":"DRAFT_PENDING_INDEPENDENT_OWNER_APPROVAL",
        "policy_approval_issue":"274",
        "original_e_policy_proposal_sha256":p.sha256,
        "original_e_owner_request_sha256":a.sha256,
        "strategy_identity":[
            {"strategy_id":s["strategy_id"],
             "strategy_version":s["strategy_version"],
             "work235_spec_sha256":s["work235_spec_sha256"],
             "work235_config_digest":s["work235_config_digest"],
             "scanner_native15m_config_digest":s["scanner_native15m_config_digest"],
             "scanner_native15m_policy_sha256":s["scanner_native15m_policy_sha256"],
             "definition_digest":s["definition_digest"],
             "dna_digest":s["dna_digest"],
             "source_policy_inherited":False}
            for s in d["strategies"]
        ],
        "market":"BINANCE:SPOT:USDT",
        "symbol":"BTCUSDT","timeframe":"15m",
        "target_months":sorted(target_months),
        "source_kind":"ORIGINAL_PUBLISHER",
        "source_lineage":"CORE_AUTHENTICATED_NATIVE_15M_ORIGINAL_ONLY",
        "source_authentication":"REQUIRED_NOT_AVAILABLE",
        "research_clock_basis":"RETROSPECTIVE_BOUNDED_CUTOFF",
        "historical_pit":"NOT_ATTESTED",
        "independent_owner_approval_receipt_sha256":None,
        "independent_source_authority_sha256":None,
        "approval_trust_root":"EXTERNAL_OWNER_ONLY_NOT_SCANNER",
        "strategy_route_status":"WAIT",
        "core_secretary_state":"NOT_ENQUEUED",
        "factory_consumer_ack":None,
        "operational_paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "orders_created":0,
        "paper_positions":0,
        "fills":None,
    }).receipt()


def verify_retrospective_policy_draft(draft,proposal,request,work_specs):
    obj=Frozen.restore(draft)
    d=obj.data
    require(d.get("schema")==POLICY_SCHEMA
            and d.get("policy_status")=="DRAFT_PENDING_INDEPENDENT_OWNER_APPROVAL"
            and d.get("approval_trust_root")=="EXTERNAL_OWNER_ONLY_NOT_SCANNER"
            and d.get("independent_owner_approval_receipt_sha256") is None
            and d.get("independent_source_authority_sha256") is None
            and d.get("historical_pit")=="NOT_ATTESTED"
            and d.get("strategy_route_status")=="WAIT"
            and d.get("trading_authority")=="NONE",
            "F_POLICY_SELF_APPROVAL_OR_PIT_FORGED")
    expected=create_retrospective_policy_draft(
        proposal,request,work_specs,target_months=d["target_months"])
    require(expected==draft,"F_POLICY_IDENTITY_OR_COHORT_TAMPER")
    return obj


def historical_route_gate(draft,proposal,request,work_specs, *,
                          core_source_authentication=None,
                          owner_policy_approval=None,
                          core_245_query=None,core_253_query=None,
                          source_ack=None):
    """No positive historical route without externally validated credentials.

    F3 deliberately does not pretend that a supplied SHA proves independent
    owner approval or independent original publisher provenance. A separate
    future Core/owner trust verifier and versioned Secretary F interface must
    independently verify issuer receipts before allowing a positive route.
    """
    p=verify_retrospective_policy_draft(draft,proposal,request,work_specs)
    evidence=(core_source_authentication,owner_policy_approval,
              core_245_query,core_253_query,source_ack)
    require(all(x is None for x in evidence),
            "F_EXTERNAL_APPROVAL_REQUIRES_INDEPENDENT_TRUST_VERIFIER")
    return Frozen.build({
        "schema":GATE_SCHEMA,
        "decision":"WAIT_SOURCE_AND_INDEPENDENT_OWNER_APPROVAL",
        "policy_draft_sha256":p.sha256,
        "historical_source_authentication_sha256":None,
        "independent_owner_policy_approval_sha256":None,
        "core_245_query_sha256":None,
        "core_253_query_sha256":None,
        "core_source_ack_sha256":None,
        "historical_pit":"NOT_ATTESTED",
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "strategy_secretary_state":"NOT_ENQUEUED",
        "factory_consumer_ack":None,
        "trading_authority":"NONE",
        "paper_execution":"NOT_ACTIVATED",
    }).receipt()
