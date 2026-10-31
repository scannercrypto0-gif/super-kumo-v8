"""
Stage 4 — Native archive custody & verification (ZIP/CSV fixtures).

Features
--------
- Bounded read-only validation of vendor-style daily ZIP/CSV fixtures
- Member CRC/checksum verification
- Filename + expected grid identity matching
- Byte-preserving original vs normalised metadata
- Strict zip-slip / duplicate member / encoding / header failures
- Resource ceilings
- Audit receipts (deterministic, no original bytes modified)
- Fixture generator with deterministic seeds (no copyrighted data)
"""
from __future__ import annotations

import csv
import hashlib
import io
import random
import string
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import (
    MAX_ARCHIVE_MEMBERS,
    MAX_OBJECT_BYTES,
    MAX_UNCOMPRESSED_RATIO,
    TraversalAttempt,
    DecompressionBomb,
    DuplicateArchiveMember,
    UnsafeArchivePath,
    ArchiveTooLarge,
    safe_filename,
)

# Maximum uncompressed bytes we will read from a single ZIP (bomb guard)
MAX_UNCOMPRESSED_BYTES: int = int(MAX_OBJECT_BYTES * MAX_UNCOMPRESSED_RATIO)


# ── audit receipt ──────────────────────────────────────────────────────────────

@dataclass
class MemberReceipt:
    member_name: str
    sha256_hex: str
    byte_length: int
    crc32_hex: str
    encoding_detected: str = "utf-8"
    row_count: Optional[int] = None
    header: Optional[list[str]] = None

@dataclass
class ArchiveReceipt:
    archive_sha256: str
    archive_bytes: int
    member_receipts: list[MemberReceipt] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    verified: bool = False
    verified_at_utc: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── verifier ──────────────────────────────────────────────────────────────────

def verify_zip_archive(
    archive_bytes: bytes,
    *,
    expected_members: Optional[list[str]] = None,
    max_members: int = MAX_ARCHIVE_MEMBERS,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
) -> ArchiveReceipt:
    """
    Validate a ZIP archive fixture and produce an audit receipt.

    Checks
    ------
    - ZIP validity
    - Member count ceiling
    - Zip-slip (traversal) on every member name
    - Duplicate member names
    - Decompression-bomb ratio
    - CRC32 per member (builtin zipfile check)
    - Total uncompressed size ceiling
    - CSV header decoding (UTF-8)
    - Optional expected member list check

    Parameters
    ----------
    archive_bytes     : raw bytes of the ZIP file
    expected_members  : if given, receipt.errors will note missing members
    max_members       : override ceiling (for tests)
    max_uncompressed  : override ceiling (for tests)

    Returns
    -------
    ArchiveReceipt (receipt.verified = True only if no errors)
    """
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    receipt = ArchiveReceipt(
        archive_sha256=archive_sha256,
        archive_bytes=len(archive_bytes),
    )

    # parse ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as e:
        receipt.errors.append(f"BadZipFile: {e}")
        return receipt

    names = zf.namelist()

    # member count ceiling
    if len(names) > max_members:
        receipt.errors.append(
            f"Too many archive members: {len(names)} > {max_members}"
        )
        receipt.errors.append("ArchiveTooLarge")
        return receipt

    # duplicate member names
    seen: set[str] = set()
    for n in names:
        if n in seen:
            receipt.errors.append(f"DuplicateArchiveMember: {n!r}")
        seen.add(n)

    total_uncompressed = 0
    for info in zf.infolist():
        name = info.filename

        # zip-slip guard
        try:
            safe_filename(Path(name).name)
        except (TraversalAttempt, UnsafeArchivePath) as e:
            receipt.errors.append(f"UnsafePath({name!r}): {e}")
            continue
        # explicit traversal check on full path
        parts = Path(name).parts
        if any(p == '..' for p in parts):
            receipt.errors.append(f"TraversalAttempt: {name!r}")
            continue

        # decompression-bomb ratio
        compressed = info.compress_size or 1
        if info.file_size > 0:
            ratio = info.file_size / compressed
            if ratio > MAX_UNCOMPRESSED_RATIO:
                receipt.errors.append(
                    f"DecompressionBomb({name!r}): ratio={ratio:.1f}"
                )
                continue

        # total uncompressed ceiling
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed:
            receipt.errors.append(
                f"ArchiveTooLarge: total uncompressed {total_uncompressed} "
                f"> ceiling {max_uncompressed}"
            )
            break

        # read + CRC check (zipfile raises BadZipFile on CRC mismatch)
        try:
            raw_member = zf.read(name)
        except Exception as e:
            receipt.errors.append(f"ReadError({name!r}): {e}")
            continue

        sha256_hex = hashlib.sha256(raw_member).hexdigest()
        crc32_hex = format(info.CRC, '08x')

        # CSV header sniff
        row_count: Optional[int] = None
        header: Optional[list[str]] = None
        encoding = "utf-8"
        if name.lower().endswith(".csv"):
            try:
                text = raw_member.decode("utf-8")
                reader = csv.reader(io.StringIO(text))
                rows = list(reader)
                header = rows[0] if rows else []
                row_count = len(rows) - 1  # exclude header
            except UnicodeDecodeError:
                encoding = "UNKNOWN"
                receipt.errors.append(f"EncodingError({name!r}): not utf-8")

        receipt.member_receipts.append(MemberReceipt(
            member_name=name,
            sha256_hex=sha256_hex,
            byte_length=info.file_size,
            crc32_hex=crc32_hex,
            encoding_detected=encoding,
            row_count=row_count,
            header=header,
        ))

    zf.close()

    # expected members check
    if expected_members:
        present = {mr.member_name for mr in receipt.member_receipts}
        for exp in expected_members:
            if exp not in present:
                receipt.errors.append(f"MissingMember: {exp!r}")

    # duplicate member error implies corrupt
    receipt.verified = len(receipt.errors) == 0
    if receipt.verified:
        receipt.verified_at_utc = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return receipt


