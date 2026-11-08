"""Package H: deterministic read-only view of previously VERIFIED Core F recovery.

This is an adapter, not a new warehouse or an independent source admission.
The caller must obtain month_result from read_recovery_diagnostic on the
same owner-approved read-only session. Never accept a synthetic self-sealed
receipt as original-source authority or promote retrospective data to PIT.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
    ADMITTED_MONTHS, EXPECTED_RECOVERY_BYTES_SHA256,
    EXPECTED_RECOVERY_INTERNAL_SHA256, SCHEMA as SOURCE_SCHEMA,
)

SCHEMA = "aql.core.h.portable-research-query.v1"
REQUEST_SCHEMA = "aql.core.h.portable-research-query-request.v1"
STEP_MS = 900_000
SHA_KEYS = (
    "source_zip_sha256", "manifest_integrity_sha256",
    "warehouse_receipt_sha256", "core245_native_query_sha256",
    "core253_local_query_sha256", "dual_map_sha256",
    "recovery_file_sha256", "recovery_raw_bytes_sha256",
)
REQUEST_FIELDS = {
    "schema", "month", "dataset_id", "start_ms", "end_exclusive_ms",
    "decision_cutoff_ms", "require_complete",
}


def _need(ok, code):
    if not ok:
        raise ValueError("CORE_H_" + code)


def _hex(value):
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value)


def _same_bar(native, local):
    return (
        type(native) is dict and type(local) is dict
        and native.get("bar_open_ms") == local.get("bar_open_ms")
        and native.get("bar_close_ms") == local.get("bar_close_ms")
        and native.get("checksum") == local.get("bar_checksum")
        and native.get("observation_lower_bound_ms") ==
            local.get("observation_lower_bound_ms")
        and native.get("historical_known_at_ms") is None
        and local.get("historical_known_at_ms") is None
    )


def adapt_verified_recovery_month(month_result, request):
    """Adapt one Core-verified month without fetching/writing any data.

    Cannot itself prove provenance: source SHA/receipt are cryptographic
    integrity checks only. No historical known-at or F5 authorization.
    """
    _need(type(request) is dict and set(request) == REQUEST_FIELDS
          and request.get("schema") == REQUEST_SCHEMA, "REQUEST_FIELDS")
    month = request["month"]
    _need(type(month) is str and month in ADMITTED_MONTHS,
          "MONTH_NOT_ADMITTED")
    _need(type(request["dataset_id"]) is str and
          request["dataset_id"] ==
          "BINANCE-SPOT-BTCUSDT-15M-" + month + "-F-v1",
          "DATASET_IDENTITY")
    start, end, cutoff = (request[k] for k in
                           ("start_ms", "end_exclusive_ms",
                            "decision_cutoff_ms"))
    _need(all(type(x) is int and x >= 0 for x in (start, end, cutoff))
          and 0 < end - start <= 4096 * STEP_MS
          and start % STEP_MS == end % STEP_MS == 0
          and type(request["require_complete"]) is bool,
          "RANGE_GRID_OR_TYPE")
    _need(type(month_result) is dict and
          set(month_result) == {"receipt", "native_bars", "local_bars"},
          "VERIFIED_RESULT_REQUIRED")
    receipt = month_result["receipt"]
    _need(type(receipt) is dict and
          receipt.get("schema") == SOURCE_SCHEMA and
          receipt.get("status") == "SOURCE_BACKED_RECOVERY_READBACK_ONLY"
          and receipt.get("month") == month
          and receipt.get("dataset_id") == request["dataset_id"]
          and receipt.get("historical_pit") == "NOT_ATTESTED"
          and receipt.get("trading_authority") == "NONE"
          and receipt.get("source_ack_sha256") is None
          and receipt.get("strategy_approval_sha256") is None
          and receipt.get("factory_consumer_ack_sha256") is None
          and receipt.get("opaque_recovery_file_pin_verified") is True
          and receipt.get("recovery_internal_canonical_recomputed") is False,
          "SOURCE_RECEIPT_SCOPE")
    _need(all(_hex(receipt.get(k)) for k in SHA_KEYS)
          and receipt["recovery_file_sha256"] ==
              EXPECTED_RECOVERY_INTERNAL_SHA256
          and receipt["recovery_raw_bytes_sha256"] ==
              EXPECTED_RECOVERY_BYTES_SHA256
          and _hex(receipt.get("receipt_sha256"))
          and digest({k: v for k, v in receipt.items()
                      if k != "receipt_sha256"}) == receipt["receipt_sha256"],
          "SOURCE_RECEIPT_SEAL")
    _need(type(receipt.get("start_ms")) is int and
          type(receipt.get("end_exclusive_ms")) is int and
          receipt["start_ms"] <= start < end <= receipt["end_exclusive_ms"]
          and receipt["start_ms"] % STEP_MS == 0
          and receipt["end_exclusive_ms"] % STEP_MS == 0,
          "RANGE_OUTSIDE_VERIFIED_COVERAGE")
    native = month_result["native_bars"]
    local = month_result["local_bars"]
    _need(type(native) is list and type(local) is list and
          len(native) == len(local) == receipt.get("bar_count") and
          len(native) == (receipt["end_exclusive_ms"] -
                          receipt["start_ms"]) // STEP_MS,
          "PARENT_BAR_CENSUS")
    for i, (a, b) in enumerate(zip(native, local)):
        opened = receipt["start_ms"] + i * STEP_MS
        _need(_same_bar(a, b) and
              a["bar_open_ms"] == opened and
              a["bar_close_ms"] == opened + STEP_MS - 1 and
              a["bar_close_ms"] < receipt["decision_cutoff_ms"],
              "DUAL_BAR_IDENTITY_OR_CUTOFF")
    chosen = [a for a in native if
              start <= a["bar_open_ms"] < end
              and a["bar_close_ms"] < cutoff]
    required = (end - start) // STEP_MS
    missing = [t for t in range(start, end, STEP_MS)
               if not any(x["bar_open_ms"] == t for x in chosen)]
    coverage = ("COMPLETE" if not missing else
                "UNKNOWN" if not chosen else "PARTIAL")
    if request["require_complete"]:
        _need(not missing, "INCOMPLETE_OR_FUTURE_RANGE")
    proof = {
        "schema": SCHEMA, "dataset_id": request["dataset_id"],
        "month": month, "start_ms": start, "end_exclusive_ms": end,
        "decision_cutoff_ms": cutoff, "status": coverage,
        "available_bar_count": len(chosen),
        "required_bar_count": required, "missing_bar_opens": missing,
        "source_receipt_sha256": receipt["receipt_sha256"],
        **{k: receipt[k] for k in SHA_KEYS},
        "range_bar_identity_sha256": digest([
            {"open_ms": b["bar_open_ms"], "checksum": b["checksum"]}
            for b in chosen]),
        "historical_pit": "NOT_ATTESTED",
        "historical_known_at_ms": None,
        "research_scope": "RETROSPECTIVE_NON_PIT",
        "evidence_boundary": "UPSTREAM_CORE_READBACK_NOT_INDEPENDENT_ATTESTATION",
        "source_ack_sha256": None, "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "trading_authority": "NONE",
        "research_evaluation": "NOT_PERFORMED",
    }
    return {"receipt": {**proof, "receipt_sha256": digest(proof)},
            "bars": chosen}
