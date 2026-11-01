"""
Audit A3 Final-Round — Prevalidation and Identity-Keyed Reconciliation
=======================================================================
Issue #215 / Audit #134 comment #6556807523

Two gaps in the previous A3 fix (commit 8dc4c0c) identified by independent audit:

Gap 1 — Prevalidation for new identity:
  admit() called _read_index() (now fail-closed) but only called _manifest_contains()
  for the idempotent same-SHA path. A NEW logical identity bypassed manifest
  prevalidation entirely — a corrupt manifest line appended by a prior partial write
  was never detected before the new object/index/manifest writes occurred.

  Fix: _prevalidate_vault_state(current_index) is now called at the top of the
  lock section, before ANY mutation, for ALL admit() paths including new identities.

Gap 2 — Identity-keyed reconciliation:
  The G3-CRASH-1 crash-recovery check used _manifest_contains(content_sha256),
  matching on SHA only. If identity A was already in the manifest with SHA=X,
  and identity B (different logical identity, same bytes, SHA=X) crashed after
  index write but before manifest write, then _manifest_contains(X) returned True
  (matching A's entry), so B's own manifest entry was never appended. Result:
  B remained in the index but absent from the manifest — an inconsistency that
  recovery_scan() would report as INCONSISTENT.

  Fix: _manifest_contains_for_identity(lid, sha) now checks the (logical_identity_key,
  content_sha256) pair exactly. A's entry does not satisfy B's recovery check.

Audit-required adversarial cases:
  (a) Corrupt manifest + new logical identity: exception before mutation,
      byte-for-byte unchanged index/manifest/object inventory.
  (b) A and B share SHA, B interrupted after index/before manifest: re-admit B,
      distinct manifest entries for A/B, recovery_scan() == CLEAN.

RED/GREEN discipline:
  RED commands run against 8dc4c0c (pre-fix):
    PYTHONPATH=. pytest tools/raw_vault_offline/tests/test_audit_a3_final_round.py::TestA3FinalRound::test_a3_corrupt_manifest_new_identity_no_mutation -v
      → FAIL (admit() returns meta instead of raising CorruptMetadata)
    PYTHONPATH=. pytest tools/raw_vault_offline/tests/test_audit_a3_final_round.py::TestA3FinalRound::test_a3_shared_sha_identity_keyed_recovery -v
      → FAIL (B's manifest entry silently skipped)
  GREEN after this commit: both PASS.

Run:
    PYTHONPATH=/home/claude/super-kumo-v8 \\
    pytest tools/raw_vault_offline/tests/test_audit_a3_final_round.py -v
"""
from __future__ import annotations

import hashlib
import json

import pytest

from tools.raw_vault_offline.schema import CorruptMetadata
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.tests._helpers import make_meta


# ── shared content ────────────────────────────────────────────────────────────

# Two different names but content that produces the SAME SHA (same bytes)
_SHARED_BYTES = b"shared-content-a-and-b-same-bytes-exactly"
_SHARED_SHA   = hashlib.sha256(_SHARED_BYTES).hexdigest()

# Distinct content for identity A (used in test (a))
_CONTENT_A = b"identity-a-initial-content-for-test-a"

# Content for a second distinct identity (used in test (a) as the "new identity")
_CONTENT_B_NEW = b"brand-new-identity-b-content-distinct"


