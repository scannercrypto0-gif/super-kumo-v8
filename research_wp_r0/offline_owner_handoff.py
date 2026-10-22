"""WP-R40: OFFLINE checkpoint handoff rehearsal — no actual independent custody.

A test directory stands in for an owner's separately retained file. No
authentication, immutable provider, signed timestamp or owner-controlled
permission is established by copying a file to another local directory.
Real owner custody must happen separately before independent_trust=True.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import (
    OwnerCheckpoint, export_checkpoint, verify_owner_checkpoint,
)
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, fingerprint,
)

T = datetime(2026, 10, 22, tzinfo=timezone.utc)


def _family():
    return FrozenSearchFamily("r40-synthetic", "protocol", "temporal",
                              "source", "net", "MAXIMIZE", ("a", "b"), 0.05, T)


def _write_owner_copy(path: Path, checkpoint: OwnerCheckpoint) -> None:
    """Create only; never replace the owner's checkpoint through this handoff."""
    # Test-only local file; it does NOT implement independently trusted custody.
    with path.open("xb") as stream:
        stream.write(checkpoint.to_json_bytes())
        stream.flush()


def _load_owner_copy(path: Path) -> OwnerCheckpoint:
    # The caller must prove this file is the SAME independently retained bytes.
    # Merely reading a locally writable path is not proof of ownership.
    return OwnerCheckpoint.from_json_bytes(path.read_bytes())


def _rewrite_all_hashes(journal_path: Path) -> None:
    records = [json.loads(line) for line in journal_path.read_bytes().splitlines()]
    records[1]["data"]["marginal_p_value"] = 0.9
    previous = "0" * 64
    for record in records:
        record["prev_hash"] = previous
        record["hash"] = fingerprint({k: v for k, v in record.items() if k != "hash"})
        previous = record["hash"]
    journal_path.write_bytes(b"".join(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                   ).encode("ascii") + b"\n" for item in records
    ))


def rehearsal() -> dict:
    """Rehearse export/import, valid replay, forged-history and rollback.

    A flag True below means the test assumes an independently trusted snapshot;
    it does NOT attest that real owner custody happened.
    """
    with tempfile.TemporaryDirectory(prefix="aql-r40-journal-") as journal_dir, \
         tempfile.TemporaryDirectory(prefix="aql-r40-owner-copy-sim-") as owner_dir:
        journal_path = Path(journal_dir) / "evidence.jsonl"
        owner_copy = Path(owner_dir) / "checkpoint.json"
        with DurableTrialJournal(journal_path, _family()) as journal:
            for candidate in ("a", "b"):
                journal.record_attempt(Attempt(
                    candidate, AttemptState.COMPLETE, "result-" + candidate,
                    T + timedelta(minutes=1), 0.4,
                ), event_id="attempt-" + candidate)
            checkpoint = export_checkpoint(journal)
        original_journal = journal_path.read_bytes()
        started = time.perf_counter()
        _write_owner_copy(owner_copy, checkpoint)
        owner_digest = hashlib.sha256(owner_copy.read_bytes()).hexdigest()
        loaded = _load_owner_copy(owner_copy)
        if loaded != checkpoint:
            raise AssertionError("Owner-copy bytes changed during handoff")
        export_import_ms = (time.perf_counter() - started) * 1000

        def verify_snapshot() -> None:
            trusted = _load_owner_copy(owner_copy)
            if hashlib.sha256(owner_copy.read_bytes()).hexdigest() != owner_digest:
                raise JournalIntegrityError("Owner-side digest changed")
            with DurableTrialJournal(journal_path, _family()) as reopened:
                verify_owner_checkpoint(
                    reopened, trusted,
                    independently_trusted=True,  # ASSUMED IN TEST ONLY
                )

        verify_snapshot()
        previous = owner_copy.read_bytes()
        # Refuse a second export onto existing owner-owned path.
        duplicate_export_blocked = False
        try:
            _write_owner_copy(owner_copy, checkpoint)
        except FileExistsError:
            duplicate_export_blocked = True
        if not duplicate_export_blocked or owner_copy.read_bytes() != previous:
            raise AssertionError("Existing owner copy replaced")

        attacks = {}
        # Attack 1: recompute entire journal hash chain after modifying trial.
        _rewrite_all_hashes(journal_path)
        try:
            verify_snapshot()
            attacks["full_chain_rewrite"] = False
        except JournalIntegrityError:
            attacks["full_chain_rewrite"] = True
        journal_path.write_bytes(original_journal)
        # Attack 2: truncate valid journal to historical state.
        journal_path.write_bytes(original_journal.splitlines(keepends=True)[0])
        try:
            verify_snapshot()
            attacks["rollback"] = False
        except JournalIntegrityError:
            attacks["rollback"] = True
        journal_path.write_bytes(original_journal)
        # Attack 3: corrupted local owner copy — fail closed, do not adopt it.
        owner_copy.write_bytes(previous.replace(b'"sequence":3', b'"sequence":2'))
        try:
            verify_snapshot()
            attacks["owner_copy_modified"] = False
        except (JournalIntegrityError, ValueError):
            attacks["owner_copy_modified"] = True
        owner_copy.write_bytes(previous)
        verify_snapshot()
        if not all(attacks.values()):
            raise AssertionError("Uncaught checkpoint attack in offline rehearsal")
        return {
            "scope": "synthetic_offline_owner_custody_REHEARSAL_ONLY",
            "external_owner_custody_verified": False,
            "owner_copy_sha256": owner_digest,
            "checkpoint_bytes": len(previous),
            "journal_events": checkpoint.sequence,
            "export_import_ms": round(export_import_ms, 3),
            "exact_bytes_restored": True,
            "existing_owner_copy_not_overwritten": duplicate_export_blocked,
            "adversarial_cases_rejected": attacks,
            "actual_power_loss_tested": False,
        }


def main():
    print(json.dumps(rehearsal(), sort_keys=True))


if __name__ == "__main__":
    main()
