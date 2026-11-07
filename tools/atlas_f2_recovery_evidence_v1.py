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
EXPECTED_RECOVERY_FILE_SHA256 = (
    "0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"
)
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


def load_recovery_evidence(path, mapping):
    """Pin actual original recovery bytes; mapping is untrusted and re-read."""
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and
            0 < p.stat().st_size <= 5_000_000, "ORIGINAL_FILE_REQUIRED")
    raw = p.read_bytes()
    require(sha256(raw).hexdigest() == EXPECTED_RECOVERY_FILE_SHA256,
            "FILE_BYTES_DIGEST_MISMATCH")
    # Recovery report is an existing owner-local artifact of unknown
    # serialization. Its exact bytes are pinned independently. The separately
    # provided versioned mapping is NEVER treated as authority: each parent
    # is checked against a new read of original vault/warehouse/query bytes.
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
