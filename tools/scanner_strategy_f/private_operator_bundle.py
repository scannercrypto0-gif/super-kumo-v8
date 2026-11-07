"""One owner-private F3 operator input bundle and fail-closed evidence gate.

No private original OHLCV, signing keys, trusted registry, or signed receipts
are materialized or returned. The bundle is a deterministic requirements
manifest. A filled private evidence envelope is validated against the *exact*
immutable original Scanner F3 parents before the Core Secretary/Factory
real-positive chain is allowed to proceed.

IMPORTANT: operator-supplied document integrity alone is NOT independent
authority: actual approver registries, private source and evaluator execution
remain separately validated by their authorized custodians.
"""
from __future__ import annotations
from tools.strategy_service_offline.common import Frozen,require
from tools.scanner_strategy_f.independent_evaluator_nomination import (
    verify_external_evaluator_receipt,create_independent_research_nomination,
    verify_research_nomination,
)
from tools.scanner_strategy_f.independent_policy_verification import (
    verify_external_policy_approval,
)
from tools.scanner_strategy_f.policy_activation_request import (
    verify_historical_activation_request,
)

SCHEMA="aql.scanner-f.private-original-evaluator-operator-bundle.v1"
EVIDENCE="aql.scanner-f.original-private-evaluation-evidence.v1"


