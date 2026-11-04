"""TEST_ONLY, read-only Core custody compatibility evidence for Factory #229 and Work #228.

This module is deliberately not an adapter that executes Factory/Work.  It binds
an actual immutable Core packet + registration receipt to the Core query result,
then issues schema-specific, fail-closed mapping verdicts.  Foreign PR-owned code
and authentic sources remain NOT_CONNECTED until separately authorized.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from research_wp_r0.aql_core_research_query_seam_v1 import (
    REQUEST_SCHEMA, SCHEMA, query_custody,
)
from research_wp_r0.aql_archive_custody_bridge_v1 import (
    PACKET_SCHEMA, RECEIPT_SCHEMA, digest, raw_sha, verify_packet,
)
from research_wp_r0.historical_library import HistoricalLibrary

SCHEMA_COMPAT = "aql.core-research.consumer-compatibility.v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
FACTORY_SCHEMA = "aql.factory.research-consumer-seam.v1"
WORK_STATUS = "NOT_CONNECTED"
FACTORY_STATUS = "NOT_CONNECTED"


def _require(ok, code):
    if not ok:
        raise ValueError("CORE_COMPAT_" + code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def compatibility_evidence(library: HistoricalLibrary, packet: dict,
                           original_source_bytes: bytes, receipt: dict,
                           request: dict) -> dict:
    """Only a pinned synthetic packet is admissible to this compatibility gate.

    Real/retrospective sources are explicitly out of scope. No consumer import,
    permission elevation, data acquisition, schedule creation or evaluation.
    """
    _require(type(request) is dict and request.get("schema") == REQUEST_SCHEMA,
             "REQUEST_SCHEMA")
    _require(type(request.get("version")) is int and request["version"] > 0,
             "EXPLICIT_VERSION_REQUIRED")
    _require(request.get("require_complete") is False
             and request.get("confirmed_only") is False, "READ_ONLY_FLAGS")
    _require(type(packet) is dict and packet.get("schema") == PACKET_SCHEMA
             and packet.get("spec", {}).get("test_only") is True
             and packet.get("evidence_class") == "SYNTHETIC_TEST"
             and packet.get("external_custody_verified") is False,
             "SYNTHETIC_ONLY")
    verify_packet(packet, original_source_bytes)
    _require(type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA,
             "RECEIPT_SCHEMA")
    seal = receipt.get("receipt_sha256")
    _require(type(seal) is str and HEX.fullmatch(seal) is not None
             and digest({k: v for k, v in receipt.items()
                         if k != "receipt_sha256"}) == seal, "RECEIPT_TAMPER")
    spec = packet["spec"]
    _require(receipt.get("packet_sha256") == packet["packet_sha256"]
             and receipt.get("source_bytes_sha256") == raw_sha(original_source_bytes)
             and receipt.get("dataset_id") == spec["dataset_id"]
             and receipt.get("version") == spec["version"]
             and receipt.get("evidence_class") == "SYNTHETIC_TEST"
             and receipt.get("destination") == "HISTORICAL_LIBRARY_IN_MEMORY_ONLY"
             and receipt.get("production_integration") == "NOT_ACTIVATED"
             and receipt.get("independent_custody_verified") is False,
             "RECEIPT_SOURCE_OR_AUTHORITY")
    _require(request.get("dataset_id") == spec["dataset_id"]
             and request["version"] == spec["version"]
             and request.get("start_ms") == spec["start_ms"]
             and request.get("end_exclusive_ms") == spec["end_exclusive_ms"]
             and type(request.get("decision_cutoff_ms")) is int
             and request["decision_cutoff_ms"] >= 0,
             "REQUEST_SOURCE_OR_SCOPE")
    query = query_custody(library, request)
    _require(query["schema"] == SCHEMA and query["status"] == "OK"
             and query["evidence_class"] == "SYNTHETIC_TEST",
             "QUERY_FAIL_CLOSED")
    result = query["result"]
    _require(result["schema"] == "aql.bridge.custody-range.v1"
             and result["dataset_id"] == spec["dataset_id"]
             and result["version"] == spec["version"]
             and result["source_bytes_sha256"] == receipt["source_bytes_sha256"]
             and result["manifest_integrity_sha256"] ==
                 receipt["manifest_integrity_sha256"]
             and result["decision_cutoff_ms"] == request["decision_cutoff_ms"]
             and result["availability_class"] == "SYNTHETIC_TEST"
             and result["source_confidence"] == "LOCAL_CHECKSUM_AND_PIN_ONLY",
             "QUERY_MANIFEST_OR_AVAILABILITY")
    expected = len(packet["bars"])
    _require(result["required_bar_count"] == expected
             and result["available_bar_count"] + len(result["missing_bar_opens"]) ==
                 expected
             and result["status"] in ("COMPLETE", "PARTIAL", "UNKNOWN")
             and (result["status"] == "COMPLETE") == (len(result["missing_bar_opens"]) == 0)
             and (result["status"] == "UNKNOWN") == (result["available_bar_count"] == 0),
             "COVERAGE_CONSERVATION")
    for bar in result["bars"]:
        _require(bar["availability_kind"] == "RETROSPECTIVE"
                 and bar["observation_cutoff_ms"] <= request["decision_cutoff_ms"],
                 "FUTURE_OR_PIT_UPGRADE")
    _require(all(b["source"] == "synthetic" for b in packet["bars"]),
             "SOURCE_PROMOTION")
    correction = {
        "version": spec["version"],
        "parent_source_sha256": spec["parent_source_sha256"],
        "correction_reason": spec["correction_reason"],
    }
    _require(spec["version"] == 1 or (
        type(correction["parent_source_sha256"]) is str
        and HEX.fullmatch(correction["parent_source_sha256"]) is not None
        and type(correction["correction_reason"]) is str
        and bool(correction["correction_reason"].strip())),
        "CORRECTION_LINEAGE")
    # Schema compatibility is a mapping, NOT a fabricated Factory feature or
    # Work receipt. Factory requires real paired schedule/attempt census and
    # Work requires independently pinned source checkouts/manifest.
    mapping = {
        "factory": {
            "target_schema": FACTORY_SCHEMA,
            "consumer_pr": 229,
            "status": FACTORY_STATUS,
            "source_manifest_sha256": result["manifest_integrity_sha256"],
            "verified_source_bytes_sha256": result["source_bytes_sha256"],
            "cutoff_ms": request["decision_cutoff_ms"],
            "feature_availability_class": "RETROSPECTIVE_NON_PIT",
            "coverage": result["status"],
            "requires": [
                "PINNED_PAIRED_SCHEDULE_AND_PAIR_ARM_CENSUS",
                "AUTHORITATIVE_FEATURE_SNAPSHOT_AT_DECISION_CUTOFF",
                "FACTORY_OWNER_ADAPTER_AUTHORIZATION",
            ],
        },
        "work": {
            "consumer_pr": 228,
            "status": WORK_STATUS,
            "source_manifest_sha256": result["manifest_integrity_sha256"],
            "verified_source_bytes_sha256": result["source_bytes_sha256"],
            "cutoff_ms": request["decision_cutoff_ms"],
            "coverage": result["status"],
            "requires": [
                "INDEPENDENT_MANIFEST_AND_CHECKOUT_PIN",
                "VERSIONED_WORK_ADAPTER_AUTHORIZATION",
                "AUTHENTIC_SOURCE_PERMISSION_AND_RECEIPT",
            ],
        },
    }
    body = {
        "schema": SCHEMA_COMPAT, "test_only": True,
        "evidence_class": "SYNTHETIC_TEST",
        "source_packet_sha256": packet["packet_sha256"],
        "source_bytes_sha256": result["source_bytes_sha256"],
        "source_receipt_sha256": receipt["receipt_sha256"],
        "manifest_integrity_sha256": result["manifest_integrity_sha256"],
        "dataset_id": spec["dataset_id"], "version": spec["version"],
        "correction_lineage": correction,
        "decision_cutoff_ms": request["decision_cutoff_ms"],
        "availability_class": "RETROSPECTIVE_NON_PIT",
        "coverage": result["status"],
        "missing_bar_opens": result["missing_bar_opens"],
        "available_bar_count": result["available_bar_count"],
        "required_bar_count": result["required_bar_count"],
        "factory_work_contract": mapping,
        "authentic_source": "NOT_CONNECTED",
        "scanner_universe": "NOT_CONNECTED",
        "discoverer": "NOT_CONNECTED",
        "production_custody": "NOT_ATTESTED",
        "pit_status": "NOT_ATTESTED", "trading_authority": "NONE",
    }
    return {**body, "artifact_sha256": sha256(_canonical(body)).hexdigest()}
