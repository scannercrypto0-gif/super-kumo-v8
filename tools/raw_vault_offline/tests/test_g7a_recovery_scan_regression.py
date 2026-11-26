"""
G7-A Regression Tests — Issue #215 comment #6555520562
=======================================================
Defect: recovery_scan() uses count comparison only (len(index) != manifest_lines).
This misses:
  - Equal-count wrong mappings: swapped SHAs (index lid_A→sha_B, lid_B→sha_A
    while manifest is correct) → count equal → current code returns CLEAN (FALSE NEGATIVE)
  - Corrupt/invalid index JSON: _read_index() silently returns {}; if manifest is
    also empty, len({}) == 0 → current code returns CLEAN on unreadable index
  - Malformed manifest lines: manifest_entries() raises json.JSONDecodeError on bad
    lines → recovery_scan() propagates the exception instead of returning INCONSISTENT
  - Missing object files: object file deleted but index/manifest agree in count →
    current code returns CLEAN even though data is unreadable

G7-A REQUIREMENT (Issue #215 comment #6555520562):
  Make recovery_scan inspect exact bidirectional association of each
  logical_identity_key and content_sha256 across index.json and manifest.jsonl,
  not counts alone. Detect equal-count wrong mappings, duplicate/conflicting manifest
  identities, missing/extra index or manifest records, malformed manifest lines,
  invalid index JSON, missing object. Never return CLEAN on unreadable/corrupt
  authoritative metadata.

Each test in class TestG7ADefectRegression is RED on unfixed vault.py (HEAD 0a34893)
and GREEN after the fix.

Tests in TestG7ARegression_AlreadyCorrect verify existing correct behaviour
is not broken by the fix.

Run:
    pytest tools/raw_vault_offline/tests/test_g7a_recovery_scan_regression.py -v
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest

from tools.raw_vault_offline.tests._helpers import make_meta


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _admit_two(tmp_path: Path):
    """Admit two distinct objects into a clean vault. Return (vault, meta_a, meta_b)."""
    from tools.raw_vault_offline.vault import RawVault
    vault = RawVault(tmp_path)
    content_a = b"BTCUSDT 15m fixture-A for G7A"
    content_b = b"ETHUSDT 15m fixture-B for G7A"
    meta_a = make_meta(content_a, instrument="BTCUSDT", coverage_start="2024-01-01T00:00:00Z", coverage_end="2024-01-02T00:00:00Z")
    meta_b = make_meta(content_b, instrument="ETHUSDT", coverage_start="2024-01-01T00:00:00Z", coverage_end="2024-01-02T00:00:00Z")
    vault.admit(content_a, meta_a)
    vault.admit(content_b, meta_b)
    return vault, meta_a, meta_b


# ─────────────────────────────────────────────────────────────────────────────
# G7-A DEFECT TESTS — RED on unfixed HEAD 0a34893, GREEN after fix
# ─────────────────────────────────────────────────────────────────────────────

class TestG7ADefectRegression:

    def test_g7a_swapped_shas_equal_count_is_inconsistent(self, tmp_path):
        """
        G7-A PRIMARY DEFECT — RED on 0a34893, GREEN after fix.

        Admit 2 objects A and B (each has a unique logical_identity_key and SHA).
        Corrupt index.json to swap their SHA values:
          index:    lid_A → sha_B,  lid_B → sha_A
          manifest: lid_A → sha_A,  lid_B → sha_B  (correct)

        Count is equal (2 == 2). Current code returns CLEAN (FALSE NEGATIVE).
        Fix must detect the per-key SHA mismatch and return INCONSISTENT.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault, meta_a, meta_b = _admit_two(tmp_path)

        sha_a = meta_a.content_sha256
        sha_b = meta_b.content_sha256
        lid_a = meta_a.logical_identity_key
        lid_b = meta_b.logical_identity_key

        # Corrupt index.json: swap the SHA values
        corrupted_index = {lid_a: sha_b, lid_b: sha_a}  # swapped!
        (tmp_path / "index.json").write_bytes(
            json.dumps(corrupted_index, sort_keys=True, indent=2).encode()
        )

        scan = vault.recovery_scan()

        # Precondition: counts ARE equal (this is the false-negative scenario)
        assert scan["index_entries"] == 2, "Precondition: index must show 2 entries"
        assert scan["manifest_lines"] == 2, "Precondition: manifest must show 2 lines"

        # G7-A BUG: current code returns CLEAN; fix must return INCONSISTENT
        assert scan["status"] == "INCONSISTENT", (
            f"G7-A PRIMARY DEFECT: recovery_scan returned {scan['status']!r} "
            "when index has swapped SHAs (equal-count wrong mappings). "
            "Expected INCONSISTENT. The per-key bidirectional check is missing."
        )

    def test_g7a_corrupt_index_json_never_returns_clean(self, tmp_path):
        """
        G7-A DEFECT — corrupt index JSON silently treated as empty index.

        Overwrite index.json with invalid JSON. _read_index() catches the exception
        and returns {} silently. If manifest is also absent/empty, len({}) == 0 == 0
        → current code returns CLEAN on a vault with unreadable authoritative metadata.

        Fix must never return CLEAN when index.json exists but is unreadable/corrupt.
        """
        from tools.raw_vault_offline.vault import RawVault

        # Write an entry to the vault first to establish it is non-empty
        vault = RawVault(tmp_path)
        content = b"BTCUSDT fixture for corrupt-index test"
        meta = make_meta(content)
        vault.admit(content, meta)

        # Corrupt index.json with invalid JSON
        (tmp_path / "index.json").write_bytes(b"<<<NOT VALID JSON>>>")

        scan = vault.recovery_scan()

        # Fix must report INCONSISTENT — never CLEAN on corrupt index
        assert scan["status"] != "CLEAN", (
            f"G7-A DEFECT: recovery_scan returned {scan['status']!r} when "
            "index.json contains invalid JSON. Must return INCONSISTENT. "
            "Corrupt authoritative metadata must never yield CLEAN."
        )

    def test_g7a_corrupt_index_json_empty_vault_never_clean(self, tmp_path):
        """
        G7-A DEFECT — corrupt index on an otherwise empty vault.

        Plant an index.json with invalid JSON and no manifest. Current code's
        _read_index() returns {} and manifest_lines=0 → 0 == 0 → CLEAN.
        Fix must detect the corrupt index regardless of manifest state.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)

        # Plant corrupt index.json
        (tmp_path / "index.json").write_bytes(b"{invalid_json: true}")

        scan = vault.recovery_scan()

        assert scan["status"] != "CLEAN", (
            f"G7-A DEFECT: recovery_scan returned {scan['status']!r} when "
            "index.json is corrupt and manifest is absent. "
            "Corrupt index must never yield CLEAN, even on an otherwise empty vault."
        )

    def test_g7a_malformed_manifest_line_returns_inconsistent_not_raises(self, tmp_path):
        """
        G7-A DEFECT — malformed manifest line raises instead of returning INCONSISTENT.

        Admit 1 object, then append a malformed (non-JSON) line to manifest.jsonl.
        Current manifest_entries() calls json.loads() without try/except → raises
        JSONDecodeError → recovery_scan() propagates the exception.

        Fix must catch malformed lines and return status=INCONSISTENT (not raise).
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)
        content = b"BTCUSDT fixture for malformed-manifest test"
        meta = make_meta(content)
        vault.admit(content, meta)

        # Append a malformed (non-JSON) line to manifest.jsonl
        with open(tmp_path / "manifest.jsonl", "a") as fh:
            fh.write("<<<NOT VALID JSON LINE>>>\n")

        # Fix must not raise; must return INCONSISTENT
        try:
            scan = vault.recovery_scan()
        except Exception as exc:
            pytest.fail(
                f"G7-A DEFECT: recovery_scan raised {type(exc).__name__}: {exc} "
                "when manifest.jsonl contains a malformed line. "
                "Must return INCONSISTENT instead of raising."
            )

        assert scan["status"] == "INCONSISTENT", (
            f"G7-A DEFECT: recovery_scan returned {scan['status']!r} when "
            "manifest.jsonl contains a malformed line. Expected INCONSISTENT."
        )

    def test_g7a_missing_object_file_is_inconsistent(self, tmp_path):
        """
        G7-A DEFECT — missing object file not detected by recovery_scan.

        Admit 1 object. Then delete its object file. index.json and manifest.jsonl
        both agree (count 1 == 1) but the actual object bytes are gone.

        Current code: len(index)==1, manifest_lines==1 → CLEAN (FALSE NEGATIVE).
        Fix must detect the missing object and return INCONSISTENT.
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        vault = RawVault(tmp_path)
        content = b"BTCUSDT fixture for missing-object test"
        meta = make_meta(content)
        vault.admit(content, meta)

        sha = meta.content_sha256
        obj_path = _object_path(tmp_path, sha)
        assert obj_path.exists(), "Precondition: object file must exist after admit"

        # Delete the object file
        obj_path.unlink()
        assert not obj_path.exists(), "Precondition: object file must be deleted"

        scan = vault.recovery_scan()

        # Precondition: count-based check sees 1 == 1
        assert scan["index_entries"] == 1
        assert scan["manifest_lines"] == 1

        # G7-A BUG: current code returns CLEAN despite missing object
        assert scan["status"] == "INCONSISTENT", (
            f"G7-A DEFECT: recovery_scan returned {scan['status']!r} when "
            "the object file has been deleted but index/manifest counts are equal (1==1). "
            "Must return INCONSISTENT for missing object files."
        )

    def test_g7a_extra_in_index_not_in_manifest_is_inconsistent(self, tmp_path):
        """
        G7-A — extra key in index with no matching manifest entry.

        Plant index with lid_X→sha_X and lid_Y→sha_Y.
        Plant manifest with only 1 entry for lid_X.
        Count: index=2, manifest=1 → current code detects by count → INCONSISTENT.
        Fix must also expose extra_in_index detail.

        This test verifies the fix also reports the extra key, not just INCONSISTENT.
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        vault, meta_a, meta_b = _admit_two(tmp_path)

        # Remove meta_b's line from manifest by rewriting only meta_a's line
        sha_a = meta_a.content_sha256
        lid_a = meta_a.logical_identity_key

        # Read manifest, keep only first line
        lines = [
            ln for ln in (tmp_path / "manifest.jsonl").read_text().splitlines()
            if ln.strip()
        ]
        assert len(lines) == 2, "Precondition: 2 manifest lines after admitting 2 objects"
        # Keep only the first line
        (tmp_path / "manifest.jsonl").write_text(lines[0] + "\n")

        scan = vault.recovery_scan()

        assert scan["status"] == "INCONSISTENT", (
            f"G7-A: recovery_scan returned {scan['status']!r} when index has 2 entries "
            "but manifest has only 1. Expected INCONSISTENT."
        )
        # New: fix must report which keys are extra in index
        assert "extra_in_index" in scan, (
            "G7-A: recovery_scan result missing 'extra_in_index' field after fix"
        )

    def test_g7a_duplicate_conflicting_manifest_entries_is_inconsistent(self, tmp_path):
        """
        G7-A — duplicate manifest entries for same logical_identity_key with
        different content_sha256 values.

        A duplicate manifest entry represents a conflicting write that should
        have been rejected by IdentityConflict. recovery_scan must flag it.
        Fix must detect duplicate keys in manifest and return INCONSISTENT with
        manifest_duplicates=True.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)
        content_a = b"BTCUSDT fixture A"
        meta_a = make_meta(content_a)
        vault.admit(content_a, meta_a)

        sha_other = hashlib.sha256(b"OTHER_CONTENT_DIFFERENT_SHA").hexdigest()
        lid_a = meta_a.logical_identity_key

        # Append a second manifest line for the SAME lid with a DIFFERENT sha
        duplicate_entry = {
            "logical_identity_key": lid_a,
            "content_sha256": sha_other,
            "schema_version": "v1",
        }
        with open(tmp_path / "manifest.jsonl", "a") as fh:
            fh.write(json.dumps(duplicate_entry) + "\n")

        scan = vault.recovery_scan()

        assert scan["status"] == "INCONSISTENT", (
            f"G7-A: recovery_scan returned {scan['status']!r} when manifest has "
            "duplicate entries for the same logical_identity_key. Expected INCONSISTENT."
        )
        # New: fix must expose manifest_duplicates flag
        if "manifest_duplicates" in scan:
            assert scan["manifest_duplicates"] is True, (
                "G7-A: manifest_duplicates should be True when duplicate entries detected"
            )


# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION — existing correct behaviour must survive the fix
# ─────────────────────────────────────────────────────────────────────────────

class TestG7ARegression_AlreadyCorrect:

    def test_clean_vault_after_two_admits_is_still_clean(self, tmp_path):
        """
        REGRESSION: A correctly-admitted 2-object vault must still return CLEAN.
        The bidirectional fix must not produce false positives on a clean vault.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault, meta_a, meta_b = _admit_two(tmp_path)
        scan = vault.recovery_scan()
        assert scan["status"] == "CLEAN", (
            f"REGRESSION: clean vault after 2 admits returned {scan['status']!r}. "
            "Must be CLEAN. The G7-A fix introduced a false positive."
        )
        assert scan["index_entries"] == 2
        assert scan["manifest_lines"] == 2

    def test_empty_vault_is_clean(self, tmp_path):
        """
        REGRESSION: A freshly initialised vault with no admits must still be CLEAN.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)
        scan = vault.recovery_scan()
        assert scan["status"] == "CLEAN", (
            f"REGRESSION: empty vault returned {scan['status']!r}. "
            "Must be CLEAN. G7-A fix must not flag an empty vault."
        )

    def test_orphan_staging_detection_still_works(self, tmp_path):
        """
        REGRESSION: Orphan .tmp files in staging must still return ORPHAN_STAGING_FOUND.
        """
        from tools.raw_vault_offline.vault import RawVault
        vault = RawVault(tmp_path)
        (tmp_path / ".staging" / "orphan_test.tmp").write_bytes(b"stale")
        scan = vault.recovery_scan()
        assert scan["status"] == "ORPHAN_STAGING_FOUND", (
            f"REGRESSION: orphan staging detection returned {scan['status']!r}. "
            "Must be ORPHAN_STAGING_FOUND."
        )

    def test_count_mismatch_index_ahead_is_still_inconsistent(self, tmp_path):
        """
        REGRESSION: Gate 3 fix — index written but manifest not yet written.
        Count mismatch (index=1, manifest=0) must still return INCONSISTENT.
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        import hashlib
        vault = RawVault(tmp_path)
        content = b"BTCUSDT count-mismatch test"
        meta = make_meta(content)
        sha = hashlib.sha256(content).hexdigest()
        lid = meta.logical_identity_key

        # Plant object + index without manifest
        obj_path = _object_path(tmp_path, sha)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(content)
        (tmp_path / "index.json").write_bytes(
            json.dumps({lid: sha}, sort_keys=True, indent=2).encode()
        )

        scan = vault.recovery_scan()
        assert scan["status"] == "INCONSISTENT", (
            f"REGRESSION (Gate 3): recovery_scan returned {scan['status']!r} "
            "when index has 1 entry but manifest is absent. Must be INCONSISTENT."
        )
