"""Actual native durable journal, synthetic execution assumptions only."""
from dataclasses import asdict
from decimal import Decimal as D
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from aql.paper_sim.contracts import Policy, digest
from aql.paper_sim.engine import PaperSimulator


def signal(**changes):
    value=dict(schema="aql.paper-sim.signal.v1",signal_id="a"*64,strategy_id="fixture",
               strategy_version="v1",definition_sha256="b"*64,config_sha256="c"*64,
               evaluator_sha256="d"*64,source_sha256="e"*64,symbol="BTCUSDT",interval_ms=60000,
               decision_ms=60000,source_close_ms=59999,available_ms=60000,
               evidence_mode="SYNTHETIC_TESTED",trading_authority="NONE")
    value.update(changes);return value


def watch(instance="one",policy=None,**changes):
    return dict(op="watch",at_ms=60000,signal=signal(**changes),
                policy=asdict(policy or Policy()),instance=instance)


def arm(**changes):
    value=dict(op="arm",at_ms=60001,mode="taker",qty="1",limit="100",stop="95",target="110",
               expiry_ms=299999,queue_ahead="0")
    value.update(changes);return value


def candle(start=120000,**changes):
    value=dict(symbol="BTCUSDT",open_ms=start,close_ms=start+59999,received_ms=start+60000,
               open="100",high="102",low="98",close="101",final=True,clock_verified=True,
               synthetic=True,taker_qty="10",maker_volume="10")
    value.update(changes)
    return dict(op="bar",at_ms=value["received_ms"],bar=value)


def setup_sim(tmp_path,*,policy=None,arm_changes=None):
    path=tmp_path/"isolated.jsonl";sim=PaperSimulator(path)
    w=watch(policy=policy);sid=sim.identity(w)
    sim.apply(sid,"watch",w)
    sim.apply(sid,"arm",arm(**(arm_changes or {})))
    return sim,sid,path


def test_full_lifecycle_cash_fees_once_and_restart(tmp_path):
    sim,sid,path=setup_sim(tmp_path)
    state=sim.apply(sid,"entry",candle())
    assert state["phase"]=="TRIGGERED" and state["filled"]=="1"
    ending=candle(180000,high="112",low="99",close="111")
    state=sim.apply(sid,"target",ending)
    assert state["phase"]=="CLOSED"
    entry=D("100")*D("1.0003");exit_=D("110")*D(".9997")
    assert D(state["fees"])==(entry+exit_)*D(".001")
    assert D(state["net_pnl"])==exit_-entry-D(state["fees"])
    original=path.read_bytes()
    assert sim.apply(sid,"target",ending)==state
    assert path.read_bytes()==original
    restored=PaperSimulator(path)
    assert restored.states[sid]==state
    exposed=restored.states;exposed[sid]["cash"]="999999"
    assert restored.states[sid]["cash"]==state["cash"]


def test_same_bar_stop_and_target_is_unknown_no_pnl(tmp_path):
    sim,sid,_=setup_sim(tmp_path)
    state=sim.apply(sid,"ambiguous",candle(low="94",high="111"))
    assert state["phase"]=="UNKNOWN" and state["net_pnl"] is None
    assert len(state["fills"])==1  # actual modeled entry exposure retained


def test_stop_gap_uses_worse_open_not_optimistic_stop(tmp_path):
    sim,sid,_=setup_sim(tmp_path);sim.apply(sid,"entry",candle())
    state=sim.apply(sid,"gap",candle(180000,open="90",high="112",low="89",close="95"))
    assert state["phase"]=="CLOSED" and state["reason"]=="STOP_GAP"
    assert D(state["fills"][-1]["price"])==D("90")*D(".9997")


def test_maker_queue_partial_fill_and_adverse_selection_cost(tmp_path):
    sim,sid,_=setup_sim(tmp_path,arm_changes=dict(mode="maker",limit="99",queue_ahead="2"))
    state=sim.apply(sid,"queue",candle(low="98",maker_volume="2"))
    assert state["filled"]=="0"
    state=sim.apply(sid,"partial",candle(180000,low="98",maker_volume=".4"))
    assert D(state["filled"])==D(".4") and state["phase"]=="TRIGGERED"
    assert state["fills"][0]["execution_ms"] is None
    assert state["fills"][0]["assumed_execution_window"]==[180000,239999]
    assert D(state["adverse_cost"])==D(".4")*99*D(".0001")
    state=sim.apply(sid,"cancel_remainder",dict(op="cancel",at_ms=240001))
    assert state["phase"]=="TRIGGERED" and state["entry_remaining"]=="0"
    state=sim.apply(sid,"target",candle(240000,high="112",low="99",close="111"))
    assert state["phase"]=="CLOSED" and D(state["exited"])==D(".4")


