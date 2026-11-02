"""B3 TEST_ONLY Core F1 original-parent bytes → real pinned Vault bridge.

This module deliberately does not import Vault into Core's production path:
dependency is injected from pinned #211 read-only overlay. Source prefix SHA
remains the ORIGINAL Core F1 fixture value, distinct from parent vault bytes.
Neither locally admitted bytes nor a self-hashed manifest is external custody.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .aql_f1_decision_capture_v1 import CaptureError, digest, jcs_bytes
from .aql_f1_parent_witness_v1 import validate_parent_binding

VAULT_PIN = "2ddfb2f4a6e145c6579820beb03e4d678594de21"
FACTORY_B2_PIN = "ac7f160005672140a3254eb2ed82f4d586432b69"
CORE_B2_BASELINE = "83d44ef23392b9ca9628d18d0f6fc909cd98e4ff"
B2_INPUT_SHA256 = "42005d09e3674420ddd8a761d40540c8e6509e8e79943d1f6a9821f692823b09"
FIXTURE_ORIGIN = "TEST_ONLY_NOT_VENDOR_ORIGINAL_2024"

def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _reject(reason: str) -> None:
    raise CaptureError(reason)

def parent_input_for_pair(schedule: Mapping[str, Any],
                          candidates: list[dict]) -> dict:
    """Construct TEST_ONLY parent raw bytes, no identity rewrite of F1."""
    if schedule.get("test_origin") != "SYNTHETIC_DETERMINISTIC_NOT_HISTORICAL_2024":
        _reject("NOT_B2_TEST_ORIGIN")
    pair = schedule["pair_id"]
    rows = [c for c in candidates if c.get("pair_id") == pair]
    if len(rows) != 2 or {c.get("arm") for c in rows} != {"BASE", "SHADOW"}:
        _reject("B3_PAIR_ARMS_INCOMPLETE")
    for rec in rows:
        if (rec["c2_identity"] != schedule["c2_identity"] or
            rec["decision_cutoff_ms"] != schedule["decision_cutoff_ms"] or
            rec["source_id"] != schedule["source_id"] or
            rec["source_version"] != schedule["source_version"] or
            rec["source_bytes_sha256"] != schedule["source_bytes_sha256"] or
            rec["correction_generation"] != schedule["correction_generation"]):
            _reject("B3_F1_SOURCE_OR_CUTOFF_MISMATCH")
    # Deterministic synthetic parent content; no backdating of an authentic
    # issuer receipt, no altering preexisting F1 source SHA/correction lineage.
    raw = jcs_bytes({
        "schema_version": "aql.b3-test-parent-bytes.v1",
        "test_origin": FIXTURE_ORIGIN,
        "pair_id": pair,
        "c2_identity": schedule["c2_identity"],
        "source_id": schedule["source_id"],
        "source_version": schedule["source_version"],
        "original_f1_source_bytes_sha256": schedule["source_bytes_sha256"],
        "correction_generation": schedule["correction_generation"],
        "decision_cutoff_ms": schedule["decision_cutoff_ms"],
        "arm_record_sha256": {
            c["arm"]: c["f1_record_sha256"] for c in rows
        },
    }) + b"\n"
    return {
        "pair_id": pair,
        "parent_bytes": raw,
        "parent_sha256": _sha(raw),
        "source_f1_sha256": schedule["source_bytes_sha256"],
        "cutoff_ms": schedule["decision_cutoff_ms"],
        "correction_generation": schedule["correction_generation"],
        "arm_sha256": {c["arm"]: c["f1_record_sha256"] for c in rows},
    }

def make_vault_meta(parent: Mapping[str, Any], meta_types: Any) -> Any:
    """Use exact #211 RawObjectMeta schema; no authority from a fake receipt."""
    Schema = meta_types
    raw = parent["parent_bytes"]
    pair = parent["pair_id"]
    # TEST_ONLY logical identity uniquely binds the immutable Core F1 pair.
    from datetime import timedelta
    start = datetime.fromtimestamp(parent["cutoff_ms"] / 1000, timezone.utc)
    end = start + timedelta(minutes=15)
    start_utc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    vendor = "AQL_TEST_ONLY"
    instrument = "B2F1_" + pair[:12]
    source_format = "JSON_LINES"
    format_version = "aql-b3-test-v1"
    lid = Schema.logical_identity_key(
        vendor=vendor, instrument=instrument, market="test",
        interval="15m", coverage_start_utc=start_utc,
        coverage_end_utc=end_utc, source_format=source_format,
        format_version=format_version,
    )
    return Schema.RawObjectMeta(
        schema_version=Schema.SCHEMA_VERSION,
        content_sha256=_sha(raw), byte_length=len(raw),
        vendor=vendor, instrument=instrument, market="test",
        interval="15m", source_format=Schema.SourceFormat.JSON_LINES,
        format_version=format_version, coverage_start_utc=start_utc,
        coverage_end_utc=end_utc,
        coverage_status=Schema.CoverageStatus.UNKNOWN,
        evidence_class=Schema.EvidenceClass.FIXTURE_SYNTHETIC,
        trust_status=Schema.TrustStatus.UNVERIFIED,
        original_filename="b3-"+pair[:12]+".jsonl",
        capture_provenance=FIXTURE_ORIGIN,
        archive_member_path="", archive_member_sha256="",
        logical_identity_key=lid,
        admitted_at_utc="2026-11-01T00:00:00Z",
        correction_generation=0,
        parent_content_sha256="",
    )

