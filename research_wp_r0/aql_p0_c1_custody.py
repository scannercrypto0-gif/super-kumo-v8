"""Core P0 fixed native Binance 15m source-byte custody; DEV NON_PIT only."""
from __future__ import annotations
import csv
import io
import json
import re
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256

OUTER_SHA = "f4e0b3680dd56c9fbe680be2473b8de29fc1d8d7e22657973c85945d2bf99f97"
MANIFEST_SHA = "f731bc19c1d4bb0dfa79198c6739a4dbd356e02904086d4df2a136773bd25456"
NORMALIZED_SHA = "a881cc99e80697f2da57784b5bea91a7f339c6c391d4d53cc0222842168af0f0"
NORM_NAME = "BTCUSDT-15m-2024-01-01_to_2024-01-08-exclusive.normalized.json"
BASE = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/15m/"
START_MS = 1704067200000
INTERVAL_MS = 900000


class SourceCustodyError(ValueError):
    """Frozen native raw source was not admitted."""


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def verify_native_bundle(outer: bytes, manifest_bytes: bytes, normalized: bytes) -> str:
    """Rehash and parse exact owner originals, 7 checksums, and every normalized bar.

    Returns verified outer bundle SHA; publisher checksum != historical PIT receipt.
    """
    if not all(isinstance(x, bytes) and bool(x) for x in (outer, manifest_bytes, normalized)):
        raise SourceCustodyError("SOURCE_BYTES_REQUIRED")
    if _sha(outer) != OUTER_SHA:
        raise SourceCustodyError("OUTER_ZIP_SHA256_MISMATCH")
    if _sha(manifest_bytes) != MANIFEST_SHA:
        raise SourceCustodyError("MANIFEST_SHA256_MISMATCH")
    if _sha(normalized) != NORMALIZED_SHA:
        raise SourceCustodyError("NORMALIZED_SHA256_MISMATCH")
    try:
        m = json.loads(manifest_bytes)
        checks = {
            "schema": "aql-p0-native-15m-source-evidence-v1",
            "exchange": "BINANCE", "market": "SPOT", "symbol": "BTCUSDT",
            "interval_ms": INTERVAL_MS, "expected_bars": 672, "observed_bars": 672,
            "gap_count": 0, "duplicate_count": 0,
            "window_start_utc": "2024-01-01T00:00:00Z",
            "window_end_exclusive_utc": "2024-01-08T00:00:00Z",
            "availability": "RETROSPECTIVE_NON_PIT",
            "historical_known_at_ms": None, "historical_receipt_ms": None,
            "correction_history": "UNKNOWN_NOT_ATTESTED",
            "normalized_file": NORM_NAME, "normalized_sha256": NORMALIZED_SHA,
        }
        if not isinstance(m, dict) or any(m.get(k) != v for k, v in checks.items()):
            raise SourceCustodyError("MANIFEST_IDENTITY_MISMATCH")
        if not isinstance(m.get("sources"), list) or len(m["sources"]) != 7:
            raise SourceCustodyError("MANIFEST_SOURCE_COUNT_INVALID")
        if not isinstance(json.loads(normalized), list):
            raise SourceCustodyError("NORMALIZED_ROOT_INVALID")
        with zipfile.ZipFile(io.BytesIO(outer)) as evidence:
            if evidence.testzip() is not None:
                raise SourceCustodyError("OUTER_ZIP_CRC_INVALID")
            names = evidence.namelist()
            if len(names) != 15 or len(set(names)) != 15:
                raise SourceCustodyError("OUTER_ZIP_INVENTORY_INVALID")
            expected = {NORM_NAME}
            recovered = []
            for di, src in enumerate(m["sources"]):
                day = (date(2024, 1, 1) + timedelta(days=di)).isoformat()
                fn = "BTCUSDT-15m-" + day + ".zip"
                cn = fn + ".CHECKSUM"
                if (not isinstance(src, dict) or src.get("date_utc") != day
                    or src.get("filename") != fn or src.get("publisher_checksum_file") != cn
                    or src.get("url") != BASE + fn or src.get("csv_rows") != 96):
                    raise SourceCustodyError("SOURCE_MANIFEST_INVENTORY_MISMATCH")
                expected.update((fn, cn))
                daily_bytes = evidence.read(fn)
                checksum_text = evidence.read(cn)
                sh = _sha(daily_bytes)
                if (sh != src.get("zip_sha256")
                    or sh != src.get("publisher_checksum_sha256")
                    or len(daily_bytes) != src.get("zip_bytes")):
                    raise SourceCustodyError("DAILY_SOURCE_SHA256_MISMATCH")
                chk_match = re.fullmatch(
                    rb"\s*([0-9a-fA-F]{64})\s+" + re.escape(fn.encode("ascii")) + rb"\s*",
                    checksum_text,
                )
                if not chk_match or chk_match.group(1).decode("ascii").lower() != sh:
                    raise SourceCustodyError("PUBLISHER_CHECKSUM_MISMATCH")
                with zipfile.ZipFile(io.BytesIO(daily_bytes)) as dayzip:
                    csv_name = fn[:-4] + ".csv"
                    if dayzip.testzip() is not None or dayzip.namelist() != [csv_name]:
                        raise SourceCustodyError("DAILY_CSV_INVENTORY_MISMATCH")
                    rows = list(csv.reader(io.StringIO(dayzip.read(csv_name).decode("utf-8-sig"))))
                if len(rows) != 96:
                    raise SourceCustodyError("DAILY_BAR_COUNT_MISMATCH")
                for i, row in enumerate(rows):
                    if len(row) < 7:
                        raise SourceCustodyError("DAILY_CSV_TRUNCATED")
                    try:
                        op, cl = int(row[0]), int(row[6])
                        o, h, l, c, v = (Decimal(row[k]) for k in (1,2,3,4,5))
                    except (ValueError, InvalidOperation, TypeError) as exc:
                        raise SourceCustodyError("DAILY_CSV_PARSE_INVALID") from exc
                    wanted = START_MS + (di * 96 + i) * INTERVAL_MS
                    if op != wanted or cl != op + INTERVAL_MS - 1:
                        raise SourceCustodyError("DAILY_CSV_TIME_GRID_INVALID")
                    if (not all(x.is_finite() for x in (o,h,l,c,v)) or
                        min(o,h,l,c) <= 0 or v < 0 or h < max(o,c,l) or l > min(o,c,h)):
                        raise SourceCustodyError("DAILY_CSV_OHLCV_INVALID")
                    recovered.append([op,str(o),str(h),str(l),str(c),str(v),cl])
            if set(names) != expected:
                raise SourceCustodyError("OUTER_ZIP_MEMBER_MISMATCH")
            if evidence.read(NORM_NAME) != normalized:
                raise SourceCustodyError("NORMALIZED_OUTER_BYTE_MISMATCH")
            if recovered != json.loads(normalized):
                raise SourceCustodyError("RAW_TO_NORMALIZED_MISMATCH")
    except SourceCustodyError:
        raise
    except (KeyError, ValueError, UnicodeDecodeError, zipfile.BadZipFile, TypeError, OSError) as exc:
        raise SourceCustodyError("SOURCE_PACKAGE_INVALID") from exc
    return OUTER_SHA
