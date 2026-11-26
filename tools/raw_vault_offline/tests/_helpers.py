"""Shared test helper to construct a valid RawObjectMeta from actual schema fields."""
import hashlib
from tools.raw_vault_offline.schema import (
    SCHEMA_VERSION,
    RawObjectMeta,
    TrustStatus,
    EvidenceClass,
    CoverageStatus,
    SourceFormat,
    logical_identity_key,
)


def make_meta(
    raw: bytes,
    *,
    instrument: str = "BTCUSDT",
    interval: str = "15m",
    coverage_start: str = "2024-01-01T00:00:00Z",
    coverage_end: str = "2024-01-02T00:00:00Z",
    correction_generation: int = 0,
    parent: str = "",
    vendor: str = "test",
    market: str = "spot",
) -> RawObjectMeta:
    sha = hashlib.sha256(raw).hexdigest()
    lid = logical_identity_key(
        vendor=vendor,
        instrument=instrument,
        market=market,
        interval=interval,
        coverage_start_utc=coverage_start,
        coverage_end_utc=coverage_end,
        source_format="ZIP_CSV",
        format_version="v1",
    )
    return RawObjectMeta(
        schema_version=SCHEMA_VERSION,
        content_sha256=sha,
        byte_length=len(raw),
        vendor=vendor,
        instrument=instrument,
        market=market,
        interval=interval,
        source_format=SourceFormat.ZIP_CSV,
        format_version="v1",
        coverage_start_utc=coverage_start,
        coverage_end_utc=coverage_end,
        coverage_status=CoverageStatus.FULL,
        evidence_class=EvidenceClass.FIXTURE_SYNTHETIC,
        trust_status=TrustStatus.VERIFIED,
        original_filename=f"{instrument}-{interval}.csv.zip",
        capture_provenance="UNKNOWN",
        archive_member_path="",
        archive_member_sha256="",
        logical_identity_key=lid,
        admitted_at_utc="2024-01-01T12:00:00Z",
        correction_generation=correction_generation,
        parent_content_sha256=parent,
    )
