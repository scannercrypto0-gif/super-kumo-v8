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



FACTORY_ROLE_SCHEMA = "aql.factory.f.external-role-approval.v1"
CUSTODIAN_ROLE = "SOURCE_CUSTODIAN"
POLICY_ROLE = "RESEARCH_POLICY_APPROVER"
EVALUATOR_ROLE = "INDEPENDENT_EVALUATOR"


def _verify_external_role_attestation(receipt, *, role, subject_sha256,
                                      trusted_role_registry, trusted_now_utc):
    """Verify a Factory-compatible out-of-band Ed25519 role/subject witness.

    The trusted registry and UTC clock must be pinned OUTSIDE any untrusted
    receipt/Scanner candidate. Never infer trust from a supplied digest alone.
    """
    require(type(receipt) is dict and set(receipt) == {
        "schema", "role", "key_id", "approver_id", "subject_sha256",
        "issued_at_utc", "expires_at_utc", "signature_hex",
    }, "CORE_F5_EXTERNAL_ROLE_FIELDS")
    require(receipt["schema"] == FACTORY_ROLE_SCHEMA
            and receipt["role"] == role
            and valid_sha(subject_sha256)
            and receipt["subject_sha256"] == subject_sha256
            and type(receipt["signature_hex"]) is str
            and SIG.fullmatch(receipt["signature_hex"]) is not None,
            "CORE_F5_EXTERNAL_ROLE_SUBJECT_DRIFT")
    require(type(trusted_role_registry) is dict
            and role in trusted_role_registry,
            "CORE_F5_EXTERNAL_ROLE_TRUST_ROOT_MISSING")
    k = trusted_role_registry[role]
    require(type(k) is dict and set(k) == {
        "key_id", "approver_id", "public_key_hex", "enabled"
    } and k["enabled"] is True
            and k["key_id"] == receipt["key_id"]
            and k["approver_id"] == receipt["approver_id"]
            and valid_sha(k["public_key_hex"]),
            "CORE_F5_EXTERNAL_ROLE_REGISTRY_DRIFT")
    require(utc(receipt["issued_at_utc"]) <= utc(trusted_now_utc)
            < utc(receipt["expires_at_utc"]),
            "CORE_F5_EXTERNAL_ROLE_EXPIRED_OR_FUTURE")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ValueError("CORE_F5_ED25519_REQUIRED") from exc
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(k["public_key_hex"])).verify(
            bytes.fromhex(receipt["signature_hex"]),
            canonical({a: b for a, b in receipt.items() if a != "signature_hex"}))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("CORE_F5_EXTERNAL_ROLE_BAD_SIGNATURE") from exc
    return digest(receipt)


def _require_distinct_signers(pairs):
    """Prohibit role aliasing through the same key or human approver."""
    identities = [p[0] for p in pairs]
    public_keys = [p[1] for p in pairs]
    require(len(set(identities)) == len(identities)
            and len(set(public_keys)) == len(public_keys),
            "CORE_F5_SIGNER_ROLE_ALIAS")


def _verified_authorization_document(document, month):
    """Owner's local document integrity; legal authority is separate witness."""
    require(type(document) is dict and set(document) == {
        "schema", "owner_permission", "rights_evidence_reference",
        "issuer_provenance_reference", "publisher_checksum_issued_via",
        "authorized_months", "source_class", "historical_pit",
        "trading_authority",
    }, "CORE_F5_CUSTODY_DOCUMENT_REQUIRED")
    require(digest(document) == EXPECTED_AUTH
            and document["schema"] == "aql.core.f.private-custody-authorization.v1"
            and document["owner_permission"] is True
            and document["source_class"] == "ORIGINAL_PUBLISHER_RETROSPECTIVE_NON_PIT"
            and document["publisher_checksum_issued_via"] == "SEPARATE_PUBLISHER_HTTPS"
            and document["historical_pit"] == "NOT_ATTESTED"
            and document["trading_authority"] == "NONE"
            and type(document["rights_evidence_reference"]) is str
            and len(document["rights_evidence_reference"]) >= 8
            and type(document["issuer_provenance_reference"]) is str
            and len(document["issuer_provenance_reference"]) >= 8
            and type(document["authorized_months"]) is list
            and month in document["authorized_months"],
            "CORE_F5_CUSTODY_RIGHTS_OR_SCOPE_DRIFT")
    return True


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


