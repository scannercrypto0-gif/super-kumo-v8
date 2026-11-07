"""Factory F4 positive gate: independent role-signature verification.

This module reads signatures with a separately trusted keyring, never from a
candidate packet. It does not mint Source ACK, StrategyApproval, or source/PIT
evidence. The real owner's trust registry is external to this repository.
"""
from __future__ import annotations
from datetime import datetime,timezone
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest,ResultsStoreError,_sha,
)

SCHEMA="aql.factory.f.external-role-approval.v1"
ROLES=("SOURCE_CUSTODIAN","RESEARCH_POLICY_APPROVER","CORE_SOURCE_SECRETARY",
       "CORE_STRATEGY_SECRETARY","INDEPENDENT_EVALUATOR")


def need(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_F_AUTH_"+reason)


def _utc(value):
    need(type(value) is str and value.endswith("Z"),"UTC_FORMAT")
    try:
        dt=datetime.fromisoformat(value[:-1]+"+00:00")
    except ValueError as exc:
        raise ResultsStoreError("FACTORY_F_AUTH_UTC_INVALID") from exc
    need(dt.tzinfo is not None and dt.utcoffset().total_seconds()==0,
         "UTC_ZONE")
    return dt


def verify_role_attestations(packet,attestations,keyring,now_utc):
    """Verify five INDEPENDENT Ed25519 roles bound to one complete input SHA.

    The keyring must come from read-only independently provisioned local trust
    custody; no root shipped with the receipt and no public CI fixture keys.
    All approver IDs and public keys are role-bound and unique.
    """
    need(type(attestations) is list and len(attestations)==len(ROLES),
         "FIVE_DISTINCT_ATTESTATIONS_REQUIRED")
    need(type(keyring) is dict and set(keyring)==set(ROLES),
         "TRUST_REGISTRY_MISSING_OR_ROLE_DRIFT")
    now=_utc(now_utc)
    seen_keys=set()
    seen_approvers=set()
    seen_roles=set()
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ResultsStoreError("FACTORY_F_AUTH_ED25519_REQUIRED") from exc
    for item in attestations:
        need(type(item) is dict and set(item)=={
             "schema","role","key_id","approver_id","subject_sha256",
             "issued_at_utc","expires_at_utc","signature_hex"},
             "ATTESTATION_FIELDS")
        role=item["role"]
        need(item["schema"]==SCHEMA and role in ROLES
             and role not in seen_roles and _sha(item["subject_sha256"])
             and item["subject_sha256"]==packet["sha256"]
             and type(item["signature_hex"]) is str
             and len(item["signature_hex"])==128,
             "ATTESTATION_SCOPE_SIGNATURE")
        root=keyring[role]
        need(type(root) is dict and set(root)=={
             "key_id","approver_id","public_key_hex","enabled"},
             "TRUST_ROOT_FIELDS")
        need(root["enabled"] is True and
             root["key_id"]==item["key_id"] and
             root["approver_id"]==item["approver_id"] and
             type(root["public_key_hex"]) is str and
             len(root["public_key_hex"])==64 and
             all(ch in "0123456789abcdef" for ch in root["public_key_hex"]) and
             root["public_key_hex"] not in seen_keys and
             root["approver_id"] not in seen_approvers,
             "INDEPENDENT_ROLE_TRUST_ROOT")
        start=_utc(item["issued_at_utc"])
        expires=_utc(item["expires_at_utc"])
        need(start<=now<expires and expires>start,
             "EXPIRED_OR_FUTURE_SIGNATURE")
        body={k:v for k,v in item.items() if k!="signature_hex"}
        try:
            Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(root["public_key_hex"])).verify(
                    bytes.fromhex(item["signature_hex"]),
                    __import__("json").dumps(body,sort_keys=True,separators=(",",":"),
                                              ensure_ascii=True,allow_nan=False).encode("ascii"))
        except (InvalidSignature,ValueError) as exc:
            raise ResultsStoreError("FACTORY_F_AUTH_INVALID_SIGNATURE") from exc
        seen_roles.add(role)
        seen_keys.add(root["public_key_hex"])
        seen_approvers.add(root["approver_id"])
    need(seen_roles==set(ROLES),"UNAUTHORIZED_ROLE_GAP")
    return {"schema":"aql.factory.f.verified-role-authority-graph.v1",
            "input_sha256":packet["sha256"],
            "roles":list(ROLES),
            "authority_receipts_sha256":{a["role"]:digest(a) for a in attestations},
            "historical_pit":"NOT_ATTESTED",
            "trading_authority":"NONE"}
