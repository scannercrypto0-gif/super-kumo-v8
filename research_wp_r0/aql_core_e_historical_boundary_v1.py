"""Package E historical source admission boundary; never promotes synthetic fixtures.

This module records a fail-closed, SHA-sealed custody preflight decision.
It does not ingest data, assert scientific PIT, or authorize trading.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

SCHEMA = "aql.core.e.historical-source-preflight.v1"
BLOCKED = "WAIT_SOURCE_PROVENANCE_NOT_CONNECTED"
VERIFIED = "HISTORICAL_SOURCE_VERIFIED_CUSTODY_ONLY"


def _seal(payload: dict) -> dict:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {**payload, "receipt_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight_historical_source(
    *,
    zip_path: str | Path | None,
    publisher_checksum_sha256: str | None,
    dataset_id: str,
    source_kind: str,
    expected_timeframe: str = "15m",
    parent_manifest_sha256: str | None = None,
) -> dict:
    """Verify locally accessible original bytes against independently supplied checksum.

    A successful result proves only byte custody and explicit dataset labeling.
    Query, temporal, warehouse and PIT claims require separate receipts.
    """
    if not dataset_id or not dataset_id.strip():
        raise ValueError("dataset_id required")
    if expected_timeframe != "15m":
        raise ValueError("historical E preflight requires 15m")
    if source_kind not in ("ORIGINAL_PUBLISHER", "SYNTHETIC_TEST_ONLY"):
        raise ValueError("source_kind must be explicit")
    payload = {
        "schema": SCHEMA,
        "dataset_id": dataset_id,
        "source_kind": source_kind,
        "timeframe": expected_timeframe,
        "status": BLOCKED,
        "source_sha256": None,
        "publisher_checksum_sha256": publisher_checksum_sha256,
        "parent_manifest_sha256": parent_manifest_sha256,
        "historical_pit": "NOT_ATTESTED",
        "trading_authority": "NONE",
        "reason": "SOURCE_UNAVAILABLE_OR_NOT_AUTHENTICATED",
    }
    if source_kind != "ORIGINAL_PUBLISHER":
        payload["reason"] = "SYNTHETIC_NEVER_HISTORICAL"
        return _seal(payload)
    if not publisher_checksum_sha256 or len(publisher_checksum_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in publisher_checksum_sha256):
        payload["reason"] = "PUBLISHER_CHECKSUM_MISSING_OR_INVALID"
        return _seal(payload)
    if zip_path is None:
        return _seal(payload)
    path = Path(zip_path)
    if not path.is_file():
        return _seal(payload)
    digest = _sha_file(path)
    payload["source_sha256"] = digest
    if digest != publisher_checksum_sha256.lower():
        payload["reason"] = "PUBLISHER_CHECKSUM_MISMATCH"
        return _seal(payload)
    if not path.name.endswith(".zip"):
        payload["reason"] = "EXPECTED_ORIGINAL_ZIP"
        return _seal(payload)
    payload["status"] = VERIFIED
    payload["reason"] = "CUSTODY_BYTES_ONLY_TEMPORAL_AND_PIT_NOT_ATTESTED"
    return _seal(payload)


def verify_preflight_receipt(receipt: Mapping) -> bool:
    if receipt.get("schema") != SCHEMA or receipt.get("trading_authority") != "NONE":
        return False
    if receipt.get("historical_pit") != "NOT_ATTESTED":
        return False
    if receipt.get("status") not in (BLOCKED, VERIFIED):
        return False
    if receipt.get("status") == VERIFIED:
        checksum = receipt.get("publisher_checksum_sha256")
        source = receipt.get("source_sha256")
        if (receipt.get("source_kind") != "ORIGINAL_PUBLISHER"
                or not isinstance(checksum, str)
                or len(checksum) != 64
                or not isinstance(source, str)
                or source != checksum.lower()):
            return False
    payload = dict(receipt)
    sha = payload.pop("receipt_sha256", None)
    return isinstance(sha, str) and _seal(payload)["receipt_sha256"] == sha