class TestA3FinalRound:

    # ── Case (a): Corrupt manifest + new logical identity ─────────────────────

    def test_a3_corrupt_manifest_new_identity_no_mutation(self, tmp_path):
        """
        Audit-required adversarial case (a):
        Corrupt manifest + new logical identity: exception before mutation,
        byte-for-byte unchanged index/manifest/object inventory.

        Setup:
          1. Admit identity A → index[A.lid]=sha_A, manifest has A's entry.
          2. Append a corrupt line to manifest.jsonl.
          3. Attempt to admit identity B (NEW, different bytes/SHA).

        Pre-fix behaviour (8dc4c0c): admit() skips manifest prevalidation for new
        identities → stages B's object → writes index[B.lid] → THEN tries to append
        manifest → _append_manifest() would only fail if the append itself errors,
        which it doesn't — the corrupt line is not checked. Test: admit() returns
        meta instead of raising. (On 8dc4c0c the test fails with AssertionError.)

        Post-fix behaviour: _prevalidate_vault_state() is called before step 3.
        It reads the manifest, hits the corrupt line, and raises CorruptMetadata.
        No object, no index update, no manifest append has occurred.

        Invariant verified:
        - CorruptMetadata raised
        - index.json unchanged (only A's entry)
        - manifest.jsonl unchanged (A's valid entry + corrupt line, no B entry)
        - object count unchanged (only A's object file)
        """
        vault = RawVault(tmp_path)

        # Admit identity A normally
        meta_a = make_meta(_CONTENT_A, instrument="BTCUSDT")
        vault.admit(_CONTENT_A, meta_a)

        # Snapshot the vault state before corruption
        objects_before = list((tmp_path / "objects").rglob("*"))
        objects_before_files = [p for p in objects_before if p.is_file()]
        index_before = (tmp_path / "index.json").read_bytes()
        manifest_before = (tmp_path / "manifest.jsonl").read_bytes()

        # Append corrupt line to manifest
        with open(tmp_path / "manifest.jsonl", "a", encoding="utf-8") as fh:
            fh.write("NOT_VALID_JSON_CORRUPT_LINE\n")

        manifest_with_corrupt = (tmp_path / "manifest.jsonl").read_bytes()

        # Attempt to admit NEW identity B (different bytes, different logical key)
        meta_b = make_meta(_CONTENT_B_NEW, instrument="ETHUSDT")

        with pytest.raises(CorruptMetadata, match="manifest.jsonl"):
            vault.admit(_CONTENT_B_NEW, meta_b)

        # ── Invariant: nothing was mutated ────────────────────────────────────

        # index.json must be byte-identical to pre-corruption snapshot
        index_after = (tmp_path / "index.json").read_bytes()
        assert index_after == index_before, (
            f"A3(a): index.json was mutated despite CorruptMetadata being raised. "
            f"Expected {index_before!r}, got {index_after!r}"
        )
        index_dict = json.loads(index_after)
        assert meta_b.logical_identity_key not in index_dict, (
            "A3(a): B's logical_identity_key was written to index.json before "
            "CorruptMetadata was raised — prevalidation did not fire first."
        )

        # manifest.jsonl must equal the state AFTER corrupt line was appended
        # (A's entry + corrupt line) — no B entry must have been appended
        manifest_after = (tmp_path / "manifest.jsonl").read_bytes()
        assert manifest_after == manifest_with_corrupt, (
            "A3(a): manifest.jsonl was changed after CorruptMetadata. "
            "B's entry must not have been appended."
        )
        # Verify B's logical_identity_key is absent from all manifest lines
        for line in manifest_after.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                assert entry.get("logical_identity_key") != meta_b.logical_identity_key, (
                    "A3(a): B's logical_identity_key found in manifest even though "
                    "CorruptMetadata was raised."
                )
            except json.JSONDecodeError:
                pass  # the corrupt line itself — expected

        # Object count must be unchanged (only A's object)
        objects_after = [
            p for p in (tmp_path / "objects").rglob("*") if p.is_file()
        ]
        assert len(objects_after) == len(objects_before_files), (
            f"A3(a): object count changed from {len(objects_before_files)} "
            f"to {len(objects_after)} — B's object was staged despite CorruptMetadata."
        )

    # ── Case (b): Shared SHA, B interrupted after index/before manifest ───────

    def test_a3_shared_sha_identity_keyed_recovery(self, tmp_path):
        """
        Audit-required adversarial case (b):
        A and B share SHA, B interrupted after index/before manifest:
        re-admit B, distinct manifest entries for A/B, recovery_scan() == CLEAN.

        Setup:
          1. Admit identity A (bytes=_SHARED_BYTES, SHA=_SHARED_SHA) normally.
             → index[A.lid]=_SHARED_SHA, manifest has A's entry.
          2. Simulate B's crash: manually write index[B.lid]=_SHARED_SHA
             (step 4 done), but do NOT append B's manifest entry (step 5 crash).
          3. Re-admit B (same bytes, same SHA — idempotent path).

        Pre-fix behaviour (8dc4c0c): crash recovery checks _manifest_contains(sha).
        SHA=_SHARED_SHA is already in manifest (A's entry). Returns True → does NOT
        append B's manifest entry. B remains in index but absent from manifest.
        recovery_scan() reports INCONSISTENT.
        Test: fails at assertion that manifest has 2 entries.

        Post-fix behaviour: _manifest_contains_for_identity(B.lid, sha) returns False
        (A's entry doesn't match B's lid). B's entry is appended. Manifest has
        two distinct entries (A and B). recovery_scan() returns CLEAN.

        Invariants verified:
        - admit() returns meta (idempotent success)
        - manifest has exactly 2 entries: one for A.lid and one for B.lid
        - both entries share the same content_sha256 (_SHARED_SHA)
        - recovery_scan()["status"] == "CLEAN"
        """
        vault = RawVault(tmp_path)

        # Build two metas for SAME bytes but DIFFERENT logical identities
        meta_a = make_meta(_SHARED_BYTES, instrument="BTCUSDT")
        meta_b = make_meta(_SHARED_BYTES, instrument="ETHUSDT")

        assert meta_a.logical_identity_key != meta_b.logical_identity_key, (
            "Test precondition: A and B must have different logical_identity_keys"
        )
        assert meta_a.content_sha256 == meta_b.content_sha256 == _SHARED_SHA, (
            "Test precondition: A and B must share the same content_sha256"
        )

        # Step 1: Admit A normally
        vault.admit(_SHARED_BYTES, meta_a)

        # Verify A is admitted correctly
        index_after_a = json.loads((tmp_path / "index.json").read_text())
        assert index_after_a.get(meta_a.logical_identity_key) == _SHARED_SHA
        manifest_lines_after_a = [
            json.loads(l) for l in
            (tmp_path / "manifest.jsonl").read_text().splitlines() if l.strip()
        ]
        assert len(manifest_lines_after_a) == 1
        assert manifest_lines_after_a[0]["logical_identity_key"] == meta_a.logical_identity_key

        # Step 2: Simulate B's crash state — index written, manifest NOT written
        # Read existing index and add B's entry (simulating admit step 4)
        index_with_b = dict(index_after_a)
        index_with_b[meta_b.logical_identity_key] = _SHARED_SHA
        (tmp_path / "index.json").write_text(
            json.dumps(index_with_b, sort_keys=True, indent=2), encoding="utf-8"
        )
        # Object already on disk (A admitted it). B's manifest entry does NOT exist.
        assert meta_b.logical_identity_key not in [
            l.get("logical_identity_key")
            for l in manifest_lines_after_a
        ], "Test precondition: B must not be in manifest at crash-state"

        # Step 3: Re-admit B — must detect manifest entry absent for B.lid and repair
        result = vault.admit(_SHARED_BYTES, meta_b)
        assert result.content_sha256 == _SHARED_SHA, (
            "A3(b): admit() did not return meta for B (idempotent path failed)"
        )

        # ── Invariant: manifest has EXACTLY 2 distinct entries ────────────────
        manifest_text = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")
        manifest_entries = [
            json.loads(l) for l in manifest_text.splitlines() if l.strip()
        ]
        assert len(manifest_entries) == 2, (
            f"A3(b): expected 2 manifest entries (A and B), got {len(manifest_entries)}. "
            f"Entries: {manifest_entries}"
        )

        entry_lids = {e["logical_identity_key"] for e in manifest_entries}
        assert meta_a.logical_identity_key in entry_lids, (
            "A3(b): A's logical_identity_key missing from manifest after B re-admission"
        )
        assert meta_b.logical_identity_key in entry_lids, (
            "A3(b): B's logical_identity_key missing from manifest — "
            "identity-keyed recovery did not append B's entry. "
            "SHA-only _manifest_contains() incorrectly matched A's entry for B."
        )

        # Both entries must share the same SHA
        for entry in manifest_entries:
            assert entry["content_sha256"] == _SHARED_SHA, (
                f"A3(b): unexpected content_sha256 in manifest entry: {entry}"
            )

        # ── Invariant: recovery_scan() reports CLEAN ──────────────────────────
        scan = vault.recovery_scan()
        assert scan["status"] == "CLEAN", (
            f"A3(b): recovery_scan() returned {scan['status']!r} after B re-admission. "
            f"Expected CLEAN. Full scan result: {scan}"
        )
        assert scan["index_entries"] == 2, (
            f"A3(b): expected 2 index entries, got {scan['index_entries']}"
        )
        assert scan["manifest_lines"] == 2, (
            f"A3(b): expected 2 manifest lines, got {scan['manifest_lines']}"
        )


