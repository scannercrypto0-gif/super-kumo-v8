"""Read-only Core→Integration RESEARCH_E2E_DIAGNOSTIC source/query seam.

This diagnostic NEVER admits data, updates a warehouse or RawVault, issues a
Source ACK/StrategyApproval, or claims original historical PIT evidence.
Only owner-authorized private runtime may call the public original-F2 entry.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    OfflineBridgeStager, digest as bridge_digest,
)
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_core_f_private_f2_v1 import (
    digest, private_directory_gate,
)
from research_wp_r0.aql_core_f5_secretary_authority_v1 import (
    EXPECTED_F2_REPORT, EXPECTED_MANIFEST, EXPECTED_LEDGER, EXPECTED_AUTH,
)
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.historical_library import HistoricalLibrary
from tools.raw_vault_offline.vault import RawVault

SCHEMA = "aql.core.f.research-e2e-diagnostic-readback.v1"
ADMITTED_MONTHS = (
    "2024-01", "2024-03", "2024-04", "2024-05", "2024-06",
    "2024-07", "2024-09", "2024-10", "2024-11", "2024-12",
)
WIDTH_MS = 900_000


def _require(ok, code):
    if not ok:
        raise ValueError(code)


def _month_bounds(month):
    _require(type(month) is str and month in ADMITTED_MONTHS,
             "DIAGNOSTIC_MONTH_NOT_ADMITTED")
    year, mo = map(int, month.split("-"))
    start = int(datetime(year, mo, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = start + calendar.monthrange(year, mo)[1] * 86_400_000
    return start, end


def _validate_original_owner_report(report):
    """Owner report is integrity pinned, *not* independent source authority."""
    _require(type(report) is dict and
             report.get("schema") ==
             "aql.core.f.private-raw-warehouse-dual-query-report.v1"
             and report.get("report_sha256") == EXPECTED_F2_REPORT
             and digest({k: v for k, v in report.items()
                         if k != "report_sha256"}) == EXPECTED_F2_REPORT
             and report.get("manifest_sha256") == EXPECTED_MANIFEST
             and report.get("f1_coverage_ledger_sha256") == EXPECTED_LEDGER
             and report.get("authorization_document_sha256") == EXPECTED_AUTH
             and report.get("f2_new_admitted_count") == 10
             and report.get("f2_previous_retained_inventory_only_count") == 2
             and report.get("historical_pit") == "NOT_ATTESTED"
             and report.get("trading_authority") == "NONE"
             and report.get("secretary_historical_strategy_route") ==
             "NOT_AUTHORIZED"
             and report.get("factory_consumer_ack") is None,
             "DIAGNOSTIC_OWNER_F2_PIN_OR_STATE_DRIFT")
    entries = report.get("entries")
    _require(type(entries) is list and len(entries) == 10 and
             all(type(x) is dict for x in entries) and
             {x.get("month") for x in entries} == set(ADMITTED_MONTHS) and
             all(type(x.get("bars")) is int for x in entries) and
             sum(x["bars"] for x in entries) == 29376 and
             all(x.get("state") == "RAW_AND_DUAL_QUERY_READBACK"
                 and x.get("historical_pit") == "NOT_ATTESTED"
                 and x.get("bars") ==
                 calendar.monthrange(2024, int(x["month"][-2:]))[1] * 96
                 for x in entries),
             "DIAGNOSTIC_OWNER_F2_COHORT_DRIFT")
    return {entry["month"]: entry for entry in entries}


def _one_read_only(warehouse_root, vault_root, *, month, source_entry,
                   start_ms, end_exclusive_ms, cutoff_ms):
    """Internal source-backed query primitive. Exposes no credential route."""
    _require(type(source_entry) is dict and
             source_entry.get("month") == month and
             source_entry.get("state") == "RAW_AND_DUAL_QUERY_READBACK" and
             type(start_ms) is int and type(end_exclusive_ms) is int and
             type(cutoff_ms) is int and start_ms < end_exclusive_ms and
             cutoff_ms >= end_exclusive_ms and
             (end_exclusive_ms-start_ms) % WIDTH_MS == 0 and
             0 < (end_exclusive_ms-start_ms)//WIDTH_MS <= 4096,
             "DIAGNOSTIC_SOURCE_RANGE_OR_CUTOFF")
    source_sha = source_entry.get("source_sha256")
    expected_native = source_entry.get("core_245_native_price_query_sha256")
    expected_local = source_entry.get("core_253_local_query_sha256")
    expected_warehouse = source_entry.get("warehouse_receipt_sha256")
    expected_map = source_entry.get("dual_query_map_sha256")
    for sha in (source_sha, expected_native, expected_local,
                expected_warehouse, expected_map):
        _require(type(sha) is str and len(sha) == 64 and
                 all(ch in "0123456789abcdef" for ch in sha),
                 "DIAGNOSTIC_SOURCE_PARENT_SHA_REQUIRED")
    dataset_id = "BINANCE-SPOT-BTCUSDT-15M-" + month + "-F-v1"
    warehouse_root = private_directory_gate(warehouse_root)
    vault_root = private_directory_gate(vault_root)
    _require((warehouse_root / "warehouse.sqlite").is_file() and
             not (warehouse_root / "warehouse.sqlite").is_symlink() and
             (warehouse_root / "stage").is_dir() and
             not (warehouse_root / "stage").is_symlink(),
             "DIAGNOSTIC_EXISTING_WAREHOUSE_ONLY")
    _require(all((vault_root / name).is_dir() and
                 not (vault_root / name).is_symlink()
                 for name in ("objects", ".staging")) and
             all((vault_root / name).is_file() and
                 not (vault_root / name).is_symlink()
                 for name in ("manifest.jsonl", "index.json")),
             "DIAGNOSTIC_EXISTING_VAULT_ONLY")
    object_parent = vault_root / "objects" / source_sha[:2]
    object_file = object_parent / source_sha[2:]
    _require(object_parent.is_dir() and not object_parent.is_symlink() and
             object_file.is_file() and not object_file.is_symlink(),
             "DIAGNOSTIC_RAW_OBJECT_LINK_OR_MISSING")
    # Open preexisting SQLite database RO, never invoke _connect/admit.
    con = sqlite3.connect(
        (warehouse_root / "warehouse.sqlite").as_uri() + "?mode=ro",
        uri=True)
    try:
        record = con.execute(
            "SELECT source_sha,manifest_sha,packet_sha FROM generations "
            "WHERE dataset_id=? AND generation=1", (dataset_id,)
        ).fetchone()
    finally:
        con.close()
    _require(record is not None and record[0] == source_sha,
             "DIAGNOSTIC_WAREHOUSE_SOURCE_PIN_MISMATCH")
    manifest_sha, packet_sha = record[1], record[2]
    _require(type(manifest_sha) is str and len(manifest_sha) == 64 and
             type(packet_sha) is str and len(packet_sha) == 64,
             "DIAGNOSTIC_WAREHOUSE_MANIFEST_PIN_MISSING")
    # No read/commit on an uncommitted stage. The existing commit() replays
    # into an in-memory HistoricalLibrary and reads the existing receipt.json;
    # it only writes a receipt when absent, precluded explicitly here.
    marker = warehouse_root / "stage" / packet_sha / "receipt.json"
    _require(marker.is_file() and not marker.is_symlink(),
             "DIAGNOSTIC_COMMITTED_STAGE_RECEIPT_REQUIRED")
    stager = OfflineBridgeStager(warehouse_root / "stage")
    library = HistoricalLibrary()
    loaded = stager.commit(packet_sha, library)
    _require(loaded.get("packet_sha256") == packet_sha and
             loaded.get("source_bytes_sha256") == source_sha and
             loaded.get("manifest_integrity_sha256") == manifest_sha,
             "DIAGNOSTIC_STAGE_SOURCE_DRIFT")
    vault = RawVault(vault_root)  # all normal constructor dirs required above
    raw = vault.read(source_sha)
    _require(len(raw) > 0 and any(
        e.get("content_sha256") == source_sha
        for e in vault.manifest_entries()),
        "DIAGNOSTIC_RAW_VAULT_SOURCE_NOT_ADMITTED")
    local = query_local(
        warehouse_root, dataset_id, 1, start_ms, end_exclusive_ms,
        cutoff_ms, required_source_sha256=source_sha,
        require_complete=True)
    req = {
        "schema": REQUEST_SCHEMA, "dataset_id": dataset_id, "version": 1,
        "start_ms": start_ms, "end_exclusive_ms": end_exclusive_ms,
        "decision_cutoff_ms": cutoff_ms, "require_complete": False,
        "confirmed_only": False,
    }
    native = query_price_custody(
        library, req, expected_source_sha256=source_sha,
        expected_manifest_integrity_sha256=manifest_sha)
    _require(native.get("status") == "OK" and
             local.get("coverage") == native.get("coverage") == "COMPLETE" and
             local.get("query_sha256") == expected_local and
             native.get("price_query_sha256") == expected_native and
             local.get("source_bytes_sha256") ==
             native.get("source_bytes_sha256") == source_sha and
             local.get("manifest_integrity_sha256") ==
             native.get("manifest_integrity_sha256") == manifest_sha and
             local.get("decision_cutoff_ms") ==
             native.get("decision_cutoff_ms") == cutoff_ms and
             local.get("available_bar_count") ==
             native.get("available_bar_count") ==
             source_entry.get("bars") ==
             (end_exclusive_ms - start_ms) // WIDTH_MS and
             local.get("missing_bar_opens") == native.get("missing_bar_opens") == [],
             "DIAGNOSTIC_DUAL_QUERY_OR_CENSUS_DRIFT")
    indexed = local["bars"]
    original = native["bars"]
    _require(len(indexed) == len(original) and
             all(a["bar_open_ms"] == b["bar_open_ms"] and
                 a["bar_close_ms"] == b["bar_close_ms"] and
                 a["bar_checksum"] == b["checksum"] and
                 a["observation_lower_bound_ms"] ==
                 b["observation_lower_bound_ms"] and
                 a["bar_close_ms"] < cutoff_ms and
                 a["historical_known_at_ms"] is None and
                 b["historical_known_at_ms"] is None
                 for a, b in zip(indexed, original)),
             "DIAGNOSTIC_BAR_IDENTITY_OR_CLOSED_CUTOFF")
    _require(local.get("historical_pit") == "NOT_ATTESTED" and
             native.get("scientific_pit") == "NOT_ATTESTED" and
             local.get("source_availability") ==
             native.get("source_availability") == "RETROSPECTIVE_NON_PIT",
             "DIAGNOSTIC_FALSE_PIT_PROMOTION")
    proof = {
        "schema": SCHEMA,
        "dataset_id": dataset_id, "month": month, "version": 1,
        "source_zip_sha256": source_sha,
        "manifest_integrity_sha256": manifest_sha,
        "warehouse_receipt_sha256": expected_warehouse,
        "core245_native_query_sha256": expected_native,
        "core253_local_query_sha256": expected_local,
        "core253_dual_map_parent_sha256": expected_map,
        "start_ms": start_ms, "end_exclusive_ms": end_exclusive_ms,
        "decision_cutoff_ms": cutoff_ms,
        "readback_bar_count": len(indexed),
        "readback_evidence": "OWNER_SOURCE_READONLY_REPLAY_NOT_SIGNED_F5",
        "historical_pit": "NOT_ATTESTED",
        "secretary_state": "NOT_ENQUEUED",
        "source_ack_sha256": None,
        "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "trading_authority": "NONE",
    }
    # Bars are available IN MEMORY to the separately authorized diagnostic
    # harness. Only receipt (without prices) is intended for sanitized logs.
    return {"receipt": {**proof, "receipt_sha256": bridge_digest(proof)},
            "native_bars": original, "local_bars": indexed}


def read_original_diagnostic(warehouse_root, vault_root, original_f2_report,
                             *, month):
    """The public owner-F2-pinned read-only diagnostic entrypoint.

    No fallback to a synthesized report or to Feb/Aug inventory-only bytes.
    Independent legal/source authority and signed F5 remain separate.
    """
    entries = _validate_original_owner_report(original_f2_report)
    start, end = _month_bounds(month)
    return _one_read_only(
        warehouse_root, vault_root, month=month,
        source_entry=entries[month], start_ms=start, end_exclusive_ms=end,
        cutoff_ms=end + 1000)
