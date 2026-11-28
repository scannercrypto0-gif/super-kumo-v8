"""Additive native Secretary receipt for unqualified forward research.

This is a durable WAIT-only route. It neither accepts historical Core #245/#253
parents nor issues Source/Strategy/Consumer ACKs. The caller verifies the actual
Factory package and Lab result before supplying their immutable SHA pointers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
import tempfile

SCHEMA = "aql.secretary.forward-research-wait.v1"
TABLE = "forward_research_wait_v1"
HEX = re.compile(r"^[a-f0-9]{64}$")
FIELDS = {"schema", "experiment_id", "analysis_receipt_sha256", "source_snapshot_sha256",
          "factory_package_sha256", "lab_sha256", "strategy_definition_sha256",
          "config_sha256", "decision_cutoff_ms", "expected_slots", "unknown_slots",
          "source_class", "evidence_grade", "state", "core_245_sha256", "core_253_sha256",
          "source_ack_sha256", "strategy_approval_sha256", "factory_consumer_ack_sha256",
          "orders", "trading_authority", "pit_oos"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _need(ok, code):
    if not ok:
        raise ValueError("FORWARD_SECRETARY_" + code)


def validate_wait_receipt(receipt):
    _need(type(receipt) is dict and set(receipt) == FIELDS | {"sha256"}, "FIELDS")
    body = {k: v for k, v in receipt.items() if k != "sha256"}
    _need(receipt["schema"] == SCHEMA and receipt["sha256"] == digest(body), "SEAL")
    _need(type(receipt["experiment_id"]) is str and
          re.fullmatch(r"FORWARD-RESEARCH-[a-f0-9]{64}", receipt["experiment_id"]), "IDENTITY")
    _need(all(type(receipt[k]) is str and HEX.fullmatch(receipt[k]) for k in (
        "analysis_receipt_sha256", "source_snapshot_sha256", "factory_package_sha256",
        "lab_sha256", "strategy_definition_sha256", "config_sha256")), "PARENTS")
    _need(receipt["source_class"] == "FORWARD_UNQUALIFIED" and
          receipt["evidence_grade"] == "GENERATED_NATIVE_INTERFACE_TEST" and
          receipt["state"] == "WAIT_AUTHENTICATED_PARENTS_AND_RESEARCH_REVIEW" and
          all(receipt[k] is None for k in ("core_245_sha256", "core_253_sha256",
              "source_ack_sha256", "strategy_approval_sha256", "factory_consumer_ack_sha256")) and
          type(receipt["orders"]) is int and receipt["orders"] == 0 and
          receipt["trading_authority"] == "NONE" and receipt["pit_oos"] == "NOT_ATTESTED", "AUTHORITY")
    _need(type(receipt["decision_cutoff_ms"]) is int and receipt["decision_cutoff_ms"] >= 0 and
          type(receipt["expected_slots"]) is int and 8 <= receipt["expected_slots"] <= 672 and
          type(receipt["unknown_slots"]) is int and 0 <= receipt["unknown_slots"] <= receipt["expected_slots"], "COUNTS")
    return receipt


def _generated_root(root):
    """Reject direct-call original paths and linked SQLite/sidecar destinations."""
    location = Path(root).absolute()
    try:
        location.resolve().relative_to(Path(tempfile.gettempdir()).resolve())
    except ValueError:
        raise ValueError("FORWARD_SECRETARY_GENERATED_ROOT_OUTSIDE_TEMP") from None
    database = location / "warehouse.sqlite"
    paths = (location, *location.parents, database,
             Path(str(database) + "-wal"), Path(str(database) + "-shm"), Path(str(database) + "-journal"))
    for path in paths:
        if path.exists() or path.is_symlink():
            info = path.lstat()
            _need(not path.is_symlink() and
                  not (getattr(info, "st_file_attributes", 0) & 0x400),
                  "LINKED_PATH_DENIED")
            if path in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm"), Path(str(database) + "-journal")):
                _need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                      "LINKED_SQLITE_DENIED")
    return location


def route_forward_wait(root, receipt):
    """Append once via native Core connection; retry/readback return identical bytes."""
    validate_wait_receipt(receipt)
    root = _generated_root(root)
    from research_wp_r0.aql_core_backbone_local_v1 import _connect
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    con = _connect(root)
    try:
        con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (experiment_id TEXT PRIMARY KEY, sha TEXT NOT NULL, document TEXT NOT NULL)")
        con.execute("BEGIN IMMEDIATE")
        previous = con.execute(f"SELECT sha,document FROM {TABLE} WHERE experiment_id=?", (receipt["experiment_id"],)).fetchone()
        _need(previous is None or previous == (receipt["sha256"], encoded), "IMMUTABLE_CONFLICT")
        if previous is None:
            con.execute(f"INSERT INTO {TABLE} VALUES(?,?,?)", (receipt["experiment_id"], receipt["sha256"], encoded))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return read_forward_wait(root, receipt["experiment_id"])


def read_forward_wait(root, experiment_id):
    """Read an existing isolated Secretary DB without creating tables or files."""
    import sqlite3
    path = _generated_root(root) / "warehouse.sqlite"
    _need(path.is_file() and not path.is_symlink(), "STORE_MISSING")
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = con.execute(f"SELECT sha,document FROM {TABLE} WHERE experiment_id=?", (experiment_id,)).fetchone()
        _need(row is not None, "MISSING")
        receipt = validate_wait_receipt(json.loads(row[1]))
        _need(receipt["experiment_id"] == experiment_id and receipt["sha256"] == row[0], "READBACK")
        return receipt
    finally:
        con.close()
