"""
Gate 3 Regression Tests — Issue #215
======================================
PM requirement (Issue #215 Gate 3): Evaluate crash window after index write
before manifest append; mark ZIP bomb/symlink/duplicate/multiprocess gaps
NOT_TESTED unless evidenced.

Bug: In vault.py admit(), the write order is:
  (1) _stage_and_commit_object  → object bytes committed
  (2) _write_index              → index updated (lid → sha256)
  (3) _append_manifest          → manifest appended

A crash after (2) but before (3) leaves the object in the index but
WITHOUT a manifest record. On re-admit with same bytes, admit() hits the
idempotent return path (existing_sha == actual_sha) WITHOUT re-appending
the missing manifest line. The manifest gap is permanent.

These defect tests must FAIL on unfixed SHA 3958a55 and PASS after the fix.
NOT_TESTED marker tests always PASS (they document gaps, not defects).

Run:
    pytest tools/raw_vault_offline/tests/test_g3_crash_window_regression.py -v
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest

from tools.raw_vault_offline.tests._helpers import make_meta


# ─────────────────────────────────────────────────────────────────────────────
# G3-CRASH: crash window defect tests (RED on 3958a55, GREEN after fix)
# ─────────────────────────────────────────────────────────────────────────────

class TestG3CrashWindowIndexBeforeManifest:

    def test_crash_after_index_write_before_manifest_leaves_manifest_gap(self, tmp_path):
        """
        G3-CRASH-1 RED: Simulate crash after index update but before manifest append.
        The actual write order in vault.py is: object → index → manifest.
        A crash between index write (2) and manifest append (3) leaves:
          - object:   EXISTS
          - index:    UPDATED (lid → sha256)
          - manifest: NOT UPDATED (0 entries)

        Bug on 3958a55: on re-admit with same bytes, admit() returns idempotent
        (index hit) WITHOUT re-appending the missing manifest line.
        The manifest gap is permanent — manifest_entries() shows 0 entries.
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        vault = RawVault(tmp_path)
        content = b"BTCUSDT 15m crash-index-before-manifest fixture"
        meta = make_meta(content)
        sha = hashlib.sha256(content).hexdigest()

        # Simulate steps 1+2 (object + index) without step 3 (manifest):
        # 1. Commit object bytes directly
        obj_path = _object_path(tmp_path, sha)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(content)

        # 2. Write index with lid entry (matching what vault would write)
        lid = meta.logical_identity_key
        index_data = json.dumps({lid: sha}, sort_keys=True, indent=2).encode()
        (tmp_path / "index.json").write_bytes(index_data)

        # 3. Manifest intentionally absent (crash before step 3)
        assert not (tmp_path / "manifest.jsonl").exists(), \
            "Precondition: manifest must be absent (simulating crash)"

        # Re-admit: vault sees existing_sha == actual_sha → idempotent return
        result = vault.admit(content, meta)
        assert result.content_sha256 == sha

        # BUG: manifest is still absent — the gap is permanent
        if not (tmp_path / "manifest.jsonl").exists():
            manifest_lines = []
        else:
            manifest_lines = [
                l for l in (tmp_path / "manifest.jsonl")
                          .read_text().strip().splitlines() if l.strip()
            ]

        assert len(manifest_lines) == 1, (
            f"G3-CRASH-1 BUG: After crash (index written, manifest absent) + re-admit, "
            f"manifest has {len(manifest_lines)} entries. Expected 1. "
            "The manifest gap must be repaired on re-admit, not silently ignored."
        )

    def test_crash_after_index_write_recovery_scan_does_not_detect_inconsistency(self, tmp_path):
        """
        G3-CRASH-2 RED: recovery_scan() does not detect index/manifest mismatch.
        After a crash between index write and manifest append:
          index_entries=1, manifest_lines=0 → recovery_scan returns CLEAN.
        The inconsistency is invisible to the operator.
        """
        from tools.raw_vault_offline.vault import RawVault, _object_path
        vault = RawVault(tmp_path)
        content = b"BTCUSDT 15m crash-recovery-scan-gap fixture"
        meta = make_meta(content)
        sha = hashlib.sha256(content).hexdigest()

        # Plant object + index without manifest
        obj_path = _object_path(tmp_path, sha)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(content)
        lid = meta.logical_identity_key
        (tmp_path / "index.json").write_bytes(
            json.dumps({lid: sha}, sort_keys=True, indent=2).encode()
        )

        scan = vault.recovery_scan()
        assert scan["index_entries"] == 1, "Precondition: index must show 1 entry"
        assert scan["manifest_lines"] == 0, "Precondition: manifest must show 0 lines"

        # BUG: recovery_scan reports CLEAN despite index/manifest mismatch
        assert scan["status"] != "CLEAN", (
            "G3-CRASH-2 BUG: recovery_scan returns CLEAN when index_entries=1 "
            "but manifest_lines=0. Must return INCONSISTENT (or similar) to alert "
            "the operator to the manifest gap."
        )


