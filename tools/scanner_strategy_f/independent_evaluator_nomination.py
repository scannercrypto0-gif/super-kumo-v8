"""Independent historical evaluator receipt for Scanner F.

An evaluator's SHA seal or caller-supplied approval flag is not authority.
Only an externally pinned Ed25519 INDEPENDENT_EVALUATOR trust root plus
original Core #245/#253 source-bound bar replay can authorize a research
nomination. This receiver never issues a Core Secretary StrategyApproval.
"""
from __future__ import annotations

import re
from datetime import datetime
from hashlib import sha256
import json
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f.strategy_specific_decision import SCHEMA as DECISION_SCHEMA

RECEIPT_SCHEMA = "aql.scanner-f.independent-original-evaluator-receipt.v1"
NOMINATION_SCHEMA = "aql.scanner-f.original-research-nomination.v1"
KEY_AUTHORITY = "INDEPENDENT_EVALUATOR"
SHA = re.compile(r"^[0-9a-f]{64}$")
SIG = re.compile(r"^[0-9a-f]{128}$")
LABEL = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")


def _canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _utc(raw):
    require(type(raw) is str and raw.endswith("Z") and len(raw)<=40,
            "F3_EVAL_UTC_REQUIRED")
    try:
        v=datetime.fromisoformat(raw[:-1]+"+00:00")
    except ValueError as exc:
        raise ValueError("F3_EVAL_BAD_UTC") from exc
    require(v.utcoffset().total_seconds()==0,"F3_EVAL_UTC_OFFSET")
    return v


