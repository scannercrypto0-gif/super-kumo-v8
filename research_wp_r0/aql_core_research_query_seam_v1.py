"""Read-only Core→Research seam; no data mutation or PIT promotion.

AQL-HISTORICAL-RESEARCH-VERTICAL-SLICE C2. The underlying bridge is the
sole owner of validation, provenance, temporal filtering and coverage.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    BridgeError, custody_range,
)
from research_wp_r0.historical_library import HistoricalDataError, HistoricalLibrary

SCHEMA = "aql.core-research.custody-query-result.v1"
REQUEST_SCHEMA = "aql.core-research.custody-query.v1"
ALLOWED_FIELDS = frozenset({
    "schema", "dataset_id", "version", "start_ms", "end_exclusive_ms",
    "decision_cutoff_ms", "require_complete", "confirmed_only",
})


def _error(code: str, *, category: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "ERROR",
        "error": {"code": code, "category": category, "retryable": False},
        "result": None,
        "evidence_class": "NO_EVIDENCE",
    }


def query_custody(library: HistoricalLibrary, request: Mapping[str, Any]) -> dict[str, Any]:
    """Return an explicit versioned success/error envelope; never raise for
    malformed client requests or expected historical/bridge query errors.

    This is NOT an authorization endpoint, independent custody attestation,
    or evidence that a retrospective bar was available in real time.
    """
    if type(request) is not dict or set(request) != ALLOWED_FIELDS:
        return _error("INVALID_REQUEST_FIELDS", category="REQUEST")
    if request.get("schema") != REQUEST_SCHEMA:
        return _error("UNSUPPORTED_REQUEST_SCHEMA", category="REQUEST")
    for key in ("dataset_id",):
        if type(request[key]) is not str or not request[key] or len(request[key]) > 160:
            return _error("INVALID_DATASET_ID", category="REQUEST")
    if request["version"] is not None and (
        type(request["version"]) is not int or request["version"] < 1
    ):
        return _error("INVALID_VERSION", category="REQUEST")
    for key in ("start_ms", "end_exclusive_ms", "decision_cutoff_ms"):
        if type(request[key]) is not int or request[key] < 0:
            return _error("INVALID_QUERY_TIME", category="REQUEST")
    if request["start_ms"] >= request["end_exclusive_ms"]:
        return _error("INVALID_QUERY_RANGE", category="REQUEST")
    if type(request["require_complete"]) is not bool or type(request["confirmed_only"]) is not bool:
        return _error("INVALID_QUERY_FLAGS", category="REQUEST")
    if not isinstance(library, HistoricalLibrary):
        return _error("HISTORICAL_LIBRARY_REQUIRED", category="REQUEST")
    try:
        result = custody_range(
            library, request["dataset_id"], request["start_ms"],
            request["end_exclusive_ms"], request["decision_cutoff_ms"],
            version=request["version"],
            require_complete=request["require_complete"],
            confirmed_only=request["confirmed_only"],
        )
    except BridgeError as exc:
        return _error(str(exc), category="CUSTODY")
    except (HistoricalDataError, KeyError, ValueError) as exc:
        # Do not expose exception text: it can contain paths/source metadata.
        return _error(type(exc).__name__.upper(), category="HISTORICAL_LIBRARY")
    # No reconstructed hashes or fake receipts: forward exactly what Core returned.
    return {
        "schema": SCHEMA,
        "status": "OK",
        "error": None,
        "result": result,
        "evidence_class": (
            "SYNTHETIC_TEST" if result["availability_class"] == "SYNTHETIC_TEST"
            else "RETROSPECTIVE_NON_PIT"
            if result["availability_class"] == "RETROSPECTIVE_NOT_PIT"
            else "CONFIRMED_ONLY_QUERY_NOT_ATTESTATION"
        ),
    }
