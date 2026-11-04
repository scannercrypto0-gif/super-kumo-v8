"""AQL-CORE-237: bounded original-byte custody *admission*, not PIT certification.

Use only already-retained, explicitly authorized bytes supplied by the caller.
This module delegates parsing, staged immutability, correction and query to
existing #226 Bridge/HistoricalLibrary. A matching supplied hash is NOT an
independently verified vendor signature or a prospective availability receipt.
"""
from __future__ import annotations

import re

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    BridgeError, OfflineBridgeStager, digest, export_archive_query,
    export_vault_csv, export_binance_native_zip, raw_sha, verify_packet,
)
from research_wp_r0.aql_core_research_query_seam_v1 import (
    REQUEST_SCHEMA, query_custody,
)
from research_wp_r0.historical_library import HistoricalLibrary

ADMISSION_SCHEMA = "aql.core.historical-original-admission.v1"
PIN_SCHEMA = "aql.core.external-original-byte-pin.v1"
_ZIP_FIELDS = frozenset(("archive_name", "csv_member_name",
                         "csv_member_sha256", "checksum_file_sha256"))
_PIN_FIELDS = frozenset((
    "schema", "source_kind", "original_object_id", "original_sha256",
    "provenance_reference", "captured_at_ms", "claimed_available_at_ms",
    "expected_inventory_sha256", "vault_object_metadata",
    "universe_manifest_sha256", "universe_member_count", "test_only",
))
_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class SourceAdmissionError(ValueError):
    """Stable typed fail-closed boundary error; no private paths in messages."""


def _require(condition, code):
    if not condition:
        raise SourceAdmissionError(code)


