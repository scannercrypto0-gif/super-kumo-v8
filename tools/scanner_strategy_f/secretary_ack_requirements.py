"""F3 research Secretary authority contract, **not** an ACK issuer.

Exactly distinct custody Source ACK, strategy-specific Secretary Approval and
Factory Consumer ACK. A Scanner proposal cannot assert any of them. Real
positive future route is Core-owned and must reference source bar readback,
trusted policy and strategy indicator decision, all re-verified by Secretary.
"""
from __future__ import annotations
from tools.strategy_service_offline.common import Frozen,require

SCHEMA="aql.scanner-f.historical-secretary-ack-requirements.v1"
DECISION_SCHEMA="aql.scanner-f.historical-original-strategy-decision.v1"
SHA_FIELDS=(
    "source_ack_sha256","strategy_approval_sha256",
    "factory_consumer_ack_sha256",
)


def propose_secretary_ack_requirements(strategy_decision,source_bound_census):
    strategy=Frozen.restore(strategy_decision)
    census=Frozen.restore(source_bound_census)
    d=strategy.data
    s=census.data
    require(d.get("schema")==DECISION_SCHEMA
            and d.get("source_bound_census_sha256")==census.sha256
            and d.get("decision")==
                "WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL"
            and d.get("selected") is False
            and d.get("historical_pit")=="NOT_ATTESTED"
            and d.get("research_scope")=="RETROSPECTIVE_NON_PIT"
            and d.get("trading_authority")=="NONE"
            and d.get("source_ack_sha256") is None
            and d.get("strategy_approval_sha256") is None
            and d.get("factory_consumer_ack_sha256") is None
            and d.get("secretary_state")=="NOT_ENQUEUED"
            and s.get("selected")==0
            and s.get("attempt_count")==24,
            "F3_NOT_AN_AUTHORIZED_SECRETARY_DECISION")
    return Frozen.build({
        "schema":SCHEMA,
        "strategy_decision_sha256":strategy.sha256,
        "source_bound_census_sha256":census.sha256,
        "policy_approval_sha256":s["verified_owner_policy_receipt_sha256"],
        "core_f2_report_sha256":s["core_f2_report_sha256"],
        "external_source_authorization_sha256":s[
            "external_source_authorization_sha256"],
        "strategy_id":d["strategy_id"],
        "strategy_version":d["strategy_version"],
        "month":d["month"],
        "strategy_definition_digest":d["strategy_definition_digest"],
        "native15m_config_digest":d["native15m_config_digest"],
        "source_zip_sha256":d["source_zip_sha256"],
        "warehouse_receipt_sha256":d["warehouse_receipt_sha256"],
        "core245_native_query_sha256":d["core245_native_query_sha256"],
        "core253_local_query_sha256":d["core253_local_query_sha256"],
        "cutoff_ms":d["cutoff_ms"],
        "source_ack_required_owner":"CORE_SOURCE_SECRETARY",
        "source_ack_schema_required":"aql.core.f.historical-source-ack.v1",
        "strategy_approval_required_owner":"CORE_STRATEGY_SECRETARY",
        "strategy_approval_schema_required":
            "aql.core.f.historical-strategy-approval.v1",
        "factory_consumer_ack_required_owner":"FACTORY",
        "factory_consumer_ack_schema_required":"aql.factory.f.consumer-ack.v1",
        "ack_parent_sha_uniqueness":"REQUIRED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }).receipt()


def verify_secretary_ack_requirements(proposal,decision,census):
    d=Frozen.restore(proposal)
    require(d.receipt()==propose_secretary_ack_requirements(decision,census),
            "F3_SECRETARY_SOURCE_STRATEGY_FACTORY_ACK_ALIAS_OR_FORGERY")
    return d
