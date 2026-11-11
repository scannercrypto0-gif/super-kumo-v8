"""Deterministic closed-loop fixtures and measured offline counters."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from math import ceil
from pathlib import Path

from tools.binance_live_feed.consumer import project
from tools.binance_live_feed.feed import Feed, INTERVALS, canonical, hash_bytes
from tools.binance_live_feed.quota import Limits, Quota, RecoveryQueue
from tools.binance_live_feed.session import Session
from tools.binance_live_feed.interface import SOURCE_MANIFEST, envelope

END = 900_000


def wire(stream, data):
    return canonical(dict(stream="btcusdt@" + stream, data={"s": "BTCUSDT", **data}))


def trade(sequence, event):
    return wire("trade", dict(e="trade", E=event, T=event-1, t=sequence, p="100.01", q="0.001"))


def bbo(sequence):
    return wire("bookTicker", dict(u=sequence, b="100", B="2", a="100.02", A="3"))


def kline(interval, end, event, final=True, **changes):
    row = dict(s="BTCUSDT", i=interval, t=end-INTERVALS[interval], T=end-1,
               x=final, o="100", h="101", l="99", c="100", v="3")
    return wire("kline_"+interval, dict(e="kline", E=event, k={**row, **changes}))


def history(open_ms, interval="1m"):
    return [open_ms, "100", "101", "99", "100", "3", open_ms+INTERVALS[interval]-1,
            "300", 2, "1", "100", "0"]


def prime(session):
    assert session.connect("socket-a", END-2000)
    samples = [
        ("15m", kline("15m", END, END+100), END+140),
        ("1m", kline("1m", END, END+130), END+160),
        ("trade", trade(1, END+140), END+170),
        ("bbo", bbo(10), END+180),
    ]
    for _, raw, received in samples:
        assert session.receive(raw, received, lambda: received+3) == "STORED"
    return samples


def percentile(values, fraction, minimum):
    if len(values) < minimum:
        return None
    return sorted(values)[ceil(len(values)*fraction)-1]


def distribution(values):
    return dict(n=len(values), p50_ms=percentile(values, .5, 1), p95_ms=percentile(values,.95,20),
                p99_ms=percentile(values,.99,100), max_ms=max(values,default=None))


def surge(path):
    limits = Limits(rest_weight=40, connections=6, ws_messages=5, subscriptions=8)
    first, second = Quota(path, limits), Quota(path, limits)

    def worker(quota):
        admitted = 0
        for _ in range(50):
            token = quota.rest("klines", 1000)
            if token:
                quota.result(token, 1000, 200)
                admitted += 1
        return admitted

    with ThreadPoolExecutor(2) as pool:
        allowed = sum(pool.map(worker, (first,second)))
    assert allowed == 10
    queue = RecoveryQueue(8)
    for i in range(100):
        queue.offer(str(i), "klines")
    assert queue.offer("essential", "time", essential=True)
    assert queue.dispatch(first, 1000) is None
    key, _, token = queue.dispatch(first, 61_001)
    assert key == "essential"
    first.result(token, 61_001, 200)
    connections = 0
    for attempt in range(10):
        at = 62_000+attempt*1000
        socket = f"storm-{attempt}"
        if second.connect(socket,at,("btcusdt@trade",)):
            connections += 1
            second.disconnect(socket,at+1,failed=False)
    assert connections == 3
    assert second.connect("new-window",362_001,("btcusdt@trade",))
    assert second.ws("new-window",362_002,"SUBSCRIBE",streams=("btcusdt@trade",))
    assert second.ws("new-window",362_002,"PONG")
    assert not second.ws("new-window",362_002,"PONG")
    return dict(workers=2, requests=100, admitted=allowed, denied=100-allowed,
                window_weight=20, mock_documented_weight=40, rest_headroom_pct=50,
                storm_connection_attempts=10, admitted_connections=connections,
                mock_connection_limit=6, ws_frames_admitted_in_one_second=2, ws_frame_limit=5,
                queue_high_water=queue.high_water, queue_rejected=queue.rejected,
                queue_capacity=queue.capacity)


def run(root):
    root = Path(root)
    root.mkdir()
    feed = Feed(root/"fixture")
    session = Session(feed, Quota(root/"quota.sqlite", Limits(40, subscriptions=8)))
    prime(session)
    for index in range(2, 122):
        now = END+200+10*index
        latency = 12+index%17
        assert session.receive(trade(index,now-latency), now, lambda: now+1) == "STORED"
        assert session.receive(bbo(100+index*2), now+2, lambda: now+3) == "STORED"
    cutoff = now+3
    view = session.research(cutoff)
    observation = project(view)
    assert observation["state"] == "OBSERVED_FIXTURE" and observation["signal"] is None
    assert session.research(cutoff+2100)["reason"] == "STALE_PRICE"
    with feed.tx(read=True) as db:
        stored = [(json.loads(raw),ack) for raw,ack in db.execute("SELECT doc,ack FROM records ORDER BY rowid")]
    trade_records = [row for row,_ in stored if row["channel"] == "trade"]
    quote_records = [row for row,_ in stored if row["channel"] == "bbo"]
    def intervals(values):
        return [b-a for a,b in zip(values,values[1:])]
    report = dict(schema="aql.binance.live-feed-simulation.v1", disposition="OFFLINE_RATE_LIMIT_SAFETY_PASS",
                  source="FIXTURE_ONLY", live_feed="NOT_RUN", real_pit_oos="BLOCKED", authority="NONE",
                  surge=surge(root/"surge.sqlite"), accepted_frames=len(stored),
                  trade_event_to_receive=distribution([r["receive_ms"]-r["event_ms"] for r in trade_records]),
                  trade_arrival_interval=distribution(intervals([r["receive_ms"] for r in trade_records])),
                  bbo_arrival_interval=distribution(intervals([r["receive_ms"] for r in quote_records])),
                  bbo_event_to_receive="NOT_ESTIMABLE_NO_EXCHANGE_EVENT_TIMESTAMP",
                  final_1m_delay=distribution([r["receive_ms"]-r["material"]["end_ms_exclusive"] for r,_ in stored if r["channel"]=="1m"]),
                  final_15m_delay=distribution([r["receive_ms"]-r["material"]["end_ms_exclusive"] for r,_ in stored if r["channel"]=="15m"]),
                  receive_to_observed_commit=distribution([ack-r["receive_ms"] for r,ack in stored]),
                  steady_fixture_latest_trade_age_ms=cutoff-view["records"]["trade"]["event_ms"],
                  simulated_max_no_event_gap_ms=2100, stale_signal_count=0,
                  read_only_consumer=observation,
                  source_manifest=SOURCE_MANIFEST,
                  source_envelopes={channel:envelope(row) for channel,row in view["records"].items()})
    result = {**report, "sha256":hash_bytes(canonical(report))}
    (root/"report.json").write_bytes(canonical(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    print(json.dumps(run(parser.parse_args().root), sort_keys=True))
