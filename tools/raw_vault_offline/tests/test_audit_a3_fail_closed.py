"""
Audit A3 — Fail-Closed Corrupt Metadata Regression Tests
=========================================================
Issue #215 / Audit #134 comment #6556506884

Blocker A3:
  admit() called _read_index() which silently returned {} on existing invalid JSON,
  and _manifest_contains() which silently skipped malformed lines.
  Result: admit() continued after damaged metadata, potentially writing new entries
  over a corrupt vault. recovery_scan() detecting the corruption LATER does not make
  the writer fail closed.

Fix:
  _read_index(): raises CorruptMetadata when index.json exists but contains invalid JSON.
  _manifest_contains(): raises CorruptMetadata on any malformed manifest line.
  admit(): inherits this fail-closed behaviour — CorruptMetadata propagates to caller.

Boundary — interrupted index-before-manifest admission (crash between step 4 and 5):
  This is the G3-CRASH-1 scenario where the object was staged AND the index was written
  (step 4 done) but the manifest append (step 5) did NOT happen.
  On re-admission of identical content (idempotent path):
    - _read_index() succeeds (valid JSON, same lid→sha)
    - _manifest_contains() is called — must not silently skip
    - If manifest is missing the entry → _append_manifest() (G3-CRASH-1 repair)
    - If manifest line is corrupt → CorruptMetadata (not silent skip)

RED on 98a8949 (pre-fix): admit() returns meta on corrupt index/manifest instead of raising.
GREEN after fix: CorruptMetadata raised; focused tests PASS.

Run:
    PYTHONPATH=/home/claude/super-kumo-v8 \\
    pytest tools/raw_vault_offline/tests/test_audit_a3_fail_closed.py -v
"""
from __future__ import annotations

import json

import pytest

from tools.raw_vault_offline.schema import CorruptMetadata
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.tests._helpers import make_meta

# ── shared fixture content ────────────────────────────────────────────────────

_CONTENT  = b"audit-a3-test-content-bytes"
_CONTENT2 = b"audit-a3-test-second-content"


# ── A3 — Corrupt index.json ───────────────────────────────────────────────────


class TestA3CorruptIndex:

    def test_a3_corrupt_index_json_blocks_admit(self, tmp_path):
        """
        A3 PRIMARY — RED on 98a8949, GREEN after fix.

        Write invalid JSON to index.json. admit() must raise CorruptMetadata
        rather than silently resetting to {} and continuing admission.
        """
        vault = RawVault(tmp_path)
        (tmp_path / "index.json").write_text("{ corrupted json !!!", encoding="utf-8")

        with pytest.raises(CorruptMetadata, match="index.json"):
            vault.admit(_CONTENT, make_meta(_CONTENT))

    def test_a3_truncated_index_json_blocks_admit(self, tmp_path):
        """
        A3: Truncated (partial) index.json — common crash scenario.
        Must raise CorruptMetadata, not silently proceed.
        """
        vault = RawVault(tmp_path)
        (tmp_path / "index.json").write_bytes(b'{"key": "value", "k2":')

        with pytest.raises(CorruptMetadata, match="index.json"):
            vault.admit(_CONTENT, make_meta(_CONTENT))

    def test_a3_non_dict_index_json_blocks_admit(self, tmp_path):
        """
        A3: index.json containing valid JSON but wrong root type (list)
        must raise CorruptMetadata — only a dict root is valid.
        """
        vault = RawVault(tmp_path)
        (tmp_path / "index.json").write_text('["not", "a", "dict"]', encoding="utf-8")

        with pytest.raises(CorruptMetadata, match="dict"):
            vault.admit(_CONTENT, make_meta(_CONTENT))

    def test_a3_absent_index_does_not_block_admit(self, tmp_path):
        """
        A3 POSITIVE: absent index.json (new vault) must NOT raise CorruptMetadata.
        """
        vault = RawVault(tmp_path)
        assert not (tmp_path / "index.json").exists()

        meta = make_meta(_CONTENT)
        result = vault.admit(_CONTENT, meta)
        assert result.content_sha256 == meta.content_sha256

    def test_a3_valid_populated_index_allows_second_admit(self, tmp_path):
        """
        A3 POSITIVE: valid index.json (from first admission) allows a second admission
        of different content with a different logical identity.
        """
        vault = RawVault(tmp_path)
        vault.admit(_CONTENT, make_meta(_CONTENT))

        # different instrument → different logical identity
        meta2 = make_meta(_CONTENT2, instrument="ETHUSDT")
        result = vault.admit(_CONTENT2, meta2)
        assert result.content_sha256 == meta2.content_sha256


# ── A3 — Corrupt manifest.jsonl ───────────────────────────────────────────────


