"""#150: offline input QUALITY only, never strategy or PIT admission.

Injected bytes and explicit bounded UTC window. Existing HistoricalLibrary
validates OHLCV; existing retrospective intake validates the ZIP envelope.
No network, local clock, storage registration, signals, or Core imports.
"""
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import re

from .historical_library import (
    HistoricalBar, HistoricalDataError, BarQuality, SourceType,
    DataAvailabilityKind, validate_bars, _interval_to_ms,
)
from .retrospective_kline_intake import read_binance_spot_archive_bytes
from .strategy_definition import canonical, identifier, integer, keys, load_json

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 100000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_META = "observed_at_ms publisher_available_at_ms first_known_at_ms vintage_id supersedes_version correction_history_ref independent_utc_ref independent_anchor_ref source_ack_ref target_ack_ref verified_source_timing real_pit_accepted"


def _text(value, maximum=2048):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise ValueError("Required bounded text")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Invalid UTF-8 metadata") from exc
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control character in metadata")


@dataclass(frozen=True, init=False)
class HistoricalInputSpec:
    payload: bytes

    def __init__(self, spec):
        keys(spec, "schema scope provider venue symbol timeframe timezone price_unit volume_unit source_uri license_reference container csv_format timestamp_unit member_name version_sha256 publisher_checksum_sha256 start_ms end_exclusive_ms review_cutoff_ms provenance")
        if (spec["schema"] != "historical-input-quality-1" or spec["scope"] != "DEV_INPUT_QUALITY_ONLY"
                or spec["timezone"] != "UTC"):
            raise ValueError("Explicit DEV-only UTC quality contract required")
        for key in ("provider", "venue", "symbol"):
            identifier(spec[key])
        for key in ("source_uri", "license_reference", "price_unit", "volume_unit"):
            _text(spec[key])
        if type(spec["timeframe"]) is not str or not re.fullmatch(r"[1-9][0-9]{0,3}m", spec["timeframe"]):
            raise ValueError("Explicit minute timeframe required")
        interval = _interval_to_ms(spec["timeframe"])
        if interval > 86400000:
            raise ValueError("Unsupported timeframe")
        for key in ("start_ms", "end_exclusive_ms", "review_cutoff_ms"):
            integer(spec[key], 0, 2**53-1)
        start, end = spec["start_ms"], spec["end_exclusive_ms"]
        if (start % interval or end % interval or not start < end <= spec["review_cutoff_ms"]
                or (end-start)//interval > MAX_ROWS):
            raise ValueError("Invalid bounded UTC window/cutoff")
        if spec["container"] not in ("CSV", "BINANCE_SPOT_ZIP") or spec["csv_format"] not in ("NORMALIZED_7", "BINANCE_KLINES_12"):
            raise ValueError("Unsupported source encoding")
        if spec["timestamp_unit"] not in ("ms", "us"):
            raise ValueError("Timestamp unit must be explicit")
        if not isinstance(spec["version_sha256"], str) or not _SHA.fullmatch(spec["version_sha256"]):
            raise ValueError("Pinned source-bytes version required")
        checksum = spec["publisher_checksum_sha256"]
        if checksum is not None and (type(checksum) is not str or not _SHA.fullmatch(checksum)):
            raise ValueError("Invalid publisher checksum")
        if spec["container"] == "BINANCE_SPOT_ZIP":
            if (spec["provider"] != "BINANCE_VISION" or spec["venue"] != "BINANCE_SPOT"
                    or spec["symbol"] != "BTCUSDT" or spec["timeframe"] != "1m"
                    or spec["csv_format"] != "BINANCE_KLINES_12"):
                raise ValueError("Shared ZIP decoder supports Binance BTCUSDT 1m only")
            if type(spec["member_name"]) is not str or not re.fullmatch(r"BTCUSDT-1m-[A-Za-z0-9_.-]+\.csv", spec["member_name"]):
                raise ValueError("Exact supported archive member required")
        elif spec["member_name"] is not None:
            raise ValueError("CSV has no archive member")
        meta = spec["provenance"]
        keys(meta, _META)
        for key, value in meta.items():
            if key in ("verified_source_timing", "real_pit_accepted"):
                if type(value) is not bool:
                    raise ValueError("Explicit claim flags required")
            elif value is not None:
                if key.endswith("_ms"):
                    integer(value, 0, 2**53-1)
                else:
                    _text(value, 256)
        object.__setattr__(self, "payload", canonical(spec))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True, init=False)
class InputQualityReceipt:
    payload: bytes

    def __init__(self, body):
        if (type(body) is not dict or body.get("schema") != "historical-input-quality-receipt-1"
                or body.get("verified_source_timing") is not False
                or body.get("real_pit_accepted") is not False
                or body.get("performance_execution_allowed") is not False
                or body.get("quality_status") not in ("SOURCE_QUALITY_ACCEPTED","SOURCE_QUALITY_BLOCKED")
                or type(body.get("pit")) is not dict
                or body["pit"].get("status") not in ("PIT_UNKNOWN","PIT_BLOCKED")):
            raise ValueError("Quality receipt cannot grant PIT/execution authority")
        object.__setattr__(self, "payload", canonical(body))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return hashlib.sha256(self.payload).hexdigest()

    def to_json(self):
        return canonical(dict(receipt=self.spec, digest=self.digest)).decode("utf-8")

    @classmethod
    def from_json(cls, raw, *, expected_digest):
        wrapper = load_json(raw)
        keys(wrapper, "receipt digest")
        obj = cls(wrapper["receipt"])
        if obj.digest != expected_digest or obj.digest != wrapper["digest"]:
            raise ValueError("Retained receipt digest mismatch")
        return obj


