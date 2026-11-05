"""Core E immutable scope-status receipt, source-boundary and final gate integration.

No historical source is invented here. Historical source validation, actual
RAW/warehouse/query and scientific PIT must be proven by separate canonical
Core contracts. This module seals external dependency status for Factory E.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

from research_wp_r0.aql_core_e_historical_boundary_v1 import (
    BLOCKED, VERIFIED, verify_preflight_receipt,
)

SCHEMA = "aql.core.e.historical-integration-status.v1"
SHA = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_EXTERNAL = (
    "authorized_private_original_archive_and_publisher_checksum_bytes",
    "independent_issuer_provenance_authentication",
    "versioned_historical_15m_research_policy_approval",
    "independent_historical_known_at_attestation_for_scientific_pit",
)
WAIT = "SOURCE_BLOCKED"
CUSTODY_ONLY = "SOURCE_CUSTODY_PIN_MATCH_ONLY_NO_HISTORICAL_ROUTE"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def _sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def make_core_e_status(*, preflight_receipt, warehouse_receipt=None,
                       native_query=None, local_query=None,
                       source_authentication=None, historical_policy=None):
    """Conservatively record Core E status from validated read-only references.

    Inputs are evidence references, not source data. A caller may provide a
    locally verified byte-pin receipt; that is never independent publisher or
    scientific-PIT proof. Unknown parents remain null, never invented hashes.
    """
    if not isinstance(preflight_receipt, Mapping) or not verify_preflight_receipt(preflight_receipt):
        raise ValueError("INVALID_PREFLIGHT_RECEIPT")
    if source_authentication not in (None, "NOT_ATTESTED"):
        raise ValueError("EXTERNAL_SOURCE_ATTESTATION_NOT_IN_SCOPE")
    if historical_policy not in (None, "NOT_APPROVED"):
        raise ValueError("HISTORICAL_POLICY_APPROVAL_NOT_IN_SCOPE")
    if any(x is not None for x in (warehouse_receipt, native_query, local_query)):
        raise ValueError("CORE_E_ACTUAL_WAREHOUSE_QUERY_CHAIN_NOT_YET_VERIFIED")
    status = preflight_receipt["status"]
    body = {
        "schema": SCHEMA,
        "status": WAIT if status == BLOCKED else CUSTODY_ONLY,
        "source_preflight_receipt_sha256": preflight_receipt["receipt_sha256"],
        "source_sha256": preflight_receipt.get("source_sha256"),
        "warehouse_receipt_sha256": None,
        "core_245_native_price_query_sha256": None,
        "core_253_local_query_sha256": None,
        "source_authentication": "NOT_ATTESTED",
        "historical_policy_approval": "NOT_APPROVED",
        "historical_pit": "NOT_ATTESTED",
        "secretary_historical_route": "NOT_AUTHORIZED",
        "factory_historical_lab": "NOT_AUTHORIZED",
        "trading_authority": "NONE",
        "requirements": list(REQUIRED_EXTERNAL),
    }
    if body["status"] == WAIT:
        body["source_sha256"] = None
    return {**body, "receipt_sha256": _digest(body)}


def verify_core_e_status(receipt, preflight_receipt):
    if type(receipt) is not dict or not isinstance(preflight_receipt, Mapping):
        return False
    if not _sha(receipt.get("receipt_sha256")):
        return False
    try:
        canonical = make_core_e_status(preflight_receipt=preflight_receipt)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    return receipt == canonical
