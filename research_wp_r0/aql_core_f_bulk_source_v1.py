"""ATLAS F0/F1 — bounded batch manifest and PRIVATE source acquisition.

No network, disk writes or provenance promotion on import. Network acquisition
requires BOTH caller opt-in and an authorized private runner; no source bytes
should ever be uploaded to public CI. Uses existing Core #226 preflight for
monthly integrity and does not replace RAW Vault or warehouse admission.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen

SCHEMA = "aql.core.f.bulk-source-manifest.v1"
LEDGER_SCHEMA = "aql.core.f.bulk-source-coverage-ledger.v1"
MONTH_RE = re.compile(r"^2024-(0[1-9]|1[0-2])$")
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/"
MAX_ARCHIVE = 8_000_000
MAX_CHECKSUM = 512
PREVIOUSLY_PINNED = frozenset(("2024-02", "2024-08"))
STATES = ("ACCEPTED_PREFLIGHT", "REJECTED_QUARANTINED", "MISSING_SOURCE", "RETAINED_PREVIOUSLY_PINNED")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _digest(obj):
    return _sha(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode())


def _require(ok, why):
    if not ok:
        raise ValueError(why)


def target_months(first="2024-01", last="2024-12"):
    _require(type(first) is str and type(last) is str
             and MONTH_RE.fullmatch(first) and MONTH_RE.fullmatch(last)
             and first <= last, "INVALID_2024_MONTH_RANGE")
    return [f"2024-{month:02d}" for month in range(int(first[-2:]), int(last[-2:]) + 1)]


def build_manifest(*, first="2024-01", last="2024-12", max_workers=3,
                   private_storage_required=True):
    _require(type(max_workers) is int and 1 <= max_workers <= 4, "WORKER_BOUND")
    _require(private_storage_required is True, "PRIVATE_CUSTODY_REQUIRED")
    rows = []
    for month in target_months(first, last):
        y, m = int(month[:4]), int(month[-2:])
        begin = datetime(y, m, 1, tzinfo=timezone.utc)
        end = datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
        count = int((end - begin).total_seconds() // 900)
        name = f"BTCUSDT-15m-{month}.zip"
        rows.append({
            "month": month, "archive_name": name,
            "publisher_archive_url": BASE + name,
            "checksum_name": name + ".CHECKSUM",
            "publisher_checksum_url": BASE + name + ".CHECKSUM",
            "expected_native_15m_bars": count,
            "expected_member_name": name[:-4] + ".csv",
            "max_archive_bytes": MAX_ARCHIVE,
            "max_checksum_bytes": MAX_CHECKSUM,
            "original_archive_sha256": None,
            "independent_publisher_checksum_sha256": None,
            "inventory_status": "RETAINED_PREVIOUSLY_PINNED" if month in PREVIOUSLY_PINNED else "TARGET_NOT_ACQUIRED",
        })
    body = {
        "schema": SCHEMA, "source": "BINANCE_SPOT_BTCUSDT_NATIVE_15M",
        "interval_ms": 900000, "target_first": first, "target_last": last,
        "month_count": len(rows), "target_new_months": sum(
            x["inventory_status"] == "TARGET_NOT_ACQUIRED" for x in rows),
        "previously_pinned_months": [x["month"] for x in rows if x["inventory_status"] == "RETAINED_PREVIOUSLY_PINNED"],
        "expected_bars_total": sum(x["expected_native_15m_bars"] for x in rows),
        "max_worker_count": max_workers,
        "max_new_archive_bytes": sum(x["max_archive_bytes"] for x in rows if x["inventory_status"] == "TARGET_NOT_ACQUIRED"),
        "max_new_checksum_bytes": sum(x["max_checksum_bytes"] for x in rows if x["inventory_status"] == "TARGET_NOT_ACQUIRED"),
        "network": "EXPLICIT_PRIVATE_RUNNER_OPT_IN_ONLY",
        "licensing": "VERIFY_PUBLISHER_TERMS_BEFORE_DOWNLOAD",
        "storage": "PRIVATE_AUTHORIZED_CREATE_ONLY",
        "scientific_pit": "NOT_ATTESTED",
        "trading_authority": "NONE",
        "rows": rows,
    }
    return {**body, "manifest_sha256": _digest(body)}


def verify_manifest(manifest):
    if type(manifest) is not dict or type(manifest.get("manifest_sha256")) is not str:
        return False
    try:
        canonical = build_manifest(first=manifest["target_first"],
                                   last=manifest["target_last"],
                                   max_workers=manifest["max_worker_count"])
    except (KeyError, ValueError, TypeError):
        return False
    return manifest == canonical


def _fetch(url, limit):
    # Calls only exact publisher URLs constructed from a verified manifest.
    req = Request(url, headers={"User-Agent": "AQL-Core-F-Private-Custody/1.0"})
    with urlopen(req, timeout=30) as response:
        _require(response.status == 200, "PUBLISHER_HTTP_NOT_200")
        declared = response.headers.get("Content-Length")
        if declared:
            _require(int(declared) <= limit, "PUBLISHER_SIZE_LIMIT")
        data = response.read(limit + 1)
        _require(0 < len(data) <= limit, "PUBLISHER_BODY_LIMIT")
        return data


def acquire_private_batch(manifest, private_dir, *, allow_network=False,
                          permission_confirmed=False, terms_reviewed=False,
                          publisher_origin_confirmed=False):
    """Private create-only bounded acquisition. Failed files never become accepted.

    The separate publisher-origin confirmation is an operator attestation and
    MUST be externally verified; this module cannot independently certify a
    provider or its historical publication/available_at timestamps.
    """
    _require(verify_manifest(manifest), "MANIFEST_TAMPER")
    _require(allow_network is True and permission_confirmed is True
             and terms_reviewed is True and publisher_origin_confirmed is True,
             "PRIVATE_NETWORK_RIGHTS_PROVENANCE_OPT_IN_REQUIRED")
    root = Path(private_dir).resolve()
    _require(root.is_dir() and not root.is_symlink(), "PRIVATE_DIRECTORY_REQUIRED")
    _require((root.stat().st_mode & 0o077) == 0, "PRIVATE_DIRECTORY_PERMISSIONS_REQUIRED")
    results = {}
    def worker(row):
        month = row["month"]
        if row["inventory_status"] == "RETAINED_PREVIOUSLY_PINNED":
            return month, {"status": "RETAINED_PREVIOUSLY_PINNED", "reason": "NOT_REACQUIRED"}
        archive = root / row["archive_name"]
        checksum = root / row["checksum_name"]
        if archive.exists() or checksum.exists():
            return month, {"status": "REJECTED_QUARANTINED", "reason": "PREEXISTING_FILES_REQUIRE_MANUAL_RECONCILIATION"}
        try:
            checksum_bytes = _fetch(row["publisher_checksum_url"], MAX_CHECKSUM)
            archive_bytes = _fetch(row["publisher_archive_url"], MAX_ARCHIVE)
            # Reuse original Core #226 parser/12-col/UTC/grid verification without duplication.
            from research_wp_r0.aql_core_bounded_monthly_source_preflight_v1 import verify_native_month
            receipt = verify_native_month(
                month, archive_bytes, checksum_bytes, provenance="PRIVATE_PUBLISHER_FETCH_OPERATOR_ATTESTED")
            staged = []
            try:
                for dest, raw in ((archive, archive_bytes), (checksum, checksum_bytes)):
                    with dest.open("xb") as fd:
                        fd.write(raw)
                        fd.flush()
                        os.fsync(fd.fileno())
                    staged.append(dest)
            except Exception:
                for p in staged:
                    p.unlink(missing_ok=True)
                raise
            return month, {"status": "ACCEPTED_PREFLIGHT",
                           "archive_sha256": receipt["archive_sha256"],
                           "checksum_file_sha256": receipt["checksum_file_sha256"],
                           "preflight_receipt_sha256": receipt["preflight_receipt_sha256"],
                           "observed_bars": receipt["observed_bars"],
                           "raw_vault": "NOT_YET_ADMITTED",
                           "warehouse": "NOT_YET_ADMITTED",
                           "historical_pit": "NOT_ATTESTED"}
        except Exception as exc:
            # Don't leak private local file paths or secrets into public logs.
            return month, {"status": "REJECTED_QUARANTINED",
                           "reason": type(exc).__name__}
    with ThreadPoolExecutor(max_workers=manifest["max_worker_count"]) as pool:
        futures = [pool.submit(worker, row) for row in manifest["rows"]]
        for future in as_completed(futures):
            key, result = future.result()
            results[key] = result
    return build_coverage_ledger(manifest, results)


def build_coverage_ledger(manifest, outcomes=None):
    _require(verify_manifest(manifest), "MANIFEST_TAMPER")
    if outcomes is None:
        outcomes = {}
    _require(type(outcomes) is dict and
             set(outcomes).issubset({x["month"] for x in manifest["rows"]}), "INVALID_OUTCOME_KEYS")
    entries = []
    for row in manifest["rows"]:
        month = row["month"]
        outcome = outcomes.get(month)
        if row["inventory_status"] == "RETAINED_PREVIOUSLY_PINNED":
            status = "RETAINED_PREVIOUSLY_PINNED"
            _require(outcome is None or (type(outcome) is dict and outcome.get("status") == status), "RETAINED_CANNOT_BE_RELABELED")
        elif outcome is None:
            outcome = {"status": "MISSING_SOURCE", "reason": "SOURCE_ACCESS_REQUIRED"}
            status = "MISSING_SOURCE"
        else:
            _require(type(outcome) is dict and outcome.get("status") in STATES
                     and outcome["status"] != "RETAINED_PREVIOUSLY_PINNED", "INVALID_SOURCE_OUTCOME")
            status = outcome["status"]
            if status != "ACCEPTED_PREFLIGHT":
                _require(all(outcome.get(k) is None for k in ("archive_sha256", "checksum_file_sha256", "preflight_receipt_sha256")), "NONACCEPTED_SOURCE_HASHES_FORBIDDEN")
            if status == "ACCEPTED_PREFLIGHT":
                _require(all(type(outcome.get(k)) is str and re.fullmatch(r"[a-f0-9]{64}", outcome[k])
                             for k in ("archive_sha256", "checksum_file_sha256", "preflight_receipt_sha256"))
                         and outcome.get("observed_bars") == row["expected_native_15m_bars"]
                         and outcome.get("raw_vault") == "NOT_YET_ADMITTED"
                         and outcome.get("warehouse") == "NOT_YET_ADMITTED"
                         and outcome.get("historical_pit") == "NOT_ATTESTED",
                         "INVALID_PREFLIGHT_ONLY_OUTCOME")
        entries.append({
            "month": month, "status": status,
            "expected_native_15m_bars": row["expected_native_15m_bars"],
            "archive_sha256": outcome.get("archive_sha256") if outcome else None,
            "checksum_file_sha256": outcome.get("checksum_file_sha256") if outcome else None,
            "preflight_receipt_sha256": outcome.get("preflight_receipt_sha256") if outcome else None,
            "reason": outcome.get("reason") if outcome else None,
        })
    census = {state: sum(x["status"] == state for x in entries) for state in STATES}
    body = {
        "schema": LEDGER_SCHEMA, "manifest_sha256": manifest["manifest_sha256"],
        "target_count": len(entries), "census": census,
        "source_access": "REQUIRES_OWNER_AUTHORIZED_PRIVATE_RUNNER" if census["MISSING_SOURCE"] else "PRIVATE_PREFLIGHT_ONLY_NOT_RAW",
        "raw_admission": "NOT_CLAIMED",
        "warehouse_query": "NOT_CLAIMED",
        "core_245_native_query_sha256": None,
        "core_253_local_query_sha256": None,
        "secretary_historical_route": "NOT_AUTHORIZED",
        "historical_pit": "NOT_ATTESTED", "trading_authority": "NONE",
        "entries": entries,
    }
    return {**body, "coverage_ledger_sha256": _digest(body)}


def verify_coverage_ledger(manifest, ledger):
    if type(ledger) is not dict:
        return False
    outcomes = {}
    try:
        for row in ledger["entries"]:
            if row["status"] == "RETAINED_PREVIOUSLY_PINNED":
                continue
            result = {"status": row["status"], "reason": row.get("reason")}
            for key in ("archive_sha256", "checksum_file_sha256", "preflight_receipt_sha256"):
                if row.get(key) is not None:
                    result[key] = row[key]
            if row["status"] == "ACCEPTED_PREFLIGHT":
                result["observed_bars"] = next(x["expected_native_15m_bars"]
                                                  for x in manifest["rows"] if x["month"] == row["month"])
                result["raw_vault"] = "NOT_YET_ADMITTED"
                result["warehouse"] = "NOT_YET_ADMITTED"
                result["historical_pit"] = "NOT_ATTESTED"
            outcomes[row["month"]] = result
        return ledger == build_coverage_ledger(manifest, outcomes)
    except (ValueError, KeyError, TypeError, StopIteration):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", default="2024-01")
    parser.add_argument("--last", default="2024-12")
    parser.add_argument("--private-dir")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--permission-confirmed", action="store_true")
    parser.add_argument("--terms-reviewed", action="store_true")
    parser.add_argument("--publisher-origin-confirmed", action="store_true")
    parser.add_argument("--max-workers", type=int, default=3)
    args = parser.parse_args()
    manifest = build_manifest(first=args.first, last=args.last, max_workers=args.max_workers)
    if args.allow_network:
        _require(args.private_dir, "PRIVATE_DIR_REQUIRED")
        result = acquire_private_batch(
            manifest, args.private_dir, allow_network=True,
            permission_confirmed=args.permission_confirmed, terms_reviewed=args.terms_reviewed,
            publisher_origin_confirmed=args.publisher_origin_confirmed)
    else:
        result = build_coverage_ledger(manifest)
    print(json.dumps({"manifest": manifest, "coverage": result}, sort_keys=True))


if __name__ == "__main__":
    main()
