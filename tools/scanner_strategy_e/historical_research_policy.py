"""ATLAS Scanner E — separately versioned historical research eligibility policy.

A policy proposal (DRAFT) is NOT an approval or historical PIT attestation.
This contract never alters frozen Work235 synthetic AAA..EEE, never overrides
Scanner C/D synthetic approval, never creates a Core Secretary route.

Positive historical source-backed selections require a future *independently*
approved policy and authenticated Core original source/known-at; this proposal
only enables explicit WAIT/INELIGIBLE research attempts until then.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen, require
from tools.strategy_service_offline.screening import StrategyScreeningSpec
from tools.scanner_strategy_b.native15m import native_15m_policy

SCHEMA = "aql.scanner-e.historical-research-eligibility-policy.v1"
STATUS = "PROPOSED_NOT_APPROVED"
SOURCE = "ORIGINAL_PUBLISHER"
SCOPE = "RESEARCH_ONLY_NO_OPERATIONAL_AUTHORITY"
DECISION = "WAIT_EXTERNAL_HISTORICAL_SOURCE_AND_POLICY_APPROVAL"


def propose_historical_research_policy(
    frozen_work_specs, *,
    target_symbols=("BTCUSDT",), market="BINANCE:SPOT:USDT",
    timeframe="15m", policy_version="historical-research-v1",
    authorization_evidence=None,
):
    """Deterministic SHA-sealed *proposal*, NOT a retroactive Work235 mutation.

    Strategy definitions and DNA are referenced by frozen digest, but current
    Work235 fixture provenance/universe is NEVER copied as permission to
    screen real market symbols. Independent policy approval remains external.
    """
    require(authorization_evidence is None, "E_NO_APPROVAL_FROM_PROPOSAL_API")
    require(type(frozen_work_specs) is list and 0<len(frozen_work_specs)<=16,
            "E_HISTORICAL_SPEC_BUDGET")
    require(type(target_symbols) in (tuple,list)
            and 0<len(target_symbols)<=256
            and all(type(s) is str and s and len(s)<=40 and
                    s.isascii() and all(c.isalnum() or c in "._:-" for c in s)
                    for s in target_symbols)
            and len(set(target_symbols))==len(target_symbols)
            and type(market) is str and market=="BINANCE:SPOT:USDT"
            and timeframe=="15m" and policy_version=="historical-research-v1",
            "E_HISTORICAL_VERSIONED_SCOPE")
    policies=[]
    for w in frozen_work_specs:
        spec=StrategyScreeningSpec.restore_spec(w)
        native=native_15m_policy(w)
        p=spec.data
        require(p["scope"]=="TEST_ONLY_UNAPPROVED_POLICY"
                and p["paper_approval"]=="NOT_FOUND"
                and p["market"]=="fixture"
                and p["timeframe"]!="15m"
                and native.data["timeframe"]=="15m"
                and native.data["operational_work235_15m"]
                    =="NOT_CONNECTED_15M_UNSUPPORTED"
                and p["dna"]["dna"]["provenance"]["kind"]
                    =="SYNTHETIC_NOT_AUTHENTICATED",
                "E_HISTORICAL_FROZEN_SOURCE_MUST_NOT_BE_GRANTED")
        policies.append({
            "strategy_id":p["strategy_id"],
            "strategy_version":p["strategy_version"],
            "work235_spec_sha256":spec.sha256,
            "work235_config_digest":p["config_digest"],
            "scanner_native15m_policy_sha256":native.sha256,
            "scanner_native15m_config_digest":native.data["config_digest"],
            "definition_digest":p["definition"]["digest"],
            "dna_digest":p["dna"]["digest"],
            "source_policy_dna_is_inherited":False,
            "historical_target_symbols":sorted(target_symbols),
            "historical_target_market":market,
            "historical_target_timeframe":"15m",
            "strategy_eligibility":"NOT_APPROVED",
            "independent_source_authentication":"REQUIRED_NOT_ATTESTED",
            "historical_known_at":"NOT_ATTESTED",
            "route_authority":"NONE",
        })
    keys=[(x["strategy_id"],x["strategy_version"]) for x in policies]
    require(len(set(keys))==len(keys), "E_DUPLICATE_FROZEN_STRATEGY")
    return Frozen.build({
        "schema":SCHEMA, "policy_version":policy_version,
        "policy_status":STATUS,
        "source_kind":SOURCE,"scope":SCOPE,
        "research_venue":market,
        "timeframe":timeframe,
        "target_symbols":sorted(target_symbols),
        "strategies":sorted(policies,key=lambda x:(x["strategy_id"],x["strategy_version"])),
        "actual_historical_source_receipt_sha256":None,
        "publisher_authentication_receipt_sha256":None,
        "independent_approval_receipt_sha256":None,
        "historical_available_at_evidence_sha256":None,
        "historical_pit":"NOT_ATTESTED",
        "scanner_nomination_status":"UNKNOWN",
        "historical_route_status":"WAIT",
        "strategy_secretary_state":"NOT_ENQUEUED",
        "paper_execution":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "orders_created":0,"paper_positions":0,"actual_fills":None,
        "decision":DECISION,
    }).receipt()


def validate_historical_policy_proposal(receipt, frozen_work_specs):
    """Verify exact canonical proposal and its Work235 source-linked parents."""
    p=Frozen.restore(receipt)
    d=p.data
    require(d.get("schema")==SCHEMA
            and d.get("policy_version")=="historical-research-v1"
            and d.get("policy_status")==STATUS
            and d.get("source_kind")==SOURCE
            and d.get("scope")==SCOPE
            and d.get("historical_pit")=="NOT_ATTESTED"
            and d.get("decision")==DECISION
            and d.get("independent_approval_receipt_sha256") is None
            and d.get("trading_authority")=="NONE"
            and d.get("strategy_secretary_state")=="NOT_ENQUEUED",
            "E_POLICY_APPROVAL_OR_AUTHORITY_FORGERY")
    expected=propose_historical_research_policy(
        frozen_work_specs,target_symbols=d["target_symbols"],
        market=d["research_venue"],timeframe=d["timeframe"],
        policy_version=d["policy_version"])
    require(expected==receipt,"E_HISTORICAL_POLICY_DIGEST_OR_PARENT_DRIFT")
    return p
