"""
Tests for Stage 3: RawVault — admit, read, conflict, idempotency, crash recovery.
"""
import pytest

from tools.raw_vault_offline.schema import (
    ChecksumMismatch,
    IdentityConflict,
    RawObjectMeta,
)
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.tests._helpers import make_meta


# ── helpers ───────────────────────────────────────────────────────────────────

def _fixture_bytes(seed: str = "abc") -> bytes:
    return f"synthetic fixture data seed={seed}".encode()


# ── basic admit + read ────────────────────────────────────────────────────────

def test_admit_and_read(tmp_path):
    vault = RawVault(tmp_path)
    raw = _fixture_bytes("v1")
    meta = make_meta(raw)
    vault.admit(raw, meta)
    result = vault.read(meta.content_sha256)
    assert result == raw


def test_admit_idempotent(tmp_path):
    vault = RawVault(tmp_path)
    raw = _fixture_bytes("v1")
    meta = make_meta(raw)
    vault.admit(raw, meta)
    # second admit with same bytes must not raise
    vault.admit(raw, meta)
    # only one manifest entry
    entries = vault.manifest_entries()
    assert len(entries) == 1


def test_read_verifies_integrity(tmp_path):
    vault = RawVault(tmp_path)
    raw = _fixture_bytes("v1")
    meta = make_meta(raw)
    vault.admit(raw, meta)

    # corrupt the stored object
    sha = meta.content_sha256
    obj_path = tmp_path / "objects" / sha[:2] / sha[2:]
    obj_path.write_bytes(b"corrupted!")

    with pytest.raises(ChecksumMismatch):
        vault.read(sha)


# ── checksum mismatch on admit ────────────────────────────────────────────────

def test_admit_checksum_mismatch(tmp_path):
    vault = RawVault(tmp_path)
    raw = _fixture_bytes("v1")
    meta = make_meta(raw)
    # lie about checksum
    bad_meta = RawObjectMeta(**{**meta.to_dict(), "content_sha256": "a" * 64})
    with pytest.raises(ChecksumMismatch):
        vault.admit(raw, bad_meta)


# ── identity conflict ─────────────────────────────────────────────────────────

def test_admit_identity_conflict(tmp_path):
    vault = RawVault(tmp_path)
    raw_v1 = _fixture_bytes("v1")
    raw_v2 = _fixture_bytes("v2_different")
    meta1 = make_meta(raw_v1)
    meta2 = make_meta(raw_v2)  # same logical identity, different bytes

    vault.admit(raw_v1, meta1)
    with pytest.raises(IdentityConflict):
        vault.admit(raw_v2, meta2)


# ── manifest entries ──────────────────────────────────────────────────────────

def test_manifest_entries(tmp_path):
    vault = RawVault(tmp_path)
    for i in range(3):
        raw = _fixture_bytes(f"seed{i}")
        meta = make_meta(raw,
                         coverage_start=f"2024-01-0{i+1}T00:00:00Z",
                         coverage_end=f"2024-01-0{i+2}T00:00:00Z")
        vault.admit(raw, meta)
    entries = vault.manifest_entries()
    assert len(entries) == 3


# ── crash recovery: orphan staging ───────────────────────────────────────────

def test_recovery_scan_detects_orphan(tmp_path):
    vault = RawVault(tmp_path)
    # simulate a crash by planting a .tmp file
    staging = tmp_path / ".staging"
    staging.mkdir(exist_ok=True)
    orphan = staging / "deadbeef.obj.tmp"
    orphan.write_bytes(b"partial write")

    scan = vault.recovery_scan()
    assert scan["status"] == "ORPHAN_STAGING_FOUND"
    assert len(scan["orphan_staging"]) == 1


def test_purge_orphan_staging(tmp_path):
    vault = RawVault(tmp_path)
    staging = tmp_path / ".staging"
    staging.mkdir(exist_ok=True)
    orphan = staging / "deadbeef.obj.tmp"
    orphan.write_bytes(b"partial write")

    removed = vault.purge_orphan_staging()
    assert removed == 1

    scan = vault.recovery_scan()
    assert scan["status"] == "CLEAN"


def test_recovery_scan_clean(tmp_path):
    vault = RawVault(tmp_path)
    raw = _fixture_bytes("v1")
    meta = make_meta(raw)
    vault.admit(raw, meta)

    scan = vault.recovery_scan()
    assert scan["status"] == "CLEAN"
    assert scan["manifest_lines"] == 1
    assert scan["objects_count"] == 1


# ── read nonexistent ──────────────────────────────────────────────────────────

def test_read_missing_raises(tmp_path):
    vault = RawVault(tmp_path)
    with pytest.raises(KeyError):
        vault.read("a" * 64)
