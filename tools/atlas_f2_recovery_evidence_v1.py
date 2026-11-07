"""Versioned, fail-closed local F2 recovery evidence validation.

This is deliberately NOT a fallback to or recreation of the canonical F2
report. No signed F5 authority, source ACK or warehouse mutation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
    ADMITTED_MONTHS, _month_bounds, _one_read_only,
)
from tools.raw_vault_offline.vault import RawVault

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


def load_recovery_evidence(path):
    """Require the actual pinned file bytes; do not trust an embedded digest."""
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and
            0 < p.stat().st_size <= 5_000_000, "ORIGINAL_FILE_REQUIRED")
    raw = p.read_bytes()
    require(sha256(raw).hexdigest() == EXPECTED_RECOVERY_FILE_SHA256,
            "FILE_BYTES_DIGEST_MISMATCH")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("F2_RECOVERY_INVALID_JSON") from exc
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


def read_recovered_diagnostic(warehouse_root, vault_root, recovery_path):
    """Read existing source 10 times, with no admission or original F2 alias.

    The underlying Core read-only primitive re-reads vault, stage, native245,
    local253, compares 15m bar identity and enforces cutoff. Here we ALSO
    recompute SHA256 of actual RawVault bytes instead of trusting the entry.
    """
    entries = load_recovery_evidence(recovery_path)
    result = {}
    for month in ADMITTED_MONTHS:
        entry = entries[month]
        start, end = _month_bounds(month)
        readback = _one_read_only(
            warehouse_root, vault_root, month=month, source_entry=entry,
            start_ms=start, end_exclusive_ms=end, cutoff_ms=end + 1000)
        actual_raw = RawVault(vault_root).read(entry["source_sha256"])
        require(sha256(actual_raw).hexdigest() == entry["source_sha256"],
                "RECOMPUTED_RAW_BYTES_DRIFT")
        receipt = readback["receipt"]
        require(receipt["readback_bar_count"] == entry["bars"] and
                receipt["core245_native_query_sha256"] ==
                entry["core_245_native_price_query_sha256"] and
                receipt["core253_local_query_sha256"] ==
                entry["core_253_local_query_sha256"] and
                receipt["owner_f2_report_sha256"] is None and
                receipt["owner_f2_report_pin_verified"] is False,
                "SOURCE_QUERY_OR_F2_BOUNDARY_DRIFT")
        result[month] = readback
    return result
