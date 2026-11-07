"""Core F5 verifier for distinct externally signed historical research authority.

Pure read-only receipt verification. Never mints a source ACK or StrategyApproval,
never touches historical bytes and never authorizes trading.
"""
from __future__ import annotations

from datetime import datetime
import json
import re
from hashlib import sha256

SOURCE_SCHEMA = "aql.core.f.historical-source-ack.v1"
STRATEGY_SCHEMA = "aql.core.f.historical-strategy-approval.v1"
SOURCE_ROLE = "CORE_SOURCE_SECRETARY"
STRATEGY_ROLE = "CORE_STRATEGY_SECRETARY"
HEX = re.compile(r"^[0-9a-f]{64}$")
SIG = re.compile(r"^[0-9a-f]{128}$")
ID = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")
EXPECTED_F2_REPORT = "daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40"
EXPECTED_MANIFEST = "f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7"
EXPECTED_LEDGER = "557c38ecb58d9c0c22784ee105c6cb0a29bf2d4dc2ba44f5ed4e2a08c1a89862"
EXPECTED_AUTH = "ced74dade0ee151eff61109bddb912c5203cbb4d091f6ba77545cb262e332439"


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def valid_sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def utc(value):
    require(type(value) is str and value.endswith("Z") and len(value) < 45,
            "CORE_F5_TRUSTED_UTC_REQUIRED")
    try:
        t = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("CORE_F5_BAD_UTC") from exc
    require(t.utcoffset().total_seconds() == 0, "CORE_F5_UTC_OFFSET_INVALID")
    return t


def _signed(role, receipt, *, trusted_registry, trusted_now_utc):
    require(type(receipt) is dict, "CORE_F5_SIGNED_RECEIPT_REQUIRED")
    expected = {
        "schema", "issuer_role", "approver_identity", "key_id",
        "not_before_utc", "expires_at_utc", "signature_scheme",
        "signature", "research_scope", "historical_pit",
        "trading_authority", "source_ack_sha256", "payload_sha256"
    }
    require(set(receipt) == expected, "CORE_F5_RECEIPT_FIELDS_DRIFT")
    require(receipt["issuer_role"] == role
            and receipt["schema"] == (SOURCE_SCHEMA if role == SOURCE_ROLE else STRATEGY_SCHEMA)
            and receipt["signature_scheme"] == "Ed25519"
            and receipt["research_scope"] == "RETROSPECTIVE_NON_PIT"
            and receipt["historical_pit"] == "NOT_ATTESTED"
            and receipt["trading_authority"] == "NONE"
            and valid_sha(receipt["payload_sha256"])
            and (receipt["source_ack_sha256"] is None if role == SOURCE_ROLE
                 else valid_sha(receipt["source_ack_sha256"]))
            and type(receipt["signature"]) is str and SIG.fullmatch(receipt["signature"]),
            "CORE_F5_RECEIPT_SCOPE_OR_SIGNATURE_INVALID")
    require(type(receipt["key_id"]) is str and ID.fullmatch(receipt["key_id"])
            and type(receipt["approver_identity"]) is str
            and ID.fullmatch(receipt["approver_identity"]), "CORE_F5_SIGNER_ID_INVALID")
    require(utc(receipt["not_before_utc"]) <= utc(trusted_now_utc)
            < utc(receipt["expires_at_utc"]), "CORE_F5_RECEIPT_EXPIRED_OR_FUTURE")
    require(type(trusted_registry) is dict
            and receipt["key_id"] in trusted_registry, "CORE_F5_TRUST_ROOT_MISSING")
    key = trusted_registry[receipt["key_id"]]
    require(type(key) is dict and set(key) == {
        "public_key_hex", "approver_identity", "authority", "enabled"}
        and key["enabled"] is True
        and key["authority"] == role
        and key["approver_identity"] == receipt["approver_identity"]
        and valid_sha(key["public_key_hex"]), "CORE_F5_SIGNER_ROLE_UNTRUSTED")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ValueError("CORE_F5_ED25519_REQUIRED") from exc
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key_hex"])).verify(
            bytes.fromhex(receipt["signature"]),
            canonical({k: v for k, v in receipt.items() if k != "signature"}))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("CORE_F5_SIGNATURE_INVALID") from exc
    return digest(receipt)