def verify_external_evaluator_receipt(
    signed_evaluation, strategy_decision,source_bound_census, *,
    trusted_evaluator_keyring, observed_at_utc
):
    """Require externally provisioned authority, not a receipt-provided key.

    A real independently trusted runner must provision the keyring, clock and
    role/revocation state. The signature does NOT itself verify the original
    warehouse bytes; these were re-queried by the source-bound decision call.
    """
    d=Frozen.restore(strategy_decision)
    c=Frozen.restore(source_bound_census)
    x=d.data
    s=c.data
    require(x.get("schema")==DECISION_SCHEMA
            and x.get("source_bound_census_sha256")==c.sha256
            and x.get("decision")==
                "WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL"
            and x.get("selected") is False
            and x.get("research_scope")=="RETROSPECTIVE_NON_PIT"
            and x.get("historical_pit")=="NOT_ATTESTED"
            and x.get("trading_authority")=="NONE"
            and x.get("source_ack_sha256") is None
            and x.get("strategy_approval_sha256") is None
            and x.get("factory_consumer_ack_sha256") is None
            and x.get("secretary_state")=="NOT_ENQUEUED"
            and s.get("attempt_count")==24
            and s.get("selected")==0
            and s.get("historical_pit")=="NOT_ATTESTED"
            and s.get("trading_authority")=="NONE",
            "F3_EVALUATOR_INPUT_NOT_AUTHORIZED")
    required={
        "schema","decision_sha256","source_bound_census_sha256",
        "policy_approval_sha256","core_f2_report_sha256",
        "strategy_id","strategy_version","month","symbol","market",
        "timeframe","strategy_definition_digest","dna_digest",
        "native15m_config_digest","warehouse_receipt_sha256",
        "core245_native_query_sha256","core253_local_query_sha256",
        "dual_query_map_sha256","cutoff_ms","last_evaluated_open_ms",
        "indicator_receipt_sha256","signal_digest","evaluator_code_sha256",
        "evaluator_version","evaluation_result","approver_identity",
        "key_id","not_before_utc","expires_at_utc","signature_scheme",
        "signature"
    }
    require(type(signed_evaluation) is dict
            and set(signed_evaluation)==required,
            "F3_EVALUATOR_RECEIPT_FIELDS")
    a=signed_evaluation
    parents={
        "decision_sha256":d.sha256,
        "source_bound_census_sha256":c.sha256,
        "policy_approval_sha256":s["verified_owner_policy_receipt_sha256"],
        "core_f2_report_sha256":s["core_f2_report_sha256"],
        "strategy_id":x["strategy_id"],
        "strategy_version":x["strategy_version"],
        "month":x["month"],"symbol":x["symbol"],"market":x["market"],
        "timeframe":x["timeframe"],
        "strategy_definition_digest":x["strategy_definition_digest"],
        "dna_digest":x["dna_digest"],
        "native15m_config_digest":x["native15m_config_digest"],
        "warehouse_receipt_sha256":x["warehouse_receipt_sha256"],
        "core245_native_query_sha256":x["core245_native_query_sha256"],
        "core253_local_query_sha256":x["core253_local_query_sha256"],
        "dual_query_map_sha256":x["dual_query_map_sha256"],
        "cutoff_ms":x["cutoff_ms"],
        "last_evaluated_open_ms":x["last_evaluated_open_ms"],
        "indicator_receipt_sha256":x["external_indicator_receipt_sha256"],
        "signal_digest":x["external_signal_digest"],
    }
    for key,v in parents.items():
        require(type(a[key])==type(v) and a[key]==v,
                "F3_EVALUATOR_SOURCE_POLICY_STRATEGY_PARENT_DRIFT:"+key)
    require(type(a["evaluator_code_sha256"]) is str
            and SHA.fullmatch(a["evaluator_code_sha256"])
            and type(a["evaluator_version"]) is str
            and LABEL.fullmatch(a["evaluator_version"])
            and a["evaluation_result"] in
                ("RESEARCH_CANDIDATE","RESEARCH_REJECTED","UNKNOWN")
            and (a["evaluation_result"]!="RESEARCH_CANDIDATE"
                 or x["signal_observation"]=="PROPOSED_RESEARCH_ONLY")
            and a["signature_scheme"]=="Ed25519"
            and type(a["signature"]) is str and SIG.fullmatch(a["signature"])
            and type(a["key_id"]) is str and LABEL.fullmatch(a["key_id"])
            and type(a["approver_identity"]) is str
            and LABEL.fullmatch(a["approver_identity"]),
            "F3_EVALUATOR_RESULT_OR_SIGNATURE_FIELDS")
    now=_utc(observed_at_utc)
    issued=_utc(a["not_before_utc"])
    expiry=_utc(a["expires_at_utc"])
    require(issued<=now<expiry,"F3_EVALUATOR_WITNESS_EXPIRED_OR_FUTURE")
    require(type(trusted_evaluator_keyring) is dict
            and a["key_id"] in trusted_evaluator_keyring,
            "F3_EVALUATOR_EXTERNAL_TRUST_ROOT_MISSING")
    k=trusted_evaluator_keyring[a["key_id"]]
    require(type(k) is dict
            and set(k)=={
                "public_key_hex","approver_identity","authority","enabled"}
            and k["enabled"] is True
            and k["authority"]==KEY_AUTHORITY
            and k["approver_identity"]==a["approver_identity"]
            and type(k["public_key_hex"]) is str
            and SHA.fullmatch(k["public_key_hex"]),
            "F3_EVALUATOR_TRUST_ROLE_OR_ID_DRIFT")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ValueError("F3_EVALUATOR_ED25519_UNAVAILABLE") from exc
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(k["public_key_hex"])).verify(
                bytes.fromhex(a["signature"]),
                _canonical({key:v for key,v in a.items() if key!="signature"}))
    except (InvalidSignature,ValueError) as exc:
        raise ValueError("F3_EVALUATOR_INVALID_SIGNATURE") from exc
    return Frozen.build({
        "schema":"aql.scanner-f.verified-independent-evaluator.v1",
        "signed_evaluator_receipt_sha256":
            sha256(_canonical(a)).hexdigest(),
        "strategy_decision_sha256":d.sha256,
        "source_bound_census_sha256":c.sha256,
        "core_f2_report_sha256":s["core_f2_report_sha256"],
        "policy_approval_sha256":s["verified_owner_policy_receipt_sha256"],
        "evaluator_identity":a["approver_identity"],
        "evaluator_key_id":a["key_id"],
        "evaluator_code_sha256":a["evaluator_code_sha256"],
        "evaluator_version":a["evaluator_version"],
        "evaluation_result":a["evaluation_result"],
        "research_class":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "trading_authority":"NONE",
    }).receipt()