# ─────────────────────────────────────────────────────────────────────────────
# G3 NOT_TESTED markers (always PASS — permanent evidence of open gaps)
# ─────────────────────────────────────────────────────────────────────────────

class TestG3NotTestedMarkers:
    """
    Gate 3 PM requirement: Mark the following gaps NOT_TESTED unless evidenced.
    These tests PASS on every SHA — they document gaps that are open,
    not defects that need fixing at this gate.
    """

    def test_g3_symlink_zip_entries_not_tested(self):
        """
        NOT_TESTED: ZIP archives containing symlink entries (ZipInfo.external_attr
        with mode 0o120000) are not detected or rejected by archive_verifier.
        A crafted ZIP with a symlink entry pointing outside the extract directory
        could allow unexpected file overwrites on some extraction paths.

        archive_verifier.py has no check for the symlink external_attr bit.
        Evidence: no 'symlink', 'external_attr', '0o120000' in archive_verifier.py
        as of HEAD 3958a55. Gap is open. NOT_TESTED.
        """
        from tools.raw_vault_offline import archive_verifier
        import inspect
        src = inspect.getsource(archive_verifier)
        has_symlink_check = any(token in src for token in [
            "symlink", "external_attr", "0o120000", "120777",
        ])
        if has_symlink_check:
            pytest.fail(
                "Gate 3 NOT_TESTED gap CLOSED: archive_verifier now checks for symlink "
                "ZIP entries. Remove or update this marker."
            )
        # Gap is open — this marker PASSES to document NOT_TESTED status
        assert True, "NOT_TESTED: symlink ZIP entries — gap documented, not fixed"

    def test_g3_multiprocess_locking_not_tested(self):
        """
        NOT_TESTED: vault.py uses fcntl.flock for process-level locking, but no
        test verifies that two concurrent processes cannot both hold the lock or
        corrupt the vault under concurrent admits.

        A proper test would require multiprocessing.Process or subprocess.Popen
        to spawn two writers simultaneously. NOT_TESTED at HEAD 3958a55.
        This gap is documented, not fixed, at this gate.
        """
        # Check test files OTHER than this one for concurrent-process tests
        test_dir = Path(__file__).parent
        concurrent_evidence = []
        for tf in test_dir.glob("test_*.py"):
            if tf.name == Path(__file__).name:
                continue  # skip this file
            src = tf.read_text()
            if "multiprocessing" in src or "subprocess.Popen" in src:
                concurrent_evidence.append(tf.name)

        if concurrent_evidence:
            pytest.fail(
                f"Gate 3 NOT_TESTED gap CLOSED: multiprocess locking now tested in "
                f"{concurrent_evidence}. Remove or update this marker."
            )
        assert True, "NOT_TESTED: multiprocess vault locking — gap documented, not fixed"

    def test_g3_correction_generation_consistency_not_tested(self):
        """
        NOT_TESTED: corrections.py allows appending a correction chain, but no
        test verifies that concurrent correction admits (two processes appending
        chain entries simultaneously) produce a consistent, cycle-free chain.

        NOT_TESTED at HEAD 3958a55: corrections tests are single-process only.
        This gap is documented, not fixed, at this gate.
        """
        assert True, (
            "NOT_TESTED: correction-generation consistency under concurrency "
            "— gap documented at HEAD 3958a55, not fixed at this gate"
        )
