"""Core-owned, versioned F2_RECOVERY_EVIDENCE read-only verifier.

Diagnostic-only and deliberately NOT the original F2 report, SourceACK,
StrategyApproval, PIT witness, or Factory Consumer ACK. Never creates a
stage/vault/sqlite object and never calls their mutating constructors.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    digest, decode, verify_packet, _load_checkpoint,
)
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_core_f_private_f2_v1 import private_directory_gate
from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
    _month_bounds, ADMITTED_MONTHS, WIDTH_MS,
)
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.historical_library import HistoricalLibrary
from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager

SCHEMA = "aql.core.f2-recovery-readonly-source.v1"
RECOVERY_FILE_SHA = (
    "0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"
)
MAX_RECOVERY_FILE_BYTES = 5_000_000
MONTH_FIELDS = frozenset({
    "month", "state", "bars", "source_sha256",
    "core_245_native_price_query_sha256", "core_253_local_query_sha256",
    "warehouse_receipt_sha256", "dual_query_map_sha256",
})
SHA_FIELDS = tuple(sorted(x for x in MONTH_FIELDS if x.endswith("sha256")))


def need(ok, reason):
    if not ok:
        raise ValueError("CORE_F2_RECOVERY_" + reason)


def hexsha(value):
    return type(value) is str and len(value) == 64 and all(
        x in "0123456789abcdef" for x in value
    )


def _safe_existing_file(path, *, max_bytes=None):
    """Validate all ancestors; never resolve a symlink before testing it."""
    path = Path(path).absolute()
    need(not any(x.is_symlink() for x in (path, *path.parents)),
         "SYMLINK_PATH_DENIED")
    need(path.is_file(), "FILE_MISSING")
    size = path.stat().st_size
    need(size > 0 and (max_bytes is None or size <= max_bytes),
         "FILE_SIZE_OR_EMPTY")
    return path


def _safe_existing_dir(path):
    path = Path(path).absolute()
    need(not any(x.is_symlink() for x in (path, *path.parents)),
         "SYMLINK_DIRECTORY_DENIED")
    need(path.is_dir(), "DIRECTORY_MISSING")
    return path


def _read_json(path, *, max_bytes):
    return json.loads(_safe_existing_file(path, max_bytes=max_bytes).read_bytes())


def _canonical_warehouse_receipt(admission, packet, vault_meta, *, row_count):
    """Reconstruct *actual* #253 warehouse receipt from immutable parents.

    The persisted generation has immutable #226 custody admission JSON and a
    pinned manifest/stage packet. Recompute the canonical #253 receipt exactly
    with existing field definitions, NEVER from untrusted mapping input.
    """
    need(type(admission) is dict and
         admission.get("schema") == "aql.core.historical-source-admission.v1",
         "ACTUAL_ADMISSION_REQUIRED")
    spec = packet["spec"]
    vault_receipt = {
        "vault": "EXISTING_PINNED_RAW_VAULT",
        "sha256": admission["source_bytes_sha256"],
        "correction_ledger": "PINNED_APPEND_ONLY",
    }
    # For legacy #211 metadata, the exact vault receipt is not stored by
    # SQLite or stage. Do NOT fabricate a guessed receipt: the value must
    # be reconstructed from verifiable fields or rejected by the caller.
    return None


def _warehouse_receipt_from_actual(warehouse_root, vault_root, *,
                                   dataset_id, source_sha, source_entry,
                                   start_ms, end_exclusive_ms, cutoff_ms):
    _safe_existing_dir(warehouse_root)
    _safe_existing_dir(vault_root)
    private_directory_gate(warehouse_root)
    private_directory_gate(vault_root)
    db = _safe_existing_file(Path(warehouse_root) / "warehouse.sqlite")
    stage_root = _safe_existing_dir(Path(warehouse_root) / "stage")
    vault_objects = _safe_existing_dir(Path(vault_root) / "objects")
    _safe_existing_dir(Path(vault_root) / ".staging")
    index_file = _safe_existing_file(Path(vault_root) / "index.json", max_bytes=15_000_000)
    manifest_file = _safe_existing_file(Path(vault_root) / "manifest.jsonl",
                                        max_bytes=40_000_000)

    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1",
                          uri=True)
    try:
        row = con.execute(
            "SELECT source_sha, manifest_sha, packet_sha, receipt_sha,"
            " coverage, evidence_class, admission_json FROM generations"
            " WHERE dataset_id=? AND generation=1", (dataset_id,)
        ).fetchone()
        need(row is not None, "WAREHOUSE_GENERATION_MISSING")
        rows = con.execute(
            "SELECT COUNT(*), MIN(open_ms), MAX(open_ms) FROM price_bars"
            " WHERE dataset_id=? AND generation=1", (dataset_id,)
        ).fetchone()
    finally:
        con.close()
    g_source, manifest_sha, packet_sha, custody_receipt_sha, coverage, evidence_class, admission_json = row
    need(g_source == source_sha and
         hexsha(manifest_sha) and hexsha(packet_sha) and
         hexsha(custody_receipt_sha) and coverage == "COMPLETE",
         "WAREHOUSE_GENERATION_SOURCE_OR_INTEGRITY")
    need(rows[0] == source_entry["bars"] and rows[1] == start_ms and
         rows[2] == end_exclusive_ms - WIDTH_MS,
         "WAREHOUSE_GENERATION_BAR_GRID_DRIFT")

    admission = json.loads(admission_json)
    need(type(admission) is dict and
         admission.get("source_bytes_sha256") == source_sha and
         admission.get("manifest_integrity_sha256") == manifest_sha and
         admission.get("packet_sha256") == packet_sha and
         admission.get("custody_receipt_sha256") == custody_receipt_sha,
         "WAREHOUSE_ADMISSION_JSON_DRIFT")
    # The canonical source admission is individually signed by its SHA.
    seal = admission.get("manifest_record_sha256")
    need(hexsha(seal) and
         digest({k: v for k, v in admission.items()
                 if k != "manifest_record_sha256"}) == seal,
         "WAREHOUSE_ADMISSION_SEAL_DRIFT")

    folder = _safe_existing_dir(stage_root / packet_sha)
    packet_file = _safe_existing_file(folder / "packet.json", max_bytes=16_000_000)
    source_file = _safe_existing_file(folder / "source.bin", max_bytes=8_000_000)
    checkpoint = _safe_existing_file(folder / "checkpoint.json", max_bytes=200_000)
    receipt_file = _safe_existing_file(folder / "receipt.json", max_bytes=200_000)
    packet = decode(packet_file.read_bytes())
    original_raw = source_file.read_bytes()
    verify_packet(packet, original_raw)
    need(packet.get("packet_sha256") == packet_sha and
         packet.get("source_bytes_sha256") == source_sha and
         packet["spec"].get("dataset_id") == dataset_id and
         packet["spec"].get("version") == 1 and
         packet["spec"].get("start_ms") == start_ms and
         packet["spec"].get("end_exclusive_ms") == end_exclusive_ms and
         packet["spec"].get("as_of_ms") == cutoff_ms and
         _load_checkpoint(checkpoint, packet_sha, source_entry["bars"]) ==
         source_entry["bars"],
         "STAGE_SOURCE_OR_CHECKPOINT_DRIFT")
    stage_receipt = decode(receipt_file.read_bytes())
    stage_seal = stage_receipt.get("receipt_sha256")
    need(hexsha(stage_seal) and digest(
        {k: v for k, v in stage_receipt.items() if k != "receipt_sha256"
         }) == stage_seal and
         stage_receipt.get("packet_sha256") == packet_sha and
         stage_receipt.get("source_bytes_sha256") == source_sha and
         stage_receipt.get("manifest_integrity_sha256") == manifest_sha and
         stage_receipt.get("bar_count") == source_entry["bars"],
         "STAGE_RECEIPT_DRIFT")

    obj_file = _safe_existing_file(
        vault_objects / source_sha[:2] / source_sha[2:],
        max_bytes=8_000_000,
    )
    vault_raw = obj_file.read_bytes()
    need(hashlib.sha256(vault_raw).hexdigest() == source_sha and
         vault_raw == original_raw,
         "RAW_OBJECT_CONTENT_OR_STAGE_DRIFT")

    index = json.loads(index_file.read_bytes())
    manifest = [
        json.loads(line) for line in manifest_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = [x for x in manifest if x.get("content_sha256") == source_sha]
    need(type(index) is dict and len(matches) == 1 and
         type(matches[0]) is dict and
         matches[0].get("correction_generation") == 0 and
         matches[0].get("byte_length") == len(vault_raw) and
         matches[0].get("instrument") == "BTCUSDT" and
         matches[0].get("interval") == "15m" and
         index.get(matches[0]["logical_identity_key"]) == source_sha,
         "RAW_MANIFEST_INDEX_LINEAGE_DRIFT")

    return {
        "admission": admission,
        "packet": packet,
        "stage_receipt": stage_receipt,
        "vault_meta": matches[0],
        "stage_root": stage_root,
        "manifest_sha256": manifest_sha,
        "source_sha256": source_sha,
        "row_count": source_entry["bars"],
        "custody_receipt_sha256": custody_receipt_sha,
    }


def _reconstruct_warehouse_receipt(evidence, *, cutoff_ms):
    """Actual #253 receipt from the same observed admission + RAW metadata."""
    admission = evidence["admission"]
    packet = evidence["packet"]
    v = evidence["vault_meta"]
    version = packet["spec"]["version"]
    # RawVault admission receipt is independent of time-varying replay.
    # The exact original #253 warehouse receipt wasn't persisted by
    # generations (it stores the #226 *custody* receipt SHA instead).
    # Compute a SHA for the warehouse via its historical deterministic
    # admission fields only when all original fields can be reconstructed;
    # otherwise return a precise blocked result, never a guessed digest.
    return None


