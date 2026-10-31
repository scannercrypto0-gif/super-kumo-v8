"""
Stage 2 — RawObject metadata contract (versioned v1).

Threat model enforced here:
  - Safe path/filename normalisation (no traversal)
  - Decompression-bomb limits
  - Content-size quotas
  - Duplicate/conflict rules
  - Failure taxonomy
  - Trust status
  - UNKNOWN provenance explicitly allowed, never fabricated

Original RAW bytes are NEVER silently overwritten.
PIT capture status is declared; never invented.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import PurePosixPath
from typing import Optional

# ── schema version ──────────────────────────────────────────────────────────
SCHEMA_VERSION = "raw_object.v1"

# ── resource ceilings ────────────────────────────────────────────────────────
MAX_OBJECT_BYTES: int = 512 * 1024 * 1024      # 512 MiB per object
MAX_UNCOMPRESSED_RATIO: float = 100.0           # decompression bomb guard
MAX_ARCHIVE_MEMBERS: int = 10_000
MAX_TOTAL_VAULT_BYTES: int = 50 * 1024 ** 3    # 50 GiB soft cap (fixture mode)

# ── enumerations ─────────────────────────────────────────────────────────────

class TrustStatus(str, Enum):
    """Declared trust level of admitted bytes."""
    VERIFIED = "VERIFIED"          # checksum matched vendor-declared hash
    UNVERIFIED = "UNVERIFIED"      # bytes accepted but hash not cross-checked
    UNKNOWN = "UNKNOWN"            # provenance information unavailable


class EvidenceClass(str, Enum):
    """How the bytes were originally retrieved."""
    DIRECT_DOWNLOAD = "DIRECT_DOWNLOAD"
    VENDOR_ARCHIVE = "VENDOR_ARCHIVE"
    MANUAL_EXPORT = "MANUAL_EXPORT"
    FIXTURE_SYNTHETIC = "FIXTURE_SYNTHETIC"   # test fixtures only
    UNKNOWN = "UNKNOWN"


class CoverageStatus(str, Enum):
    """Coverage declaration for the declared time window."""
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class SourceFormat(str, Enum):
    ZIP_CSV = "ZIP_CSV"
    RAW_CSV = "RAW_CSV"
    PARQUET = "PARQUET"
    JSON_LINES = "JSON_LINES"
    UNKNOWN = "UNKNOWN"


# ── failure taxonomy ──────────────────────────────────────────────────────────

class VaultError(Exception):
    """Base for all raw-vault errors."""

class ChecksumMismatch(VaultError):
    """SHA-256 of received bytes does not match declared digest."""

class IdentityConflict(VaultError):
    """Same logical identity exists with DIFFERENT bytes (not a duplicate)."""

class TraversalAttempt(VaultError):
    """Archive member path attempts directory traversal."""

class DecompressionBomb(VaultError):
    """Uncompressed size exceeds MAX_UNCOMPRESSED_RATIO × compressed size."""

class OversizedObject(VaultError):
    """Object byte-length exceeds MAX_OBJECT_BYTES."""

class UnknownProvenanceError(VaultError):
    """Caller attempted to assert PIT capture without evidence."""

class MalformedIdentity(VaultError):
    """Required identity fields are missing or violate format rules."""

class DuplicateArchiveMember(VaultError):
    """Archive contains two members with the same normalised path."""

class UnsafeArchivePath(VaultError):
    """Archive member path contains unsafe characters."""

class ArchiveTooLarge(VaultError):
    """Archive member count or total size exceeds ceiling."""


# ── safe path normalisation ───────────────────────────────────────────────────

_SAFE_FILENAME_RE = re.compile(r'^[\w\.\-]+$', re.ASCII)

def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)

def safe_filename(name: str) -> str:
    """Return NFC-normalised filename; raise UnsafeArchivePath if dangerous."""
    name = _nfc(name.strip())
    # reject null bytes
    if '\x00' in name:
        raise UnsafeArchivePath(f"Null byte in filename: {name!r}")
    # reject traversal components
    parts = PurePosixPath(name).parts
    if any(p in ('..', '.', '/') for p in parts):
        raise TraversalAttempt(f"Traversal component in: {name!r}")
    # reject absolute paths
    if name.startswith('/') or (len(name) >= 2 and name[1] == ':'):
        raise TraversalAttempt(f"Absolute path rejected: {name!r}")
    if not _SAFE_FILENAME_RE.match(name.replace('/', '_').replace('\\', '_')):
        raise UnsafeArchivePath(f"Unsafe characters in filename: {name!r}")
    return name


# ── independent identity key vs content key ───────────────────────────────────

def content_key(raw_bytes: bytes) -> str:
    """SHA-256 hex of raw bytes — content-addressed identity."""
    return hashlib.sha256(raw_bytes).hexdigest()

def _canonical_identity(
    vendor: str,
    instrument: str,
    market: str,
    interval: str,
    coverage_start_utc: str,
    coverage_end_utc: str,
    source_format: str,
    format_version: str,
) -> str:
    """Deterministic JSON string for the *logical* identity key (independent of bytes)."""
    obj = dict(
        vendor=vendor,
        instrument=instrument,
        market=market,
        interval=interval,
        coverage_start_utc=coverage_start_utc,
        coverage_end_utc=coverage_end_utc,
        source_format=source_format,
        format_version=format_version,
    )
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def logical_identity_key(
    vendor: str,
    instrument: str,
    market: str,
    interval: str,
    coverage_start_utc: str,
    coverage_end_utc: str,
    source_format: str,
    format_version: str,
) -> str:
    """SHA-256 of the canonical logical identity JSON — used to detect conflicts."""
    s = _canonical_identity(
        vendor, instrument, market, interval,
        coverage_start_utc, coverage_end_utc, source_format, format_version,
    )
    return hashlib.sha256(s.encode()).hexdigest()


# ── RawObject dataclass ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class RawObjectMeta:
    """
    Immutable metadata envelope for one admitted RAW object.

    Fields
    ------
    schema_version      : always SCHEMA_VERSION
    content_sha256      : SHA-256 hex of the ORIGINAL source bytes
    byte_length         : exact byte count of original bytes
    vendor              : data vendor name (e.g. "BINANCE_SPOT")
    instrument          : trading instrument (e.g. "BTCUSDT")
    market              : market type (e.g. "SPOT", "PERP")
    interval            : candle interval (e.g. "15m", "1d")
    source_format       : SourceFormat enum value
    format_version      : vendor format version string (e.g. "v1")
    coverage_start_utc  : ISO-8601 UTC, inclusive, half-open start [
    coverage_end_utc    : ISO-8601 UTC, exclusive, half-open end )
    coverage_status     : CoverageStatus enum
    evidence_class      : EvidenceClass enum
    trust_status        : TrustStatus enum
    original_filename   : original filename (may be "UNKNOWN")
    capture_provenance  : free text or "UNKNOWN"
    archive_member_path : path inside archive, or "" if not archived
    archive_member_sha256: SHA-256 of archive member, or "" if not archived
    logical_identity_key: SHA-256 of logical identity fields (conflict detection)
    admitted_at_utc     : ISO-8601 UTC admission timestamp
    correction_generation: int ≥ 0; 0 = original, N > 0 = correction
    parent_content_sha256: content_sha256 of the generation-0 or prior gen object
    """
    schema_version: str
    content_sha256: str
    byte_length: int
    vendor: str
    instrument: str
    market: str
    interval: str
    source_format: str
    format_version: str
    coverage_start_utc: str
    coverage_end_utc: str
    coverage_status: str
    evidence_class: str
    trust_status: str
    original_filename: str
    capture_provenance: str
    archive_member_path: str
    archive_member_sha256: str
    logical_identity_key: str
    admitted_at_utc: str
    correction_generation: int = 0
    parent_content_sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RawObjectMeta":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── validation ────────────────────────────────────────────────────────────────

_ISO8601_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$'
)

def validate_meta(m: RawObjectMeta) -> None:
    """Raise MalformedIdentity or another VaultError if meta is invalid."""
    if m.schema_version != SCHEMA_VERSION:
        raise MalformedIdentity(f"Unknown schema_version: {m.schema_version!r}")
    if not m.vendor.strip():
        raise MalformedIdentity("vendor must not be blank")
    if not m.instrument.strip():
        raise MalformedIdentity("instrument must not be blank")
    if not m.market.strip():
        raise MalformedIdentity("market must not be blank")
    if not m.interval.strip():
        raise MalformedIdentity("interval must not be blank")
    if not _ISO8601_RE.match(m.coverage_start_utc):
        raise MalformedIdentity(f"coverage_start_utc not ISO-8601 UTC: {m.coverage_start_utc!r}")
    if not _ISO8601_RE.match(m.coverage_end_utc):
        raise MalformedIdentity(f"coverage_end_utc not ISO-8601 UTC: {m.coverage_end_utc!r}")
    if m.byte_length <= 0:
        raise MalformedIdentity(f"byte_length must be > 0, got {m.byte_length}")
    if m.byte_length > MAX_OBJECT_BYTES:
        raise OversizedObject(f"Object {m.byte_length} bytes > MAX {MAX_OBJECT_BYTES}")
    if not re.fullmatch(r'[0-9a-f]{64}', m.content_sha256):
        raise MalformedIdentity(f"content_sha256 not 64-hex: {m.content_sha256!r}")
    if m.correction_generation < 0:
        raise MalformedIdentity(f"correction_generation must be ≥ 0")
    if m.correction_generation > 0 and not m.parent_content_sha256:
        raise MalformedIdentity("correction_generation > 0 requires parent_content_sha256")
    # trust check: VERIFIED requires non-UNKNOWN evidence class
    if m.trust_status == TrustStatus.VERIFIED and m.evidence_class == EvidenceClass.UNKNOWN:
        raise MalformedIdentity("VERIFIED trust requires non-UNKNOWN evidence_class")