@pytest.mark.parametrize("changes,reason",[
    ({"low":"99"},"TOUCH_DOES_NOT_PROVE_QUEUE_FILL"),
    ({"low":"98","maker_volume":None},"MAKER_QUEUE_VOLUME_UNAVAILABLE"),
    ({"open":"98","low":"97"},"POST_ONLY_MARKETABLE_OR_GAP"),
    ({"low":"94"},"MAKER_ENTRY_EXIT_ORDER_UNKNOWN")])
def test_maker_unknowns_never_manufacture_pnl(tmp_path,changes,reason):
    sim,sid,_=setup_sim(tmp_path,arm_changes=dict(mode="maker",limit="99"))
    state=sim.apply(sid,"bar",candle(**changes))
    assert state["phase"]=="UNKNOWN" and state["reason"]==reason and state["net_pnl"] is None


def test_partial_taker_entry_and_exit_do_not_overfill(tmp_path):
    sim,sid,_=setup_sim(tmp_path)
    state=sim.apply(sid,"partial",candle(taker_qty=".4"))
    assert D(state["filled"])==D(".4")
    sim.apply(sid,"request",dict(op="exit",at_ms=180001))
    # First following open precedes receipt of exit request; no retroactive open fill.
    state=sim.apply(sid,"before_known",candle(180000,taker_qty=".1"))
    assert state["exited"]=="0"
    state=sim.apply(sid,"exit_partial",candle(240000,taker_qty=".1"))
    assert D(state["exited"])==D(".1") and state["phase"]=="TRIGGERED"
    state=sim.apply(sid,"exit_rest",candle(300000,taker_qty="10"))
    assert state["phase"]=="CLOSED" and D(state["exited"])==D(".4")


def test_maker_fallback_is_explicit_later_open_with_taker_cost(tmp_path):
    sim,sid,_=setup_sim(tmp_path,policy=Policy(allow_fallback=True),
                       arm_changes=dict(mode="maker",limit="97",expiry_ms=179999))
    sim.apply(sid,"unfilled",candle(low="98"))
    sim.apply(sid,"fallback",dict(op="fallback",at_ms=180001,expiry_ms=299999))
    state=sim.apply(sid,"already_open",candle(180000))
    assert state["filled"]=="0"
    state=sim.apply(sid,"next_open",candle(240000))
    assert state["phase"]=="TRIGGERED" and state["fills"][0]["liquidity"]=="ASSUMED_TAKER"
    assert D(state["fees"])==D(state["entry_notional"])*D(".001")


def test_no_fill_requires_complete_expiry_coverage(tmp_path):
    sim,sid,_=setup_sim(tmp_path,arm_changes=dict(mode="maker",limit="97",expiry_ms=179999))
    sim.apply(sid,"bar",candle(low="98"))
    assert sim.apply(sid,"expire",dict(op="expire",at_ms=180001))["phase"]=="NO_FILL"


def test_missing_future_is_unknown_not_expired_no_fill(tmp_path):
    sim,sid,_=setup_sim(tmp_path,arm_changes=dict(expiry_ms=179999))
    state=sim.apply(sid,"expire",dict(op="expire",at_ms=180001))
    assert state["phase"]=="UNKNOWN" and state["reason"]=="EXPIRY_COVERAGE_UNAVAILABLE"


@pytest.mark.parametrize("change",[{"final":False},{"clock_verified":False},{"synthetic":False},
    {"received_ms":999999},{"high":"NaN"},{"low":"103"},{"taker_qty":"-1"},{"symbol":"ETHUSDT"}])