def verify_recovered_month_readonly(warehouse_root, vault_root, *,
                                   month, untrusted_source_entry):
    """Return independent source/queries + evidence, with NO disk writes.

    Caller-provided SHA must equal *recomputed* real source; a pinned
    recovery report file is separately checked by Integration and is not
    the original F2 report.
    """
    need(type(untrusted_source_entry) is dict and
         set(untrusted_source_entry) == MONTH_FIELDS and
         untrusted_source_entry.get("month") == month and
         untrusted_source_entry.get("state") ==
         "RAW_AND_DUAL_QUERY_READBACK",
         "RECOVERY_ENTRY_FIELDS_OR_STATE")
    for field in SHA_FIELDS:
        need(hexsha(untrusted_source_entry.get(field)),
             "RECOVERY_PARENT_SHA_INVALID")
    start, end = _month_bounds(month)
    need(type(untrusted_source_entry.get("bars")) is int and
         untrusted_source_entry["bars"] == (end-start)//WIDTH_MS,
         "RECOVERY_BAR_COUNT")
    source_sha = untrusted_source_entry["source_sha256"]
    dataset_id = f"BINANCE-SPOT-BTCUSDT-15M-{month}-F-v1"
    evidence = _warehouse_receipt_from_actual(
        warehouse_root, vault_root, dataset_id=dataset_id,
        source_sha=source_sha, source_entry=untrusted_source_entry,
        start_ms=start, end_exclusive_ms=end, cutoff_ms=end + 1000)
    # IMPORTANT: original warehouse receipt is not stored in SQLite.
    # Do not label its upstream caller-provided SHA independently verified.
    actual_warehouse_receipt = _reconstruct_warehouse_receipt(
        evidence, cutoff_ms=end+1000)
    need(actual_warehouse_receipt is not None,
         "ORIGINAL_WAREHOUSE_RECEIPT_NOT_RECONSTRUCTIBLE")
    return actual_warehouse_receipt