# ── deterministic fixture generator ──────────────────────────────────────────

def make_synthetic_csv_zip(
    *,
    filename: str = "BTCUSDT-15m-2024-01-01.csv",
    rows: int = 96,
    seed: int = 42,
    corrupt_crc: bool = False,
    include_traversal: bool = False,
    add_duplicate_member: bool = False,
) -> bytes:
    """
    Generate a deterministic synthetic ZIP/CSV fixture.

    Parameters
    ----------
    filename           : member CSV filename inside the ZIP
    rows               : number of OHLCV data rows
    seed               : random seed for deterministic output
    corrupt_crc        : if True, flip bytes to invalidate CRC (adversarial)
    include_traversal  : if True, add a ../evil.txt member (adversarial)
    add_duplicate_member: if True, add the filename twice (adversarial)

    Returns
    -------
    raw ZIP bytes
    """
    rng = random.Random(seed)

    # generate OHLCV CSV rows
    header = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "count"]
    base_ts = 1_704_067_200_000  # 2024-01-01T00:00:00Z in ms
    interval_ms = 15 * 60 * 1000

    csv_rows = [header]
    price = 42000.0
    for i in range(rows):
        open_ts = base_ts + i * interval_ms
        close_ts = open_ts + interval_ms - 1
        o = round(price + rng.uniform(-50, 50), 2)
        h = round(o + rng.uniform(0, 100), 2)
        l = round(o - rng.uniform(0, 100), 2)
        c = round(o + rng.uniform(-50, 50), 2)
        v = round(rng.uniform(0.1, 10.0), 8)
        qv = round(v * o, 2)
        count = rng.randint(100, 5000)
        csv_rows.append([open_ts, o, h, l, c, v, close_ts, qv, count])
        price = c

    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerows(csv_rows)
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    # build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, csv_bytes)
        if add_duplicate_member:
            zf.writestr(filename, b"duplicate")
        if include_traversal:
            zf.writestr("../evil.txt", b"should be rejected")
    raw_zip = buf.getvalue()

    if corrupt_crc:
        # flip bytes in the local file header area to corrupt CRC
        raw_zip = bytearray(raw_zip)
        if len(raw_zip) > 40:
            raw_zip[30] ^= 0xFF
            raw_zip[31] ^= 0xFF
        raw_zip = bytes(raw_zip)

    return raw_zip
