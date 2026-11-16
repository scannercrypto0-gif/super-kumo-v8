"""ATLAS Factory E immutable, versioned research results store (SQLite).

Owned by Factory. No external network, broker execution, trades, private source
archive storage, or historical/PIT promotion. Stores only SHA-sealed metadata,
attempt census and bounded redacted Lab/Paper result summaries.

An explicit history/source status is part of every experiment, not silently
derived from a synthetic software PASS.
"""
from __future__ import annotations

import json
import re
import sqlite3
from hashlib import sha256
from pathlib import Path

def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()

SCHEMA = "aql.factory.e.research-experiment.v1"
RESULT_SCHEMA = "aql.factory.e.research-store-receipt.v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
ALLOWED = {"SYNTHETIC_ENGINEERING_PASS", "HISTORICAL_SOURCE_BLOCKED",
           "RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT"}
ATTEMPT_STATES = {"SELECTED", "REJECTED", "UNKNOWN", "UNSCANNED",
                  "INELIGIBLE", "FAILED", "QUARANTINED", "NOT_VERIFIED"}
LANES = {"SCANNER", "DISCOVERER", "HISTORICAL_SOURCE"}
MAX_ATTEMPTS = 10000


class ResultsStoreError(ValueError):
    pass


def _need(ok, reason):
    if not ok:
        raise ResultsStoreError("FACTORY_E_" + reason)


def _sha(v):
    return type(v) is str and bool(HEX.fullmatch(v))


def _seal(body, field="sha256"):
    return {**body, field: digest(body)}


def _check_seal(doc, field="sha256"):
    _need(type(doc) is dict and _sha(doc.get(field))
          and digest({k: v for k, v in doc.items() if k != field}) == doc[field],
          "SEALED_DOCUMENT_TAMPER")


def _attempts(attempts):
    _need(type(attempts) is list and 0 < len(attempts) <= MAX_ATTEMPTS,
          "ATTEMPT_DENOMINATOR")
    ids = set()
    for v in attempts:
        _need(type(v) is dict and set(v) == {
            "attempt_id", "candidate_id", "state", "source_receipt_sha256"},
            "ATTEMPT_SHAPE")
        _need(type(v["attempt_id"]) is str and bool(v["attempt_id"])
              and len(v["attempt_id"]) <= 160 and v["attempt_id"] not in ids
              and type(v["candidate_id"]) is str and bool(v["candidate_id"])
              and len(v["candidate_id"]) <= 160
              and v["state"] in ATTEMPT_STATES
              and _sha(v["source_receipt_sha256"]), "ATTEMPT_ID_OR_POLICY")
        ids.add(v["attempt_id"])


def build_experiment(*, experiment_id, lane, source_status, source_sha256,
                     source_query_245_sha256, source_query_253_sha256,
                     strategy_definition_sha256, config_sha256,
                     code_sha256, environment_sha256,
                     parent_receipt_sha256, attempts, lab_receipt_sha256=None,
                     paper_receipt_sha256=None, result_sha256=None,
                     evidence_class="TEST_ONLY", historical_pit="NOT_ATTESTED",
                     holdout="SEALED_UNOPENED",
                     trading_authority="NONE", orders_created=0,
                     paper_positions=0, actual_fills=None):
    _need(type(experiment_id) is str and 0 < len(experiment_id) <= 160
          and re.fullmatch(r"[A-Za-z0-9_.:+-]+", experiment_id)
          and lane in LANES and source_status in ALLOWED, "EXPERIMENT_SCOPE")
    source_parents = (source_sha256, source_query_245_sha256,
                      source_query_253_sha256, strategy_definition_sha256,
                      config_sha256)
    if source_status == "HISTORICAL_SOURCE_BLOCKED":
        _need(all(x is None or _sha(x) for x in source_parents),
              "BLOCKED_UNKNOWN_PARENT_MUST_BE_NULL_OR_SHA")
    else:
        _need(all(_sha(x) for x in source_parents),
              "PARENT_SHA_REQUIRED")
    for item in (code_sha256, environment_sha256, parent_receipt_sha256):
        _need(_sha(item), "CODE_ENV_AND_BLOCKER_RECEIPT_REQUIRED")
    for item in (lab_receipt_sha256, paper_receipt_sha256, result_sha256):
        _need(item is None or _sha(item), "RESULT_SHA")
    _attempts(attempts)
    if source_status != "HISTORICAL_SOURCE_BLOCKED":
        _need(source_query_245_sha256 != source_query_253_sha256,
              "CORE_NATIVE_LOCAL_SHA_ALIAS")
    _need(evidence_class in ("TEST_ONLY", "RETROSPECTIVE_NON_PIT")
          and historical_pit == "NOT_ATTESTED"
          and holdout == "SEALED_UNOPENED"
          and trading_authority == "NONE"
          and orders_created == 0 and paper_positions == 0
          and actual_fills is None, "EVIDENCE_AUTHORITY")
    if source_status == "HISTORICAL_SOURCE_BLOCKED":
        _need(lab_receipt_sha256 is None and paper_receipt_sha256 is None
              and result_sha256 is None, "BLOCKED_CANNOT_HAVE_RESULTS")
    if lane == "DISCOVERER":
        _need(source_status != "RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT",
              "DISCOVERER_SOURCE_NOT_ATTESTED")
    body = {
        "schema": SCHEMA, "schema_version": 1,
        "experiment_id": experiment_id, "lane": lane,
        "source_status": source_status,
        "source_sha256": source_sha256,
        "core_245_price_query_sha256": source_query_245_sha256,
        "core_253_query_local_sha256": source_query_253_sha256,
        "strategy_definition_sha256": strategy_definition_sha256,
        "config_sha256": config_sha256,
        "code_sha256": code_sha256, "environment_sha256": environment_sha256,
        "parent_receipt_sha256": parent_receipt_sha256,
        "attempts": attempts, "attempt_count": len(attempts),
        "attempt_states": {state: sum(x["state"] == state for x in attempts)
                           for state in sorted(ATTEMPT_STATES)},
        "lab_receipt_sha256": lab_receipt_sha256,
        "paper_receipt_sha256": paper_receipt_sha256,
        "result_sha256": result_sha256,
        "evidence_class": evidence_class,
        "historical_pit": historical_pit, "holdout": holdout,
        "trading_authority": trading_authority,
        "orders_created": orders_created, "paper_positions": paper_positions,
        "actual_fills": actual_fills,
        "strategy_performance_accepted": False,
    }
    return _seal(body)


