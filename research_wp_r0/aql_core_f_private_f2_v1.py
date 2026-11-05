"""Core F2 owner-private immutable admission from an existing F1 artifact.

One local command, no new downloader/parser/vault. F1 local ZIP/CHECKSUM bytes
and owner ledger are re-read; missing/rejected months never enter RAW. Fresh
publisher CHECKSUM is fetched over authenticated TLS on explicit opt-in, not
treated as historical issuer PIT proof. No Scanner strategy/policy ACK is minted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from research_wp_r0.aql_core_f_bulk_source_v1 import (
    _fetch, MAX_CHECKSUM, build_coverage_ledger, verify_coverage_ledger,
    verify_manifest, PREVIOUSLY_PINNED,
)
from research_wp_r0.aql_core_f_ntfs_acl_v1 import require_private_windows_directory

SHA = re.compile(r"^[0-9a-f]{64}$")
SCHEMA = "aql.core.f.private-raw-warehouse-dual-query-report.v1"


def need(ok, code):
    if not ok:
        raise ValueError(code)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canon(value)).hexdigest()


def file_read_bounded(path, bound):
    # Caller must have checked the private directory and its reparse points.
    path = Path(path)
    need(path.is_file() and not path.is_symlink(), "F2_FILE_UNAVAILABLE_OR_LINK")
    need(0 < path.stat().st_size <= bound, "F2_FILE_SIZE_LIMIT")
    data = path.read_bytes()
    need(0 < len(data) <= bound, "F2_FILE_CHANGED_OR_EMPTY")
    return data


def verify_f1_container(data, expected_manifest_sha, expected_ledger_sha):
    need(type(data) is dict and set(data) == {"manifest", "coverage"},
         "F2_F1_BUNDLE_FIELDS")
    manifest, ledger = data["manifest"], data["coverage"]
    need(type(expected_manifest_sha) is str and SHA.fullmatch(expected_manifest_sha)
         and type(expected_ledger_sha) is str and SHA.fullmatch(expected_ledger_sha),
         "F2_OUT_OF_BAND_SHA_REQUIRED")
    need(verify_manifest(manifest)
         and manifest["manifest_sha256"] == expected_manifest_sha,
         "F2_MANIFEST_SHA_OR_SCOPE_DRIFT")
    need(verify_coverage_ledger(manifest, ledger)
         and ledger["coverage_ledger_sha256"] == expected_ledger_sha,
         "F2_F1_LEDGER_SHA_DRIFT")
    return manifest, ledger


def private_directory_gate(root):
    import os
    root = Path(root).absolute()
    need(root.is_dir() and not root.is_symlink(), "F2_PRIVATE_DIRECTORY_REQUIRED")
    if os.name == "nt":
        require_private_windows_directory(root)
    else:
        need(root.stat().st_mode & 0o077 == 0, "F2_PRIVATE_DIRECTORY_PERMISSIONS_REQUIRED")
    return root


def check_local_batch(manifest, ledger, local_dir, *,
                      allow_network=False, publisher_recheck=False):
    """Byte-reconcile and optionally re-fetch publisher CHECKSUM in owner runner.

    The re-fetch validates current TLS endpoint consistency, not a historical
    signature. The returned byte candidates remain private and are not saved
    in a GitHub CI artifact. Only exact F1 accepted months are checked.
    """
    need(verify_manifest(manifest) and verify_coverage_ledger(manifest, ledger),
         "F2_F1_RECEIPT_INVALID")
    root = private_directory_gate(local_dir)
    need(allow_network is True and publisher_recheck is True,
         "F2_INDEPENDENT_PUBLISHER_RECHECK_REQUIRED")
    from research_wp_r0.aql_core_bounded_monthly_source_preflight_v1 import verify_native_month
    entries = {r["month"]: r for r in ledger["entries"]}
    rows, candidates = [], {}
    for m in manifest["rows"]:
        month = m["month"]
        entry = entries[month]
        if month in PREVIOUSLY_PINNED:
            rows.append({"month": month, "state": "RETAINED_INVENTORY_ONLY",
                         "reason": "FEB_AUG_BYTES_NOT_REVERIFIED"})
            continue
        if entry["status"] != "ACCEPTED_PREFLIGHT":
            rows.append({"month": month, "state": "MISSING_OR_QUARANTINED",
                         "reason": entry["status"]})
            continue
        try:
            raw = file_read_bounded(root / m["archive_name"], m["max_archive_bytes"])
            checksum = file_read_bounded(root / m["checksum_name"], m["max_checksum_bytes"])
            actual_zip_sha = hashlib.sha256(raw).hexdigest()
            actual_cs_sha = hashlib.sha256(checksum).hexdigest()
            need(actual_zip_sha == entry["archive_sha256"]
                 and actual_cs_sha == entry["checksum_file_sha256"],
                 "F2_LOCAL_SHA_NOT_F1_LEDGER")
            remote_checksum = _fetch(m["publisher_checksum_url"], MAX_CHECKSUM)
            need(remote_checksum == checksum, "F2_INDEPENDENT_PUBLISHER_CHECKSUM_DRIFT")
            receipt = verify_native_month(
                month, raw, checksum, provenance="PRIVATE_PUBLISHER_FETCH_OPERATOR_ATTESTED")
            need(receipt["preflight_receipt_sha256"]
                 == entry["preflight_receipt_sha256"], "F2_PREFLIGHT_RECEIPT_DRIFT")
            need(receipt["observed_bars"] == m["expected_native_15m_bars"]
                 and receipt["coverage"] == "COMPLETE",
                 "F2_NATIVE_MONTH_CENSUS")
            candidates[month] = (raw, checksum, receipt)
            rows.append({"month": month, "state": "REVERIFIED_PRIVATE_BYTES",
                         "archive_sha256": actual_zip_sha,
                         "checksum_file_sha256": actual_cs_sha,
                         "csv_member_sha256": receipt["csv_member_sha256"],
                         "observed_bars": receipt["observed_bars"]})
        except Exception as exc:
            rows.append({"month": month, "state": "REJECTED_QUARANTINED",
                         "reason": type(exc).__name__})
    return rows, candidates


def authorize_local_admission(authorization, expected_authorization_sha, manifest):
    """Verify separately pinned custodian authorization, not issuer signature."""
    need(type(authorization) is dict and set(authorization) == {
        "schema", "owner_permission", "rights_evidence_reference",
        "issuer_provenance_reference", "publisher_checksum_issued_via",
        "authorized_months", "source_class", "historical_pit",
        "trading_authority",
    }, "F2_EXTERNAL_AUTHORIZATION_FIELDS")
    need(type(expected_authorization_sha) is str
         and SHA.fullmatch(expected_authorization_sha)
         and digest(authorization) == expected_authorization_sha,
         "F2_EXTERNAL_AUTHORIZATION_PIN_MISMATCH")
    need(authorization["schema"] == "aql.core.f.private-custody-authorization.v1"
         and authorization["owner_permission"] is True
         and authorization["source_class"] == "ORIGINAL_PUBLISHER_RETROSPECTIVE_NON_PIT"
         and authorization["historical_pit"] == "NOT_ATTESTED"
         and authorization["trading_authority"] == "NONE"
         and authorization["publisher_checksum_issued_via"] == "SEPARATE_PUBLISHER_HTTPS"
         and type(authorization["rights_evidence_reference"]) is str
         and 8 <= len(authorization["rights_evidence_reference"]) <= 160
         and type(authorization["issuer_provenance_reference"]) is str
         and 8 <= len(authorization["issuer_provenance_reference"]) <= 160
         and type(authorization["authorized_months"]) is list
         and len(authorization["authorized_months"]) == len(set(authorization["authorized_months"]))
         and set(authorization["authorized_months"]).issubset(
             {x["month"] for x in manifest["rows"]} - PREVIOUSLY_PINNED),
         "F2_INDEPENDENT_RIGHTS_OR_ISSUER_WITNESS_MISSING")
    return True


def execute_local_f2(owner_f1, private_dir, warehouse_root, vault_root, *,
                     expected_manifest_sha, expected_ledger_sha,
                     authorization, expected_authorization_sha,
                     allow_network=False, publisher_recheck=False,
                     allow_raw_admission=False):
    manifest, ledger = verify_f1_container(
        owner_f1, expected_manifest_sha, expected_ledger_sha)
    authorize_local_admission(authorization, expected_authorization_sha, manifest)
    need(allow_raw_admission is True, "F2_EXPLICIT_RAW_PERMISSION_REQUIRED")
    need(set(authorization["authorized_months"]) ==
         {x["month"] for x in ledger["entries"]
          if x["status"] == "ACCEPTED_PREFLIGHT"}, "F2_APPROVED_COHORT_MISMATCH")
    rows, candidates = check_local_batch(
        manifest, ledger, private_dir, allow_network=allow_network,
        publisher_recheck=publisher_recheck)
    warehouse_root = private_directory_gate(warehouse_root)
    vault_root = private_directory_gate(vault_root)
    # Avoid claiming whole cohort success after one original/source failure.
    if len(candidates) != manifest["target_new_months"]:
        raise ValueError("F2_SOURCE_BATCH_INCOMPLETE_STOP_BEFORE_RAW")
    from tools.raw_vault_offline.vault import RawVault
    from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
    from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
    from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
    from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
    from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
    from research_wp_r0.historical_library import HistoricalLibrary

    vault = RawVault(vault_root)
    accepted = []
    for row in manifest["rows"]:
        month = row["month"]
        if month in PREVIOUSLY_PINNED:
            continue
        raw, checksum, preflight = candidates[month]
        observed = next(x for x in rows if x["month"] == month)
        start, end = preflight["start_ms"], preflight["end_exclusive_ms"]
        cutoff = end + 1000  # retrospective completed bars; NOT issuer known-at
        dataset_id = "BINANCE-SPOT-BTCUSDT-15M-" + month + "-F-v1"
        pin = {
            "schema": "aql.core.external-original-byte-pin.v1",
            "source_kind": "BINANCE_KLINES_ZIP",
            "original_object_id": dataset_id,
            "original_sha256": preflight["archive_sha256"],
            "provenance_reference": "OWNER_PRIVATE_PUBLISHER_RECHECK",
            "captured_at_ms": None, "claimed_available_at_ms": None,
            "expected_inventory_sha256": None, "vault_object_metadata": None,
            "universe_manifest_sha256": None, "universe_member_count": None,
            "test_only": False,
            "archive_name": preflight["archive_name"],
            "csv_member_name": row["expected_member_name"],
            "csv_member_sha256": preflight["csv_member_sha256"],
            "checksum_file_sha256": preflight["checksum_file_sha256"],
        }
        spec = {
            "dataset_id": dataset_id, "version": 1,
            "symbol": "BTCUSDT", "interval": "15m", "exchange": "BINANCE",
            "market": "SPOT", "source_label": "OWNER_PRIVATE_RETROSPECTIVE",
            "start_ms": start, "end_exclusive_ms": end, "as_of_ms": cutoff,
            "parent_source_sha256": None, "correction_reason": None,
            "test_only": False,
        }
        receipt = admit_local_original(
            warehouse_root, raw, checksum, pin, spec,
            decision_cutoff_ms=cutoff, vault=vault)
        need(receipt["status"] == "OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
             and receipt["vault"]["vault"] == "EXISTING_PINNED_RAW_VAULT"
             and receipt["coverage"] == "COMPLETE"
             and receipt["bar_count"] == preflight["expected_bars"],
             "F2_RAW_WAREHOUSE_INCOMPLETE")
        local = query_local(warehouse_root, dataset_id, 1, start, end, cutoff,
                            required_source_sha256=preflight["archive_sha256"],
                            require_complete=True)
        library = HistoricalLibrary()
        OfflineBridgeStager(warehouse_root / "stage").replay_committed(library)
        request = {
            "schema": REQUEST_SCHEMA, "dataset_id": dataset_id, "version": 1,
            "start_ms": start, "end_exclusive_ms": end,
            "decision_cutoff_ms": cutoff, "require_complete": False,
            "confirmed_only": False,
        }
        native = query_price_custody(
            library, request,
            expected_source_sha256=preflight["archive_sha256"],
            expected_manifest_integrity_sha256=receipt["manifest_integrity_sha256"])
        dual = bind_dual_query_identities(native, local, receipt)
        need(local == query_local(
            warehouse_root, dataset_id, 1, start, end, cutoff,
            required_source_sha256=preflight["archive_sha256"], require_complete=True),
            "F2_RESTART_QUERY_DRIFT")
        need(vault.read(preflight["archive_sha256"]) == raw,
             "F2_RAW_VAULT_READBACK_DRIFT")
        accepted.append({
            "month": month, "state": "RAW_AND_DUAL_QUERY_READBACK",
            "source_sha256": preflight["archive_sha256"],
            "checksum_file_sha256": preflight["checksum_file_sha256"],
            "csv_member_sha256": preflight["csv_member_sha256"],
            "warehouse_receipt_sha256": receipt["receipt_sha256"],
            "core_245_native_price_query_sha256": native["price_query_sha256"],
            "core_253_local_query_sha256": local["query_sha256"],
            "dual_query_map_sha256": dual.get("identity_map_sha256") or dual.get("map_sha256"),
            "bars": local["available_bar_count"],
            "historical_pit": "NOT_ATTESTED",
        })
    report = {
        "schema": SCHEMA, "manifest_sha256": manifest["manifest_sha256"],
        "f1_coverage_ledger_sha256": ledger["coverage_ledger_sha256"],
        "authorization_document_sha256": expected_authorization_sha,
        "provenance": "CURRENT_PUBLISHER_TLS_CHECKSUM_OPERATOR_ATTESTED_NOT_HISTORICAL_ISSUER_SIGNATURE",
        "f2_new_admitted_count": len(accepted),
        "f2_previous_retained_inventory_only_count": len(PREVIOUSLY_PINNED),
        "entries": accepted,
        "strategy_policy_approval": "NOT_ATTESTED_BY_CORE",
        "secretary_historical_strategy_route": "NOT_AUTHORIZED",
        "factory_consumer_ack": None,
        "historical_pit": "NOT_ATTESTED", "trading_authority": "NONE",
    }
    return {**report, "report_sha256": digest(report)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--f1-output", required=True)
    p.add_argument("--private-dir", required=True)
    p.add_argument("--warehouse-root", required=True)
    p.add_argument("--vault-root", required=True)
    p.add_argument("--authorization-json", required=True)
    p.add_argument("--authorization-sha256", required=True)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--expected-ledger-sha256", required=True)
    p.add_argument("--allow-network", action="store_true")
    p.add_argument("--recheck-publisher-checksums", action="store_true")
    p.add_argument("--allow-raw-admission", action="store_true")
    args = p.parse_args()
    source = private_directory_gate(Path(args.f1_output).absolute().parent)
    witness = private_directory_gate(Path(args.authorization_json).absolute().parent)
    f1 = json.loads(file_read_bounded(source / Path(args.f1_output).name, 100_000))
    authorization = json.loads(file_read_bounded(
        witness / Path(args.authorization_json).name, 50_000))
    result = execute_local_f2(
        f1, args.private_dir, args.warehouse_root, args.vault_root,
        expected_manifest_sha=args.expected_manifest_sha256,
        expected_ledger_sha=args.expected_ledger_sha256,
        authorization=authorization,
        expected_authorization_sha=args.authorization_sha256,
        allow_network=args.allow_network,
        publisher_recheck=args.recheck_publisher_checksums,
        allow_raw_admission=args.allow_raw_admission,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
