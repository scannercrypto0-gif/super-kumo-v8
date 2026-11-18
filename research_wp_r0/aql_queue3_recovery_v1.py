"""Bounded local snapshot/restore for the accepted synthetic Queue 2 consumer.

Uses existing SQLite backup and custody-manifest contracts. A separately supplied
manifest pin is mandatory. This does not provide encryption, production key
custody, host recovery, offsite storage or independent custody attestation.
"""
from contextlib import closing
import hashlib
import json
import sqlite3

from aql.archive.backup import sqlite_snapshot
from aql.observation.position_journal import _exclusive_writer
from aql.paper_sim.engine import PaperSimulator
from research_wp_r0.aql_factory_e_research_results_store_v1 import _check_seal, digest
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from research_wp_r0.custody_anchor_verifier import verify_custody_bundle
from tools import offline_custody_kit as kit
from tools.atlas_queue2_dev import readback as read_queue2

FILES = {"evidence.json", "results.sqlite", "simulation.jsonl"}
MAX_BYTES = 64 << 20


def require(condition, reason):
    if not condition:
        raise ValueError("QUEUE3_" + reason)


def file_sha(path):
    path = kit.checked(path)
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, "FILE_BOUND")
    with path.open("rb") as stream:
        result = hashlib.sha256()
        total = 0
        for block in iter(lambda: stream.read(1 << 20), b""):
            total += len(block)
            require(total <= MAX_BYTES, "GROWING_FILE_BOUND")
            result.update(block)
    return result.hexdigest()


def check_pin(value):
    require(type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value), "EXTERNAL_PIN_REQUIRED")


def read_consumers(root):
    """Read a sealed, detached SQLite snapshot and zero-exposure journal."""
    root = kit.checked(root)
    require((root / "evidence.json").stat().st_size <= 1 << 20, "EVIDENCE_SIZE_BOUND")
    queue2 = read_queue2(root)
    uri = (root / "results.sqlite").as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        require(con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLITE_INTEGRITY")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require(tables == {"experiments", "experiment_index_v2", TABLE}, "SYNTHETIC_STORE_TABLE_SCOPE")
        require(con.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 1
                and con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0] == 2,
                "SYNTHETIC_STORE_POPULATION")
    simulation = PaperSimulator(root / "simulation.jsonl", max_events=2)
    states = simulation.states
    require(len(states) == 1 and len(simulation.journal.ledger.events) == 2,
            "SIMULATION_EVENT_SCOPE")
    state = next(iter(states.values()))
    require(state["phase"] == "CANCELLED" and state["filled"] == "0"
            and state["exited"] == "0" and state["fills"] == []
            and state["trading_authority"] == "NONE", "SIMULATION_EXPOSURE")
    return {"queue2_evidence_sha256": queue2["evidence_sha256"],
            "paired_package_sha256": queue2["package_sha256"],
            "simulation_state_sha256": digest(states), "simulation_events": 2,
            "simulation_phase": "CANCELLED", "open_exposure": 0,
            "orders_created": 0, "paper_positions": 0, "dispatches": 0,
            "trading_authority": "NONE"}


def create_snapshot(source, destination, *, expected_evidence_sha256, expected_journal_sha256):
    """New immutable snapshot; manifest is the final publication marker.

    Interrupted destinations remain unsealed for inspection. Nothing deletes,
    overwrites or repairs the source, orphan locks or an existing destination.
    """
    source, destination = kit.checked(source), kit.checked(destination)
    check_pin(expected_evidence_sha256)
    check_pin(expected_journal_sha256)
    require(kit.disjoint(source, destination) and not destination.exists()
            and destination.parent.is_dir(), "NEW_DISJOINT_DESTINATION_REQUIRED")
    inventory, _ = kit.inventory(source)
    require(FILES <= set(inventory)
            and set(inventory) <= FILES | {"results.sqlite-wal", "results.sqlite-shm"},
            "SOURCE_FILE_SCOPE")
    require((source / "evidence.json").stat().st_size <= 1 << 20, "EVIDENCE_SIZE_BOUND")
    require(file_sha(source / "evidence.json") == expected_evidence_sha256,
            "SOURCE_EVIDENCE_PIN")
    evidence = json.loads((source / "evidence.json").read_text(encoding="utf-8"))
    _check_seal(evidence)
    require(evidence["source_class"] == "SYNTHETIC_FIXTURE_ONLY"
            and evidence["trading_authority"] == "NONE", "SYNTHETIC_SOURCE_REQUIRED")
    with _exclusive_writer(source / "simulation.jsonl"):
        require(file_sha(source / "simulation.jsonl") == expected_journal_sha256,
                "SOURCE_JOURNAL_PIN")
        destination.mkdir()  # Exclusive creation, including against a racing creator.
        sqlite_snapshot(source / "results.sqlite", destination / "results.sqlite",
                        timeout=15, max_bytes=MAX_BYTES)
        kit.copy_file(source / "evidence.json", destination / "evidence.json")
        kit.copy_file(source / "simulation.jsonl", destination / "simulation.jsonl")
        require(file_sha(destination / "evidence.json") == expected_evidence_sha256
                and file_sha(destination / "simulation.jsonl") == expected_journal_sha256
                and file_sha(source / "evidence.json") == expected_evidence_sha256,
                "SNAPSHOT_SOURCE_DRIFT")
        read_consumers(destination)
        report = kit.run("manifest", destination, execute=True, quiescent=True)
    return {"manifest_sha256": report["manifest_sha256"], "file_count": 3,
            "source_class": "SYNTHETIC_FIXTURE_ONLY", "encrypted": False,
            "independent_custody_verified": False, "trading_authority": "NONE"}


def verify_snapshot(bundle, anchor, *, expected_manifest_sha256):
    """Verify caller-retained pin, exact files and both native consumers."""
    bundle = kit.checked(bundle)
    check_pin(expected_manifest_sha256)
    anchor = kit.check_anchor(bundle, anchor)
    require(anchor.read_text(encoding="ascii").strip() == expected_manifest_sha256,
            "RETAINED_ANCHOR_PIN")
    files, _ = kit.inventory(bundle)
    require(set(files) == FILES | {kit.MANIFEST}, "SNAPSHOT_FILE_SCOPE")
    verified = verify_custody_bundle(bundle, anchor)
    require(verified["manifest_sha256"] == expected_manifest_sha256, "MANIFEST_PIN")
    body = {"schema": "aql.queue3.synthetic-recovery-receipt.v1",
            "manifest_sha256": expected_manifest_sha256, "file_count": 3,
            "source_class": "SYNTHETIC_FIXTURE_ONLY", "encrypted": False,
            "independent_custody_verified": False, **read_consumers(bundle)}
    return {**body, "sha256": digest(body)}


def restore_snapshot(bundle, anchor, destination, *, expected_manifest_sha256):
    """Restore into a new isolated directory through the accepted custody kit."""
    expected = verify_snapshot(bundle, anchor, expected_manifest_sha256=expected_manifest_sha256)
    kit.run("restore", bundle, anchor=anchor, target=destination, execute=True, quiescent=True)
    actual = verify_snapshot(destination, anchor, expected_manifest_sha256=expected_manifest_sha256)
    require(actual == expected, "RESTORED_CONSUMER_DRIFT")
    return actual