def verify_source_ack(receipt, *, custodian_attestation, authorization_document,
                      trusted_registry, trusted_role_registry, trusted_now_utc,
                      f2_report, source_zip_sha256, warehouse_receipt_sha256,
                      native245_sha256, local253_sha256, month):
    """Verify independently issued Source ACK with external custodian role proof.

    Signature keys MUST be independently provisioned, not copied from the
    authorization document, a GitHub comment or the ACK. A caller boolean
    never substitutes for custody evidence.
    """
    expected = expected_source_payload(
        f2_report=f2_report, source_zip_sha256=source_zip_sha256,
        warehouse_receipt_sha256=warehouse_receipt_sha256,
        native245_sha256=native245_sha256, local253_sha256=local253_sha256,
        month=month)
    _verified_authorization_document(authorization_document, month)
    _verify_external_role_attestation(
        custodian_attestation, role=CUSTODIAN_ROLE,
        subject_sha256=expected, trusted_role_registry=trusted_role_registry,
        trusted_now_utc=trusted_now_utc)
    require(type(receipt) is dict and receipt.get("payload_sha256") == expected,
            "CORE_F5_SOURCE_ACK_PARENT_DRIFT")
    _signed(SOURCE_ROLE, receipt, trusted_registry=trusted_registry,
            trusted_now_utc=trusted_now_utc)
    root = trusted_registry[receipt["key_id"]]
    custodian_root = trusted_role_registry[CUSTODIAN_ROLE]
    _require_distinct_signers([
        (root["approver_identity"], root["public_key_hex"]),
        (custodian_root["approver_id"], custodian_root["public_key_hex"]),
    ])
    return digest(receipt)



NOMINATION_SCHEMA = "aql.scanner-f.original-research-nomination.v1"


def verify_scanner_nomination(nomination, *, nomination_sha256,
                              independent_policy_sha256,
                              evaluator_receipt_sha256,
                              strategy_definition_sha256,
                              expected_f2_report_sha256,
                              month, warehouse_receipt_sha256,
                              native245_sha256, local253_sha256):
    """Verify sealed Scanner candidate, not a real research selection.

    Sender must independently run the full Scanner verifier against original
    source and signed evaluator/policy. The SHA seal alone is NOT that proof.
    """
    require(type(nomination) is dict
            and set(nomination) == {"payload", "sha256"}
            and type(nomination["payload"]) is dict
            and valid_sha(nomination_sha256)
            and nomination["sha256"] == nomination_sha256
            and digest(nomination["payload"]) == nomination_sha256,
            "CORE_F5_SCANNER_NOMINATION_SEAL_REQUIRED")
    data = nomination["payload"]
    require(data.get("schema") == NOMINATION_SCHEMA
            and data.get("decision") == "NOMINATED_RESEARCH_ONLY"
            and data.get("selected") is False
            and data.get("secretary_status") == "NOT_ENQUEUED"
            and data.get("factory_lab") == "NOT_EVALUATED"
            and data.get("paper") == "NOT_ACTIVATED"
            and data.get("holdout") == "SEALED"
            and data.get("historical_pit") == "NOT_ATTESTED"
            and data.get("research_class") == "RETROSPECTIVE_NON_PIT"
            and data.get("trading_authority") == "NONE"
            and data.get("core_source_ack_sha256") is None
            and data.get("core_secretary_strategy_approval_sha256") is None
            and data.get("factory_consumer_ack_sha256") is None
            and data.get("core_f2_report_sha256") == expected_f2_report_sha256
            and data.get("verified_policy_approval_sha256") ==
                independent_policy_sha256
            and data.get("signed_evaluator_receipt_sha256") ==
                evaluator_receipt_sha256
            and data.get("strategy_definition_digest") ==
                strategy_definition_sha256
            and data.get("month") == month
            and data.get("symbol") == "BTCUSDT"
            and data.get("timeframe") == "15m"
            and data.get("market") == "BINANCE:SPOT:USDT"
            and data.get("warehouse_receipt_sha256") ==
                warehouse_receipt_sha256
            and data.get("core245_native_query_sha256") ==
                native245_sha256
            and data.get("core253_local_query_sha256") ==
                local253_sha256
            and all(valid_sha(data.get(k)) for k in (
                "strategy_decision_sha256",
                "source_bound_census_sha256",
                "verified_independent_evaluator_sha256",
                "dna_digest", "native15m_config_digest", "dual_query_map_sha256"))
            and type(data.get("strategy_id")) is str
            and ID.fullmatch(data["strategy_id"])
            and type(data.get("strategy_version")) is str
            and ID.fullmatch(data["strategy_version"])
            and type(data.get("cutoff_ms")) is int
            and type(data.get("last_evaluated_open_ms")) is int
            and 0 <= data["last_evaluated_open_ms"] + 900000 <
                data["cutoff_ms"],
            "CORE_F5_SCANNER_NOMINATION_OR_SOURCE_SCOPE_DRIFT")
    return data


