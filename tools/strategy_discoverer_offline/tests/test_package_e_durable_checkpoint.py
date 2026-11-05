"""Focused Package E closure: SQLite durability, restart, fault/forgery and replay.

Old Discoverer bounded tests intentionally not repeated by this workflow.
"""
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace

import pytest

from tools.strategy_discoverer_offline.durable_checkpoint_e import (
    DurableDiscovererCheckpoint, DurableDiscovererError,
)
from tools.strategy_discoverer_offline.tests.test_package_e_membership import (
    setup_case, admission,
)


def fixture():
    tmp = TemporaryDirectory()
    db = Path(tmp.name) / "discoverer-e.sqlite"
    case = setup_case()
    durable = DurableDiscovererCheckpoint(db)
    e,p,ledger,attempt,head,receipt,log_head = case
    checkpoint_sha = durable.append_ledger(ledger.to_dict_list())
    h,d,intake,membership = admission(case)
    return tmp,db,durable,case,checkpoint_sha,d


def test_restart_recovers_exact_ledger_and_membership():
    tmp,db,store,case,sha,decision = fixture()
    try:
        reopened=DurableDiscovererCheckpoint(db)
        assert reopened.read_latest_ledger()["checkpoint_sha"] == sha
        assert reopened.verify_membership(
            package=case[1], ledger_attempt_id=case[3],
            ledger_head_digest=case[4], ledger_reference="e-ledger",
        ).checkpoint_head == case[4]
    finally: tmp.cleanup()


def test_replaying_identical_ledger_is_idempotent():
    tmp,db,store,case,sha,d = fixture()
    try:
        assert DurableDiscovererCheckpoint(db).append_ledger(case[2].to_dict_list()) == sha
        assert len(store.ledger_snapshots()) == 1
    finally: tmp.cleanup()


def test_invalid_checkpoint_is_rejected_without_partial_write():
    tmp,db,store,case,sha,d = fixture()
    try:
        tampered=case[2].to_dict_list()
        tampered[0]["reason"]="forged"
        with pytest.raises(DurableDiscovererError, match="invalid ledger chain"):
            store.append_ledger(tampered)
        assert store.read_latest_ledger()["checkpoint_sha"]==sha
    finally: tmp.cleanup()


def test_conflicting_shorter_ledger_rejected():
    tmp,db,store,case,sha,d=fixture()
    try:
        with pytest.raises(DurableDiscovererError,match="conflicting ledger append"):
            store.append_ledger(case[2].to_dict_list()[:1])
        assert len(store.ledger_snapshots())==1
    finally: tmp.cleanup()


def test_append_only_growth_and_fresh_process_readback():
    tmp,db,store,case,sha,d=fixture()
    try:
        from tools.strategy_discoverer_offline.ledger import AttemptState
        ledger=case[2]
        ledger.register("attempt-e-002","new-id",case[1].family_id,
                        case[1].strategy_definition_digest,case[1].search_plan_digest,
                        case[0].nomination_digest)
        next_sha=store.append_ledger(ledger.to_dict_list())
        assert next_sha!=sha
        recovered=DurableDiscovererCheckpoint(db).ledger_snapshots()
        assert len(recovered)==2
        assert recovered[-1]["entries"][:len(recovered[0]["entries"])] == recovered[0]["entries"]
    finally: tmp.cleanup()


def test_durable_attempt_log_includes_reject_and_quarantine():
    tmp,db,store,case,sha,decision=fixture()
    try:
        values=[]
        for i,status in enumerate(["ELIGIBLE_FOR_FACTORY_RESEARCH",
                                   "REJECTED_OR_QUARANTINED_NOT_VERIFIED",
                                   "REJECTED_OR_QUARANTINED_NOT_VERIFIED"]):
            values.append(store.append_attempt(
                attempt_key=f"delivery-{i}",outcome=status,
                candidate_id=case[1].candidate_id,
                package_digest=case[1].package_digest,
                decision_digest=decision.decision_digest,
                reason=("valid","forged attempt","quarantined")[i],
            ))
        reopened=DurableDiscovererCheckpoint(db)
        assert [e["event_sha"] for e in reopened.attempt_events()]==values
        assert len(reopened.attempt_events())==3
    finally:tmp.cleanup()


def test_retry_event_exact_idempotency_and_changed_payload_conflict():
    tmp,db,store,case,sha,decision=fixture()
    try:
        args=dict(attempt_key="try-1",outcome="REJECTED",
                  candidate_id=case[1].candidate_id,
                  package_digest=case[1].package_digest,
                  decision_digest=decision.decision_digest,reason="bad proof")
        first=store.append_attempt(**args)
        assert DurableDiscovererCheckpoint(db).append_attempt(**args)==first
        with pytest.raises(DurableDiscovererError,match="idempotency conflict"):
            store.append_attempt(**dict(args,reason="different"))
        assert len(store.attempt_events())==1
    finally:tmp.cleanup()


def test_sql_transaction_rollback_on_invalid_event():
    tmp,db,store,case,sha,decision=fixture()
    try:
        with pytest.raises(DurableDiscovererError):
            store.append_attempt(attempt_key="bad",outcome="REJECTED",
                                 candidate_id="bad",package_digest="xyz",
                                 decision_digest=decision.decision_digest)
        assert store.attempt_events()==()
    finally:tmp.cleanup()


def test_tampering_persisted_rows_fails_closed():
    tmp,db,store,case,sha,decision=fixture()
    try:
        store.append_attempt(attempt_key="event-1",outcome="REJECTED",
                             candidate_id=case[1].candidate_id,
                             package_digest=case[1].package_digest,
                             decision_digest=decision.decision_digest)
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE handoff_attempts SET canonical_json='{}' WHERE sequence=1")
        with pytest.raises(DurableDiscovererError,match="tampered record"):
            DurableDiscovererCheckpoint(db).attempt_events()
    finally:tmp.cleanup()


def test_tampered_ledger_checkpoint_rejected_on_restart():
    tmp,db,store,case,sha,decision=fixture()
    try:
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE ledger_checkpoints SET checkpoint_sha=? WHERE sequence=1",
                         ("f"*64,))
        with pytest.raises(DurableDiscovererError,match="tampered record"):
            DurableDiscovererCheckpoint(db).read_latest_ledger()
    finally:tmp.cleanup()


def test_sqlite_incomplete_transaction_not_visible_after_reopen():
    tmp,db,store,case,sha,decision=fixture()
    try:
        conn=sqlite3.connect(db)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""INSERT INTO handoff_attempts
            (sequence,predecessor_sha,attempt_key,event_sha,canonical_json,schema_version)
            VALUES (1,?,?,?,?,?)""",
            ("0"*64,"incomplete","0"*64,"{}", "aql.discoverer.e.durable-checkpoint.v1"))
        conn.rollback()
        conn.close()
        assert DurableDiscovererCheckpoint(db).attempt_events()==()
    finally:tmp.cleanup()


def test_durable_checkpoint_is_not_unsigned_fake_membership():
    tmp,db,store,case,sha,decision=fixture()
    try:
        with pytest.raises(ValueError,match="not a member"):
            store.verify_membership(package=case[1],ledger_attempt_id="fabricated",
                                    ledger_head_digest=case[4],ledger_reference="e-ledger")
    finally:tmp.cleanup()