def test_bad_bar_leaves_durable_state_unchanged(tmp_path,change):
    sim,sid,path=setup_sim(tmp_path);before=path.read_bytes()
    command=candle(**change);command["at_ms"]=180000
    with pytest.raises(ValueError):sim.apply(sid,"bad",command)
    assert path.read_bytes()==before and sim.states[sid]["phase"]=="ARMED"


def test_missing_depth_unknown_and_cost_stress(tmp_path):
    sim,sid,_=setup_sim(tmp_path)
    assert sim.apply(sid,"unknown",candle(taker_qty=None))["phase"]=="UNKNOWN"
    low=Policy(taker_fee_bps="1",half_spread_bps="0",slippage_bps="0")
    high=Policy(taker_fee_bps="20",half_spread_bps="5",slippage_bps="5")
    results=[]
    for policy in (low,high):
        w=watch(instance=policy.taker_fee_bps,policy=policy);key=sim.identity(w)
        sim.apply(key,"w",w);sim.apply(key,"a",arm())
        sim.apply(key,"in",candle())
        results.append(D(sim.apply(key,"out",candle(180000,high="112",low="99",close="111"))["net_pnl"]))
    assert results[1]<results[0]


def test_duplicates_conflicts_gaps_terminal_and_bounds(tmp_path):
    sim,sid,path=setup_sim(tmp_path);before=path.read_bytes()
    with pytest.raises(ValueError):sim.apply(sid,"arm",arm(qty="2"))
    with pytest.raises(ValueError):sim.apply(sid,"gap",candle(180000))
    assert path.read_bytes()==before
    sim.apply(sid,"cancel",dict(op="cancel",at_ms=60002))
    with pytest.raises(ValueError):sim.apply(sid,"late",candle())
    small=PaperSimulator(tmp_path/"small.jsonl",max_events=1)
    w=watch();key=small.identity(w);small.apply(key,"w",w)
    with pytest.raises(ValueError):small.apply(key,"a",arm())


def test_two_same_symbol_strategies_and_frozen_versions_are_independent(tmp_path):
    sim=PaperSimulator(tmp_path/"multi.jsonl")
    keys=[]
    for name in ("alpha","beta"):
        w=watch(strategy_id=name);key=sim.identity(w);keys.append(key)
        sim.apply(key,"watch",w);sim.apply(key,"arm",arm());sim.apply(key,"entry",candle())
    assert keys[0]!=keys[1] and len(sim.states)==2
    sim.apply(keys[0],"out",candle(180000,high="112",low="99",close="111"))
    assert sim.states[keys[0]]["phase"]=="CLOSED" and sim.states[keys[1]]["phase"]=="TRIGGERED"
    with pytest.raises(ValueError):sim.apply(keys[1],"watch",watch(strategy_version="v2"))


def test_real_process_exit_after_fsync_before_memory_update_recovers(tmp_path):
    w=watch();key=PaperSimulator.identity(w);path=tmp_path/"crash.jsonl"
    code="from aql.paper_sim.engine import PaperSimulator; import os,json; s=PaperSimulator("+repr(str(path))+",post_commit=lambda:os._exit(23)); s.apply("+repr(key)+",'watch',json.loads("+repr(json.dumps(w))+"))"
    result=subprocess.run([sys.executable,"-B","-c",code],env=os.environ.copy(),capture_output=True)
    assert result.returncode==23,result.stderr.decode()
    reopened=PaperSimulator(path)
    assert reopened.states[key]["phase"]=="WATCH"
    before=path.read_bytes();reopened.apply(key,"watch",w)
    assert path.read_bytes()==before


def test_torn_record_and_stale_writer_are_rejected(tmp_path):
    sim,sid,path=setup_sim(tmp_path)
    stale=PaperSimulator(path)
    sim.apply(sid,"bar",candle())
    with pytest.raises(ValueError):stale.apply(sid,"cancel",dict(op="cancel",at_ms=180001))
    with path.open("ab") as f:f.write(b'{"torn":')
    with pytest.raises(ValueError):PaperSimulator(path)


@pytest.mark.parametrize("field,value",[("taker_fee_bps","-1"),("slippage_bps","NaN"),
    ("maker_fee_bps","1001"),("allow_fallback",1),("version",2),("max_notional","20000")])
def test_policy_negative_guards(field,value):
    with pytest.raises(ValueError):Policy(**{field:value})
