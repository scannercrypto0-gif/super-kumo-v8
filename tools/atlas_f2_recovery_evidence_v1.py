"""Versioned, fail-closed local F2 recovery evidence validation.

This is deliberately NOT a fallback to or recreation of the canonical F2
report. No signed F5 authority, source ACK or warehouse mutation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
    ADMITTED_MONTHS, _month_bounds,
)

SCHEMA = "aql.integration.f2-recovery-evidence.v1"
OWNER_REPORT_SCHEMA = "aql.owner-local.f2-recovery-evidence.v1"
EXPECTED_RECOVERY_FILE_SHA256 = (
    "0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"
)  # Report's internal recovery identity, NOT a hash of raw JSON bytes.
EXPECTED_RECOVERY_RAW_BYTES_SHA256 = (
    "52b47d7d93f5966fffe41ae16cb21486fb14a0753a2821dccc35f4f09e4903d2"
)  # Independently observed by owner PowerShell SHA256.
OWNER_REPORT_REQUIRED_FIELDS = frozenset((
    "schema", "recovery_sha256", "disposition", "verified_months",
))
HEX = frozenset("0123456789abcdef")
ENTRY_FIELDS = frozenset((
    "month", "state", "bars", "source_sha256",
    "core_245_native_price_query_sha256", "core_253_local_query_sha256",
    "warehouse_receipt_sha256", "dual_query_map_sha256",
))
ROOT_FIELDS = frozenset((
    "schema", "source_class", "historical_pit", "trading_authority",
    "owner_f2_report_sha256", "entries",
))


def require(ok, code):
    if not ok:
        raise ValueError("F2_RECOVERY_" + code)


def _hex(value):
    return type(value) is str and len(value) == 64 and all(c in HEX for c in value)


def _owner_report_matches_reconstructed_mapping(parent, row):
    """Producer verification is distinct from the reconstructed Core mapping.

    The genuine byte-pinned owner report says DUAL_READBACK_VERIFIED;
    Core's independently derived mapping says RAW_AND_DUAL_QUERY_READBACK.
    Neither state implies original F2 restoration, PIT, F5, or approval.
    """
    return (type(parent) is dict and type(row) is dict and
            parent.get("state") == "DUAL_READBACK_VERIFIED" and
            row.get("state") == "RAW_AND_DUAL_QUERY_READBACK" and
            parent.get("dataset_id") ==
                "BINANCE-SPOT-BTCUSDT-15M-" + row.get("month", "") + "-F-v1" and
            parent.get("month") == row.get("month") and
            parent.get("bars") == row.get("bars") and
            parent.get("source_sha256") == row.get("source_sha256") and
            parent.get("core245_native_query_sha256") ==
                row.get("core_245_native_price_query_sha256") and
            parent.get("core253_local_query_sha256") ==
                row.get("core_253_local_query_sha256") and
            _hex(parent.get("manifest_sha256")))


def load_recovery_evidence(path, mapping):
    """Pin actual original recovery bytes; mapping is untrusted and re-read."""
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and
            0 < p.stat().st_size <= 5_000_000, "ORIGINAL_FILE_REQUIRED")
    raw = p.read_bytes()
    require(sha256(raw).hexdigest() == EXPECTED_RECOVERY_RAW_BYTES_SHA256,
            "FILE_BYTES_DIGEST_MISMATCH")
    # Two distinct identities: genuine raw file bytes, and the producer's
    # internal recovery_sha256. The canonical *producer computation* is not
    # available in this repo; never pretend that hashing the file verifies it.
    def no_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "REPORT_DUPLICATE_JSON_KEY")
            value[key] = item
        return value

    def no_nonfinite(value):
        raise ValueError("F2_RECOVERY_REPORT_NONFINITE_NUMBER")

    try:
        report = json.loads(raw, object_pairs_hook=no_duplicate_keys,
                            parse_constant=no_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("F2_RECOVERY_OWNER_REPORT_INVALID_JSON") from exc
    require(type(report) is dict and
            OWNER_REPORT_REQUIRED_FIELDS.issubset(report) and
            report["schema"] == OWNER_REPORT_SCHEMA and
            report["recovery_sha256"] == EXPECTED_RECOVERY_FILE_SHA256 and
            report["disposition"] == "OWNER_LOCAL_DUAL_READBACK_PASS" and
            type(report["verified_months"]) is int and
            report["verified_months"] == len(ADMITTED_MONTHS) and
            type(report.get("verified_bars")) is int and
            report["verified_bars"] == 29376 and
            type(report.get("entries")) is list and
            len(report["entries"]) == len(ADMITTED_MONTHS) and
            all(type(row) is dict and set(row) == {
                "bars", "core245_native_query_sha256",
                "core253_local_query_sha256", "dataset_id",
                "manifest_sha256", "month", "source_sha256", "state",
            } for row in report["entries"]) and
            {row["month"] for row in report["entries"]} ==
            set(ADMITTED_MONTHS) and
            all(type(row["bars"]) is int and
                row["bars"] == (_month_bounds(row["month"])[1] -
                               _month_bounds(row["month"])[0]) // 900_000
                for row in report["entries"]),
            "OWNER_REPORT_IDENTITY_OR_CENSUS_DRIFT")
    # Report shape beyond the verified owner fields was not made available.
    # Do not fabricate canonical producer hashing or inferred month mappings.
    # A strictly checked untrusted mapping must still be independently
    # verified against original RAW, Warehouse, Core245 and Core253.
    value = mapping
    require(type(value) is dict and set(value) == ROOT_FIELDS and
            value["schema"] == SCHEMA and
            value["source_class"] == "OWNER_LOCAL_RECOVERY_NOT_ORIGINAL_F2" and
            value["historical_pit"] == "NOT_ATTESTED" and
            value["trading_authority"] == "NONE" and
            value["owner_f2_report_sha256"] is None,
            "RECOVERY_SCOPE_OR_F2_IMPERSONATION")
    rows = value["entries"]
    require(type(rows) is list and len(rows) == 10 and
            all(type(x) is dict and set(x) == ENTRY_FIELDS for x in rows) and
            {x["month"] for x in rows} == set(ADMITTED_MONTHS),
            "EXACT_ADMITTED_COHORT")
    require(all(x["state"] == "RAW_AND_DUAL_QUERY_READBACK" and
                type(x["bars"]) is int and
                x["bars"] == (_month_bounds(x["month"])[1] -
                               _month_bounds(x["month"])[0]) // 900_000 and
                all(_hex(x[k]) for k in ENTRY_FIELDS if k.endswith("sha256"))
                for x in rows) and
            sum(x["bars"] for x in rows) == 29376,
            "RECOVERY_CENSUS_OR_PARENT_SHAS")
    # Real report's identities are not sufficient to invent missing warehouse
    # and dual-map parents. Match every available source/native/local parent
    # without ever silently turning report rows into a trusted mapping.
    reported = {x["month"]:x for x in report["entries"]}
    for row in rows:
        parent = reported[row["month"]]
        require(_owner_report_matches_reconstructed_mapping(parent, row),
                "OWNER_REPORT_VS_UNTRUSTED_MAPPING_DRIFT")
    return {x["month"]: x for x in rows}


def read_recovered_diagnostic(warehouse_root, vault_root, recovery_path, mapping):
    """Delegate all source/warehouse/dual-query verification to Core owner.

    In particular, never construct RawVault or OfflineBridgeStager here:
    their constructors may create directories or modify private custody.
    """
    from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
        read_recovery_diagnostic,
    )
    # Independently verify actual opaque file bytes and strict untrusted
    # mapping shape first, then Core recomputes each month from original bytes.
    load_recovery_evidence(recovery_path, mapping)
    results = read_recovery_diagnostic(
        warehouse_root, vault_root, recovery_path, mapping)
    require(type(results) is dict and set(results) == set(ADMITTED_MONTHS),
            "CORE_SOURCE_COHORT_MISMATCH")
    for month, result in results.items():
        receipt = result["receipt"]
        require(receipt["schema"] ==
                "aql.core.f2-recovery-readonly-source.v1"
                and receipt["month"] == month
                and receipt["original_f2_report_sha256"] is None
                and receipt["recovery_file_sha256"] ==
                    EXPECTED_RECOVERY_FILE_SHA256
                and receipt["bar_count"] == mapping["entries"][
                    [x["month"] for x in mapping["entries"]].index(month)]["bars"]
                and receipt["source_ack_sha256"] is None
                and receipt["strategy_approval_sha256"] is None
                and receipt["factory_consumer_ack_sha256"] is None
                and receipt["trading_authority"] == "NONE",
                "CORE_RECOVERY_RECEIPT_BOUNDARY_DRIFT")
    return results


def main():
    """Standalone source gate only; NOT the full Scanner/Factory diagnostic."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Owner-private F2 recovery source verification only")
    parser.add_argument("--recovery-file", required=True)
    parser.add_argument("--mapping-file", required=True)
    parser.add_argument("--warehouse-root", required=True)
    parser.add_argument("--vault-root", required=True)
    parser.add_argument("--owner-private-authorized", action="store_true")
    a = parser.parse_args()
    try:
        require(a.owner_private_authorized, "OWNER_PRIVATE_AUTHORIZATION_REQUIRED")
        p = Path(a.mapping_file)
        require(p.is_file() and not p.is_symlink(), "MAPPING_REQUIRED")
        mapping = json.loads(p.read_text(encoding="utf-8"))
        result = read_recovered_diagnostic(
            a.warehouse_root, a.vault_root, a.recovery_file, mapping)
        counts = {m: result[m]["receipt"]["bar_count"]
                  for m in ADMITTED_MONTHS}
        require(len(counts) == 10 and sum(counts.values()) == 29376,
                "RECOMPUTED_BAR_CENSUS")
        packet = {
            "schema": "aql.integration.f2-recovery-source-gate.v1",
            "status": "SOURCE_READBACK_PASS_DIAGNOSTIC_NOT_RUN",
            "recovery_file_sha256": EXPECTED_RECOVERY_FILE_SHA256,
            "original_f2_report_sha256": None,
            "source_rights": "OWNER_LOCAL_NOT_INDEPENDENT",
            "historical_pit": "NOT_ATTESTED",
            "trading_authority": "NONE",
            "months": counts,
            "source_query_parents": {
                m: {
                    "raw": result[m]["receipt"]["source_zip_sha256"],
                    "native245": result[m]["receipt"]["core245_native_query_sha256"],
                    "local253": result[m]["receipt"]["core253_local_query_sha256"],
                    "warehouse_receipt": result[m]["receipt"]["warehouse_receipt_sha256"],
                    "manifest": result[m]["receipt"]["manifest_integrity_sha256"],
                } for m in ADMITTED_MONTHS
            },
            "scanner_factory": "PRIVATE_WAIT",
            "signed_f5": "BLOCKED_EXTERNAL_INPUT",
        }
        print(json.dumps({**packet, "sha256": sha256(
            json.dumps(packet, sort_keys=True, separators=(",",":")).encode()
        ).hexdigest()}, sort_keys=True))
    except Exception as exc:
        code = str(exc)
        if not code.startswith("F2_RECOVERY_"):
            code = "F2_RECOVERY_PRIVATE_INPUT_OR_READBACK_FAILED"
        print("PRIVATE_WAIT " + code, file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