def create_independent_research_nomination(
    verified_evaluator, strategy_decision,source_bound_census
):
    """Research-only nomination, never Core StrategyApproval or Lab ACK."""
    e=Frozen.restore(verified_evaluator)
    d=Frozen.restore(strategy_decision)
    c=Frozen.restore(source_bound_census)
    s=c.data
    x=d.data
    a=e.data
    require(a.get("schema")=="aql.scanner-f.verified-independent-evaluator.v1"
            and a.get("strategy_decision_sha256")==d.sha256
            and a.get("source_bound_census_sha256")==c.sha256
            and a.get("policy_approval_sha256")==s["verified_owner_policy_receipt_sha256"]
            and a.get("core_f2_report_sha256")==s["core_f2_report_sha256"]
            and x.get("source_bound_census_sha256")==c.sha256
            and a.get("research_class")=="RETROSPECTIVE_NON_PIT"
            and a.get("historical_pit")=="NOT_ATTESTED"
            and a.get("trading_authority")=="NONE",
            "F3_NOMINATION_PARENT_OR_PIT_TAMPER")
    decision={
        "RESEARCH_CANDIDATE":"NOMINATED_RESEARCH_ONLY",
        "RESEARCH_REJECTED":"REJECTED_RESEARCH_ONLY",
        "UNKNOWN":"UNKNOWN",
    }[a["evaluation_result"]]
    return Frozen.build({
        "schema":NOMINATION_SCHEMA,
        "strategy_decision_sha256":d.sha256,
        "source_bound_census_sha256":c.sha256,
        "verified_independent_evaluator_sha256":e.sha256,
        "signed_evaluator_receipt_sha256":a["signed_evaluator_receipt_sha256"],
        "verified_policy_approval_sha256":a["policy_approval_sha256"],
        "core_f2_report_sha256":a["core_f2_report_sha256"],
        "strategy_id":x["strategy_id"],"strategy_version":x["strategy_version"],
        "strategy_definition_digest":x["strategy_definition_digest"],
        "dna_digest":x["dna_digest"],
        "native15m_config_digest":x["native15m_config_digest"],
        "month":x["month"],"symbol":x["symbol"],
        "market":x["market"],"timeframe":x["timeframe"],
        "warehouse_receipt_sha256":x["warehouse_receipt_sha256"],
        "core245_native_query_sha256":x["core245_native_query_sha256"],
        "core253_local_query_sha256":x["core253_local_query_sha256"],
        "dual_query_map_sha256":x["dual_query_map_sha256"],
        "cutoff_ms":x["cutoff_ms"],
        "last_evaluated_open_ms":x["last_evaluated_open_ms"],
        "decision":decision,
        "selected":False,
        "core_source_ack_sha256":None,
        "core_secretary_strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_status":"NOT_ENQUEUED",
        "factory_lab":"NOT_EVALUATED",
        "historical_pit":"NOT_ATTESTED",
        "research_class":"RETROSPECTIVE_NON_PIT",
        "paper":"NOT_ACTIVATED",
        "holdout":"SEALED",
        "trading_authority":"NONE",
    }).receipt()


def verify_research_nomination(nomination,verified_evaluator,
                               strategy_decision,source_bound_census):
    o=Frozen.restore(nomination)
    require(o.receipt()==create_independent_research_nomination(
        verified_evaluator,strategy_decision,source_bound_census),
        "F3_NOMINATION_RESEALED_STRATEGY_ACK_OR_SCOPE_TAMPER")
    return o
