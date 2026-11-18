"""
Tests for Stage 7: derived_view — provenance, determinism, gap/unknown markers.
"""
import pytest

from tools.raw_vault_offline.derived_view import (
    derive_view,
    DERIVED_VIEW_POLICY_VERSION,
)

BASE_MS = 1_704_067_200_000
STEP_15M = 900_000

_CSV_HEADER = "open_time,open,high,low,close,volume,close_time,quote_volume,count\n"


def _make_csv(rows: int, *, base_ms: int = BASE_MS, step_ms: int = STEP_15M) -> bytes:
    lines = [_CSV_HEADER.rstrip()]
    for i in range(rows):
        open_ms = base_ms + i * step_ms
        close_ms = open_ms + step_ms - 1
        lines.append(f"{open_ms},42000.0,42100.0,41900.0,42050.0,1.5,{close_ms},63075.0,500")
    return "\n".join(lines).encode("utf-8")


SHA = "a" * 64


# ── happy path ────────────────────────────────────────────────────────────────

def test_derive_basic():
    raw = _make_csv(4)
    rows, manifest = derive_view(
        raw,
        source_content_sha256=SHA,
        instrument="BTCUSDT",
        interval="15m",
    )
    assert len(rows) == 4
    assert manifest.row_count == 4
    assert manifest.policy_version == DERIVED_VIEW_POLICY_VERSION
    assert manifest.output_digest != ""


def test_derive_provenance_per_row():
    raw = _make_csv(3)
    rows, _ = derive_view(
        raw,
        source_content_sha256=SHA,
        instrument="BTCUSDT",
        interval="15m",
    )
    for row in rows:
        assert row.source_content_sha256 == SHA
        assert row.normalization_policy == DERIVED_VIEW_POLICY_VERSION
        assert row.gap_marker is False
        assert row.unknown_marker is False


def test_derive_open_time_preserved():
    raw = _make_csv(2)
    rows, _ = derive_view(
        raw,
        source_content_sha256=SHA,
        instrument="BTCUSDT",
        interval="15m",
    )
    assert rows[0].open_time_utc_ms == BASE_MS
    assert rows[1].open_time_utc_ms == BASE_MS + STEP_15M


# ── determinism ───────────────────────────────────────────────────────────────

def test_derive_deterministic():
    raw = _make_csv(4)
    _, m1 = derive_view(raw, source_content_sha256=SHA,
                        instrument="BTCUSDT", interval="15m")
    _, m2 = derive_view(raw, source_content_sha256=SHA,
                        instrument="BTCUSDT", interval="15m")
    assert m1.output_digest == m2.output_digest


def test_derive_different_policy_different_digest():
    raw = _make_csv(4)
    _, m1 = derive_view(raw, source_content_sha256=SHA,
                        instrument="BTCUSDT", interval="15m",
                        policy_version="canonical_ohlcv.v1")
    _, m2 = derive_view(raw, source_content_sha256=SHA,
                        instrument="BTCUSDT", interval="15m",
                        policy_version="canonical_ohlcv.v2_hypothetical")
    assert m1.output_digest != m2.output_digest


# ── available_at_utc passthrough ──────────────────────────────────────────────

def test_derive_available_at_unknown_by_default():
    raw = _make_csv(2)
    rows, _ = derive_view(raw, source_content_sha256=SHA,
                          instrument="BTCUSDT", interval="15m")
    for row in rows:
        assert row.available_at_utc == "UNKNOWN"


def test_derive_available_at_declared():
    raw = _make_csv(2)
    rows, _ = derive_view(raw, source_content_sha256=SHA,
                          instrument="BTCUSDT", interval="15m",
                          available_at_utc="2024-01-02T00:00:00Z")
    for row in rows:
        assert row.available_at_utc == "2024-01-02T00:00:00Z"


# ── unparseable CSV → parse error manifest ────────────────────────────────────

def test_derive_bad_csv():
    rows, manifest = derive_view(
        b"not,csv,data\nbut,invalid,structure",
        source_content_sha256=SHA,
        instrument="BTCUSDT",
        interval="15m",
    )
    assert rows == []
    assert manifest.row_count == 0
    assert any("PARSE_ERROR" in n for n in manifest.notes)


def test_derive_empty_bytes():
    rows, manifest = derive_view(
        b"",
        source_content_sha256=SHA,
        instrument="BTCUSDT",
        interval="15m",
    )
    assert rows == []
    assert manifest.row_count == 0


# ── correction generation passthrough ────────────────────────────────────────

def test_derive_correction_generation():
    raw = _make_csv(2)
    rows, manifest = derive_view(
        raw,
        source_content_sha256=SHA,
        source_correction_generation=2,
        instrument="BTCUSDT",
        interval="15m",
    )
    assert manifest.source_correction_generation == 2
    for row in rows:
        assert row.source_correction_generation == 2


# ── view_generation ───────────────────────────────────────────────────────────

def test_derive_view_generation():
    raw = _make_csv(2)
    _, manifest = derive_view(raw, source_content_sha256=SHA,
                              instrument="BTCUSDT", interval="15m",
                              view_generation=3)
    assert manifest.view_generation == 3