def expected_source_payload(*, f2_report, source_zip_sha256,
                            warehouse_receipt_sha256, native245_sha256,
                            local253_sha256, month):
    require(type(f2_report) is dict and f2_report.get("schema") ==
            "aql.core.f.private-raw-warehouse-dual-query-report.v1",
            "CORE_F5_ACTUAL_F2_REPORT_REQUIRED")
    require(f2_report.get("report_sha256") == EXPECTED_F2_REPORT
            and digest({k:v for k,v in f2_report.items() if k!="report_sha256"}) ==
            EXPECTED_F2_REPORT
            and f2_report.get("manifest_sha256") == EXPECTED_MANIFEST
            and f2_report.get("f1_coverage_ledger_sha256") == EXPECTED_LEDGER
            and f2_report.get("authorization_document_sha256") == EXPECTED_AUTH
            and f2_report.get("f2_new_admitted_count") == 10
            and f2_report.get("f2_previous_retained_inventory_only_count") == 2
            and f2_report.get("historical_pit") == "NOT_ATTESTED"
            and f2_report.get("trading_authority") == "NONE",
            "CORE_F5_F2_REPORT_LINEAGE_INVALID")
    require(type(month) is str and month in (
        "2024-01","2024-03","2024-04","2024-05","2024-06",
        "2024-07","2024-09","2024-10","2024-11","2024-12"),
        "CORE_F5_NOT_ADMITTED_MONTH")
    entries=f2_report.get("entries")
    require(type(entries) is list and len(entries)==10
            and len({x["month"] for x in entries})==10
            and sum(x["bars"] for x in entries)==29376,
            "CORE_F5_F2_CENSUS_INVALID")
    row=next((x for x in entries if x["month"]==month), None)
    require(row is not None and row.get("state")=="RAW_AND_DUAL_QUERY_READBACK"
            and row.get("historical_pit")=="NOT_ATTESTED"
            and row.get("source_sha256")==source_zip_sha256
            and row.get("warehouse_receipt_sha256")==warehouse_receipt_sha256
            and row.get("core_245_native_price_query_sha256")==native245_sha256
            and row.get("core_253_local_query_sha256")==local253_sha256
            and all(valid_sha(x) for x in (
                source_zip_sha256,warehouse_receipt_sha256,
                native245_sha256,local253_sha256)),
            "CORE_F5_SOURCE_QUERY_PARENT_DRIFT")
    return digest({
        "schema":"aql.core.f.historical-source-proof.v1",
        "f2_report_sha256":EXPECTED_F2_REPORT,
        "source_authorization_sha256":EXPECTED_AUTH,
        "month":month,
        "source_zip_sha256":source_zip_sha256,
        "warehouse_receipt_sha256":warehouse_receipt_sha256,
        "core245_native_query_sha256":native245_sha256,
        "core253_local_query_sha256":local253_sha256,
    })


def verify_source_ack(receipt, *, trusted_registry, trusted_now_utc,
                      f2_report, source_zip_sha256, warehouse_receipt_sha256,
                      native245_sha256, local253_sha256, month,
                      independently_witnessed_source: bool = False):
    """Verify genuine issuer-signature and exact source lineage, never issue ACK.

    independently_witnessed_source must come from separately authorized read-only
    witness. Boolean alone is insufficient to prove authenticity: require the
    independently pinned and signed receipt via trusted_registry too.
    """
    require(independently_witnessed_source is True,
            "CORE_F5_EXTERNAL_SOURCE_WITNESS_MISSING")
    expected=expected_source_payload(
        f2_report=f2_report, source_zip_sha256=source_zip_sha256,
        warehouse_receipt_sha256=warehouse_receipt_sha256,
        native245_sha256=native245_sha256,local253_sha256=local253_sha256,
        month=month)
    require(receipt.get("payload_sha256")==expected,
            "CORE_F5_SOURCE_ACK_PARENT_DRIFT")
    return _signed(SOURCE_ROLE,receipt,trusted_registry=trusted_registry,
                   trusted_now_utc=trusted_now_utc)


def verify_strategy_approval(receipt, *, source_receipt, source_ack_sha256,
                             strategy_nomination_sha256,
                             independent_policy_sha256,
                             evaluator_receipt_sha256,
                             strategy_definition_sha256,
                             trusted_registry, trusted_now_utc,
                             authenticated_nomination: bool = False):
    require(authenticated_nomination is True,
            "CORE_F5_AUTHENTIC_EVALUATOR_NOMINATION_REQUIRED")
    require(all(valid_sha(x) for x in (
        source_ack_sha256,strategy_nomination_sha256,
        independent_policy_sha256,evaluator_receipt_sha256,
        strategy_definition_sha256)), "CORE_F5_STRATEGY_PARENTS_INVALID")
    require(type(source_receipt) is dict
            and digest(source_receipt)==source_ack_sha256
            and source_receipt.get("issuer_role")==SOURCE_ROLE
            and receipt.get("source_ack_sha256")==source_ack_sha256,
            "CORE_F5_SOURCE_ACK_NOT_VERIFIED")
    _signed(SOURCE_ROLE,source_receipt,trusted_registry=trusted_registry,
            trusted_now_utc=trusted_now_utc)
    expected=digest({
        "schema":"aql.core.f.historical-strategy-proof.v1",
        "source_ack_sha256":source_ack_sha256,
        "strategy_nomination_sha256":strategy_nomination_sha256,
        "independent_policy_sha256":independent_policy_sha256,
        "evaluator_receipt_sha256":evaluator_receipt_sha256,
        "strategy_definition_sha256":strategy_definition_sha256,
    })
    require(receipt.get("payload_sha256")==expected,
            "CORE_F5_STRATEGY_APPROVAL_PARENT_DRIFT")
    return _signed(STRATEGY_ROLE,receipt,trusted_registry=trusted_registry,
                   trusted_now_utc=trusted_now_utc)


def pending_authority():
    return {
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }
