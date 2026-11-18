"""
Tests for Stage 2: schema, identity keys, safe_filename, validate_meta.
"""
import hashlib
import pytest

from tools.raw_vault_offline.schema import (
    content_key,
    logical_identity_key,
    safe_filename,
    validate_meta,
    RawObjectMeta,
    TrustStatus,
    EvidenceClass,
    CoverageStatus,
    SourceFormat,
    SCHEMA_VERSION,
    ChecksumMismatch,
    MalformedIdentity,
    TraversalAttempt,
    UnsafeArchivePath,
)
from tools.raw_vault_offline.tests._helpers import make_meta


# ── content_key ───────────────────────────────────────────────────────────────

def test_content_key_is_sha256():
    data = b"hello world"
    expected = hashlib.sha256(data).hexdigest()
    assert content_key(data) == expected


def test_content_key_deterministic():
    data = b"\x00\x01\x02"
    assert content_key(data) == content_key(data)


def test_content_key_empty():
    assert len(content_key(b"")) == 64


# ── logical_identity_key ──────────────────────────────────────────────────────

def test_logical_identity_key_deterministic():
    lid = logical_identity_key(
        vendor="binance", instrument="BTCUSDT", market="spot", interval="15m",
        coverage_start_utc="2024-01-01T00:00:00Z",
        coverage_end_utc="2024-01-02T00:00:00Z",
        source_format="csv_zip", format_version="v1",
    )
    lid2 = logical_identity_key(
        vendor="binance", instrument="BTCUSDT", market="spot", interval="15m",
        coverage_start_utc="2024-01-01T00:00:00Z",
        coverage_end_utc="2024-01-02T00:00:00Z",
        source_format="csv_zip", format_version="v1",
    )
    assert lid == lid2


def test_logical_identity_key_differs_on_interval():
    kwargs = dict(
        vendor="binance", instrument="BTCUSDT", market="spot",
        coverage_start_utc="2024-01-01T00:00:00Z",
        coverage_end_utc="2024-01-02T00:00:00Z",
        source_format="csv_zip", format_version="v1",
    )
    lid_15m = logical_identity_key(interval="15m", **kwargs)
    lid_1h  = logical_identity_key(interval="1h",  **kwargs)
    assert lid_15m != lid_1h


def test_logical_identity_key_is_hex64():
    lid = logical_identity_key(
        vendor="x", instrument="y", market="z", interval="1m",
        coverage_start_utc="a", coverage_end_utc="b",
        source_format="csv_zip", format_version="v1",
    )
    assert len(lid) == 64
    int(lid, 16)


# ── safe_filename ─────────────────────────────────────────────────────────────

def test_safe_filename_valid():
    assert safe_filename("BTCUSDT-15m-2024-01-01.csv.zip") == "BTCUSDT-15m-2024-01-01.csv.zip"


def test_safe_filename_rejects_traversal():
    with pytest.raises(TraversalAttempt):
        safe_filename("../evil.txt")


def test_safe_filename_rejects_absolute():
    with pytest.raises(TraversalAttempt):
        safe_filename("/etc/passwd")


def test_safe_filename_rejects_null_byte():
    with pytest.raises((UnsafeArchivePath, MalformedIdentity, ValueError)):
        safe_filename("file\x00name.csv")


def test_safe_filename_rejects_empty():
    with pytest.raises((MalformedIdentity, ValueError, UnsafeArchivePath)):
        safe_filename("")


# ── RawObjectMeta and validate_meta ──────────────────────────────────────────

def test_validate_meta_valid():
    raw = b"fixture data"
    meta = make_meta(raw)
    validate_meta(meta)   # must not raise


def test_validate_meta_blank_vendor():
    raw = b"fixture data"
    meta = make_meta(raw)
    # rebuild with blank vendor
    d = meta.to_dict()
    d["vendor"] = ""
    bad = RawObjectMeta(**d)
    with pytest.raises(MalformedIdentity):
        validate_meta(bad)


def test_validate_meta_blank_instrument():
    raw = b"fixture data"
    meta = make_meta(raw)
    d = meta.to_dict()
    d["instrument"] = ""
    bad = RawObjectMeta(**d)
    with pytest.raises(MalformedIdentity):
        validate_meta(bad)


def test_validate_meta_zero_byte_length():
    raw = b"fixture data"
    meta = make_meta(raw)
    d = meta.to_dict()
    d["byte_length"] = 0
    bad = RawObjectMeta(**d)
    with pytest.raises(MalformedIdentity):
        validate_meta(bad)


def test_validate_meta_negative_correction_generation():
    raw = b"fixture data"
    meta = make_meta(raw)
    d = meta.to_dict()
    d["correction_generation"] = -1
    bad = RawObjectMeta(**d)
    with pytest.raises(MalformedIdentity):
        validate_meta(bad)


def test_validate_meta_correction_needs_parent():
    raw = b"fixture data"
    meta = make_meta(raw)
    d = meta.to_dict()
    d["correction_generation"] = 1
    d["parent_content_sha256"] = ""
    bad = RawObjectMeta(**d)
    with pytest.raises(MalformedIdentity):
        validate_meta(bad)


def test_meta_to_dict_roundtrip():
    raw = b"fixture data"
    meta = make_meta(raw)
    d = meta.to_dict()
    assert d["vendor"] == "test"
    assert d["schema_version"] == SCHEMA_VERSION