def _pit(meta, end, cutoff):
    statuses, reasons = {}, []
    names = dict(first_known_at_ms="HISTORICAL_FIRST_KNOWN", publisher_available_at_ms="PUBLISHER_AVAILABILITY",
        vintage_id="VINTAGE_ID", correction_history_ref="CORRECTION_HISTORY",
        independent_utc_ref="INDEPENDENT_UTC", independent_anchor_ref="INDEPENDENT_ANCHOR",
        source_ack_ref="SOURCE_ACK", target_ack_ref="TARGET_ACK")
    for field, code in names.items():
        missing = meta[field] is None
        statuses[field] = "MISSING" if missing else "CALLER_SUPPLIED_NOT_VERIFIED"
        reasons.append(code + ("_MISSING" if missing else "_UNVERIFIED"))
    blocked = meta["verified_source_timing"] or meta["real_pit_accepted"]
    if blocked:
        reasons.append("CALLER_PIT_CLAIM_REJECTED")
    for field in ("first_known_at_ms", "publisher_available_at_ms"):
        value = meta[field]
        if value is not None and not end <= value <= cutoff:
            reasons.append("SOURCE_VERSION_NOT_KNOWN_AT_CUTOFF_OR_INVALID_CHRONOLOGY")
            blocked = True
    reasons.append("EXTERNAL_AUTHORITY_VERIFICATION_NOT_IMPLEMENTED")
    return dict(status="PIT_BLOCKED" if blocked else "PIT_UNKNOWN", evidence_status=statuses,
                reasons=sorted(set(reasons)), local_observed_at_ms=meta["observed_at_ms"],
                claimed_metadata={k:v for k,v in meta.items() if k not in ("verified_source_timing","real_pit_accepted")},
                local_observation_authority="DIAGNOSTIC_ONLY_NOT_HISTORICAL_FIRST_KNOWN")


