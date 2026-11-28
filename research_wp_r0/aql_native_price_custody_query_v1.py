"""Core #245: read-only, price-bearing historical custody range.

Query IDs and source/manifest pins must match the existing Bridge result.
Prices are HistoricalLibrary float representations of source-native CSV decimal
strings; exact original decimals remain anchored in immutable original ZIP.
Never reports independent availability, PIT attestation or eligibility.
"""
from __future__ import annotations

from math import isfinite

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_research_query_seam_v1 import query_custody
from research_wp_r0.historical_library import (
    BarQuality, DataAvailabilityKind, HistoricalLibrary, HistoricalDataError,
)

PRICE_QUERY_SCHEMA = "aql.core.historical-price-custody-query.v1"


def query_price_custody(
    library: HistoricalLibrary,
    request: dict,
    *, expected_source_sha256: str,
    expected_manifest_integrity_sha256: str,
) -> dict:
    """Enforces source/version/cutoff/coverage preservation before exposing OHLCV.

    The caller must pin original source and manifest digests from a trusted
    upstream admission. This read-only method does not authenticate such pins.
    """
    def deny(code):
        return {
            "schema": PRICE_QUERY_SCHEMA, "status": "ERROR",
            "error": code, "bars": [], "scientific_pit": "NOT_ATTESTED",
        }
    if type(library) is not HistoricalLibrary or type(request) is not dict:
        return deny("PRICE_QUERY_INVALID_INPUT")
    if (type(expected_source_sha256) is not str
            or type(expected_manifest_integrity_sha256) is not str
            or len(expected_source_sha256) != 64
            or len(expected_manifest_integrity_sha256) != 64):
        return deny("PRICE_QUERY_SOURCE_PINS_REQUIRED")
    if request.get("confirmed_only") is not False:
        return deny("PRICE_QUERY_RETROSPECTIVE_ONLY")
    base = query_custody(library, request)
    if base["status"] != "OK":
        return deny("PRICE_QUERY_CORE_QUERY_REJECTED")
    q = base["result"]
    if (q["source_bytes_sha256"] != expected_source_sha256
            or q["manifest_integrity_sha256"] != expected_manifest_integrity_sha256
            or q["version"] != request.get("version")
            or q["dataset_id"] != request.get("dataset_id")
            or q["decision_cutoff_ms"] != request.get("decision_cutoff_ms")):
        return deny("PRICE_QUERY_PIN_OR_SCOPE_MISMATCH")
    try:
        stored_manifest = library.get_manifest(q["dataset_id"], q["version"])
        all_bars = library.snapshot(
            q["dataset_id"], q["decision_cutoff_ms"], version=q["version"],
            require_confirmed_availability=False,
        )
    except (HistoricalDataError, ValueError, KeyError):
        return deny("PRICE_QUERY_LIBRARY_READ_FAILURE")
    if (not stored_manifest.verify_integrity()
            or stored_manifest.manifest_integrity_hash != q["manifest_integrity_sha256"]
            or stored_manifest.source_hash != q["source_bytes_sha256"]):
        return deny("PRICE_QUERY_MANIFEST_TAMPER")
    rows = []
    for b in all_bars:
        if not request["start_ms"] <= b.bar_open < request["end_exclusive_ms"]:
            continue
        if (not b.verify_checksum() or b.quality != BarQuality.FINAL
                or b.availability_kind != DataAvailabilityKind.RETROSPECTIVE
                or b.observation_cutoff_ms > q["decision_cutoff_ms"]
                or not all(isfinite(v) for v in
                           (b.open, b.high, b.low, b.close, b.volume))
                or b.low <= 0 or b.high < max(b.open, b.close, b.low)
                or b.low > min(b.open, b.close, b.high)
                or b.volume < 0):
            return deny("PRICE_QUERY_BAR_INVALID")
        rows.append({
            "bar_open_ms": b.bar_open, "bar_close_ms": b.bar_close,
            "open": b.open, "high": b.high, "low": b.low,
            "close": b.close, "volume": b.volume,
            "checksum": b.checksum,
            "observation_lower_bound_ms": b.observation_cutoff_ms,
            "historical_known_at_ms": None,
            "availability_kind": "RETROSPECTIVE",
        })
    rows.sort(key=lambda x: x["bar_open_ms"])
    base_rows = q["bars"]
    if (len(rows) != q["available_bar_count"]
            or len(base_rows) != len(rows)
            or any(
                x["bar_open_ms"] != y["bar_open"]
                or x["checksum"] != y["checksum"]
                or x["observation_lower_bound_ms"] != y["observation_cutoff_ms"]
                for x, y in zip(rows, base_rows)
            )):
        return deny("PRICE_QUERY_CUSTODY_DRIFT")
    if (len(rows) + len(q["missing_bar_opens"]) != q["required_bar_count"]
            or (q["status"] == "COMPLETE") != (not q["missing_bar_opens"])
            or (q["status"] == "UNKNOWN") != (len(rows) == 0)):
        return deny("PRICE_QUERY_COVERAGE_DRIFT")
    body = {
        "schema": PRICE_QUERY_SCHEMA, "status": "OK", "error": None,
        "dataset_id": q["dataset_id"], "version": q["version"],
        "source_bytes_sha256": q["source_bytes_sha256"],
        "manifest_integrity_sha256": q["manifest_integrity_sha256"],
        "decision_cutoff_ms": q["decision_cutoff_ms"],
        "coverage": q["status"],
        "required_bar_count": q["required_bar_count"],
        "available_bar_count": len(rows),
        "missing_bar_opens": q["missing_bar_opens"],
        "bars": rows,
        "numeric_projection": "HISTORICAL_LIBRARY_FLOAT_FROM_ORIGINAL_NATIVE_DECIMALS",
        "historical_known_at_ms": None,
        "source_availability": "RETROSPECTIVE_NON_PIT",
        "scientific_pit": "NOT_ATTESTED",
        "factory_scientific_input": "BLOCKED_PENDING_INDEPENDENT_EVIDENCE",
        "paper_live_trading": "DISABLED",
    }
    return {**body, "price_query_sha256": digest(body)}