def verify_strategy_approval(receipt, *, source_receipt, source_attestation,
                             authorization_document, f2_report, scanner_nomination,
                             source_zip_sha256, warehouse_receipt_sha256,
                             native245_sha256, local253_sha256, month,
                             strategy_nomination_sha256,
                             independent_policy_sha256,
                             evaluator_receipt_sha256,
                             strategy_definition_sha256,
                             policy_attestation, evaluator_attestation,
                             trusted_registry, trusted_role_registry,
                             trusted_now_utc):
    """Verify separately signed Secretary StrategyApproval and all parents.

    This does NOT infer genuine historical evaluator execution merely from
    a signed SHA. The independent evaluator must have witnessed the original
    source-bound Core query run and the externally trusted policy owner must
    have signed the exact research policy; external integration checks these.
    """
    source_ack_sha256 = verify_source_ack(
        source_receipt, custodian_attestation=source_attestation,
        authorization_document=authorization_document,
        trusted_registry=trusted_registry,
        trusted_role_registry=trusted_role_registry,
        trusted_now_utc=trusted_now_utc, f2_report=f2_report,
        source_zip_sha256=source_zip_sha256,
        warehouse_receipt_sha256=warehouse_receipt_sha256,
        native245_sha256=native245_sha256, local253_sha256=local253_sha256,
        month=month)
    require(all(valid_sha(x) for x in (
        source_ack_sha256, strategy_nomination_sha256,
        independent_policy_sha256, evaluator_receipt_sha256,
        strategy_definition_sha256)), "CORE_F5_STRATEGY_PARENTS_INVALID")
    nominee = verify_scanner_nomination(
        scanner_nomination,
        nomination_sha256=strategy_nomination_sha256,
        independent_policy_sha256=independent_policy_sha256,
        evaluator_receipt_sha256=evaluator_receipt_sha256,
        strategy_definition_sha256=strategy_definition_sha256,
        expected_f2_report_sha256=EXPECTED_F2_REPORT,
        month=month, warehouse_receipt_sha256=warehouse_receipt_sha256,
        native245_sha256=native245_sha256, local253_sha256=local253_sha256)
    require(type(receipt) is dict and
            receipt.get("source_ack_sha256") == source_ack_sha256,
            "CORE_F5_SOURCE_ACK_NOT_VERIFIED")
    _verify_external_role_attestation(
        policy_attestation, role=POLICY_ROLE,
        subject_sha256=independent_policy_sha256,
        trusted_role_registry=trusted_role_registry,
        trusted_now_utc=trusted_now_utc)
    _verify_external_role_attestation(
        evaluator_attestation, role=EVALUATOR_ROLE,
        subject_sha256=evaluator_receipt_sha256,
        trusted_role_registry=trusted_role_registry,
        trusted_now_utc=trusted_now_utc)
    expected = digest({
        "schema": "aql.core.f.historical-strategy-proof.v1",
        "source_ack_sha256": source_ack_sha256,
        "strategy_nomination_sha256": strategy_nomination_sha256,
        "independent_policy_sha256": independent_policy_sha256,
        "evaluator_receipt_sha256": evaluator_receipt_sha256,
        "strategy_definition_sha256": strategy_definition_sha256,
        "strategy_id": nominee["strategy_id"],
        "strategy_version": nominee["strategy_version"],
        "strategy_dna_digest": nominee["dna_digest"],
        "native15m_config_digest": nominee["native15m_config_digest"],
        "dual_query_map_sha256": nominee["dual_query_map_sha256"],
        "cutoff_ms": nominee["cutoff_ms"],
        "month": nominee["month"],
    })
    require(receipt.get("payload_sha256") == expected,
            "CORE_F5_STRATEGY_APPROVAL_PARENT_DRIFT")
    _signed(STRATEGY_ROLE, receipt, trusted_registry=trusted_registry,
            trusted_now_utc=trusted_now_utc)
    roots = [
        trusted_registry[source_receipt["key_id"]],
        trusted_registry[receipt["key_id"]],
    ]
    _require_distinct_signers(
        [(item["approver_identity"], item["public_key_hex"]) for item in roots]
        + [(trusted_role_registry[role]["approver_id"],
            trusted_role_registry[role]["public_key_hex"])
           for role in (CUSTODIAN_ROLE, POLICY_ROLE, EVALUATOR_ROLE)])
    return digest(receipt)


def pending_authority():
    return {
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }
