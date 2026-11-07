"""Scanner F3 independent Ed25519 research-only owner approval verification.

The verifier NEVER accepts caller-supplied trust roots. Exact authorized
public key and approver identity come from independent read-only governance
configuration provided by the operating custodian. No key is embedded or
created here. Approval verification is separate from Core original-source
authentication, Source ACK, Secretary strategy approval and Factory ACK.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f.policy_activation_request import (
    make_historical_activation_request,
    verify_historical_activation_request,
)

SCHEMA = "aql.scanner-f.independent-research-policy-approval.v1"
REQUIRED = frozenset((
    "schema","decision","activation_request_sha256","policy_id",
    "policy_draft_sha256","strategy_identity_digest","approved_symbol",
    "approved_market","approved_timeframe","approved_months","cutoff_rule",
    "evidence_class","historical_pit","trading_authority","holdout_state",
    "source_gate","approver_identity","approval_time_utc","expires_at_utc",
    "trusted_record_reference","signature_scheme","key_id","signature",
))
SHA64 = re.compile(r"^[0-9a-f]{64}$")
HEX128 = re.compile(r"^[0-9a-f]{128}$")
ID = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _parse_utc(raw):
    require(type(raw) is str and raw.endswith("Z")
            and len(raw)<=40,"F3_APPROVAL_UTC_REQUIRED")
    try:
        value=datetime.fromisoformat(raw[:-1]+"+00:00")
    except ValueError as exc:
        raise ValueError("F3_APPROVAL_TIME_FORMAT") from exc
    require(value.utcoffset().total_seconds()==0
            and value.isoformat().endswith("+00:00"),
            "F3_APPROVAL_TIMEZONE")
    return value


def verify_external_policy_approval(
    approval_receipt, activation_request, policy_draft, proposal,
    request, work_specs, *,
    trusted_keyring, observed_at_utc,
):
    """Verify a non-Scanner signed policy approval with caller's *configured*
    independently provisioned keyring.

    trusted_keyring is an administrator-controlled mapping keyed by key_id:
    {'public_key_hex':..., 'approver_identity':..., 'authority':
      'INDEPENDENT_STRATEGY_POLICY_OWNER', 'enabled':True}.
    It must not be sourced from the receipt or Scanner repo. A matched
    signature is not proof of independent provisioning if the caller passes
    attacker-chosen keys; the custodian must pin keyring out of band.
    """
    verified_request=verify_historical_activation_request(
        activation_request,policy_draft,proposal,request,work_specs)
    require(type(approval_receipt) is dict
            and set(approval_receipt)==REQUIRED,
            "F3_SIGNED_APPROVAL_FIELDS")
    a=approval_receipt
    require(a["schema"]==SCHEMA
            and a["decision"]=="APPROVE_RESEARCH_ONLY_RETROSPECTIVE_NON_PIT"
            and a["activation_request_sha256"]==verified_request.sha256
            and a["policy_id"]=="btc-spot-15m-retrospective-non-pit-v1"
            and a["signature_scheme"]=="Ed25519"
            and type(a["signature"]) is str
            and HEX128.fullmatch(a["signature"])
            and type(a["key_id"]) is str and ID.fullmatch(a["key_id"])
            and type(a["approver_identity"]) is str and ID.fullmatch(a["approver_identity"])
            and type(a["trusted_record_reference"]) is str
            and 8<=len(a["trusted_record_reference"])<=256,
            "F3_SIGNED_APPROVAL_SCOPE_OR_SIGNATURE")
    scope=verified_request.data["scope"]
    for key in (
        "policy_id","policy_draft_sha256","strategy_identity_digest",
        "approved_symbol","approved_market","approved_timeframe",
        "approved_months","cutoff_rule","evidence_class",
        "historical_pit","trading_authority","holdout_state","source_gate",
    ):
        require(type(a[key])==type(scope[key]) and a[key]==scope[key],
                "F3_SIGNED_APPROVAL_PARENT_OR_SCOPE_DRIFT:"+key)
    issued=_parse_utc(a["approval_time_utc"])
    expires=_parse_utc(a["expires_at_utc"])
    now=_parse_utc(observed_at_utc)
    require(issued<=now<expires and expires>issued,
            "F3_SIGNED_APPROVAL_EXPIRED_OR_FUTURE")
    require(type(trusted_keyring) is dict
            and a["key_id"] in trusted_keyring,
            "F3_INDEPENDENT_TRUST_ROOT_UNAVAILABLE")
    k=trusted_keyring[a["key_id"]]
    require(type(k) is dict
            and set(k)=={"public_key_hex","approver_identity","authority","enabled"}
            and k["enabled"] is True
            and k["authority"]=="INDEPENDENT_STRATEGY_POLICY_OWNER"
            and k["approver_identity"]==a["approver_identity"]
            and type(k["public_key_hex"]) is str
            and SHA64.fullmatch(k["public_key_hex"]),
            "F3_TRUST_ROOT_APPROVER_DRIFT")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ValueError("F3_ED25519_VERIFIER_NOT_INSTALLED") from exc
    body={key:a[key] for key in a if key!="signature"}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(k["public_key_hex"])).verify(
            bytes.fromhex(a["signature"]),_canonical(body))
    except (InvalidSignature,ValueError) as exc:
        raise ValueError("F3_POLICY_APPROVAL_SIGNATURE_INVALID") from exc
    sealed=Frozen.build({
        "schema":"aql.scanner-f.verified-independent-policy-approval.v1",
        "approval_receipt_sha256":sha256(_canonical(a)).hexdigest(),
        "activation_request_sha256":verified_request.sha256,
        "policy_draft_sha256":scope["policy_draft_sha256"],
        "strategy_identity_digest":scope["strategy_identity_digest"],
        "signed_approver_identity":a["approver_identity"],
        "key_id":a["key_id"],
        "trusted_record_reference":a["trusted_record_reference"],
        "source_gate":"STILL_SEPARATELY_REQUIRED",
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "core_source_verified":False,
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "factory_lab":"NOT_EVALUATED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    })
    return sealed.receipt()