def _connect(path):
    p = Path(path)
    _need(p.suffix == ".sqlite" and p.parent.is_dir(),
          "STORE_PATH")
    con = sqlite3.connect(p, timeout=15)
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY, sha TEXT NOT NULL,
        document TEXT NOT NULL, immutable INTEGER NOT NULL DEFAULT 1
      );
      CREATE INDEX IF NOT EXISTS idx_experiment_sha ON experiments(sha);
    """)
    return con


def register_experiment(path, record):
    _check_seal(record)
    _need(record.get("schema") == SCHEMA
          and record.get("schema_version") == 1
          and record.get("strategy_performance_accepted") is False,
          "SCHEMA_OR_PROMOTION")
    # Canonical revalidation rules; no self-declared green status.
    expected = build_experiment(
        experiment_id=record["experiment_id"], lane=record["lane"],
        source_status=record["source_status"],
        source_sha256=record["source_sha256"],
        source_query_245_sha256=record["core_245_price_query_sha256"],
        source_query_253_sha256=record["core_253_query_local_sha256"],
        strategy_definition_sha256=record["strategy_definition_sha256"],
        config_sha256=record["config_sha256"],
        code_sha256=record["code_sha256"],
        environment_sha256=record["environment_sha256"],
        parent_receipt_sha256=record["parent_receipt_sha256"],
        attempts=record["attempts"],
        lab_receipt_sha256=record["lab_receipt_sha256"],
        paper_receipt_sha256=record["paper_receipt_sha256"],
        result_sha256=record["result_sha256"],
        evidence_class=record["evidence_class"],
        historical_pit=record["historical_pit"],
        holdout=record["holdout"],
        trading_authority=record["trading_authority"],
        orders_created=record["orders_created"],
        paper_positions=record["paper_positions"],
        actual_fills=record["actual_fills"])
    _need(expected == record, "SCHEMA_FIELDS_DRIFT")
    con = _connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        old = con.execute("SELECT sha, document FROM experiments WHERE experiment_id=?",
                          (record["experiment_id"],)).fetchone()
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
        _need(old is None or old == (record["sha256"], encoded),
              "IMMUTABLE_IDEMPOTENCY_CONFLICT")
        layout = _layout(con)
        _need(layout in (0, 1, 2), "UNKNOWN_LAYOUT_VERSION")
        if layout == 2:
            index = con.execute(
                "SELECT canonical_sha256,source_status,lane FROM experiment_index_v2 WHERE experiment_id=?",
                (record["experiment_id"],)).fetchone()
            if old is None:
                _need(index is None, "V2_ORPHAN_INDEX_ENTRY")
            else:
                _need(index == (record["sha256"],record["source_status"],
                                  record["lane"]), "V2_EXISTING_INDEX_DRIFT")
        if old is None:
            con.execute("INSERT INTO experiments(experiment_id,sha,document) VALUES(?,?,?)",
                        (record["experiment_id"],record["sha256"],encoded))
            if layout == 2:
                con.execute(
                    "INSERT INTO experiment_index_v2(experiment_id,canonical_sha256,source_status,lane) VALUES(?,?,?,?)",
                    (record["experiment_id"],record["sha256"],
                     record["source_status"],record["lane"]))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return _seal({
        "schema": RESULT_SCHEMA, "experiment_id": record["experiment_id"],
        "experiment_sha256": record["sha256"],
        "status": "STORED_IMMUTABLE" if old is None else "REPLAY_IDENTICAL",
        "source_status": record["source_status"],
        "trading_authority": "NONE", "orders_created": 0,
    })


def read_experiment(path, experiment_id, *, detached_snapshot=False):
    """Read a sealed experiment without initializing or migrating its store.

    Detached snapshots must be immutable copies with all WAL data checkpointed.
    Never use detached_snapshot on an active store.
    """
    p = Path(path)
    _need(p.suffix == ".sqlite" and p.is_file(), "STORE_PATH")
    options = "?mode=ro"
    if detached_snapshot:
        wal = p.with_name(p.name + "-wal")
        _need(not wal.exists() or wal.stat().st_size == 0, "SNAPSHOT_WAL_NOT_CHECKPOINTED")
        options += "&immutable=1"
    con = sqlite3.connect(p.resolve().as_uri() + options, uri=True, timeout=15)
    try:
        row = con.execute("SELECT sha, document FROM experiments WHERE experiment_id=?",
                          (experiment_id,)).fetchone()
        _need(row is not None, "EXPERIMENT_NOT_FOUND")
        obj = json.loads(row[1])
        _check_seal(obj)
        _need(obj["sha256"] == row[0], "DATABASE_SHA_TAMPER")
        _need(obj["experiment_id"] == experiment_id and obj["schema"] == SCHEMA
              and obj["schema_version"] == 1, "EXPERIMENT_SCHEMA_OR_ID")
        return obj
    finally:
        con.close()


def compare_experiments(path, left_id, right_id):
    left = read_experiment(path, left_id)
    right = read_experiment(path, right_id)
    keys = ("lane", "source_status", "source_sha256",
            "core_245_price_query_sha256", "core_253_query_local_sha256",
            "strategy_definition_sha256", "config_sha256",
            "evidence_class", "historical_pit")
    comparable = all(left[k] == right[k] for k in keys)
    return _seal({
        "schema": "aql.factory.e.research-experiment-comparison.v1",
        "left_experiment_sha256": left["sha256"],
        "right_experiment_sha256": right["sha256"],
        "comparison_status": ("SAME_ELIGIBLE_PARENT_SCOPE" if comparable
                              and left["source_status"] != "HISTORICAL_SOURCE_BLOCKED"
                              else "NOT_COMPARABLE_DISTINCT_OR_BLOCKED_SCOPE"),
        "profitability_comparison": "NOT_AUTHORIZED",
        "trading_authority": "NONE",
    })


# Store layout v2 is an additive, journaled migration. Existing v1 experiment
# documents and their original experiment SHA never change. Rollback is only
# allowed if no v2-only consumer evidence has been written.
LAYOUT_SCHEMA = "aql.factory.e.sqlite-layout.v2"
MIGRATION_SCHEMA = "aql.factory.e.store-layout-migration.v1"


def _layout(con):
    row = con.execute("PRAGMA user_version").fetchone()
    return row[0]


def migrate_store_v2(path, *, fail_after_step=None):
    """Atomic v1->v2 metadata migration; no mutation of historical receipts.

    A caller can inject a pre-commit failure and prove a clean rollback.
    The new metadata table is an append-only receipt index; ordinary v1
    registration remains compatible. v2 records must be reproducible from
    immutable canonical documents, not a caller-supplied receipt.
    """
    _need(fail_after_step in (None, "metadata", "backfill"), "FAULT_POINT")
    con = _connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        current = _layout(con)
        _need(current in (0, 1, 2), "UNKNOWN_LAYOUT_VERSION")
        if current == 2:
            con.rollback()
            return _seal({"schema": MIGRATION_SCHEMA, "operation": "UPGRADE",
                          "status": "ALREADY_V2", "layout_version": 2,
                          "experiment_count": con.execute(
                              "SELECT count(*) FROM experiments").fetchone()[0]})
        # Each operation uses SQLite's rollback journal/WAL transaction.
        con.execute("""CREATE TABLE IF NOT EXISTS experiment_index_v2(
          experiment_id TEXT PRIMARY KEY,
          canonical_sha256 TEXT NOT NULL,
          source_status TEXT NOT NULL,
          lane TEXT NOT NULL,
          FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
        )""")
        if fail_after_step == "metadata":
            raise ResultsStoreError("FACTORY_E_INJECTED_MIGRATION_CRASH")
        rows = con.execute("SELECT experiment_id,sha,document FROM experiments ORDER BY experiment_id").fetchall()
        for experiment_id, pinned_sha, encoded in rows:
            try:
                item = json.loads(encoded)
                _check_seal(item)
                _need(item["sha256"] == pinned_sha
                      and item["experiment_id"] == experiment_id,
                      "MIGRATION_PARENT_CONFLICT")
                con.execute(
                    "INSERT INTO experiment_index_v2(experiment_id,canonical_sha256,source_status,lane) VALUES(?,?,?,?)",
                    (experiment_id,pinned_sha,item["source_status"],item["lane"]))
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ResultsStoreError("FACTORY_E_MIGRATION_CORRUPT_ROW") from exc
        if fail_after_step == "backfill":
            raise ResultsStoreError("FACTORY_E_INJECTED_MIGRATION_CRASH")
        con.execute("PRAGMA user_version = 2")
        con.commit()
        return _seal({"schema": MIGRATION_SCHEMA, "operation": "UPGRADE",
                      "status": "UPGRADED_V2", "layout_version": 2,
                      "experiment_count": len(rows)})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rollback_store_v1(path, *, fail_before_commit=False):
    """Atomic downgrade of the additive index. Never alters sealed v1 docs."""
    _need(type(fail_before_commit) is bool, "FAULT_POINT")
    con = _connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        current = _layout(con)
        _need(current in (0, 1, 2), "UNKNOWN_LAYOUT_VERSION")
        if current < 2:
            con.rollback()
            return _seal({"schema": MIGRATION_SCHEMA, "operation": "ROLLBACK",
                          "status": "ALREADY_V1", "layout_version": current})
        count = con.execute("SELECT count(*) FROM experiments").fetchone()[0]
        index_rows = con.execute("SELECT experiment_id,canonical_sha256,source_status,lane FROM experiment_index_v2 ORDER BY experiment_id").fetchall()
        rows = con.execute("SELECT experiment_id,sha,document FROM experiments ORDER BY experiment_id").fetchall()
        _need(len(index_rows) == len(rows) == count, "ROLLBACK_INDEX_DRIFT")
        for idx, row in zip(index_rows, rows):
            item=json.loads(row[2])
            _check_seal(item)
            _need(idx == (row[0],row[1],item["source_status"],item["lane"]),
                  "ROLLBACK_PARENT_DRIFT")
        con.execute("DROP TABLE experiment_index_v2")
        if fail_before_commit:
            raise ResultsStoreError("FACTORY_E_INJECTED_ROLLBACK_CRASH")
        con.execute("PRAGMA user_version = 1")
        con.commit()
        return _seal({"schema": MIGRATION_SCHEMA, "operation": "ROLLBACK",
                      "status": "ROLLED_BACK_V1", "layout_version": 1,
                      "experiment_count": count})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def audit_store_layout(path):
    """Read-only full document/index census for restart/recovery gate."""
    con=_connect(path)
    try:
        version=_layout(con)
        _need(version in (0,1,2), "UNKNOWN_LAYOUT_VERSION")
        rows=con.execute("SELECT experiment_id,sha,document FROM experiments ORDER BY experiment_id").fetchall()
        for experiment_id,pin,serialized in rows:
            obj=json.loads(serialized)
            _check_seal(obj)
            _need(obj["experiment_id"]==experiment_id and obj["sha256"]==pin,
                  "STORE_ROW_MUTATION")
        if version == 2:
            indexed=con.execute("SELECT experiment_id,canonical_sha256,source_status,lane FROM experiment_index_v2 ORDER BY experiment_id").fetchall()
            _need(len(indexed)==len(rows), "STORE_INDEX_MISSING_ROW")
            for row, idx in zip(rows,indexed):
                obj=json.loads(row[2])
                _need(idx==(row[0],row[1],obj["source_status"],obj["lane"]),
                      "STORE_INDEX_MISMATCH")
        return _seal({"schema":LAYOUT_SCHEMA,"layout_version":version,
                      "experiment_count":len(rows),
                      "all_document_shas":[r[1] for r in rows],
                      "trading_authority":"NONE"})
    finally:
        con.close()
