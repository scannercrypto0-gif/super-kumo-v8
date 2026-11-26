"""Read-only external RAW archive + receipt acquisition gate for Factory research.

This is not a downloader, issuer, timestamp authority, or operational proof.
Missing independently retained original artifacts must be reported BLOCKED.
No arbitrary self-hashed receipt or generated clock can become a trust root.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from typing import Callable

from .aql_w1_opportunity_outcomes import EvidenceError


SHA = re.compile(r"^[0-9a-f]{64}$")
BAR_MS = 900000


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def inspect_original_raw_archive(
    archive_bytes: bytes | None, *,
    source_id: str, expected_archive_sha256: str,
    expected_member: str, expected_first_open_ms: int,
    expected_15m_bars: int,
    issuer_receipt_bytes: bytes | None = None,
    independently_retained_manifest_bytes: bytes | None = None,
    expected_manifest_sha256: str | None = None,
    verify_external_custody: Callable | None = None,
    verify_independent_clock: Callable | None = None,
):
    """Classify exact RAW ZIP integrity separately from independent PIT/custody.

    Minimal immutable refs must be passed by an operator, not inferred from
    a ZIP's contents or a local clock. Raw ZIP is parsed read-only. The
    original file is not rewritten, and no F1 direction is inferred.
    """
    result = dict(
        schema="AQL-FACTORY-RAW-SOURCE-INSPECTION-v1",
        source_id=source_id,
        expected_archive_sha256=expected_archive_sha256,
        observed_archive_sha256=None,
        expected_member=expected_member,
        observed_15m_bars=0,
        expected_15m_bars=expected_15m_bars,
        integrity_status="NOT_VERIFIED",
        external_evidence_status="BLOCKED_EXTERNAL_EVIDENCE",
        independently_anchored=False,
        publication_clock_proven=False,
        external_custody_proven=False,
        research_only=True,
        no_fill_or_pnl_inference=True,
        blockers=[],
    )
    if not source_id or not SHA.fullmatch(str(expected_archive_sha256)):
        raise EvidenceError("unbound RAW original source identity")
    if (type(expected_first_open_ms) is not int or
            expected_first_open_ms < 0 or expected_first_open_ms % BAR_MS != 0 or
            type(expected_15m_bars) is not int or
            expected_15m_bars <= 0 or expected_15m_bars > 288 * 30):
        raise EvidenceError("invalid bounded original 15m time grid")
    if (type(archive_bytes) is not bytes or not archive_bytes):
        result["blockers"].append("ORIGINAL_RAW_ZIP_BYTES_NOT_SUPPLIED")
        return result
    if len(archive_bytes) > 512 * 1024 * 1024:
        raise EvidenceError("RAW ZIP larger than bounded limit")
    result["observed_archive_sha256"] = _sha(archive_bytes)
    if result["observed_archive_sha256"] != expected_archive_sha256:
        result["integrity_status"] = "HASH_MISMATCH"
        result["blockers"].append("RAW_ORIGINAL_BYTES_CHANGED")
        return result
    if (not expected_member or "/" in expected_member or "\\" in expected_member
            or not expected_member.endswith(".csv")):
        raise EvidenceError("invalid original ZIP member identity")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = archive.namelist()
            if (len(names) != 1 or names != [expected_member]
                    or archive.infolist()[0].file_size > 128 * 1024 * 1024):
                raise EvidenceError("original ZIP member mismatch")
            data = archive.read(expected_member)
    except (zipfile.BadZipFile, RuntimeError, ValueError, KeyError) as exc:
        raise EvidenceError("unreadable original RAW ZIP") from exc
    # Binance Vision 15-minute exports have 12 CSV fields, without a header.
    # This checks chronological coverage and high/low sanity; it does not
    # fabricate the original publication time or an external receipt.
    import csv
    from decimal import Decimal
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
        if len(rows) != expected_15m_bars:
            raise EvidenceError("incomplete original 15m bar denominator")
        for i, row in enumerate(rows):
            if len(row) != 12:
                raise EvidenceError("original RAW Binance kline schema mismatch")
            opened = int(row[0])
            if opened != expected_first_open_ms + BAR_MS * i:
                raise EvidenceError("original RAW 15m grid mismatch")
            high, low = Decimal(row[2]), Decimal(row[3])
            if not (high.is_finite() and low.is_finite() and high >= low > 0):
                raise EvidenceError("invalid original market extrema")
            close_time = int(row[6])
            if close_time != opened + BAR_MS - 1:
                raise EvidenceError("original 15m close time mismatch")
    except (UnicodeError, ValueError, IndexError, ArithmeticError) as exc:
        raise EvidenceError("invalid RAW market row") from exc
    result["integrity_status"] = "ORIGINAL_BYTES_HASH_AND_GRID_MATCH"
    result["observed_15m_bars"] = len(rows)
    if not issuer_receipt_bytes:
        result["blockers"].append("ORIGINAL_ISSUER_RECEIPT_NOT_SUPPLIED")
    if not independently_retained_manifest_bytes:
        result["blockers"].append("INDEPENDENT_MANIFEST_BYTES_NOT_SUPPLIED")
    elif not expected_manifest_sha256 or _sha(independently_retained_manifest_bytes) != expected_manifest_sha256:
        result["blockers"].append("INDEPENDENT_MANIFEST_DIGEST_NOT_VERIFIED")
    if not callable(verify_external_custody):
        result["blockers"].append("EXTERNAL_CUSTODIAN_WITNESS_MISSING")
    if not callable(verify_independent_clock):
        result["blockers"].append("ORIGINAL_PUBLISH_CORRECTION_CLOCK_WITNESS_MISSING")
    # Invocation accepts two independently supplied witnesses, never a
    # self-reported flag or receipt digest as sufficient proof.
    if (not result["blockers"] and callable(verify_external_custody)
            and callable(verify_independent_clock)):
        try:
            custody_ok = verify_external_custody(
                archive_bytes, issuer_receipt_bytes,
                independently_retained_manifest_bytes) is True
            clock_ok = verify_independent_clock(
                issuer_receipt_bytes, source_id) is True
            result["external_custody_proven"] = custody_ok
            result["publication_clock_proven"] = clock_ok
            result["independently_anchored"] = custody_ok and clock_ok
        except Exception:
            result["blockers"].append("EXTERNAL_WITNESS_ERROR")
    if not result["independently_anchored"]:
        result["blockers"].append("INDEPENDENT_AUTHORITY_NOT_ESTABLISHED")
    else:
        # Even a true host callback is only valid after separately audited
        # independence of its issuer, protected retention and clock source.
        result["external_evidence_status"] = "HOST_WITNESS_CALLBACK_AFFIRMED_NOT_AUDITED"
    return result
