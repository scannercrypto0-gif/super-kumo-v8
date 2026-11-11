"""Focused tests for the new scheduled, bidirectional research delta."""
from pathlib import Path
import subprocess
import sys

import pytest

from tools.strategy_discoverer_offline import continuous_research as r

P = r.policy(origin=200,step=100,members={
    "BTC":{"sector":"benchmark","rank_eligible":False},
    "PAXG":{"sector":"gold","rank_eligible":False},
    "ALT":{"sector":"application","rank_eligible":True},
})


def snapshot(slot,bps):
    data = r.seal(dict(schema="aql.core.discoverer-snapshot.fixture.v1",slot=slot,venue="BINANCE",
                       market="SPOT",source_class="TEST_ONLY",authority="NONE",
                       membership_sha256=r._digest(P["members"]),
                       observations={s:dict(return_bps=v,onset=slot-100,end=slot-3,published=slot-2,
                                            received=slot-1,known_at=slot,receipt_sha256=r._digest([slot,s,v]))
                                     for s,v in bps.items()}))
    return data,data["sha256"]


def feature(query,name="liquidity", value=2,offset=-1,version=1):
    cutoff = query["cutoff_exclusive_ms"]
    return dict(feature=name,value=value,effective=cutoff-10,published=cutoff+offset,
                received=cutoff+offset,known_at=cutoff+offset,version=version,
                source_sha256=r._digest([name,value,version]),parent_sha256="1"*64 if version>1 else None,
                mode="MONITOR_ONLY")


def context(query):
    records = [feature(query),feature(query,"news",offset=1),feature(query,offset=2,version=2)]
    result = r.seal(dict(schema="aql.core.discoverer-context.fixture.v1",query_sha256=query["sha256"],
                         source_class="TEST_ONLY",records=records))
    return result,result["sha256"]


def tick(loop,slot,values,query=context):
    return loop.tick(slot,*snapshot(slot,values),query)


def test_bidirectional_and_quiet_controls(tmp_path):
    loop = r.Loop(tmp_path/"store",P,P["sha256"])
    first = tick(loop,200,{"ALT":200,"BTC":-200})
    assert first["watch"]["gainers"] == ["ALT"] and first["watch"]["losers"] == ["BTC"]
    assert first["watch"]["census"] == {"UP":1,"DOWN":1,"UNKNOWN":1}
    assert first["watch"]["top_alts"] == ["ALT"] and not first["candidates"]
    quiet = tick(loop,300,{"ALT":0,"BTC":0,"PAXG":0})
    assert quiet["watch"]["census"] == {"NO_EVENT":3}
    assert quiet["search_census"] == {"COMPLETE":3}
    assert {c["comparison"]["direction"] for c in quiet["candidates"]} == {"UP","DOWN"}
    for candidate in quiet["candidates"]:
        assert candidate["comparison"]["counts"]["CONTROL_TRIGGER"] == 1
        assert candidate["comparison"]["counts"]["EVENT_TRIGGER"] == 1
        assert candidate["comparison"]["denominator"] == 6
        assert candidate["holdout"] == "SEALED_UNOPENED"
    assert all("news" not in s["features"] and s["features"]["liquidity"]["version"]==1
               and s["excluded"]=={"OUTSIDE_PRE_ONSET":2} for s in quiet["samples"])
    assert not tick(loop,400,{"ALT":0,"BTC":0,"PAXG":0})["candidates"]
    forward_tick = tick(loop,500,{"ALT":200,"BTC":0,"PAXG":-200})
    for candidate in quiet["candidates"]:
        result = r.forward(candidate,candidate["sha256"],[(s,s["sha256"]) for s in forward_tick["samples"]])
        assert result["counts"] == {"TP":1,"FP":2}
        with pytest.raises(ValueError,match="FORWARD_CHRONOLOGY"):
            r.forward(candidate,candidate["sha256"],[(quiet["samples"][0],quiet["samples"][0]["sha256"])])


def test_bounded_poll_outage_and_gaps(tmp_path):
    loop = r.Loop(tmp_path/"store",P,P["sha256"])
    with pytest.raises(ValueError,match="UNRECORDED_SCHEDULE_GAP"):
        tick(loop,300,{"BTC":0})
    out = loop.poll(1000,lambda slot:None,context)
    assert len(out) == 4 and all(t["watch"]["census"]=={"MISSED":3} for t in out)
    assert loop.poll(500,lambda slot:None,context) == []
    with pytest.raises(ValueError,match="CLOCK_REGRESSION"):
        loop.poll(400,lambda slot:None,context)


def test_invalid_failed_and_no_event_preserved(tmp_path):
    def broken(query):
        if query["symbol"]=="BTC":
            raise OSError("offline Core fixture")
        return context(query)[0],"0"*64
    loop = r.Loop(tmp_path/"store",P,P["sha256"])
    result = tick(loop,200,{"ALT":0,"BTC":0},broken)
    assert result["search_census"] == {"FAILED":1,"INVALID":1,"UNAVAILABLE":1}
    assert result["watch"]["census"] == {"NO_EVENT":2,"UNKNOWN":1}
    assert not result["candidates"]