def exercised_vault_parent(pair_input: Mapping[str, Any],
                           vault: Any, schema: Any) -> dict:
    """Actual Vault.admit + .read + .manifest_entries; no mocked calls."""
    raw = pair_input["parent_bytes"]
    metadata = make_vault_meta(pair_input, schema)
    vault.admit(raw, metadata)
    readback = vault.read(metadata.content_sha256)
    if readback != raw or _sha(readback) != metadata.content_sha256:
        _reject("B3_VAULT_READBACK_MISMATCH")
    entries = [item for item in vault.manifest_entries()
               if item.get("logical_identity_key") == metadata.logical_identity_key]
    if len(entries) != 1 or entries[0]["content_sha256"] != _sha(raw):
        _reject("B3_VAULT_MANIFEST_IDENTITY_MISMATCH")
    manifest_bytes = jcs_bytes(entries[0]) + b"\n"
    # No forged historical source timestamps: hardcode only bounded TEST_ONLY
    # time pins for a schema check, never third-party publication assertion.
    return {
        "pair_id": pair_input["pair_id"],
        "vault_parent_sha256": _sha(raw),
        "vault_manifest_record_sha256": _sha(manifest_bytes),
        "vault_manifest_record": entries[0],
        "vault_logical_identity_key": metadata.logical_identity_key,
        "f1_source_bytes_sha256": pair_input["source_f1_sha256"],
        "f1_original_record_sha256_by_arm": pair_input["arm_sha256"],
        "cutoff_ms": pair_input["cutoff_ms"],
        "correction_generation": pair_input["correction_generation"],
        "evidence_class": FIXTURE_ORIGIN,
        "software_vault_readback": "PASS_LOCAL_VAULT_BYTES_MANIFEST",
        "original_parent_issuer_custody_clock": "BLOCKED_EXTERNAL_EVIDENCE",
        "parent_bytes": raw,
        "manifest_bytes": manifest_bytes,
    }

def bound_parent_evidence(record: Mapping[str, Any],
                          retained: Mapping[str, Any],
                          *,
                          source_published_at_ms: int,
                          source_finalized_at_ms: int,
                          correction_published_at_ms: int,
                          parent_receipt_ref: str = "TEST_ONLY_VAULT_LOCAL_MANIFEST_NOT_EXTERNAL") -> dict:
    """Core parent binding + exact readback bytes, synthetic timestamps labeled."""
    if (record["pair_id"] != retained["pair_id"] or
        record["f1_record_sha256"] != retained["f1_original_record_sha256_by_arm"].get(record["arm"]) or
        record["source_bytes_sha256"] != retained["f1_source_bytes_sha256"] or
        record["decision_cutoff_ms"] != retained["cutoff_ms"] or
        record["correction_generation"] != retained["correction_generation"]):
        _reject("B3_ORIGINAL_F1_PARENT_IDENTITY_DRIFT")
    binding = {
        "schema_version": "aql.f1-raw-parent-binding.v1",
        "parent_source_id": "AQL_TEST_ONLY_VAULT_" + record["pair_id"][:12],
        "parent_source_version": "aql-b3-test-v1",
        "parent_source_bytes_sha256": retained["vault_parent_sha256"],
        "parent_manifest_sha256": retained["vault_manifest_record_sha256"],
        "source_id": record["source_id"],
        "source_version": record["source_version"],
        "source_bytes_sha256": record["source_bytes_sha256"],
        "correction_generation": record["correction_generation"],
        "correction_lineage_sha256": record["correction_lineage_sha256"],
        "source_published_at_ms": source_published_at_ms,
        "correction_published_at_ms": correction_published_at_ms,
        "source_finalized_at_ms": source_finalized_at_ms,
        "parent_receipt_ref": parent_receipt_ref,
    }
    binding["parent_binding_sha256"] = digest(binding)
    # Validate parent binding even with synthetic positive callback but NEVER
    # translate returned True into independently authorized proof.
    controlled_structure_valid = validate_parent_binding(
        record, binding,
        parent_manifest_bytes=retained["manifest_bytes"],
        parent_bytes=retained["parent_bytes"],
        parent_witness=lambda _: True,
    )
    independently_verified = validate_parent_binding(
        record, binding,
        parent_manifest_bytes=retained["manifest_bytes"],
        parent_bytes=retained["parent_bytes"],
        parent_witness=None,
    )
    return {
        "raw_parent_binding": binding,
        "structural_parent_binding_test_only": controlled_structure_valid,
        "independent_parent_proof": independently_verified,
        "f1_capture_status": "UNVERIFIED",
        "external_evidence_status": "BLOCKED_EXTERNAL_EVIDENCE",
    }

def report_safe_pair(retained: Mapping[str, Any]) -> dict:
    return {k:v for k,v in retained.items()
            if k not in ("parent_bytes","manifest_bytes")}
