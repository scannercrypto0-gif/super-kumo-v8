"""Offline adversarial checks for the new #303 material delta."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.binance_live_feed.consumer import project
from tools.binance_live_feed.feed import Feed, ROTATE_MS, normalize, rest_candle
from tools.binance_live_feed.quota import Limits, Quota, STREAMS
from tools.binance_live_feed.session import Session, check_depth_sequence
from tools.binance_live_feed.simulation import END, bbo, history, kline, prime, surge, trade, wire
from tools.binance_live_feed.interface import HISTORICAL_HEAD, check_contract, envelope


@pytest.fixture
def session(tmp_path):
    return Session(Feed(tmp_path/"feed"), Quota(tmp_path/"quota.sqlite", Limits(40, connections=6, subscriptions=8)))


def test_10x_two_workers_no_overshoot(tmp_path):
    evidence = surge(tmp_path/"shared.sqlite")
    assert (evidence["requests"], evidence["admitted"], evidence["window_weight"]) == (100,10,20)
    assert evidence["queue_high_water"] == evidence["queue_capacity"] == 8
    assert evidence["queue_rejected"] == 93


def test_separate_processes_share_one_ip_ledger(tmp_path):
    path = tmp_path/"ip.sqlite"
    Quota(path,Limits(20))
    worker = """from tools.binance_live_feed.quota import Quota, Limits
import sys
q = Quota(sys.argv[1], Limits(20))
admitted = 0
for _ in range(25):
    token = q.rest('klines', 100)
    if token:
        q.result(token, 100, 200)
        admitted += 1