class TestA3FinalRoundSafety:
    """
    Indispensable safety cases: ensure the new prevalidation gate does not
    break valid admission paths, and crash/replay/idempotency is correct.
    """

    def test_a3_prevalidation_does_not_block_clean_vault(self, tmp_path):
        """
        POSITIVE: new vault with no prior admissions — prevalidation passes,
        first admission succeeds.
        """
        vault = RawVault(tmp_path)
        meta = make_meta(b"clean-vault-first-admission")
        result = vault.admit(b"clean-vault-first-admission", meta)
        assert result.content_sha256 == meta.content_sha256

    def test_a3_prevalidation_does_not_block_after_valid_admission(self, tmp_path):
        """
        POSITIVE: after a clean first admission, second admission of a new
        identity must succeed — prevalidation must not flag a clean vault.
        """
        vault = RawVault(tmp_path)
        meta_a = make_meta(b"first-identity-content", instrument="BTCUSDT")
        vault.admit(b"first-identity-content", meta_a)

        meta_b = make_meta(b"second-identity-content", instrument="ETHUSDT")
        result = vault.admit(b"second-identity-content", meta_b)
        assert result.content_sha256 == meta_b.content_sha256

    def test_a3_crash_replay_idempotent_single_identity(self, tmp_path):
        """
        CRASH/REPLAY: single identity, crash after index write before manifest write.
        Re-admission must repair (append manifest entry) and be idempotent.
        Second re-admission must not append a duplicate entry.
        """
        vault = RawVault(tmp_path)
        content = b"crash-replay-idempotent-content"
        meta = make_meta(content, instrument="BTCUSDT")
        sha = meta.content_sha256

        # Simulate crash: object staged, index written, manifest NOT written
        obj_path = tmp_path / "objects" / sha[:2] / sha[2:]
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(content)
        (tmp_path / "index.json").write_text(
            json.dumps({meta.logical_identity_key: sha}, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        assert not (tmp_path / "manifest.jsonl").exists()

        # First re-admission: repairs manifest
        result1 = vault.admit(content, meta)
        assert result1.content_sha256 == sha

        manifest_lines = [
            l for l in (tmp_path / "manifest.jsonl").read_text().splitlines()
            if l.strip()
        ]
        assert len(manifest_lines) == 1, (
            f"Expected 1 manifest entry after repair, got {len(manifest_lines)}"
        )

        # Second re-admission: idempotent, must NOT duplicate manifest entry
        result2 = vault.admit(content, meta)
        assert result2.content_sha256 == sha

        manifest_lines_after = [
            l for l in (tmp_path / "manifest.jsonl").read_text().splitlines()
            if l.strip()
        ]
        assert len(manifest_lines_after) == 1, (
            f"A3 IDEMPOTENCY: second re-admission appended duplicate manifest entry. "
            f"Expected 1, got {len(manifest_lines_after)}"
        )