class TestA3CorruptManifest:

    def test_a3_corrupt_manifest_line_blocks_readmission(self, tmp_path):
        """
        A3 PRIMARY — RED on 98a8949, GREEN after fix.

        After a valid first admission, append a malformed line to manifest.jsonl.
        Re-admission of the same content must trigger _manifest_contains(), which
        must raise CorruptMetadata rather than silently skipping the bad line.
        """
        vault = RawVault(tmp_path)
        vault.admit(_CONTENT, make_meta(_CONTENT))

        # Corrupt the manifest
        manifest_path = tmp_path / "manifest.jsonl"
        with open(manifest_path, "a", encoding="utf-8") as fh:
            fh.write("CORRUPTED_LINE_NOT_JSON\n")

        # Re-admission triggers _manifest_contains → must raise
        with pytest.raises(CorruptMetadata, match="manifest.jsonl"):
            vault.admit(_CONTENT, make_meta(_CONTENT))

    def test_a3_truncated_manifest_line_blocks_readmission(self, tmp_path):
        """
        A3: A truncated (partial write crash) manifest line raises CorruptMetadata.
        """
        vault = RawVault(tmp_path)
        vault.admit(_CONTENT, make_meta(_CONTENT))

        manifest_path = tmp_path / "manifest.jsonl"
        with open(manifest_path, "a", encoding="utf-8") as fh:
            fh.write('{"content_sha256": "abc", "partial":\n')

        with pytest.raises(CorruptMetadata, match="manifest.jsonl"):
            vault.admit(_CONTENT, make_meta(_CONTENT))

    def test_a3_empty_manifest_lines_are_not_corrupt(self, tmp_path):
        """
        A3 POSITIVE: blank lines in manifest.jsonl are harmless (not malformed JSON).
        A subsequent admission of new (different identity) content must succeed.
        """
        vault = RawVault(tmp_path)
        vault.admit(_CONTENT, make_meta(_CONTENT))

        # Add blank lines only — not invalid JSON
        manifest_path = tmp_path / "manifest.jsonl"
        with open(manifest_path, "a", encoding="utf-8") as fh:
            fh.write("\n\n")

        # Different instrument → different logical identity → does not call
        # _manifest_contains for _CONTENT's SHA, so no CorruptMetadata risk here.
        meta2 = make_meta(_CONTENT2, instrument="ETHUSDT")
        result = vault.admit(_CONTENT2, meta2)
        assert result.content_sha256 == meta2.content_sha256


# ── A3 — Crash boundary (index written, manifest missing/corrupt) ─────────────


class TestA3CrashBoundary:

    def test_a3_crash_index_written_manifest_missing_is_repaired(self, tmp_path):
        """
        A3 CRASH BOUNDARY (G3-CRASH-1): object staged, index written (step 4),
        manifest NOT appended (step 5). Re-admission of identical content must:
          1. Read index (valid) → find lid→sha match
          2. Call _manifest_contains(sha) → manifest absent → False
          3. Append manifest (repair)
          4. Return meta (idempotent)
        No CorruptMetadata must be raised in this scenario.
        """
        import hashlib

        vault = RawVault(tmp_path)
        meta = make_meta(_CONTENT)
        sha = meta.content_sha256

        # Manually simulate the crash state:
        # ── step 3: stage + commit object ──
        obj_path = tmp_path / "objects" / sha[:2] / sha[2:]
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(_CONTENT)

        # ── step 4: update index ──
        index = {meta.logical_identity_key: sha}
        (tmp_path / "index.json").write_text(
            json.dumps(index, sort_keys=True, indent=2), encoding="utf-8"
        )
        # step 5 (manifest append) did NOT happen → crash boundary

        # Re-admission must repair
        result = vault.admit(_CONTENT, meta)
        assert result.content_sha256 == sha

        # Manifest must now contain exactly one entry
        manifest_path = tmp_path / "manifest.jsonl"
        assert manifest_path.exists()
        lines = [
            l for l in manifest_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        assert len(lines) == 1, f"Expected 1 manifest line after repair, got {len(lines)}"
        entry = json.loads(lines[0])
        assert entry["content_sha256"] == sha

    def test_a3_crash_index_written_manifest_corrupt_blocks(self, tmp_path):
        """
        A3 CRASH BOUNDARY + CORRUPT: index written (step 4), manifest exists but
        is corrupt (partial write during step 5). Re-admission must raise
        CorruptMetadata — cannot safely decide idempotency with corrupt manifest.
        """
        vault = RawVault(tmp_path)
        meta = make_meta(_CONTENT)
        sha = meta.content_sha256

        # Stage object
        obj_path = tmp_path / "objects" / sha[:2] / sha[2:]
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(_CONTENT)

        # Write valid index (step 4 done)
        index = {meta.logical_identity_key: sha}
        (tmp_path / "index.json").write_text(
            json.dumps(index, sort_keys=True, indent=2), encoding="utf-8"
        )

        # Write corrupt manifest (partial crash during step 5)
        (tmp_path / "manifest.jsonl").write_text("CORRUPT_PARTIAL_LINE\n", encoding="utf-8")

        with pytest.raises(CorruptMetadata, match="manifest.jsonl"):
            vault.admit(_CONTENT, meta)