print(admitted)
"""
    processes = [subprocess.Popen([sys.executable,"-B","-c",worker,str(path)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
    counts = []
    for proc in processes:
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, err.decode()
        counts.append(int(out))
    assert sum(counts) == 5


def test_ip_header_and_fixed_endpoint_weights(tmp_path):
    q = Quota(tmp_path/"shared.sqlite", Limits(50))
    token = q.rest("klines", 10)
    q.result(token, 11, 200, used_weight=24)
    assert q.rest("klines", 12) is None
    assert q.rest("klines", 60_001)
    with pytest.raises(KeyError):
        q.rest("order", 60_002)
    with pytest.raises(ValueError, match="UNKNOWN"):
        Limits(0)
    with pytest.raises(ValueError, match="POLICY_DRIFT"):
        Quota(q.path, Limits(100))


def test_raw_requests_and_weight_are_independent_windows(tmp_path):
    q = Quota(tmp_path/"ip.sqlite", Limits(100,raw_requests=4))
    for now in (10,11):
        token = q.rest("time",now)
        assert token
        q.result(token,now,200)
    assert q.rest("time",60_011) is None
    assert q.rest("time",300_010)


def test_429_5xx_half_open_418_shared_and_persistent(tmp_path):
    path = tmp_path/"shared.sqlite"
    q = Quota(path, Limits(40))
    token = q.rest("klines", 0)
    q.result(token, 1, 429, retry_after_ms=10_000)
    assert q.rest("time", 10_000) is None
    token = q.rest("klines", 10_001)
    assert token and q.rest("time", 10_001) is None
    q.result(token, 10_002, 503)
    with q.tx() as db:
        until = q.get(db,"retry_at")
    assert 12_002 <= until <= 12_252
    assert q.rest("time", until-1) is None
    token = q.rest("time", until)
    q.result(token, until+1, 418)
    restarted = Quota(path, Limits(40))
    assert restarted.rest("time", 1_000_000) is None
    assert not restarted.connect("new", 1_000_000, STREAMS)


def test_unanswered_request_expires_with_backoff(tmp_path):
    q = Quota(tmp_path/"shared.sqlite", Limits(40))
    assert q.rest("klines", 1, recovery=True)
    assert not q.expire_request(5000)
    assert q.expire_request(5001)
    assert q.rest("klines", 5002) is None
    token = q.rest("klines", 6300, recovery=True)
    q.result(token, 6301, 200)
    assert q.rest("klines", 7000, recovery=True) is None
    with pytest.raises(ValueError, match="CLOCK"):
        q.rest("time", 6999)


def test_ws_messages_subscriptions_and_ip_connections(tmp_path):
    q = Quota(tmp_path/"shared.sqlite", Limits(40, connections=6, subscriptions=8))
    assert not q.connect("bad", 1, ["wrong"])
    assert q.connect("a", 1, STREAMS)
    assert not q.connect("parallel", 1, STREAMS)
    assert q.ws("a", 2, "SUBSCRIBE", streams=tuple(STREAMS))
    assert not q.ws("a", 2, "SUBSCRIBE", streams=tuple(STREAMS))
    assert q.ws("a", 2, "PONG")
    assert not q.ws("a", 2, "PONG")
    assert not q.ws("a", 2, "PING")
    q.disconnect("a", 3, failed=False)
    for i in (4,6):
        assert q.connect(str(i),i,STREAMS)
        q.disconnect(str(i),i+1,failed=False)
    assert not q.connect("storm",8,STREAMS)
    assert q.connect("later",300_001,STREAMS)


def test_ping_reconnect_24h_and_expired_data(session):
    assert session.connect("a",100)
    assert session.ping(b"provider payload",20_100) == b"provider payload"
    assert not session.tick(80_100)
    assert not session.connect("early",80_101)
    assert session.connect("b",82_000)
    # Inject the persisted heartbeat checkpoint near the 24h boundary.
    # Heartbeat admission and timeout were checked separately above.
    with session.quota.tx() as db:
        db.execute("UPDATE sockets SET last_ping=? WHERE id='b'", (82_000+ROTATE_MS-20_000,))
    assert session.tick(82_000+ROTATE_MS-1)
    assert not session.tick(82_000+ROTATE_MS)
    assert session.research(82_000+ROTATE_MS)["bars"] == {}
    assert session.connect("c",82_000+ROTATE_MS+3000)
    assert session.research(82_000+ROTATE_MS+3001)["reason"] == "WARMUP_OR_ASOF"


def test_finality_native_contract_and_stale(session):
    prime(session)
    now = END+200
    view = session.research(now)
    assert view["records"]["bbo"]["event_ms"] is None
    assert all(r["first_known_at_ms"] is None for r in view["records"].values())
    assert project(view)["state"] == "OBSERVED_FIXTURE"
    assert project(view, embargo_or_holdout=((END-100, END+1000),))["reason"] == "EMBARGO_OR_HOLDOUT"
    session.receive(kline("1m",END+60_000,now+5,False,c="100.50"),now+6,lambda: now+7)
    assert session.research(now+10)["bars"]["1m"]["bar_close"] == END-1
    assert project(session.research(now+2001))["signal"] is None
    assert session.research(now+2001)["reason"] == "STALE_PRICE"


def test_pinned_historical_contract(session):
    prime(session)
    provided = os.environ.get("ATLAS_302_INTERFACE")
    if provided:
        raw = Path(provided).read_bytes()
    else:
        raw = subprocess.check_output(["git","show",HISTORICAL_HEAD+":tools/historical_source_qa/interface.json"])
    reference = json.loads(raw.decode("utf-8-sig"))
    for row in session.research(END+200)["records"].values():
        check_contract(reference,envelope(row))


def test_native_scanner_factory_kernel_and_stale_guard(session):
    from research_wp_r0.strategy_definition import StrategyDefinition
    indicator = {"op":"indicator","name":"trend","field":"value","lag":0}
    definition = StrategyDefinition({
        "schema_version":"1","strategy_id":"feed_fixture","strategy_version":"v1","scope":"RESEARCH_ONLY",
        "indicators":[{"name":"trend","indicator_id":"SMA_v1","version":"1","parameters":{"period":3},
                       "constraints":{"period":{"type":"int","min":2,"max":20}}}],
        "entry":{"op":"gt","left":indicator,"right":{"op":"constant","value":100}},
        "exit":{"op":"lt","left":indicator,"right":{"op":"constant","value":99}},
        "timing":{"decision":"CONFIRMED_CLOSE","entry_execution":"NEXT_ELIGIBLE_OPEN","ambiguity":"REJECT"},
        "risk":{"unit":"ENTRY_NOTIONAL","max_exposure":1,"max_leverage":1,"stop_fraction":.02,
                "target_fraction":.04,"entry_ttl_bars":2,"holding_bars":10}})
    prime(session)
    observed = project(session.research(END+200),definition=definition)
    assert observed["diagnostic"] == "UNKNOWN" and observed["signal"] is None
    stale = project(session.research(END+2500),definition=definition)
    assert stale == dict(state="UNKNOWN",reason="STALE_PRICE",signal=None,authority="NONE")


def test_late_final_never_becomes_actionable(session):
    assert session.connect("late",END-100)
    for raw, now in [(kline("15m",END,END+6000),END+6001),
                     (kline("1m",END,END+6000),END+6002),
                     (trade(1,END+6000),END+6003), (bbo(1),END+6004)]:
        session.receive(raw,now,lambda:now+1)
    assert session.research(END+6006)["reason"] == "STALE_FINAL_BAR"


@pytest.mark.parametrize("raw,when,reason", [
    (trade(1,END+10),END,"EVENT_CLOCK_FUTURE"),
    (wire("bookTicker",dict(u=1,b="102",a="100",B="1",A="1")),END,"CROSSED_BBO"),
    (wire("trade",dict(s="ETHUSDT",e="trade",E=1,T=1,t=1,p="1",q="1")),END,"SOURCE_IDENTITY"),
    (kline("1m",END,END-100),END-50,"FUTURE_FINAL_BAR"),
    (kline("1m",END,END+1,t=10),END+2,"KLINE_GRID"),
    (b"x"*4097,END,"FRAME_BOUND"),
])
def test_wire_attacks(raw, when, reason):
    with pytest.raises(ValueError, match=reason):
        normalize(raw,when)


def test_trade_gap_recovery_and_fresh_generation(session):
    prime(session)
    when = END+300
    assert session.receive(trade(1,END+140),when,lambda:when+1) == "DUPLICATE"
    with pytest.raises(ValueError, match="SEQUENCE_GAP"):
        session.receive(trade(3,when+1),when+2,lambda:when+3)
    assert session.research(when+3)["reason"] == "DISCONNECTED"
    with pytest.raises(ValueError, match="RECOVERY_NOT_EXPECTED"):
        session.feed.recover_trade(dict(id=4,time=when,price="100",qty="1"),when+4,lambda:when+5)
    assert session.feed.recover_trade(dict(id=2,time=when,price="100",qty="1"),when+4,lambda:when+5) == "STORED"
    assert session.connect("recovered",when+2000)
    assert session.receive(trade(3,when+2001),when+2002,lambda:when+2003) == "STORED"
    assert session.research(when+2004)["reason"] == "WARMUP_OR_ASOF"


def test_kline_gap_recovery_preserves_null_first_known(tmp_path):
    f = Feed(tmp_path/"feed")
    f.start(END-10)
    assert f.ingest(kline("1m",END,END+2),END+3,lambda:END+4) == "STORED"
    later = END+120_100
    with pytest.raises(ValueError, match="SEQUENCE_GAP"):
        f.ingest(kline("1m",END+120_000,later),later,lambda:later+1)
    with pytest.raises(ValueError, match="REST_OPEN_OR_STALE"):
        f.recover_candle(history(END),"1m",later,later-5000,lambda:later+2)
    assert f.recover_candle(history(END),"1m",later,later,lambda:later+2) == "STORED"
    with f.tx(read=True) as db:
        raw = db.execute("SELECT doc FROM records WHERE channel='1m' AND key=?", (str(END),)).fetchone()[0]
    assert json.loads(raw)["first_known_at_ms"] is None
    f.start(later+3)
    assert f.read(later+4)["bars"] == {}


def test_recovery_response_uses_shared_weight_and_spacing(session):
    prime(session)
    later = END+180_100
    # Reconnect to exercise sequence checking after a network outage.
    session.disconnect(END+1000,failed=False)
    assert session.connect("after-outage",later-100)
    with pytest.raises(ValueError,match="SEQUENCE_GAP"):
        session.receive(kline("1m",END+180_000,later),later,lambda:later+1)
    assert session.recover("1m",history(END),later+1,lambda:later+2,server_time=later) == "STORED"
    assert session.recover("1m",history(END+60_000),later+2,lambda:later+3,server_time=later) == "RECOVERY_BACKPRESSURE"
    assert session.recover("1m",history(END+60_000),later+1001,lambda:later+1002,server_time=later+1001) == "STORED"
    with session.quota.tx() as db:
        assert session.quota.used(db,"rest",later+1001,60_000) == 4
    assert session.research(later+1003)["bars"] == {}


def test_revision_rejected_and_original_retained(session):
    prime(session)
    with pytest.raises(ValueError, match="REVISION"):
        session.receive(kline("15m",END,END+220,c="100.50"),END+221,lambda:END+222)
    assert session.research(END+230)["bars"] == {}
    with session.feed.tx(read=True) as db:
        assert db.execute("SELECT COUNT(*) FROM records WHERE channel='15m'").fetchone() == (1,)


def test_depth_sequence_guard():
    snap = dict(lastUpdateId=4,receive_ms=100)
    assert check_depth_sequence(snap,[dict(U=4,u=6,E=110)],120) == 6
    with pytest.raises(ValueError,match="GAP"):
        check_depth_sequence(snap,[dict(U=6,u=7,E=110)],120)
    with pytest.raises(ValueError,match="STALE"):
        check_depth_sequence(snap,[],2200)


def test_storage_capacity_and_clock_regression(tmp_path):
    f = Feed(tmp_path/"feed",max_rows=4)
    f.start(10)
    for n in range(4):
        f.ingest(trade(n,10+n),10+n,lambda:11+n)
    with pytest.raises(ValueError,match="STORAGE_FULL"):
        f.ingest(trade(4,14),14,lambda:15)
    assert f.read(20)["bars"] == {}
    f = Feed(tmp_path/"other")
    f.start(10)
    with pytest.raises(ValueError,match="CLOCK_REGRESSION"):
        f.ingest(trade(1,8),9,lambda:11)
    assert f.read(20)["bars"] == {}


def test_database_tamper_and_unowned_store(session,tmp_path):
    prime(session)
    with session.feed.tx() as db:
        db.execute("UPDATE records SET ack=recv WHERE channel='trade'")
    assert session.research(END+210)["reason"] == "STORE_TAMPER"
    with pytest.raises(ValueError,match="UNOWNED"):
        Feed(tmp_path)


def test_hard_crash_after_data_commit(tmp_path):
    target = tmp_path/"crash"
    command = """from tools.binance_live_feed.feed import Feed
from tools.binance_live_feed.simulation import trade
from pathlib import Path
import sys
f=Feed(Path(sys.argv[1]))
f.start(100)
f.ingest(trade(1,101),102,lambda:103,crash=True)
"""
    proc = subprocess.run([sys.executable,"-B","-c",command,str(target)],capture_output=True,timeout=30)
    assert proc.returncode == 73, proc.stderr.decode()
    restarted = Feed(target)
    assert restarted.read(105)["bars"] == {}
    with pytest.raises(ValueError,match="UNCONFIRMED_COMMIT"):
        restarted.start(106)


def test_two_fresh_simulations_are_canonical(tmp_path):
    for label in ("a","b"):
        proc = subprocess.run([sys.executable,"-B","-m","tools.binance_live_feed.simulation",str(tmp_path/label)],
                              capture_output=True,timeout=90)
        assert proc.returncode == 0, proc.stderr.decode()
    assert (tmp_path/"a/report.json").read_bytes() == (tmp_path/"b/report.json").read_bytes()