def test_exact_boundary_and_unknown_clock():
    query = r.context_query(P,{"symbol":"BTC","onset":100})
    rows = [feature(query,offset=0),{**feature(query,"news"),"known_at":None}]
    response = r.seal(dict(schema="aql.core.discoverer-context.fixture.v1",query_sha256=query["sha256"],
                           source_class="TEST_ONLY",records=rows))
    result = r.precursor(query,response,response["sha256"])
    assert result["features"] == {}
    assert result["excluded"] == {"UNKNOWN_CLOCK":1,"OUTSIDE_PRE_ONSET":1}


def test_crash_recovery_and_factory_ack(tmp_path):
    root = tmp_path/"store"
    child = """import sys
from tools.strategy_discoverer_offline.tests.test_continuous_research import P,snapshot,context,r
loop=r.Loop(sys.argv[1],P,P['sha256'])
loop.tick(200,*snapshot(200,{'ALT':200,'BTC':-200}),context,crash=True)
"""
    proc = subprocess.run([sys.executable,"-B","-c",child,str(root)],capture_output=True,timeout=30)
    assert proc.returncode == 73,proc.stderr.decode()
    loop = r.Loop(root,P,P["sha256"])
    with pytest.raises(ValueError,match="UNACKNOWLEDGED_PARENT"):
        tick(loop,300,{"ALT":0,"BTC":0})
    first = tick(loop,200,{"ALT":200,"BTC":-200})
    assert first == tick(loop,200,{"ALT":200,"BTC":-200})
    second = tick(loop,300,{"ALT":0,"BTC":0})
    c = second["candidates"][0]
    receipt = r.seal(dict(schema="aql.factory.discoverer-feedback.v1",candidate_sha256=c["sha256"],
                          status="UNKNOWN",authority="NONE",holdout="SEALED_UNOPENED",
                          factory_result_sha256="1"*64))
    ack = r.accept_factory_feedback(loop.journal,c,receipt,receipt["sha256"])
    assert r.accept_factory_feedback(loop.journal,c,receipt,receipt["sha256"]) == ack
    assert len(loop.journal.attempt_events()) == 3
    with pytest.raises(ValueError,match="CORE_OR_PLAN_PIN"):
        r.accept_factory_feedback(loop.journal,c,{**receipt,"status":"PASS"},receipt["sha256"])


def test_storage_pin_conflict_and_cpu_scope(tmp_path):
    root = tmp_path/"store"
    loop = r.Loop(root,P,P["sha256"])
    tick(loop,200,{"ALT":0})
    with pytest.raises(ValueError,match="IMMUTABLE_REPLAY_CONFLICT"):
        tick(loop,200,{"ALT":300})
    with pytest.raises(ValueError,match="POLL_BUDGET"):
        loop.poll(300,lambda slot:None,context,max_ticks=5)
    with pytest.raises(ValueError,match="SCHEDULE_BUDGET"):
        tick(loop,6600,{"ALT":0})


def test_separate_forward_freeze_and_settlement(tmp_path):
    loop = r.Loop(tmp_path/"store",P,P["sha256"])
    tick(loop,200,{"ALT":200,"BTC":-200})
    trained = tick(loop,300,{"ALT":0,"BTC":0})
    for candidate in trained["candidates"]:
        sources = {symbol: context(r.context_query(P,{"symbol":symbol,"onset":399}))
                   for symbol in ("ALT","BTC")}
        lock = r.freeze_predictions(tmp_path,candidate,candidate["sha256"],P,onset=400,issued=399,sources=sources)
        forward = r.settle_predictions(P,lock,lock["sha256"],*snapshot(500,{"ALT":200,"BTC":-200}))
        assert forward["counts"] == {"TP":1,"FP":1,"UNKNOWN":1} and forward["denominator"] == 3
        with pytest.raises(ValueError,match="PREDICTION_CHRONOLOGY"):
            r.freeze_predictions(tmp_path,candidate,candidate["sha256"],P,onset=400,issued=400,sources=sources)
        with pytest.raises(ValueError,match="CORE_SCOPE"):
            r.settle_predictions(P,lock,lock["sha256"],*snapshot(600,{"ALT":200,"BTC":-200}))


def test_bounded_soak_retains_quiet_search(tmp_path):
    loop = r.Loop(tmp_path/"store",P,P["sha256"])
    for index in range(24):
        slot = 200+100*index
        result = loop.poll(slot,lambda at:snapshot(at,{"ALT":0,"BTC":0,"PAXG":0}),context)[0]
        assert result["search_census"] == {"COMPLETE":3}
    assert len(loop.journal.attempt_events()) == 24
