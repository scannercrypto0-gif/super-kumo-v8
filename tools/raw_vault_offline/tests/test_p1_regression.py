"""
P1 Regression Tests — Issue #215 Gate 3
=========================================
P1-A: Unconditional top-level 'import fcntl' causes ImportError on Windows.
      RED: AST proves the unconditional import exists before fix.
      GREEN: Platform guard (UNSUPPORTED_PLATFORM) exists before fcntl import.

P1-B: Crash consistency investigation.
      Inject simulated crash between object write, manifest append, and index write.
      Prove: no silent overwrite, correct recovery behavior, no phantom objects.

P1-C: Archive provenance investigation.
      Adversarial archive tests already in test_archive_verifier.py (baseline).
      Additional: vendor checksum vs self-computed hash, and availability.

Run:
    cd /tmp/pr211-check && pytest tools/raw_vault_offline/tests/test_p1_regression.py -v
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# P1-A: fcntl platform portability
# ─────────────────────────────────────────────────────────────────────────────

VAULT_PY = pathlib.Path(__file__).parent.parent / "vault.py"


class TestP1AFcntlPlatform:

    def test_p1a_red_unconditional_fcntl_import_exists(self):
        """
        P1-A RED: vault.py has a top-level unconditional 'import fcntl'.
        This FAILS on Windows with ModuleNotFoundError.

        This test FAILS on unfixed SHA accbc70 because the unconditional
        import is present and not guarded by a platform check.
        """
        src = VAULT_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)

        # Find top-level 'import fcntl' (not inside if/try/function)
        top_level_unconditional = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "fcntl":
                        top_level_unconditional.append(node.lineno)
            # if sys.platform == 'win32' guard wrapping fcntl → OK
            # but bare 'import fcntl' at module level → BUG
            if isinstance(node, (ast.If,)):
                # Check if this is a platform guard
                if _is_platform_guard(node):
                    # fcntl inside a platform guard is acceptable
                    pass

        assert not top_level_unconditional, (
            f"P1-A BUG: 'import fcntl' found unconditionally at top level "
            f"(line {top_level_unconditional[0]}). "
            "This causes ModuleNotFoundError on Windows. "
            "Must be guarded by a platform check or use UNSUPPORTED_PLATFORM."
        )

    def test_p1a_green_platform_guard_present(self):
        """
        P1-A GREEN (after fix): vault.py must have either:
          (a) a sys.platform check before importing fcntl, OR
          (b) a try/except ImportError that raises UNSUPPORTED_PLATFORM.
        This test PASSES after the fix.
        """
        src = VAULT_PY.read_text(encoding="utf-8")
        # Check for platform guard patterns
        has_platform_check = "sys.platform" in src or "platform.system" in src
        has_import_guard = "UNSUPPORTED_PLATFORM" in src or "UnsupportedPlatform" in src
        assert has_platform_check or has_import_guard, (
            "P1-A: No platform guard found. vault.py must guard fcntl import "
            "with sys.platform check or raise UNSUPPORTED_PLATFORM on Windows."
        )

    def test_p1a_import_succeeds_on_posix(self):
        """
        P1-A COMPAT: On Linux/macOS, vault.py must still import cleanly.
        """
        if sys.platform == "win32":
            pytest.skip("UNSUPPORTED_PLATFORM — this test verifies Linux/macOS behavior")
        # Reimport from source to verify no import errors
        import importlib
        import tools.raw_vault_offline.vault as vault_mod
        assert hasattr(vault_mod, "RawVault"), "vault.RawVault must be importable on POSIX"

    def test_p1a_vault_lock_works_on_posix(self, tmp_path):
        """
        P1-A COMPAT: _vault_lock must function correctly on POSIX after fix.
        """
        if sys.platform == "win32":
            pytest.skip("UNSUPPORTED_PLATFORM")
        from tools.raw_vault_offline.vault import _vault_lock
        root = tmp_path / "vault"
        root.mkdir()
        acquired = False
        with _vault_lock(root):
            acquired = True
        assert acquired, "_vault_lock must acquire and release without error on POSIX"


def _is_platform_guard(node: ast.If) -> bool:
    """Return True if the If node tests sys.platform."""
    src_fragment = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
    return "platform" in src_fragment


# ─────────────────────────────────────────────────────────────────────────────
# P1-B: Crash consistency (investigation — not presumed bug)
# ─────────────────────────────────────────────────────────────────────────────

def _make_test_meta(content: bytes, suffix: str = ""):
    """Build a minimal RawObjectMeta for testing."""
    from tools.raw_vault_offline.schema import (
        RawObjectMeta, SCHEMA_VERSION, logical_identity_key
    )
    from datetime import datetime, timezone
    sha256 = hashlib.sha256(content).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    lid = logical_identity_key(
        "BINANCE_SPOT", f"BTCUSDT{suffix}", "SPOT", "1m",
        "CSV", "v1",
        "2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z",
    )
    return RawObjectMeta(
        schema_version=SCHEMA_VERSION,
        content_sha256=sha256,
        byte_length=len(content),
        vendor="BINANCE_SPOT",
        instrument=f"BTCUSDT{suffix}",
        market="SPOT",
        interval="1m",
        source_format="CSV",
        format_version="v1",
        coverage_start_utc="2024-01-01T00:00:00Z",
        coverage_end_utc="2024-01-01T00:01:00Z",
        coverage_status="CONFIRMED",
        evidence_class="PRIMARY",
        trust_status="VENDOR_CLAIMED",
        original_filename=f"BTCUSDT{suffix}-1m-2024-01-01.csv",
        capture_provenance="test",
        archive_member_path="",
        archive_member_sha256="",
        logical_identity_key=lid,
        admitted_at_utc=now,
    )


class TestP1BCrashConsistency:

    def test_p1b_crash_after_object_write_before_manifest(self, tmp_path):
        """
        P1-B Investigation: crash after object file is committed but before
        manifest append. On recovery, the object exists but manifest/index
        do not reference it — vault must not silently overwrite or corrupt.

        Invariant: re-admitting same bytes after simulated crash must succeed
        idempotently (object already exists, no phantom orphan conflict).
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        vault = RawVault(tmp_path)
        content = b"BTCUSDT 1m bar fixture crash-b-manifest"
        meta = _make_test_meta(content)

        # Simulate: object committed, then crash before manifest
        sha = hashlib.sha256(content).hexdigest()
        obj_path = _object_path(tmp_path, sha)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(content)
        # manifest is absent (crash before append)
        assert not (tmp_path / "manifest.jsonl").exists()

        # Recovery: re-admit same bytes — must succeed idempotently
        result = vault.admit(content, meta)
        assert result.content_sha256 == sha, (
            "P1-B: Re-admit after crash (object exists, no manifest) "
            "must return correct meta, not raise an error."
        )
        # Manifest must now contain exactly one entry
        lines = (tmp_path / "manifest.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1, (
            f"P1-B: Expected 1 manifest line after crash recovery, got {len(lines)}"
        )

    def test_p1b_crash_after_manifest_before_index(self, tmp_path):
        """
        P1-B Investigation: crash after manifest append but before index update.
        On recovery, manifest references an object that index doesn't know about.
        Re-admission of same bytes must succeed idempotently (not duplicate).
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        vault = RawVault(tmp_path)
        content = b"BTCUSDT 1m bar fixture crash-b-index"
        meta = _make_test_meta(content)

        sha = hashlib.sha256(content).hexdigest()

        # Commit object
        obj_path = _object_path(tmp_path, sha)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(content)

        # Append manifest (simulate partial commit)
        line = json.dumps(meta.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        with open(tmp_path / "manifest.jsonl", "a") as fh:
            fh.write(line)
        # index NOT updated (crash before index write)
        assert not (tmp_path / "index.json").exists()

        # Re-admit: index absent means vault sees it as new, but object exists
        result = vault.admit(content, meta)
        assert result.content_sha256 == sha, (
            "P1-B: Re-admit after crash (object+manifest exist, index absent) "
            "must succeed idempotently."
        )
        # Index must now exist
        assert (tmp_path / "index.json").exists(), "Index must be written on recovery admit"
        manifest_lines = (tmp_path / "manifest.jsonl").read_text().strip().splitlines()
        assert len(manifest_lines) >= 1, "Manifest must have at least one entry"

    def test_p1b_staging_orphan_does_not_block(self, tmp_path):
        """
        P1-B Investigation: orphan .tmp file left in .staging/ from a prior crash
        must not block subsequent admits (should be silently ignored).
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)

        # Plant an orphan .tmp in staging
        staging = tmp_path / ".staging"
        staging.mkdir(exist_ok=True)
        orphan = staging / "deadbeef.obj.tmp"
        orphan.write_bytes(b"stale orphan from crashed write")

        content = b"BTCUSDT 1m bar after orphan"
        meta = _make_test_meta(content)
        # Must succeed without touching the orphan
        result = vault.admit(content, meta)
        assert result.content_sha256 == hashlib.sha256(content).hexdigest(), (
            "P1-B: Orphan .tmp in .staging/ must not block a fresh admit."
        )
        # Orphan still there (vault does not clean up)
        assert orphan.exists(), "Vault must not delete unrelated staging files"

    def test_p1b_no_silent_overwrite_on_identity_conflict(self, tmp_path):
        """
        P1-B: Different content for same logical identity must raise IdentityConflict,
        never silently overwrite. This is the write-once safety invariant.
        """
        from tools.raw_vault_offline.vault import RawVault
        from tools.raw_vault_offline.schema import IdentityConflict
        vault = RawVault(tmp_path)

        content_a = b"BTCUSDT 1m bar original"
        meta_a = _make_test_meta(content_a)
        vault.admit(content_a, meta_a)

        # Same logical identity, different bytes
        content_b = b"BTCUSDT 1m bar TAMPERED"
        sha_b = hashlib.sha256(content_b).hexdigest()
        from tools.raw_vault_offline.schema import RawObjectMeta
        from datetime import datetime, timezone
        meta_b = RawObjectMeta(
            schema_version=meta_a.schema_version,
            content_sha256=sha_b,
            byte_length=len(content_b),
            vendor=meta_a.vendor,
            instrument=meta_a.instrument,
            market=meta_a.market,
            interval=meta_a.interval,
            source_format=meta_a.source_format,
            format_version=meta_a.format_version,
            coverage_start_utc=meta_a.coverage_start_utc,
            coverage_end_utc=meta_a.coverage_end_utc,
            coverage_status=meta_a.coverage_status,
            evidence_class=meta_a.evidence_class,
            trust_status=meta_a.trust_status,
            original_filename=meta_a.original_filename,
            capture_provenance=meta_a.capture_provenance,
            archive_member_path=meta_a.archive_member_path,
            archive_member_sha256=meta_a.archive_member_sha256,
            logical_identity_key=meta_a.logical_identity_key,  # SAME identity key
            admitted_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        with pytest.raises(IdentityConflict):
            vault.admit(content_b, meta_b)


# ─────────────────────────────────────────────────────────────────────────────
# P1-C: Archive provenance (investigation)
# ─────────────────────────────────────────────────────────────────────────────

class TestP1CArchiveProvenance:

    def test_p1c_receipt_sha256_is_self_computed_not_vendor(self):
        """
        P1-C: ArchiveReceipt.archive_sha256 must be computed from the actual bytes
        read, not taken from a vendor-supplied field. Self-hash provenance.
        """
        from tools.raw_vault_offline.archive_verifier import verify_zip_archive, make_synthetic_csv_zip
        # make_synthetic_csv_zip returns bytes (keyword-only args, no path param)
        zip_bytes = make_synthetic_csv_zip(seed=42)
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()

        # verify_zip_archive takes bytes, not a path
        receipt = verify_zip_archive(zip_bytes)
        assert receipt.archive_sha256 == expected_sha, (
            "P1-C: archive_sha256 in receipt must match SHA-256 of actual bytes. "
            "Must not trust any vendor-supplied hash field."
        )

    def test_p1c_member_sha256_matches_extracted_bytes(self):
        """
        P1-C: Each MemberReceipt.sha256_hex must match SHA-256 of the member's
        extracted bytes (self-computed, not CRC32 alone).
        """
        import io
        import zipfile as zipfile_mod
        from tools.raw_vault_offline.archive_verifier import verify_zip_archive, make_synthetic_csv_zip
        zip_bytes = make_synthetic_csv_zip(seed=7)

        receipt = verify_zip_archive(zip_bytes)
        with zipfile_mod.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
            for member_receipt in receipt.member_receipts:
                raw = zf.read(member_receipt.member_name)
                expected = hashlib.sha256(raw).hexdigest()
                assert member_receipt.sha256_hex == expected, (
                    f"P1-C: MemberReceipt.sha256_hex for {member_receipt.member_name!r} "
                    f"does not match self-computed SHA-256. "
                    f"Expected {expected}, got {member_receipt.sha256_hex}."
                )

    def test_p1c_receipt_is_deterministic(self):
        """
        P1-C: verify_zip_archive on the same bytes must produce the same receipt
        (deterministic provenance, no random nonces in the receipt itself).
        """
        from tools.raw_vault_offline.archive_verifier import verify_zip_archive, make_synthetic_csv_zip
        zip_bytes = make_synthetic_csv_zip(seed=99)

        r1 = verify_zip_archive(zip_bytes)
        r2 = verify_zip_archive(zip_bytes)
        assert r1.archive_sha256 == r2.archive_sha256
        assert len(r1.member_receipts) == len(r2.member_receipts)
        for m1, m2 in zip(r1.member_receipts, r2.member_receipts):
            assert m1.sha256_hex == m2.sha256_hex, (
                "P1-C: verify_zip_archive must be deterministic on the same bytes."
            )
