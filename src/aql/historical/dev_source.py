"""Versioned, read-only DEV import. Requires the repository's historical_library.

Bytes/hash quality is separate from issuer availability, UTC and custody proof.
No network, source writes, strategy execution or existing PIT gate changes.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path

from research_wp_r0.historical_library import (
    BarQuality, DataAvailabilityKind, DatasetManifest, HistoricalBar,
    HistoricalDataError, SourceType, validate_bars,
)

MAX_BYTES = 16 * 1024 * 1024
MAX_BARS = 100_000
INTERVALS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "1d": 86_400_000}


class DevSourceError(ValueError):
    """A machine-readable boundary, separate from PIT research qualification."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(f"{category}: {message}")


def _fail(category, message):
    raise DevSourceError(category, message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True, init=False)
class DevSourceEnvelope:
    """Canonical immutable metadata, asserted by caller, not authenticated proof.

    V1 deliberately supports only unknown issuer version/correction authority.
    A later proven revision contract needs a new reviewed schema, not a flag flip.
    """
    payload: bytes

    def __init__(self, value):
        fields = {
            "schema", "scope", "origin", "market", "symbol", "interval",
            "start_ms", "end_ms_exclusive", "bytes_ref", "archive_sha256", "archive_size",
            "format", "member", "checksum_provenance", "normalization",
            "source_version", "correction_status", "issuer_first_available_at",
            "bounded_UTC", "independent_custody",
        }
        if type(value) is not dict or set(value) != fields:
            _fail("SCHEMA", "exact envelope fields required")
        fixed = {"schema": "core-dev-source-1", "scope": "DEV_ONLY",
                 "normalization": "ohlcv-ms-float64-grid-1",
                 "source_version": "UNKNOWN", "correction_status": "UNKNOWN",
                 "issuer_first_available_at": "UNKNOWN", "bounded_UTC": "UNKNOWN",
                 "independent_custody": "UNKNOWN"}
        if any(value[k] != v for k, v in fixed.items()):
            _fail("SCHEMA", "unsupported version, scope or asserted provenance/correction")
        for k in ("origin", "market", "symbol"):
            if type(value[k]) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value[k]):
                _fail("SCHEMA", "explicit origin/market/instrument required")
        if type(value["interval"]) is not str or value["interval"] not in INTERVALS:
            _fail("SCHEMA", "unsupported interval")
        step = INTERVALS[value["interval"]]
        start, end = value["start_ms"], value["end_ms_exclusive"]
        if (type(start) is not int or type(end) is not int or start < 0 or
                end <= start or end > 2**53 - 1 or start % step or end % step or
                (end - start) // step > MAX_BARS):
            _fail("SCHEMA", "bounded aligned nonempty UTC grid required")
        if type(value["archive_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["archive_sha256"]):
            _fail("SCHEMA", "exact lowercase SHA256 required")
        size = value["archive_size"]
        if type(size) is not int or not 0 < size <= MAX_BYTES:
            _fail("SCHEMA", "bounded exact archive size required")
        ref = value["bytes_ref"]
        if ref is not None and (type(ref) is not str or not 0 < len(ref) <= 1024):
            _fail("SCHEMA", "opaque immutable bytes reference or null required")
        if type(value["checksum_provenance"]) is not str or value["checksum_provenance"] not in ("UNKNOWN", "SAME_PUBLISHER_REPORTED", "SYNTHETIC_FIXTURE"):
            _fail("SCHEMA", "unsupported checksum provenance")
        if value["format"] == "canonical-csv-7-v1":
            if value["member"] is not None:
                _fail("SCHEMA", "plain CSV has no member")
        elif value["format"] == "binance-spot-zip-12-ms-v1":
            if value["market"] != "SPOT" or value["origin"] != "BINANCE_VISION":
                _fail("SCHEMA", "Binance ZIP requires explicit SPOT origin")
            member = value["member"]
            if type(member) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]+\.csv", member) or ".." in member:
                _fail("SCHEMA", "one flat exact CSV member required")
            if not member.startswith(value["symbol"] + "-" + value["interval"] + "-"):
                _fail("SCHEMA", "member instrument/interval mismatch")
        else:
            _fail("SCHEMA", "unsupported normalization/parser version")
        object.__setattr__(self, "payload", _canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def source_id(self):
        return "dev1:" + hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True)
class DevHistory:
    envelope: DevSourceEnvelope
    bars: tuple[HistoricalBar, ...]
    manifest: DatasetManifest

    def range_query(self, start_ms: int, end_ms_exclusive: int, decision_cutoff_ms: int,
                    *, require_pit: bool = False) -> tuple[HistoricalBar, ...]:
        """Complete DEV range using closed-bar lower bound, NEVER issuer as-of proof."""
        if require_pit is not False:
            _fail("PIT_QUALIFICATION", "issuer timing/UTC/custody unavailable")
        spec = self.envelope.spec
        step = INTERVALS[spec["interval"]]
        if (any(type(x) is not int for x in (start_ms, end_ms_exclusive, decision_cutoff_ms)) or
                start_ms < spec["start_ms"] or end_ms_exclusive > spec["end_ms_exclusive"] or
                start_ms >= end_ms_exclusive or start_ms % step or end_ms_exclusive % step):
            _fail("SOURCE_QUALITY", "complete aligned in-envelope range required")
        if decision_cutoff_ms < end_ms_exclusive:
            _fail("LOOKAHEAD", "requested bar not closed at DEV cutoff")
        return tuple(b for b in self.bars if start_ms <= b.bar_open < end_ms_exclusive)

    @property
    def receipt(self):
        return {"schema": "core-dev-import-1", "source_id": self.envelope.source_id,
                "scope": "DEV_ONLY", "availability": "BYTES_VERIFIED",
                "source_quality": "VALIDATED_GRID_OHLCV", "real_pit_accepted": False,
                "verified_source_timing": False, "empirical_eligible": False,
                "issuer_first_available_at": "UNKNOWN", "bounded_UTC": "UNKNOWN",
                "independent_custody": "UNKNOWN", "correction_status": "UNKNOWN",
                "normalized_ohlcv_sha256": hashlib.sha256(_canonical([
                    [b.bar_open, b.bar_close, b.open, b.high, b.low, b.close, b.volume]
                    for b in self.bars
                ])).hexdigest(), "manifest": self.manifest.to_dict()}


def import_bytes(envelope: DevSourceEnvelope, raw: bytes | None) -> DevHistory:
    """Hash and parse the SAME bounded snapshot. Never sort, fill, fetch or overwrite."""
    if not isinstance(envelope, DevSourceEnvelope):
        _fail("SCHEMA", "validated envelope required")
    s = envelope.spec
    if raw is None:
        _fail("DATA_AVAILABILITY", "MISSING_BYTES")
    if type(raw) is not bytes:
        _fail("SCHEMA", "immutable bytes required")
    if len(raw) != s["archive_size"] or hashlib.sha256(raw).hexdigest() != s["archive_sha256"]:
        _fail("SOURCE_INTEGRITY", "archive hash/size mismatch")
    content = raw
    if s["format"] == "binance-spot-zip-12-ms-v1":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                if (len(members) != 1 or members[0].filename != s["member"] or
                        members[0].is_dir() or members[0].file_size > MAX_BYTES):
                    _fail("SOURCE_QUALITY", "unexpected/oversized ZIP members")
                with archive.open(members[0]) as stream:
                    content = stream.read(MAX_BYTES + 1)
                if len(content) > MAX_BYTES:
                    _fail("SOURCE_QUALITY", "oversized expanded CSV")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
            raise DevSourceError("SOURCE_QUALITY", "unreadable ZIP") from exc
    bars = []
    step = INTERVALS[s["interval"]]
    try:
        rows = csv.reader(io.StringIO(content.decode("utf-8")), strict=True)
        for i, row in enumerate(rows):
            if i >= MAX_BARS:
                _fail("SOURCE_QUALITY", "too many rows")
            if s["format"] == "canonical-csv-7-v1":
                if len(row) != 7:
                    _fail("SOURCE_QUALITY", "exactly 7 CSV columns required")
                opened, closed = int(row[0]), int(row[1])
                values = [float(x) for x in row[2:]]
            else:
                if len(row) != 12:
                    _fail("SOURCE_QUALITY", "exactly 12 Binance columns required")
                opened, closed = int(row[0]), int(row[6])
                values = [float(x) for x in row[1:6]]
            # Positional comparison rejects gaps, duplicates, reordering and
            # off-grid rows BEFORE the legacy validator can allocate gap lists.
            if opened != s["start_ms"] + i * step or opened >= s["end_ms_exclusive"]:
                _fail("SOURCE_QUALITY", "duplicate/out-of-order/missing/off-grid row")
            bars.append(HistoricalBar(
                symbol=s["symbol"], interval=s["interval"], bar_open=opened, bar_close=closed,
                open=values[0], high=values[1], low=values[2], close=values[3], volume=values[4],
                quality=BarQuality.FINAL, source=SourceType.FIXTURE, source_label=envelope.source_id,
                observation_cutoff_ms=closed + 1, ingest_time_ms=None,
                availability_kind=DataAvailabilityKind.RETROSPECTIVE,
            ))
        if len(bars) != (s["end_ms_exclusive"] - s["start_ms"]) // step:
            _fail("SOURCE_QUALITY", "incomplete declared coverage")
        validated, manifest = validate_bars(bars, s["symbol"], s["interval"])
    except (UnicodeError, csv.Error, ValueError, HistoricalDataError) as exc:
        if isinstance(exc, DevSourceError):
            raise
        raise DevSourceError("SOURCE_QUALITY", str(exc)) from exc
    # Legacy manifest requires an integer creation timestamp: zero is this
    # adapter's deterministic UNRECORDED sentinel, never a receipt/publication.
    manifest = replace(manifest, dataset_id=envelope.source_id, exchange=s["origin"],
                       market=s["market"], source_hash=s["archive_sha256"], created_at_ms=0)
    return DevHistory(envelope, tuple(validated), manifest)


def import_local(envelope: DevSourceEnvelope, path: str | Path) -> DevHistory:
    """Explicit local resolver only; bytes_ref is never fetched or presumed present."""
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        _fail("DATA_AVAILABILITY", "MISSING_BYTES or unsupported file")
    try:
        with p.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise DevSourceError("DATA_AVAILABILITY", "unreadable bytes") from exc
    return import_bytes(envelope, raw)
