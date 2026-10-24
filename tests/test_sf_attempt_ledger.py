"""Real disposable SQLite durability boundaries, not hardware certification."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sf_research_int_01 import candidate, fixture, protocol, BASE_MS, IMS, spec
from research_wp_r0.strategy_definition import AttemptRecorder, StrategyDefinition
from research_wp_r0.attempt_ledger import AttemptLedger, STATE_MAPPING, prepare_durable_candidate


def event(state="PENDING", **changes):
    e=dict(state=state,family_id="family",candidate_id="candidate",
           input_digest="a"*64,strategy_digest="b"*64)
    e.update(changes);return e


def test_typed_mapping_and_legacy_absence():
    assert {r.main_state:r.legacy_state for r in STATE_MAPPING} == dict(
        PENDING="ABSENT", INVALID="INELIGIBLE", FAILED="FAILED", ABANDONED="ABSENT", COMPLETE="COMPLETE")


def test_real_append_reopen_detached_snapshot_and_external_checkpoint(tmp_path):
    ledger=AttemptLedger(tmp_path/"ledger.db");e=event()
    ack=ledger.record_attempt(e);e["candidate_id"]="mutated"
    (tmp_path/"independently-saved.json").write_text(json.dumps(ack))
    reopened=AttemptLedger(ledger.path,expected_checkpoint=tuple(json.loads((tmp_path/"independently-saved.json").read_text())))
    events, cp=reopened.snapshot();assert cp==ack and events==[event()]
    events[0]["state"]="BAD";assert reopened.snapshot()[0]==[event()]
    db=sqlite3.connect(ledger.path)
    try: assert db.execute("PRAGMA journal_mode").fetchone()[0]=="wal"
    finally:db.close()


@pytest.mark.parametrize("terminal", ["FAILED","ABANDONED"])
def test_terminal_paths_and_identical_replay_after_restart(tmp_path,terminal):
    l=AttemptLedger(tmp_path/"db");l.record_attempt(event());cp=l.record_attempt(event(terminal))
    reopened=AttemptLedger(l.path,expected_checkpoint=cp)
    assert reopened.record_attempt(event())==cp
    assert reopened.record_attempt(event(terminal))==cp
    assert len(reopened.snapshot()[0])==2


@pytest.mark.parametrize("state", ["INVALID","FAILED"])
def test_initial_error_accounting(tmp_path,state):
    l=AttemptLedger(tmp_path/"db");e=event(state,error_type="ValueError")
    l.record_attempt(e);assert l.snapshot()[0]==[e]


@pytest.mark.parametrize("change", [{"strategy_digest":"c"*64},{"error_type":"different"}])
def test_same_id_conflict_rejected(tmp_path,change):
    l=AttemptLedger(tmp_path/"db");cp=l.record_attempt(event())
    with pytest.raises(ValueError,match="Conflicting"):l.record_attempt(event(**change))
    assert l.snapshot()[1]==cp


@pytest.mark.parametrize("bad", [event("COMPLETE",result_digest="c"*64),event("UNKNOWN"),
    event("ABANDONED"),event(input_digest=None),event(input_digest="BAD"),
    event(extra=1),event(family_id=""),event(strategy_digest=None)])
def test_schema_and_completion_gate(tmp_path,bad):
    l=AttemptLedger(tmp_path/"db")
    with pytest.raises((ValueError,TypeError)):l.record_attempt(bad)
    assert l.snapshot()[0]==[]


def test_error_size_and_external_anchor_mismatch(tmp_path):
    l=AttemptLedger(tmp_path/"db");anchor=l.record_attempt(event())
    with pytest.raises(ValueError):l.record_attempt(event("FAILED",error_type="x"*129))
    with pytest.raises(ValueError):AttemptLedger(l.path,expected_checkpoint=(1,"f"*64))
    assert l.snapshot()[1]==anchor


def test_family_candidate_uniqueness_and_terminal_conflict(tmp_path):
    l=AttemptLedger(tmp_path/"db");l.record_attempt(event())
    with pytest.raises(ValueError):l.record_attempt(event(input_digest="c"*64))
    l.record_attempt(event("FAILED"))
    with pytest.raises(ValueError):l.record_attempt(event("ABANDONED"))


def test_real_bridge_and_immutable_input_receipt_no_complete(tmp_path):
    l=AttemptLedger(tmp_path/"db");_,_,acc=fixture()
    args=(StrategyDefinition(spec()).to_json(),"family","candidate",acc,"BTC1M",1,
          BASE_MS,BASE_MS+9*IMS,BASE_MS+10*IMS,protocol())
    prepared,inputs=prepare_durable_candidate(l,*args)
    events,cp=l.snapshot();assert [e["state"] for e in events]==["PENDING","INPUTS"]
    assert json.loads(events[-1]["inputs"])["state"]=="INPUTS_ONLY_NOT_EVALUATED"
    prepare_durable_candidate(l,*args);assert l.snapshot()[1]==cp
    with pytest.raises(ValueError):AttemptRecorder(l).finish(prepared,"COMPLETE",result_digest="d"*64)
    assert l.snapshot()[1]==cp


def test_existing_bridge_invalid_failed_abandoned(tmp_path):
    for name,raw,kw,expected in [("invalid",'{"bad":1}',{},["INVALID"]),
                              ("failed",None,{"symbol_mapping":"OTHER"},["PENDING","FAILED"])]:
        l=AttemptLedger(tmp_path/name)
        with pytest.raises(ValueError):candidate(AttemptRecorder(l),raw,**kw)
        assert [e["state"] for e in l.snapshot()[0]]==expected
    l=AttemptLedger(tmp_path/"abandoned");prepared,_=candidate(AttemptRecorder(l))
    AttemptRecorder(l).finish(prepared,"ABANDONED")
    assert l.snapshot()[0][-1]["state"]=="ABANDONED"


@pytest.mark.parametrize("mode",["payload","hash","sequence","delete","version"])
def test_corruption_reopen_fail_closed(tmp_path,mode):
    l=AttemptLedger(tmp_path/"db");anchor=l.record_attempt(event())
    with sqlite3.connect(l.path) as db:
        if mode=="payload":db.execute("UPDATE receipts SET payload=?",(b'{"torn":',))
        if mode=="hash":db.execute("UPDATE receipts SET chain_hash=?",("f"*64,))
        if mode=="sequence":db.execute("UPDATE receipts SET seq=2")
        if mode=="delete":db.execute("DELETE FROM receipts")
        if mode=="version":db.execute("PRAGMA user_version=2")
    with pytest.raises((ValueError,sqlite3.DatabaseError)):AttemptLedger(l.path,expected_checkpoint=anchor)


def test_truncated_database_and_missing_anchored_file(tmp_path):
    l=AttemptLedger(tmp_path/"db");anchor=l.record_attempt(event())
    db=sqlite3.connect(l.path);db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.close()
    with l.path.open("r+b") as f:f.truncate(128)
    with pytest.raises((ValueError,sqlite3.DatabaseError)):AttemptLedger(l.path,expected_checkpoint=anchor)
    with pytest.raises(ValueError):AttemptLedger(tmp_path/"absent",expected_checkpoint=anchor)
    assert not (tmp_path/"absent").exists()


@pytest.mark.parametrize("committed",[True,False])
def test_real_process_exit_commit_and_uncommitted_write(tmp_path,committed):
    l=AttemptLedger(tmp_path/"db");anchor=l.record_attempt(event())
    code='''import os,sys,sqlite3
from research_wp_r0.attempt_ledger import AttemptLedger
l=AttemptLedger(sys.argv[1])
if sys.argv[2]=="True":
 l.record_attempt(dict(state="FAILED",family_id="family",candidate_id="candidate",input_digest="a"*64,strategy_digest="b"*64))
else:
 d=sqlite3.connect(sys.argv[1]);d.execute("BEGIN IMMEDIATE");d.execute("UPDATE receipts SET payload=?",(b"torn",))
os._exit(93)
'''
    r=subprocess.run([sys.executable,"-B","-c",code,str(l.path),str(committed)],cwd=Path(__file__).resolve().parents[1],capture_output=True,timeout=15)
    assert r.returncode==93,r.stderr
    events,cp=AttemptLedger(l.path,expected_checkpoint=anchor).snapshot()
    assert len(events)==(2 if committed else 1)
    assert events[0]==event()


def test_concurrent_duplicate_is_single_receipt(tmp_path):
    l=AttemptLedger(tmp_path/"db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(lambda _: l.record_attempt(event()),range(8)))
    assert len(set(receipts))==1 and len(l.snapshot()[0])==1


def test_real_sink_abort_no_ack(tmp_path):
    l=AttemptLedger(tmp_path/"db")
    with sqlite3.connect(l.path) as db:db.execute("CREATE TRIGGER deny_insert BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'injected write failure'); END")
    with pytest.raises(sqlite3.DatabaseError):candidate(AttemptRecorder(l))
    assert l.snapshot()[0]==[]


def test_inputs_ack_failure_propagates(tmp_path):
    l=AttemptLedger(tmp_path/"db")
    original=l.record_attempt
    def reject_inputs(e):
        if e["state"]=="INPUTS":raise OSError("input receipt write failed")
        return original(e)
    l.record_attempt=reject_inputs
    _,_,acc=fixture()
    with pytest.raises(OSError):prepare_durable_candidate(l,StrategyDefinition(spec()).to_json(),"family","candidate",acc,"BTC1M",1,BASE_MS,BASE_MS+9*IMS,BASE_MS+10*IMS,protocol())
    assert [e["state"] for e in l.snapshot()[0]]==["PENDING"]


def test_path_replacement_rejected(tmp_path):
    l=AttemptLedger(tmp_path/"db");l.record_attempt(event())
    other=AttemptLedger(tmp_path/"replacement");other.record_attempt(event(candidate_id="other"))
    # Disposable databases closed; replacing the pathname is never a reopen ACK.
    l.path.rename(tmp_path/"original");other.path.rename(l.path)
    with pytest.raises(ValueError,match="replaced"):l.snapshot()
