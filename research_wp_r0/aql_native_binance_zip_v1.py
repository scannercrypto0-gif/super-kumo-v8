"""Core #245: bounded Binance monthly klines ORIGINAL ZIP reader.

Does not download data, authenticate vendor origin, claim independent PIT, or
rewrite a 12-column member as a 7-column original. ZIP bytes remain the custody
source object; CSV/normalization hashes and original line lineage are retained.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
import re
import stat
from zipfile import ZipFile, BadZipFile, ZIP_STORED, ZIP_DEFLATED

MAX_MEMBER_BYTES = 8_000_000
MAX_ROWS = 4096
_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,150}$")


class NativeZipError(ValueError):
    pass


def _check(ok, code):
    if not ok:
        raise NativeZipError(code)


def _hash(buf):
    return sha256(buf).hexdigest()


def _safe_name(name):
    return (
        type(name) is str and _NAME.fullmatch(name) is not None
        and "/" not in name and "\\" not in name
        and name not in (".", "..") and ".." not in name
    )


def parse_binance_zip(source_raw, spec, meta, *, make_bar):
    """Reparse from original ZIP, verify retained CHECKSUM and one native member."""
    _check(type(meta) is dict and set(meta) == {
        "kind", "archive_name", "archive_sha256", "member_name",
        "member_sha256", "checksum_file_sha256", "checksum_text",
    } and meta["kind"] == "NATIVE_BINANCE_KLINES_ZIP",
           "NATIVE_ZIP_META_FIELDS")
    _check(type(source_raw) is bytes and 0 < len(source_raw) <= MAX_MEMBER_BYTES,
           "NATIVE_ZIP_SOURCE_BOUNDS")
    _check(_safe_name(meta["archive_name"]) and meta["archive_name"].endswith(".zip")
           and _safe_name(meta["member_name"]) and meta["member_name"].endswith(".csv"),
           "NATIVE_ZIP_MEMBER_NAME")
    month = datetime.fromtimestamp(spec["start_ms"]/1000,timezone.utc).strftime("%Y-%m")
    stem = f'{spec["symbol"]}-{spec["interval"]}-{month}'
    _check(meta["archive_name"] == stem+".zip" and meta["member_name"] == stem+".csv"
           and spec["exchange"] == "BINANCE" and spec["market"] == "SPOT",
           "NATIVE_ZIP_SCOPE_OR_IDENTITY")
    _check(all(type(meta[k]) is str and _SHA.fullmatch(meta[k])
               for k in ("archive_sha256","member_sha256","checksum_file_sha256")),
           "NATIVE_ZIP_SHA_FIELDS")
    _check(_hash(source_raw) == meta["archive_sha256"], "NATIVE_ZIP_SHA_MISMATCH")
    checksum = meta["checksum_text"]
    _check(type(checksum) is str and 0 < len(checksum) <= 512 and checksum.isascii()
           and _hash(checksum.encode("ascii")) == meta["checksum_file_sha256"],
           "NATIVE_ZIP_CHECKSUM_FILE_MISMATCH")
    lines = checksum.strip().splitlines()
    _check(len(lines) == 1, "NATIVE_ZIP_CHECKSUM_SHAPE")
    matched = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+\*?([A-Za-z0-9_.-]+)",lines[0])
    _check(matched is not None and matched.group(1).lower() == meta["archive_sha256"]
           and matched.group(2) == meta["archive_name"],
           "NATIVE_ZIP_CHECKSUM_ASSERTION")
    try:
        with ZipFile(BytesIO(source_raw)) as archive:
            entries = archive.infolist()
            _check(len(entries) == 1, "NATIVE_ZIP_MEMBER_CENSUS")
            info = entries[0]
            _check(info.filename == meta["member_name"] and not info.is_dir()
                   and not (info.flag_bits & 0x1)
                   and info.compress_type in (ZIP_STORED, ZIP_DEFLATED)
                   and info.file_size <= MAX_MEMBER_BYTES
                   and info.file_size > 0
                   and info.compress_size > 0
                   and info.file_size <= 200 * info.compress_size,
                   "NATIVE_ZIP_UNSAFE_MEMBER")
            mode = info.external_attr >> 16
            _check(not stat.S_ISLNK(mode), "NATIVE_ZIP_SYMLINK")
            member = archive.read(info)  # ZIP module verifies CRC32.
    except (BadZipFile, OSError, RuntimeError, EOFError, ValueError) as exc:
        if isinstance(exc, NativeZipError):
            raise
        raise NativeZipError("NATIVE_ZIP_CORRUPT") from exc
    _check(_hash(member) == meta["member_sha256"], "NATIVE_ZIP_MEMBER_SHA_MISMATCH")
    try:
        rows = list(csv.reader(StringIO(member.decode("utf-8-sig"), newline="")))
    except (UnicodeError, csv.Error, ValueError) as exc:
        raise NativeZipError("NATIVE_ZIP_CSV_ENCODING") from exc
    _check(1 <= len(rows) <= MAX_ROWS, "NATIVE_ZIP_ROW_BOUNDS")
    width = (spec["end_exclusive_ms"] - spec["start_ms"]) // len(rows)
    # The existing Bridge validates native interval width and exact contiguous
    # grid; no missing rows are repaired or synthesized.
    from research_wp_r0.historical_library import _interval_to_ms
    actual_width = _interval_to_ms(spec["interval"])
    _check(width == actual_width, "NATIVE_ZIP_INCOMPLETE_GRID")
    bars, origin = [], []
    for i, row in enumerate(rows):
        _check(len(row) == 12, "NATIVE_ZIP_REQUIRES_12_COLUMNS")
        try:
            opened = int(row[0])
            closed = int(row[6])
            trades = int(row[8])
            # Exact raw decimal source strings remain in the immutable ZIP;
            # existing HistoricalBar uses floats for computation.
            from decimal import Decimal, InvalidOperation
            auxiliary = [Decimal(row[k]) for k in (7,9,10,11)]
        except (ValueError, InvalidOperation, IndexError) as exc:
            raise NativeZipError("NATIVE_ZIP_INVALID_NATIVE_ROW") from exc
        _check(opened == spec["start_ms"] + i*actual_width
               and closed == opened+actual_width-1
               and trades >= 0
               and all(v.is_finite() and v >= 0 for v in auxiliary),
               "NATIVE_ZIP_TIMESTAMP_OR_MARKET_FIELDS")
        bar = make_bar(spec,opened,closed,row[1:6],receipt_ms=None)
        bars.append(bar)
        origin.append({
            "source_format":"BINANCE_KLINES_NATIVE_12",
            "original_zip_sha256":meta["archive_sha256"],
            "original_csv_member_sha256":meta["member_sha256"],
            "original_checksum_file_sha256":meta["checksum_file_sha256"],
            "native_csv_line":i+1,
            "source_close_ms":closed,
            "source_publish_ms":None,
            "historical_known_at_ms":None,
            "historical_receipt_ms":None,
            "native_trades":trades,
        })
    return bars, origin
