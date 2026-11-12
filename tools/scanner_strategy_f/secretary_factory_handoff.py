"""Scanner F3 -> Secretary/Factory immutable *handoff proposal*, never an ACK.

No owner other than Core Secretary can issue Source ACK or StrategyApproval;
no Factory consumer ACK/positive Lab is minted here. This receipt carries the
entire source+policy+attempt graph and explicit research eligibility state.
"""
from __future__ import annotations
from tools.strategy_service_offline.common import Frozen,require

SCHEMA="aql.scanner-f.historical-secretary-factory-handoff.v1"
INPUT_SCHEMA="aql.scanner-f.historical-source-bound-research-intake.v1"


def create_research_handoff(source_bound_census):
    c=Frozen.restore(source_bound_census)
    d=c.data
    require(d.get("schema")==INPUT_SCHEMA
            and d.get("research_scope")=="RETROSPECTIVE_NON_PIT"
            and d.get("historical_pit")=="NOT_ATTESTED"
            and d.get("attempt_count")==24
            and d.get("ready_for_independent_research_screening")==20
            and d.get("unknown_retained")==4
            and d.get("selected")==0
            and d.get("secretary_state")=="NOT_ENQUEUED"
            and d.get("factory_consumer_ack_sha256") is None
            and d.get("factory_lab")=="NOT_EVALUATED"
            and d.get("trading_authority")=="NONE",
            "F3_SOURCE_AND_POLICY_GRAPH_NOT_READY_FOR_PROPOSAL")
    identities=set()
    for item in d["attempts"]:
        a=Frozen.restore(item).data
        require(a.get("schema")==
                "aql.scanner-f.historical-source-bound-research-attempt.v1"
                and a.get("historical_pit")=="NOT_ATTESTED"
                and a.get("trading_authority")=="NONE"
                and a.get("source_ack_sha256") is None
                and a.get("strategy_approval_sha256") is None
                and a.get("factory_consumer_ack_sha256") is None,
                "F3_ATTEMPT_PREAPPROVAL_FORGERY")
        key=(a["strategy_id"],a["strategy_version"],a["month"],a["symbol"])
        require(key not in identities,"F3_DUPLICATE_STRATEGY_MONTH")
        identities.add(key)
    return Frozen.build({
        "schema":SCHEMA,
        "source_bound_research_census_sha256":c.sha256,
        "core_f2_report_sha256":d["core_f2_report_sha256"],
        "core_f1_manifest_sha256":d["source_manifest_sha256"],
        "core_f1_coverage_sha256":d["f1_coverage_sha256"],
        "independent_source_authorization_sha256":
            d["external_source_authorization_sha256"],
        "independent_verified_policy_sha256":
            d["verified_owner_policy_receipt_sha256"],
        "strategy_month_symbol_attempt_count":24,
        "source_verified_month_attempts":20,
        "retained_inventory_unknown_attempts":4,
        "research_strategy_selection":"PENDING_ACTUAL_ORIGINAL_BAR_EVALUATION",
        "historical_pit":"NOT_ATTESTED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_route":"NOT_ENQUEUED",
        "factory_lab":"NOT_EVALUATED",
        "holdout":"SEALED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    }).receipt()


def verify_research_handoff(handoff, source_bound_census):
    o=Frozen.restore(handoff)
    require(o.receipt()==create_research_handoff(source_bound_census),
            "F3_HANDOFF_PARENT_ACK_OR_STATUS_TAMPER")
    return o