def _sha(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def _ms(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def _validate_pin(pin, spec, cutoff):
    _require(type(pin) is dict and set(pin) ==
             (_PIN_FIELDS | _ZIP_FIELDS if pin.get("source_kind") == "BINANCE_KLINES_ZIP"
              else _PIN_FIELDS), "INVALID_PIN_FIELDS")
    _require(pin["schema"] == PIN_SCHEMA, "INVALID_PIN_SCHEMA")
    _require(pin["source_kind"] in ("SEALED_ARCHIVE_QUERY", "RAW_VAULT_CSV", "BINANCE_KLINES_ZIP"),
             "UNSUPPORTED_ORIGINAL_SOURCE")
    _require(type(pin["original_object_id"]) is str
             and _IDENTIFIER.fullmatch(pin["original_object_id"]) is not None
             and type(pin["provenance_reference"]) is str
             and _IDENTIFIER.fullmatch(pin["provenance_reference"]) is not None,
             "SOURCE_IDENTITY_REQUIRED")
    _require(_sha(pin["original_sha256"]), "EXTERNAL_ORIGINAL_SHA_REQUIRED")
    _require(type(pin["test_only"]) is bool
             and type(spec) is dict and type(spec.get("test_only")) is bool
             and pin["test_only"] == spec["test_only"], "SOURCE_TEST_CLASS_MISMATCH")
    for field in ("captured_at_ms", "claimed_available_at_ms"):
        _require(pin[field] is None or _ms(pin[field]), "INVALID_CAPTURE_OR_AVAILABILITY")
    if pin["captured_at_ms"] is not None and pin["claimed_available_at_ms"] is not None:
        _require(pin["claimed_available_at_ms"] <= pin["captured_at_ms"],
                 "CLAIMED_AVAILABILITY_AFTER_CAPTURE")
    if pin["claimed_available_at_ms"] is not None:
        _require(pin["claimed_available_at_ms"] <= cutoff,
                 "CLAIMED_SOURCE_UNAVAILABLE_AT_CUTOFF")
    if pin["universe_manifest_sha256"] is not None:
        _require(_sha(pin["universe_manifest_sha256"])
                 and type(pin["universe_member_count"]) is int
                 and pin["universe_member_count"] >= 1,
                 "INVALID_UNIVERSE_CLAIM")
    else:
        _require(pin["universe_member_count"] is None, "UNIVERSE_COUNT_UNANCHORED")
    if pin["source_kind"] == "SEALED_ARCHIVE_QUERY":
        _require(_sha(pin["expected_inventory_sha256"])
                 and pin["vault_object_metadata"] is None,
                 "ARCHIVE_INVENTORY_PIN_REQUIRED")
    elif pin["source_kind"] == "BINANCE_KLINES_ZIP":
        _require(pin["expected_inventory_sha256"] is None
                 and pin["vault_object_metadata"] is None
                 and all(_sha(pin[k]) for k in
                         ("csv_member_sha256", "checksum_file_sha256"))
                 and type(pin["archive_name"]) is str
                 and type(pin["csv_member_name"]) is str,
                 "NATIVE_ZIP_EXTERNAL_PINS_REQUIRED")
    else:
        _require(pin["expected_inventory_sha256"] is None
                 and type(pin["vault_object_metadata"]) is dict,
                 "VAULT_METADATA_REQUIRED")
        if not pin["test_only"]:
            _require(pin["vault_object_metadata"].get("evidence_class")
                     != "FIXTURE_SYNTHETIC", "SYNTHETIC_AS_REAL_DENIED")


def source_not_available(dataset_id=None):
    """Explicit non-success response when original bytes are not accessible."""
    return {
        "schema": ADMISSION_SCHEMA,
        "status": "SOURCE_NOT_AVAILABLE",
        "dataset_id": dataset_id,
        "source_bytes_sha256": None,
        "manifest_integrity_sha256": None,
        "query": None,
        "authenticated_source": "NOT_CONNECTED",
        "independent_provenance": "NOT_ATTESTED",
        "confirmed_pit": "NOT_ATTESTED",
        "complete_market_universe": "NOT_ATTESTED",
        "factory_scientific_input": "BLOCKED",
        "reason": "NO_AUTHORIZED_RETAINED_ORIGINAL_BYTES",
    }


def admit_original_bytes(
    source_bytes, pin, spec, *, stager: OfflineBridgeStager,
    library: HistoricalLibrary, decision_cutoff_ms: int,
    checksum_file_bytes: bytes | None = None,
):
    """Stage one bounded original source object and return sealed custody proof.

    The outside caller owns lawful-access and independent trust verification.
    This function cannot turn an asserted provenance_reference or self-reported
    capture/available timestamp into verified evidence, and ALWAYS denies
    prospective PIT/Factory scientific eligibility until external verification.
    It does not access any external URL or filesystem source beyond the
    explicitly supplied Bridge staging directory.
    """
    if source_bytes is None:
        return source_not_available(spec.get("dataset_id") if type(spec) is dict else None)
    _require(type(source_bytes) is bytes and len(source_bytes) > 0,
             "ORIGINAL_BYTES_REQUIRED")
    _require(type(stager) is OfflineBridgeStager
             and type(library) is HistoricalLibrary, "EXISTING_BRIDGE_REQUIRED")
    _require(_ms(decision_cutoff_ms), "INVALID_DECISION_CUTOFF")
    _validate_pin(pin, spec, decision_cutoff_ms)
    # Caller-supplied expected hash is checked against raw bytes independently
    # of decoding. This is a pin match; trust in that supplied pin is not proven.
    _require(raw_sha(source_bytes) == pin["original_sha256"],
             "ORIGINAL_BYTE_SHA_MISMATCH")
    if pin["source_kind"] == "SEALED_ARCHIVE_QUERY":
        packet = export_archive_query(
            source_bytes,
            expected_source_sha256=pin["original_sha256"],
            expected_inventory_hash=pin["expected_inventory_sha256"],
            spec=spec,
        )
    elif pin["source_kind"] == "BINANCE_KLINES_ZIP":
        _require(type(checksum_file_bytes) is bytes,
                 "NATIVE_ZIP_CHECKSUM_FILE_REQUIRED")
        packet = export_binance_native_zip(
            source_bytes, expected_zip_sha256=pin["original_sha256"],
            archive_name=pin["archive_name"],
            member_name=pin["csv_member_name"],
            member_sha256=pin["csv_member_sha256"],
            checksum_file_bytes=checksum_file_bytes,
            checksum_file_sha256=pin["checksum_file_sha256"],
            spec=spec,
        )
    else:
        packet = export_vault_csv(
            source_bytes,
            expected_source_sha256=pin["original_sha256"],
            object_metadata=pin["vault_object_metadata"],
            spec=spec,
        )
    verify_packet(packet, source_bytes)
    _require(packet["source_bytes_sha256"] == pin["original_sha256"]
             and packet["spec"]["dataset_id"] == spec["dataset_id"]
             and packet["spec"]["version"] == spec["version"]
             and packet["evidence_class"] ==
                 ("SYNTHETIC_TEST" if pin["test_only"]
                  else "RETROSPECTIVE_NON_PIT"),
             "PACKET_SOURCE_IDENTITY_DRIFT")

    key = stager.stage(packet, source_bytes)
    # Reuse bounded checkpoints, exact source-byte readback, version and
    # correction checks; do not duplicate/import a separate custody store.
    progress = 0
    while progress < len(packet["bars"]):
        progress, total = stager.advance(key, batch_size=64)
        _require(total == len(packet["bars"]), "CHECKPOINT_TOTAL_DRIFT")
    receipt = stager.commit(key, library)
    _require(receipt["packet_sha256"] == key
             and receipt["source_bytes_sha256"] == pin["original_sha256"]
             and receipt["manifest_integrity_sha256"], "CUSTODY_RECEIPT_DRIFT")
    req = {
        "schema": REQUEST_SCHEMA, "dataset_id": spec["dataset_id"],
        "version": spec["version"], "start_ms": spec["start_ms"],
        "end_exclusive_ms": spec["end_exclusive_ms"],
        "decision_cutoff_ms": decision_cutoff_ms,
        "require_complete": False, "confirmed_only": False,
    }
    query = query_custody(library, req)
    _require(query["status"] == "OK", "READ_ONLY_QUERY_DENIED")
    result = query["result"]
    _require(result["source_bytes_sha256"] == pin["original_sha256"]
             and result["manifest_integrity_sha256"] ==
                 receipt["manifest_integrity_sha256"]
             and result["dataset_id"] == spec["dataset_id"]
             and result["version"] == spec["version"]
             and result["decision_cutoff_ms"] == decision_cutoff_ms
             and result["status"] in ("COMPLETE", "PARTIAL", "UNKNOWN")
             and result["available_bar_count"]
                 + len(result["missing_bar_opens"]) ==
                 result["required_bar_count"],
             "QUERY_COVERAGE_OR_SOURCE_DRIFT")
    _require(all(b["availability_kind"] == "RETROSPECTIVE"
                 and b["observation_cutoff_ms"] <= decision_cutoff_ms
                 for b in result["bars"]), "FALSE_PIT_UPGRADE")
    body = {
        "schema": ADMISSION_SCHEMA,
        "status": ("TEST_ONLY_INTEGRITY_VERIFIED" if pin["test_only"]
                   else "ORIGINAL_PIN_MATCHED_PROVENANCE_PENDING"),
        "dataset_id": spec["dataset_id"], "version": spec["version"],
        "source_kind": pin["source_kind"],
        "original_object_id": pin["original_object_id"],
        "original_pin_claim_sha256": digest(pin),
        "source_bytes_sha256": pin["original_sha256"],
        "native_csv_member_sha256": (pin["csv_member_sha256"]
                                     if pin["source_kind"] == "BINANCE_KLINES_ZIP"
                                     else None),
        "native_checksum_file_sha256": (pin["checksum_file_sha256"]
                                         if pin["source_kind"] == "BINANCE_KLINES_ZIP"
                                         else None),
        "packet_sha256": key,
        "custody_receipt_sha256": receipt["receipt_sha256"],
        "manifest_integrity_sha256": receipt["manifest_integrity_sha256"],
        "correction_parent_source_sha256": spec["parent_source_sha256"],
        "correction_reason": spec["correction_reason"],
        "decision_cutoff_ms": decision_cutoff_ms,
        "coverage": result["status"],
        "missing_bar_opens": result["missing_bar_opens"],
        "available_bar_count": result["available_bar_count"],
        "required_bar_count": result["required_bar_count"],
        "underlying_availability_class": result["availability_class"],
        "query": query,
        "authenticated_source": "NOT_ATTESTED",
        "independent_provenance": "NOT_ATTESTED",
        "source_available_at_cutoff": "NOT_ATTESTED",
        "confirmed_pit": "NOT_ATTESTED",
        "complete_market_universe": "NOT_ATTESTED",
        "factory_scientific_input": "BLOCKED",
        "work_authentic_e2e": "NOT_CONNECTED",
        "production_custody": "NOT_ATTESTED",
        "paper_live_trading": "DISABLED",
    }
    return {**body, "manifest_record_sha256": digest(body)}