def prepare_original_evaluator_operator_bundle(
    *,source_bound_census,strategy_decision,activation_request,
    policy_draft,original_e_proposal,original_e_request,work_specs,
):
    """Public sanitized deterministic request for a real private run.

    This function does NOT run actual original-query evaluator; a strategy
    decision must previously be produced through genuine query_local replay.
    """
    c=Frozen.restore(source_bound_census)
    d=Frozen.restore(strategy_decision)
    a=verify_historical_activation_request(
        activation_request,policy_draft,original_e_proposal,
        original_e_request,work_specs)
    p=Frozen.restore(policy_draft)
    x=d.data;s=c.data
    require(s.get("schema")=="aql.scanner-f.historical-source-bound-research-intake.v1"
            and s.get("attempt_count")==24
            and s.get("strategy_count")==2
            and s.get("month_count")==12
            and s.get("unknown_retained")==4
            and s.get("ready_for_independent_research_screening")==20
            and s.get("selected")==0
            and s.get("historical_pit")=="NOT_ATTESTED"
            and s.get("research_scope")=="RETROSPECTIVE_NON_PIT"
            and x.get("schema")=="aql.scanner-f.historical-original-strategy-decision.v1"
            and x.get("source_bound_census_sha256")==c.sha256
            and x.get("selected") is False
            and x.get("decision")==
                "WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL"
            and x.get("historical_pit")=="NOT_ATTESTED"
            and x.get("research_scope")=="RETROSPECTIVE_NON_PIT"
            and x.get("trading_authority")=="NONE"
            and x.get("source_ack_sha256") is None
            and x.get("strategy_approval_sha256") is None
            and x.get("factory_consumer_ack_sha256") is None
            and x.get("secretary_state")=="NOT_ENQUEUED"
            and a.data["scope"]["policy_draft_sha256"]==p.sha256
            and s["policy_draft_sha256"]==p.sha256,
            "F3_OPERATOR_SOURCE_POLICY_STRATEGY_SCOPE")
    require(type(x.get("source_zip_sha256")) is str
            and x["source_zip_sha256"]==next(
                (v["original_source_sha256"] for v in
                 (Frozen.restore(a).data for a in s["attempts"])
                 if v["month"]==x["month"]
                 and v["strategy_id"]==x["strategy_id"]
                 and v["strategy_version"]==x["strategy_version"]), None),
            "F3_OPERATOR_ORIGINAL_SOURCE_REQUIRED")
    original=[Frozen.restore(v).data for v in s["attempts"]]
    candidates=[v for v in original
                if v["month"]==x["month"]
                and v["strategy_id"]==x["strategy_id"]
                and v["strategy_version"]==x["strategy_version"]]
    require(len(candidates)==1 and
            candidates[0]["status"]=="PENDING_RESEARCH_EVALUATION"
            and candidates[0]["core245_native_query_sha256"]==
                x["core245_native_query_sha256"]
            and candidates[0]["core253_local_query_sha256"]==
                x["core253_local_query_sha256"]
            and candidates[0]["original_source_sha256"]==
                x["source_zip_sha256"],
            "F3_OPERATOR_MISSING_OR_RETAINED_BAR_SOURCE")
    return Frozen.build({
        "schema":SCHEMA,
        "bundle_status":"REQUIRES_EXTERNAL_AUTHORITY_AND_PRIVATE_RUN",
        "source_bound_census_sha256":c.sha256,
        "strategy_decision_sha256":d.sha256,
        "activation_request_sha256":a.sha256,
        "policy_draft_sha256":p.sha256,
        "core_f2_report_sha256":s["core_f2_report_sha256"],
        "independent_policy_verified_sha256":s["verified_owner_policy_receipt_sha256"],
        "source_authorization_sha256":s["external_source_authorization_sha256"],
        "strategy_id":x["strategy_id"],
        "strategy_version":x["strategy_version"],
        "strategy_definition_digest":x["strategy_definition_digest"],
        "dna_digest":x["dna_digest"],
        "native15m_config_digest":x["native15m_config_digest"],
        "work235_config_digest":candidates[0]["work235_config_digest"],
        "month":x["month"],"market":x["market"],
        "symbol":"BTCUSDT","timeframe":"15m",
        "core245_native_query_sha256":x["core245_native_query_sha256"],
        "core253_local_query_sha256":x["core253_local_query_sha256"],
        "warehouse_receipt_sha256":x["warehouse_receipt_sha256"],
        "dual_query_map_sha256":x["dual_query_map_sha256"],
        "decision_cutoff_ms":x["cutoff_ms"],
        "last_closed_bar_open_ms":x["last_evaluated_open_ms"],
        "indicator_receipt_sha256":x["external_indicator_receipt_sha256"],
        "signal_digest":x["external_signal_digest"],
        "attempt_count":24,
        "admitted_attempts":20,
        "feb_aug_unknown_attempts":4,
        "historical_pit":"NOT_ATTESTED",
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "independent_evaluator_receipt_sha256":None,
        "research_nomination_sha256":None,
        "core_source_ack_sha256":None,
        "core_secretary_strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "source_issuer":"CORE_SOURCE_CUSTODIAN",
        "policy_issuer":"INDEPENDENT_STRATEGY_POLICY_OWNER",
        "evaluator_issuer":"INDEPENDENT_EVALUATOR",
        "source_ack_issuer":"CORE_SOURCE_SECRETARY",
        "strategy_approval_issuer":"CORE_STRATEGY_SECRETARY",
        "factory_consumer_ack_issuer":"FACTORY",
        "private_original_source_readback":"REQUIRED_NOT_ATTESTED_BY_BUNDLE",
        "evaluator_code_execution_proof":"REQUIRED_NOT_ATTESTED_BY_BUNDLE",
        "trusted_external_registry":"REQUIRED_OUT_OF_BAND",
        "trusted_clock":"REQUIRED_OUT_OF_BAND",
        "allowed_next_step":"CORE_SECRETARY_REVIEW_ONLY_AFTER_AUTHORITY",
        "selected":False,
        "secretary_state":"NOT_ENQUEUED",
        "factory_lab":"NOT_EVALUATED",
        "holdout":"SEALED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    }).receipt()


def verify_original_evaluator_operator_bundle(
    bundle,*,source_bound_census,strategy_decision,activation_request,
    policy_draft,original_e_proposal,original_e_request,work_specs,
):
    o=Frozen.restore(bundle)
    require(o.receipt()==prepare_original_evaluator_operator_bundle(
        source_bound_census=source_bound_census,
        strategy_decision=strategy_decision,
        activation_request=activation_request,policy_draft=policy_draft,
        original_e_proposal=original_e_proposal,
        original_e_request=original_e_request,work_specs=work_specs),
        "F3_OPERATOR_BUNDLE_RESEALED_AUTHORITY_OR_SCOPE")
    return o


def verify_real_evaluator_operator_envelope(
    envelope,bundle,source_bound_census,strategy_decision,
    activation_request,policy_draft,original_e_proposal,original_e_request,
    work_specs,*,signed_policy_approval,trusted_policy_keyring,
    signed_evaluator_receipt,trusted_evaluator_keyring,observed_at_utc
):
    """Assemble a *review-only* trusted proof graph, never ACK/SELECTED.

    External signer and trusted clock must be independently configured.
    Current code cannot attest private original query/evaluator execution:
    the operator must supply an independently witnessed original run;
    missing proof blocks any real positive action.
    """
    b=verify_original_evaluator_operator_bundle(
        bundle,source_bound_census=source_bound_census,
        strategy_decision=strategy_decision,
        activation_request=activation_request,policy_draft=policy_draft,
        original_e_proposal=original_e_proposal,
        original_e_request=original_e_request,work_specs=work_specs)
    require(type(envelope) is dict and set(envelope)=={
        "schema","bundle_sha256","source_bound_census_sha256",
        "strategy_decision_sha256","policy_approval_verified_sha256",
        "evaluator_verified_sha256","nomination_sha256",
        "independent_source_witness_sha256",
        "original_query_execution_witness_sha256",
        "evaluator_execution_witness_sha256",
        "result_class","historical_pit","trading_authority",
        "source_ack_sha256","strategy_approval_sha256",
        "factory_consumer_ack_sha256",
    } and envelope["schema"]==EVIDENCE
            and envelope["bundle_sha256"]==b.sha256
            and envelope["source_bound_census_sha256"]==
                b.data["source_bound_census_sha256"]
            and envelope["strategy_decision_sha256"]==
                b.data["strategy_decision_sha256"],
            "F3_OPERATOR_ENVELOPE_IDENTITY")
    policy=verify_external_policy_approval(
        signed_policy_approval,activation_request,policy_draft,
        original_e_proposal,original_e_request,work_specs,
        trusted_keyring=trusted_policy_keyring,
        observed_at_utc=observed_at_utc)
    evaluator=verify_external_evaluator_receipt(
        signed_evaluator_receipt,strategy_decision,source_bound_census,
        trusted_evaluator_keyring=trusted_evaluator_keyring,
        observed_at_utc=observed_at_utc)
    nomination=create_independent_research_nomination(
        evaluator,strategy_decision,source_bound_census)
    require(envelope["policy_approval_verified_sha256"]==policy["sha256"]
            and envelope["evaluator_verified_sha256"]==evaluator["sha256"]
            and envelope["nomination_sha256"]==nomination["sha256"]
            and envelope["result_class"]==nomination["payload"]["decision"]
            and envelope["historical_pit"]=="NOT_ATTESTED"
            and envelope["trading_authority"]=="NONE"
            and envelope["source_ack_sha256"] is None
            and envelope["strategy_approval_sha256"] is None
            and envelope["factory_consumer_ack_sha256"] is None,
            "F3_OPERATOR_ENVELOPE_APPROVAL_EVALUATOR_DRIFT")
    # A bare supplied SHA cannot prove independent issuer/source rights or
    # private query/evaluator execution; exact external roots are mandatory,
    # distinct from trusted policy/evaluator keys. This verifier intentionally
    # remains review-only and never promotes the envelope to authorization.
    return Frozen.build({
        "schema":"aql.scanner-f.private-original-evaluator-review.v1",
        "operator_bundle_sha256":b.sha256,
        "signed_policy_approval_sha256":policy.sha256,
        "signed_evaluator_receipt_sha256":evaluator.sha256,
        "research_nomination_sha256":nomination["sha256"],
        "source_witness_status":"REQUIRES_EXTERNAL_ATTESTATION",
        "original_query_execution_status":"REQUIRES_INDEPENDENT_REPLAY",
        "evaluator_execution_status":"REQUIRES_INDEPENDENT_REPLAY",
        "decision":"WAIT_EXTERNAL_SOURCE_AND_EXECUTION_WITNESSES",
        "selected":False,
        "core_source_ack_sha256":None,
        "core_secretary_strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }).receipt()