def inspect_historical_input(raw, spec, *, expected_spec_digest):
    """Inspect supplied bytes; no file/network access or strategy calculation.

    Malformed contracts raise; bad source bytes produce SOURCE_QUALITY_BLOCKED.
    SOURCE_QUALITY_ACCEPTED is never an authorization to run a historical study.
    """
    if not isinstance(spec, HistoricalInputSpec) or spec.digest != expected_spec_digest:
        raise ValueError("Pinned input specification mismatch")
    s = spec.spec
    interval = _interval_to_ms(s["timeframe"])
    counts = dict(rows=0, parsed_rows=0, malformed_rows=0, duplicate_opens=0,
        out_of_order=0, off_grid=0, outside_window=0, bad_close_time=0,
        invalid_ohlcv=0, nonfinite_ohlcv=0, expected_slots=(s["end_exclusive_ms"]-s["start_ms"])//interval,
        missing_slots=None, observed_slots=0)
    reasons, samples, openings = set(), [], []
    actual = hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None
    csv_bytes = raw
    def seal():
        pit = _pit(s["provenance"], s["end_exclusive_ms"], s["review_cutoff_ms"])
        return InputQualityReceipt(dict(schema="historical-input-quality-receipt-1", spec_digest=spec.digest,
            scope=s["scope"], source={k:s[k] for k in ("provider","venue","symbol","timeframe","timezone","source_uri","license_reference","price_unit","volume_unit","container","csv_format","timestamp_unit","member_name")},
            requested_window_ms=[s["start_ms"],s["end_exclusive_ms"]], review_cutoff_ms=s["review_cutoff_ms"],
            version_sha256=actual, expected_version_sha256=s["version_sha256"],
            csv_sha256=hashlib.sha256(csv_bytes).hexdigest() if type(csv_bytes) is bytes and not early else None,
            checksum_status=("MISMATCH" if "PUBLISHER_CHECKSUM_MISMATCH" in reasons else
                "CALLER_SUPPLIED_PUBLISHER_CHECKSUM_MATCH_NOT_INDEPENDENT" if s["publisher_checksum_sha256"] is not None and actual==s["publisher_checksum_sha256"]
                else "NOT_SUPPLIED_VERSION_FINGERPRINT_ONLY"),
            source_identity_authority="CALLER_DECLARED_NOT_PROVIDER_AUTHENTICATED",
            quality_status="SOURCE_QUALITY_BLOCKED" if reasons else "SOURCE_QUALITY_ACCEPTED",
            quality_reasons=sorted(reasons), counts=counts, diagnostic_samples=samples,
            first_open_ms=min(openings) if openings else None, last_open_ms=max(openings) if openings else None,
            pit=pit, verified_source_timing=False, real_pit_accepted=False,
            performance_execution_allowed=False, oos_access="NOT_AUTHORIZED", strategy_executed=False))
    early = True
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        reasons.add("INVALID_OR_OVERSIZED_SOURCE_BYTES"); return seal()
    if actual != s["version_sha256"]:
        reasons.add("VERSION_HASH_MISMATCH")
    if s["publisher_checksum_sha256"] is not None and actual != s["publisher_checksum_sha256"]:
        reasons.add("PUBLISHER_CHECKSUM_MISMATCH")
    if reasons:
        return seal()
    if s["container"] == "BINANCE_SPOT_ZIP":
        try:
            csv_bytes, _, member = read_binance_spot_archive_bytes(raw, expected_sha256=s["version_sha256"])
            if member != s["member_name"]:
                reasons.add("ARCHIVE_MEMBER_MISMATCH"); return seal()
        except (ValueError, OSError, RuntimeError):
            reasons.add("INVALID_ARCHIVE_ENVELOPE"); return seal()
    if len(csv_bytes) > MAX_BYTES:
        reasons.add("OVERSIZED_CSV"); return seal()
    early = False
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeError:
        reasons.add("INVALID_CSV_UTF8"); return seal()
    seen, previous = set(), None
    try:
        for line, record in enumerate(csv.reader(io.StringIO(text), strict=True), 1):
            counts["rows"] += 1
            if counts["rows"] > MAX_ROWS:
                reasons.add("ROW_LIMIT_EXCEEDED"); break
            width = 12 if s["csv_format"] == "BINANCE_KLINES_12" else 7
            try:
                if len(record) != width:
                    raise ValueError("Missing columns")
                op_idx, close_idx = 0, 6 if width==12 else 1
                stamps = [record[op_idx],record[close_idx]]
                if any(not re.fullmatch(r"[0-9]{1,17}", x) for x in stamps):
                    raise ValueError("Invalid integer timestamps")
                opening, closing = map(int, stamps)
                if s["timestamp_unit"] == "us":
                    if opening%1000 or closing%1000!=999:
                        raise ValueError("Microsecond boundary")
                    opening//=1000; closing//=1000
                integer(opening,0,2**53-1); integer(closing,0,2**53-1)
                indexes = (1,2,3,4,5) if width==12 else (2,3,4,5,6)
                values = [float(record[i]) for i in indexes]
            except (ValueError, OverflowError):
                counts["malformed_rows"]+=1; reasons.add("MALFORMED_CSV_ROW")
                if len(samples)<10:samples.append(dict(line=line,reason="MALFORMED_CSV_ROW"))
                continue
            counts["parsed_rows"]+=1; openings.append(opening)
            if opening in seen:counts["duplicate_opens"]+=1; reasons.add("DUPLICATE_OPEN")
            seen.add(opening)
            if previous is not None and opening<previous:counts["out_of_order"]+=1; reasons.add("OUT_OF_ORDER")
            previous=opening
            if opening%interval:counts["off_grid"]+=1; reasons.add("OFF_GRID")
            if not s["start_ms"]<=opening<s["end_exclusive_ms"]:counts["outside_window"]+=1; reasons.add("OUTSIDE_FROZEN_WINDOW")
            if closing!=opening+interval-1:counts["bad_close_time"]+=1; reasons.add("BAD_CLOSE_TIME")
            bar=HistoricalBar(s["symbol"],s["timeframe"],opening,opening+interval-1,*values,
                quality=BarQuality.FINAL,source=SourceType.ARCHIVE,source_label=s["provider"],
                observation_cutoff_ms=opening+interval,ingest_time_ms=None,
                availability_kind=DataAvailabilityKind.RETROSPECTIVE)
            try:
                # Only numeric OHLCV validation is reused here. Derived close is
                # checked against the supplied close separately above. No library
                # manifest/created_at timestamp is retained or trusted as custody.
                validate_bars([bar],s["symbol"],s["timeframe"])
            except HistoricalDataError as exc:
                counts["invalid_ohlcv"]+=1; reasons.add("INVALID_OHLCV")
                if str(exc).startswith("Non-finite"):counts["nonfinite_ohlcv"]+=1
                if len(samples)<10:samples.append(dict(line=line,reason="INVALID_OHLCV"))
    except csv.Error:
        reasons.add("MALFORMED_CSV_SYNTAX")
    expected = set(range(s["start_ms"],s["end_exclusive_ms"],interval))
    counts["observed_slots"]=len(expected & seen)
    counts["missing_slots"]=len(expected-seen)
    if not counts["rows"]:reasons.add("EMPTY_INPUT")
    if counts["missing_slots"]:reasons.add("MISSING_GRID_SLOTS")
    return seal()


def replay_input_quality(raw, spec, receipt, *, expected_spec_digest, expected_receipt_digest):
    if not isinstance(receipt, InputQualityReceipt) or receipt.digest != expected_receipt_digest:
        raise ValueError("Pinned quality receipt required")
    actual=inspect_historical_input(raw,spec,expected_spec_digest=expected_spec_digest)
    if actual.payload!=receipt.payload:
        raise ValueError("Input quality replay mismatch")
    return actual
