"""Native immutable result/journal snapshots, external pins and bounded retry."""
import os
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest

from aql.observation.position_journal import _exclusive_writer
from aql.paper_sim.engine import PaperSimulator
from research_wp_r0 import aql_queue3_recovery_v1 as recovery
from tools.atlas_queue2_dev import produce as produce_queue2
from tools.atlas_queue3_recovery import negative_checks, seed_journal


@pytest.fixture(scope="module")
def source_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("queue3-source") / "source"
    supplied = os.environ.get("AQL_QUEUE3_TEST_SOURCE")
    if supplied:
        root.mkdir()
        for name in recovery.FILES:
            shutil.copyfile(Path(supplied) / name, root / name)
    else:
        if sys.platform == "win32":
            pytest.skip("RAW generation uses POSIX; CI supplies the verified Ubuntu snapshot")
        produce_queue2(root)
        seed_journal(root)
    return root


@pytest.fixture
def source(source_fixture, tmp_path):
    root = tmp_path / "source"
    shutil.copytree(source_fixture, root)
    return root


def create(source, target):
    return recovery.create_snapshot(
        source, target, expected_evidence_sha256=recovery.file_sha(source / "evidence.json"),
        expected_journal_sha256=recovery.file_sha(source / "simulation.jsonl"),
    )


def anchor(root, snapshot):
    result = create(root / "source", snapshot)
    path = root / (snapshot.name + ".sha256")
    path.write_text(result["manifest_sha256"], encoding="ascii")
    return path, result["manifest_sha256"]


def test_native_create_seal_restore_reopen_and_deterministic_pins(source, tmp_path):
    first, second = tmp_path / "snapshot-a", tmp_path / "snapshot-b"
    external, pin = anchor(tmp_path, first)
    assert create(source, second)["manifest_sha256"] == pin
    before = {name: recovery.file_sha(source / name) for name in recovery.FILES}
    expected = recovery.verify_snapshot(first, external, expected_manifest_sha256=pin)
    restored = recovery.restore_snapshot(first, external, tmp_path / "restored", expected_manifest_sha256=pin)
    assert restored == expected
    assert restored["simulation_events"] == 2
    assert restored["simulation_phase"] == "CANCELLED"
    assert restored["open_exposure"] == restored["orders_created"] == restored["paper_positions"] == 0
    assert {name: recovery.file_sha(source / name) for name in recovery.FILES} == before
    with pytest.raises(ValueError):
        recovery.restore_snapshot(first, external, tmp_path / "restored", expected_manifest_sha256=pin)


def test_corruption_truncation_self_reseal_traversal_and_missing_pins(source, tmp_path):
    snapshot = tmp_path / "snapshot"
    external, pin = anchor(tmp_path, snapshot)
    assert len(negative_checks(snapshot, external, pin)) == 6
    assert recovery.verify_snapshot(snapshot, external, expected_manifest_sha256=pin)["manifest_sha256"] == pin


def test_replayed_receipt_cannot_substitute_other_generation_and_old_pin_still_works(source, tmp_path):
    first, second = tmp_path / "snapshot-a", tmp_path / "snapshot-b"
    first_anchor, first_pin = anchor(tmp_path, first)
    # Disposable fixture generation changes, never automatic journal repair.
    (source / "simulation.jsonl").unlink()
    seed_journal(source, instance="queue3-second-generation")
    second_anchor, second_pin = anchor(tmp_path, second)
    assert first_pin != second_pin
    with pytest.raises(ValueError):
        recovery.restore_snapshot(second, first_anchor, tmp_path / "bad", expected_manifest_sha256=first_pin)
    assert not (tmp_path / "bad").exists()
    assert recovery.verify_snapshot(first, first_anchor, expected_manifest_sha256=first_pin)
    assert recovery.verify_snapshot(second, second_anchor, expected_manifest_sha256=second_pin)


def test_sqlite_backup_includes_committed_wal_pages(source, tmp_path):
    connection = sqlite3.connect(source / "results.sqlite")
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA application_id=71")
        connection.commit()
        assert (source / "results.sqlite-wal").stat().st_size > 0
        snapshot = tmp_path / "snapshot"
        create(source, snapshot)
        copied = sqlite3.connect(snapshot / "results.sqlite")
        try:
            assert copied.execute("PRAGMA application_id").fetchone()[0] == 71
        finally:
            copied.close()
    finally:
        connection.close()


def test_interrupted_snapshot_keeps_unsealed_evidence_and_retries_to_new_target(source, tmp_path, monkeypatch):
    original = recovery.kit.copy_file
    snapshot = tmp_path / "interrupted"

    def interrupted(src, dst):
        if Path(src).name == "simulation.jsonl":
            raise RuntimeError("simulated interrupted copy")
        return original(src, dst)

    monkeypatch.setattr(recovery.kit, "copy_file", interrupted)
    with pytest.raises(RuntimeError, match="interrupted copy"):
        create(source, snapshot)
    assert snapshot.exists() and not (snapshot / "custody-manifest.json").exists()
    monkeypatch.setattr(recovery.kit, "copy_file", original)
    with pytest.raises(ValueError, match="NEW_DISJOINT_DESTINATION"):
        create(source, snapshot)
    external, pin = anchor(tmp_path, tmp_path / "retry")
    assert recovery.verify_snapshot(tmp_path / "retry", external, expected_manifest_sha256=pin)
    assert snapshot.exists()


def test_live_writer_lock_is_preserved_and_blocks_snapshot(source, tmp_path):
    path = source / "simulation.jsonl"
    with _exclusive_writer(path):
        with pytest.raises(ValueError):
            create(source, tmp_path / "blocked")
        assert path.with_name(path.name + ".writer.lock").exists()
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("which", ["evidence", "journal"])
def test_wrong_expected_source_pin_rejected_without_publishing(source, tmp_path, which):
    with pytest.raises(ValueError, match="SOURCE_.*_PIN"):
        recovery.create_snapshot(
            source, tmp_path / "blocked",
            expected_evidence_sha256="0" * 64 if which == "evidence" else recovery.file_sha(source / "evidence.json"),
            expected_journal_sha256="0" * 64 if which == "journal" else recovery.file_sha(source / "simulation.jsonl"),
        )
    assert not (tmp_path / "blocked").exists()


def test_valid_resealed_journal_for_other_source_rejected(source):
    path = source / "simulation.jsonl"
    original = PaperSimulator(path)
    event = next(iter(original.journal.ledger.events.values()))
    command = json.loads(event.reason)["command"]
    command["signal"]["source_sha256"] = "f" * 64
    # Replace only this isolated test fixture with another valid native chain.
    path.unlink()
    simulation = PaperSimulator(path)
    identity = simulation.identity(command)
    simulation.apply(identity, "watch", command)
    simulation.apply(identity, "cancel", {"op": "cancel", "at_ms": command["at_ms"] + 1})
    with pytest.raises(ValueError, match="SIMULATION_SOURCE_BINDING"):
        recovery.read_consumers(source)
