"""Factory static contract review only: no files, Core imports or engine calls.

Checks injected Core149 metadata + normalized7 records against caller-retained
commitments. This does not independently measure archive bytes or consumer ACK.
"""
from dataclasses import dataclass
import hashlib
import json
import re

from .historical_library import (
    BarQuality, DataAvailabilityKind, DatasetManifest, HistoricalBar,
    HistoricalDataError, SourceType, validate_bars,
)

INTERVALS = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000, "1d": 86400000}


def canonical(value):
    # Core149 uses default ensure_ascii=True; numeric normalized7 has no text.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class ReadinessError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise ReadinessError(reason)


def sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, init=False)
class SourceReview:
    payload: bytes

    def __init__(self, value):
        object.__setattr__(self, "payload", canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def receipt_sha256(self):
        return hashlib.sha256(self.payload).hexdigest()


def inspect_source(envelope, core_receipt, normalized7, *, expected, declarations):
    """Verify one complete injected DEV resource, never admit it for execution.

    expected has separately retained source_id, archive_sha256, archive_size,
    normalized7_sha256 and core_receipt_sha256. These are caller commitments,
    NOT issuer authentication, a raw-file measurement or an ACK from this tool.
    Timing/quote declarations must explicitly remain UNKNOWN/None in this port.
    """
    require(type(expected) is dict and set(expected) == {
        "source_id", "archive_sha256", "archive_size", "normalized7_sha256", "core_receipt_sha256"
    }, "MISSING_EXPECTED_COMMITMENTS")
    require(all(sha(expected[k]) for k in ("archive_sha256", "normalized7_sha256", "core_receipt_sha256")),
            "INVALID_EXPECTED_HASH")
    require(type(declarations) is dict and declarations == {
        "availability": "UNKNOWN", "correction_timing": "UNKNOWN", "bounded_UTC": "UNKNOWN",
        "independent_custody": "UNKNOWN", "available_ms": None, "modeled_quote": None,
        "verified_source_timing": False, "real_pit_accepted": False,
    } and declarations["verified_source_timing"] is False and declarations["real_pit_accepted"] is False,
            "PROVENANCE_OR_QUOTE_CONFLICT")
    fields = {"schema", "scope", "origin", "market", "symbol", "interval", "start_ms",
              "end_ms_exclusive", "bytes_ref", "archive_sha256", "archive_size", "format", "member",
              "checksum_provenance", "normalization", "source_version", "correction_status",
              "issuer_first_available_at", "bounded_UTC", "independent_custody"}
    require(type(envelope) is dict and set(envelope) == fields, "CORE_ENVELOPE_SHAPE")
    require(envelope["schema"] == "core-dev-source-1" and envelope["scope"] == "DEV_ONLY"
            and envelope["normalization"] == "ohlcv-ms-float64-grid-1", "UNSUPPORTED_CORE_VERSION")
    require(all(envelope[k] == "UNKNOWN" for k in (
        "source_version", "correction_status", "issuer_first_available_at", "bounded_UTC", "independent_custody"
    )), "UNSUPPORTED_PROVENANCE_CLAIM")
    for k in ("origin", "market", "symbol"):
        require(type(envelope[k]) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", envelope[k]),
                "INVALID_SOURCE_IDENTITY")
    interval = envelope["interval"]
    require(type(interval) is str and interval in INTERVALS, "UNSUPPORTED_INTERVAL")
    step = INTERVALS[interval]
    start, end = envelope["start_ms"], envelope["end_ms_exclusive"]
    require(type(start) is int and type(end) is int and 0 <= start < end <= 2**53-1
            and start % step == 0 and end % step == 0 and (end-start)//step <= 100000,
            "INVALID_DECLARED_GRID")
    require(type(envelope["archive_size"]) is int and 0 < envelope["archive_size"] <= 16*1024*1024
            and type(expected["archive_size"]) is int and envelope["archive_size"] == expected["archive_size"]
            and envelope["archive_sha256"] == expected["archive_sha256"], "ARCHIVE_COMMITMENT_MISMATCH")
    require(envelope["bytes_ref"] is None or (type(envelope["bytes_ref"]) is str
            and 0 < len(envelope["bytes_ref"]) <= 1024), "INVALID_BYTES_REFERENCE")
    require(envelope["checksum_provenance"] in ("UNKNOWN", "SAME_PUBLISHER_REPORTED", "SYNTHETIC_FIXTURE"),
            "INVALID_CHECKSUM_PROVENANCE")
    if envelope["format"] == "canonical-csv-7-v1":
        require(envelope["member"] is None, "INVALID_MEMBER_IDENTITY")
    else:
        m = envelope["member"]
        require(envelope["format"] == "binance-spot-zip-12-ms-v1" and envelope["origin"] == "BINANCE_VISION"
                and envelope["market"] == "SPOT" and type(m) is str
                and re.fullmatch(r"[A-Za-z0-9_.-]+\.csv", m) and ".." not in m
                and m.startswith(envelope["symbol"]+"-"+interval+"-"), "INVALID_MEMBER_IDENTITY")
    source_id = "dev1:" + digest(envelope)
    require(source_id == expected["source_id"], "SOURCE_ID_MISMATCH")
    require(type(core_receipt) is dict and digest(core_receipt) == expected["core_receipt_sha256"],
            "CORE_RECEIPT_COMMITMENT_MISMATCH")
    require(set(core_receipt) == {"schema", "source_id", "scope", "availability", "source_quality",
            "real_pit_accepted", "verified_source_timing", "empirical_eligible", "issuer_first_available_at",
            "bounded_UTC", "independent_custody", "correction_status", "normalized_ohlcv_sha256", "manifest"},
            "CORE_RECEIPT_SHAPE")
    require(core_receipt["schema"] == "core-dev-import-1" and core_receipt["source_id"] == source_id
            and core_receipt["scope"] == "DEV_ONLY" and core_receipt["availability"] == "BYTES_VERIFIED"
            and core_receipt["source_quality"] == "VALIDATED_GRID_OHLCV"
            and all(core_receipt[k] is False for k in ("real_pit_accepted", "verified_source_timing", "empirical_eligible"))
            and all(core_receipt[k] == "UNKNOWN" for k in (
                "issuer_first_available_at", "bounded_UTC", "independent_custody", "correction_status")),
            "CORE_RECEIPT_CLAIM_CONFLICT")
    require(type(normalized7) in (list, tuple) and len(normalized7) == (end-start)//step,
            "INCOMPLETE_NORMALIZED_GRID")
    bars = []
    for i, row in enumerate(normalized7):
        require(type(row) in (list, tuple) and len(row) == 7, "NORMALIZED7_SHAPE")
        require(type(row[0]) is int and type(row[1]) is int and row[0] == start+i*step
                and row[1] == row[0]+step-1, "GAP_DUPLICATE_ORDER_OR_CLOSE")
        require(all(type(x) is float for x in row[2:]), "NORMALIZATION_FLOAT64_REQUIRED")
        # Reconstruct ONLY the documented Core HistoricalBar representation to
        # reuse legacy quality/checksum validation. Never create engine rows,
        # available_ms or modeled_quote, and never claim issuer first-known.
        bars.append(HistoricalBar(
            symbol=envelope["symbol"], interval=interval, bar_open=row[0], bar_close=row[1],
            open=row[2], high=row[3], low=row[4], close=row[5], volume=row[6],
            quality=BarQuality.FINAL, source=SourceType.FIXTURE, source_label=source_id,
            observation_cutoff_ms=row[1]+1, ingest_time_ms=None,
            availability_kind=DataAvailabilityKind.RETROSPECTIVE,
        ))
    try:
        validate_bars(bars, envelope["symbol"], interval)
        m = DatasetManifest.from_dict(core_receipt["manifest"])
        require(m.provenance_verified and m.verify_integrity() and m.verify_hash(bars)
                and m.source_hash == expected["archive_sha256"] and m.dataset_id == source_id
                and m.symbol == envelope["symbol"] and m.interval == interval
                and m.exchange == envelope["origin"] and m.market == envelope["market"]
                and m.source_label == source_id and m.timezone == "UTC" and m.version == 1
                and m.parent_version is None and m.lineage_reason is None and m.created_at_ms == 0
                and m.bar_count == len(bars) and m.min_bar_open == start and m.max_bar_open == end-step
                and m.coverage_pct == 100.0 and m.gap_count == 0 and not m.gap_bar_opens
                and m.duplicate_count == 0 and m.non_final_count == 0, "MANIFEST_BINDING_CONFLICT")
    except (HistoricalDataError, TypeError, KeyError) as exc:
        raise ReadinessError("QUALITY_OR_MANIFEST_INVALID") from exc
    normalized_hash = digest(normalized7)
    require(normalized_hash == expected["normalized7_sha256"]
            and normalized_hash == core_receipt["normalized_ohlcv_sha256"], "NORMALIZED_HASH_MISMATCH")
    return SourceReview({
        "schema": "sf-post149-source-review-1", "status": "READY_FOR_CONTRACT_REVIEW",
        "scope": "DEV_ONLY_STATIC_REVIEW", "source_quality": "PASS_SOURCE_QUALITY",
        "quality_scope": "INJECTED_NORMALIZED_RECORDS_AND_METADATA_ONLY",
        "pit_status": "BLOCKED_PIT", "consumer_status": "NEED_CONSUMER_ACK",
        "archive_readback": "NOT_PERFORMED", "source_id": source_id,
        "expected_commitments": dict(expected), "envelope_sha256": digest(envelope),
        "record_count": len(bars), "start_ms": start, "end_ms_exclusive": end,
        "declarations": dict(declarations), "factory_execution_eligible": False,
        "verified_source_timing": False, "real_pit_accepted": False,
        "missing_evidence": ["THIS_CODEX_CONSUMER_ZIP_AND_RECEIPT_ACK", "ISSUER_VERSION_FIRST_KNOWN",
                             "CORRECTION_CHRONOLOGY", "BOUNDED_UTC_AUTHORITY", "INDEPENDENT_CUSTODY",
                             "COUNCIL_148_149_AND_157_ACCEPTANCE", "OWNER_DEV_TIME_QUOTE_MODEL_PERMISSION",
                             "SIGNED_INTERFACE_AGREEMENT", "OWNER_INTEGRATION_AUTHORIZATION"],
    })
