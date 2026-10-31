"""
Tests for Stage 4: archive_verifier — adversarial ZIP/CSV fixture handling.
"""
import io
import zipfile

import pytest

from tools.raw_vault_offline.archive_verifier import (
    verify_zip_archive,
    make_synthetic_csv_zip,
)


# ── happy path ────────────────────────────────────────────────────────────────

def test_verify_valid_zip():
    raw_zip = make_synthetic_csv_zip(seed=42)
    receipt = verify_zip_archive(raw_zip)
    assert receipt.verified is True
    assert len(receipt.member_receipts) == 1
    mr = receipt.member_receipts[0]
    assert mr.row_count == 96
    assert mr.header is not None
    assert "open_time" in mr.header


def test_verify_zip_deterministic():
    z1 = make_synthetic_csv_zip(seed=99, rows=50)
    z2 = make_synthetic_csv_zip(seed=99, rows=50)
    r1 = verify_zip_archive(z1)
    r2 = verify_zip_archive(z2)
    assert r1.archive_sha256 == r2.archive_sha256
    assert r1.member_receipts[0].sha256_hex == r2.member_receipts[0].sha256_hex


def test_verify_expected_members_pass():
    raw_zip = make_synthetic_csv_zip(filename="BTCUSDT-15m-2024-01-01.csv")
    receipt = verify_zip_archive(
        raw_zip, expected_members=["BTCUSDT-15m-2024-01-01.csv"]
    )
    assert receipt.verified is True
    assert receipt.errors == []


def test_verify_expected_members_missing():
    raw_zip = make_synthetic_csv_zip(filename="BTCUSDT-15m-2024-01-01.csv")
    receipt = verify_zip_archive(
        raw_zip, expected_members=["MISSING_FILE.csv"]
    )
    assert receipt.verified is False
    assert any("MissingMember" in e for e in receipt.errors)


# ── adversarial: bad ZIP bytes ────────────────────────────────────────────────

def test_verify_not_a_zip():
    receipt = verify_zip_archive(b"this is not a zip file")
    assert receipt.verified is False
    assert any("BadZipFile" in e for e in receipt.errors)


# ── adversarial: traversal attempt ───────────────────────────────────────────

def test_verify_traversal_rejected():
    raw_zip = make_synthetic_csv_zip(include_traversal=True)
    receipt = verify_zip_archive(raw_zip)
    assert receipt.verified is False
    assert any("Traversal" in e or "Unsafe" in e for e in receipt.errors)


# ── adversarial: duplicate member ────────────────────────────────────────────

def test_verify_duplicate_member():
    raw_zip = make_synthetic_csv_zip(add_duplicate_member=True)
    receipt = verify_zip_archive(raw_zip)
    assert receipt.verified is False
    assert any("Duplicate" in e for e in receipt.errors)


# ── adversarial: member count ceiling ────────────────────────────────────────

def test_verify_too_many_members():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for i in range(15):
            zf.writestr(f"file_{i}.csv", b"data")
    receipt = verify_zip_archive(buf.getvalue(), max_members=10)
    assert receipt.verified is False
    assert any("Too many" in e for e in receipt.errors)


# ── adversarial: decompression bomb ratio ────────────────────────────────────

def test_verify_decompression_bomb():
    # build a file with very high compression ratio
    big_data = b"\x00" * (10 * 1024 * 1024)  # 10 MiB of zeros → tiny compressed
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.csv", big_data)
    raw_zip = buf.getvalue()
    receipt = verify_zip_archive(raw_zip, max_members=10, max_uncompressed=1024)
    # Should hit either ratio or size ceiling
    assert receipt.verified is False


# ── synthetic fixture: row count ─────────────────────────────────────────────

def test_synthetic_rows_count():
    raw_zip = make_synthetic_csv_zip(rows=48, seed=7)
    receipt = verify_zip_archive(raw_zip)
    assert receipt.verified is True
    assert receipt.member_receipts[0].row_count == 48


# ── receipt metadata ──────────────────────────────────────────────────────────

def test_receipt_has_archive_sha256():
    raw_zip = make_synthetic_csv_zip()
    receipt = verify_zip_archive(raw_zip)
    assert len(receipt.archive_sha256) == 64
    assert receipt.archive_bytes == len(raw_zip)
