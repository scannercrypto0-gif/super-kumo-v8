"""
G7-A Audit Remediation Regression Tests — Issue #215 / Audit #134 comment #6555797225
========================================================================================
Three Audit CHANGES_REQUIRED findings on PR #211 HEAD 9adf3c0c3d3fa7860bd4e12a47fbe90703ef133e:

A1 — Object existence ≠ content authenticity
  recovery_scan() calls obj_path.exists() only. A file whose bytes were altered
  still reports CLEAN because SHA256 is never recomputed. Require: read bytes,
  recompute SHA256, fail INCONSISTENT on mismatch. New corrupted_objects field.

A2 — Status precedence: ORPHAN_STAGING_FOUND hides INCONSISTENT
  When orphan staging files exist AND integrity is violated (corrupt index /
  sha_mismatch / missing_objects), the current if-orphans branch returns
  ORPHAN_STAGING_FOUND before the integrity check, hiding INCONSISTENT.
  Require: INCONSISTENT takes precedence when any integrity failure exists.

A3 — Crash boundary (docstring / bounded scope)
  admit() writes index before append-manifest; _read_index() silently returns {}
  on corrupt index; _manifest_contains() suppresses malformed lines.
  recovery_scan() DOES flag those; the Audit accepts this as "bounded documented"
  — the requirement is that recovery_scan reports INCONSISTENT on corrupt
  metadata (already covered by G7-A) and that the behaviour is documented.
  No additional code change required for A3 beyond clear docstring update.

FAIL → PASS cycle:
  RED on HEAD 9adf3c0 (pre-fix): A1 and A2 tests fail
  GREEN after fix: all tests pass
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest

from tools.raw_vault_offline.tests._helpers import make_meta


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _admit_one(tmp_path: Path):
    """Admit one object into a clean vault. Return (vault, meta, sha, content)."""
    from tools.raw_vault_offline.vault import RawVault
    vault = RawVault(tmp_path)
    content = b"BTCUSDT 15m fixture for audit remediation A1/A2"
    sha = hashlib.sha256(content).hexdigest()
    meta = make_meta(content)
    vault.admit(content, meta)
    return vault, meta, sha, content


# ─────────────────────────────────────────────────────────────────────────────
# A1 — Object byte-hash validation (mutated bytes must be INCONSISTENT)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditA1ObjectByteIntegrity:
    """
    A1 defect: obj_path.exists() is True but bytes are altered → CLEAN (false negative).
    Fix: recovery_scan() reads object bytes and recomputes SHA256; reports
    corrupted_objects and INCONSISTENT when the stored hash doesn't match the path-key.

    RED on 9adf3c0: test_a1_mutated_object_bytes_is_inconsistent → FAIL
    GREEN after fix: all tests PASS
    """

    def test_a1_mutated_object_bytes_is_inconsistent(self, tmp_path):
        """
        A1 defect: An object file whose bytes are altered but path is unchanged
        must be detected as INCONSISTENT (not CLEAN).

        On 9adf3c0: obj_path.exists() returns True → CLEAN (false negative).
        After fix: recovery_scan() reads bytes, recomputes SHA256, detects mismatch
        → INCONSISTENT with corrupted_objects containing the SHA.
        """
        vault, meta, sha, original_content = _admit_one(tmp_path)

        # Confirm baseline CLEAN
        result = vault.recovery_scan()
        assert result["status"] == "CLEAN", f"Precondition: expected CLEAN, got {result}"

        # Mutate the stored object bytes (but keep the file at its path)
        from tools.raw_vault_offline.vault import _object_path
        obj_path = _object_path(tmp_path, sha)
        obj_path.write_bytes(b"CORRUPTED_BYTES_XYZ_NOT_ORIGINAL")

        result = vault.recovery_scan()
        assert result["status"] == "INCONSISTENT", (
            f"A1 BUG: mutated object bytes must yield INCONSISTENT, got {result['status']}. "
            f"obj_path.exists()=True but content SHA256 does not match the stored key. "
            f"recovery_scan() must read and recompute SHA256, not just check existence."
        )
        corrupted = result.get("corrupted_objects", [])
        assert sha in corrupted or len(corrupted) > 0, (
            f"A1 BUG: corrupted_objects field missing or empty: {corrupted!r}. "
            "The result must identify which object SHAs have byte-level corruption."
        )

    def test_a1_unreadable_object_file_is_inconsistent(self, tmp_path):
        """
        A1 extension: A non-regular-file at the object path (e.g. a directory)
        must also be reported as INCONSISTENT (cannot read bytes from a directory).
        """
        vault, meta, sha, original_content = _admit_one(tmp_path)

        from tools.raw_vault_offline.vault import _object_path
        obj_path = _object_path(tmp_path, sha)

        # Replace file with an empty directory (same path, not a regular file)
        obj_path.unlink()
        obj_path.mkdir()

        result = vault.recovery_scan()
        assert result["status"] == "INCONSISTENT", (
            f"A1 extension: non-regular-file at object path must yield INCONSISTENT, "
            f"got {result['status']}. "
            "recovery_scan() must handle non-regular-file at expected path."
        )

    def test_a1_clean_vault_byte_check_still_passes(self, tmp_path):
        """
        A1 regression: a genuinely clean vault with unmodified bytes must still
        report CLEAN after the byte-hash check is added.
        """
        vault, meta, sha, original_content = _admit_one(tmp_path)
        result = vault.recovery_scan()
        assert result["status"] == "CLEAN", (
            f"A1 regression: clean vault must remain CLEAN after byte-hash fix. "
            f"Got: {result['status']}, corrupted_objects={result.get('corrupted_objects')}"
        )
        assert result.get("corrupted_objects") == [], (
            f"A1 regression: corrupted_objects must be empty for clean vault. "
            f"Got {result.get('corrupted_objects')!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A2 — Status precedence: INCONSISTENT > ORPHAN_STAGING_FOUND
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditA2StatusPrecedence:
    """
    A2 defect: when orphan staging files AND integrity failure coexist,
    the code returns ORPHAN_STAGING_FOUND, hiding INCONSISTENT.

    Fix: collect all findings independently; if any integrity failure exists
    (index_corrupt, manifest_malformed, manifest_duplicates, extra_in_index,
    extra_in_manifest, sha_mismatches, missing_objects, corrupted_objects),
    return INCONSISTENT regardless of orphan staging, while still reporting
    the orphan_staging list in the result.

    RED on 9adf3c0: test_a2_orphan_plus_corrupt_index_is_inconsistent → FAIL
    (returns ORPHAN_STAGING_FOUND because orphans are checked first)
    GREEN after fix: returns INCONSISTENT with orphan_staging still reported.
    """

    def test_a2_orphan_plus_corrupt_index_is_inconsistent(self, tmp_path):
        """
        A2 defect: orphan staging file exists AND index.json is corrupt.
        Must return INCONSISTENT (not ORPHAN_STAGING_FOUND).
        On 9adf3c0: orphan is found first → ORPHAN_STAGING_FOUND, hides corruption.
        After fix: INCONSISTENT, orphan_staging still populated.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)

        # Create an orphan staging .tmp file
        vault._staging.mkdir(parents=True, exist_ok=True)
        (vault._staging / "orphan.tmp").write_bytes(b"orphan content")

        # Corrupt the index.json
        vault._index_path.parent.mkdir(parents=True, exist_ok=True)
        vault._index_path.write_bytes(b"NOT VALID JSON {{{")

        result = vault.recovery_scan()
        assert result["status"] == "INCONSISTENT", (
            f"A2 BUG: orphan + corrupt index must yield INCONSISTENT, "
            f"got {result['status']}. "
            "ORPHAN_STAGING_FOUND must not take precedence over integrity failures."
        )
        # Orphan staging must still be reported in the result
        assert result["orphan_staging"], (
            "A2: orphan_staging list must still be populated even when INCONSISTENT"
        )

    def test_a2_orphan_plus_mutated_object_is_inconsistent(self, tmp_path):
        """
        A2 combined: orphan staging AND mutated object bytes.
        Must return INCONSISTENT (not ORPHAN_STAGING_FOUND).
        """
        vault, meta, sha, original_content = _admit_one(tmp_path)

        # Create an orphan staging .tmp file
        (vault._staging / "orphan2.tmp").write_bytes(b"orphan content")

        # Mutate the object bytes
        from tools.raw_vault_offline.vault import _object_path
        obj_path = _object_path(tmp_path, sha)
        obj_path.write_bytes(b"CORRUPTED")

        result = vault.recovery_scan()
        assert result["status"] == "INCONSISTENT", (
            f"A2+A1 combined: orphan + mutated object must yield INCONSISTENT, "
            f"got {result['status']}."
        )
        assert result["orphan_staging"], "orphan_staging must still be listed"

    def test_a2_orphan_only_without_integrity_failure_stays_orphan(self, tmp_path):
        """
        A2 regression: when ONLY orphans exist and no integrity failure,
        must still return ORPHAN_STAGING_FOUND.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)
        vault._staging.mkdir(parents=True, exist_ok=True)
        (vault._staging / "only_orphan.tmp").write_bytes(b"orphan content")

        result = vault.recovery_scan()
        assert result["status"] == "ORPHAN_STAGING_FOUND", (
            f"A2 regression: orphan-only (no integrity failure) must still return "
            f"ORPHAN_STAGING_FOUND, got {result['status']}."
        )
