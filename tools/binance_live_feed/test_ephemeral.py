"""Focused opt-in delta; all transport data are injected fixtures."""

import pytest

from tools.binance_live_feed.ephemeral import EphemeralFeed, MODE
from tools.binance_live_feed.run_pilot import capture
from tools.binance_live_feed.simulation import bbo, kline, trade, wire
from tools.binance_live_feed.test_run_pilot import Clock, FixtureTransport, LIMITS, START


@pytest.fixture
def admission():
    return dict(start_ms=START, source_rights_ref="fixture", region_entity_ref="fixture",
                egress_inventory_ref="fixture", clock_ref="fixture", custody_ref="fixture",
                clock_error_ms=10, clock_checked_ms=START-100, verified_limits=LIMITS,
                capture_mode=MODE, memory_safety_ref="fixture")


def run(root, admission, transport, clock, *, out="out"):
    return capture(admission, root/out, root/"quota.sqlite", transport=transport, clock=clock,
                   ephemeral=True)


def check_outputs(root):
    assert {p.name for p in (root/"out").iterdir()} == {"activation.json", "report.json"}
    for path in root.rglob("*"):
        if path.is_file():
            payload = path.read_bytes()
            assert b"RAW_SENTINEL" not in payload
            assert trade(1, START+9997) not in payload


def test_ephemeral_native_runner_success_and_restart(tmp_path, admission):
    clock = Clock()
    transport = FixtureTransport(clock)
    report = run(tmp_path, admission, transport, clock)
    assert report["quality"] == "PASS_EPHEMERAL_FEED_QUALITY_NON_PIT"
    assert report["metrics"]["final_15m"]["n"] == 1
    assert "commit" not in report["metrics"] and report["metrics"]["processing"]["n"]
    assert report["custody"] == "RAW_CUSTODY_NOT_AVAILABLE" and not report["raw_persisted"]
    assert report["native_research"]["factory"] == "EVALUATION_PENDING"
    assert report["native_research"]["core"] == report["native_research"]["scanner"] == "RAW_CUSTODY_NOT_AVAILABLE"
    assert report["native_research"]["discoverer"] == "RAW_CUSTODY_NOT_AVAILABLE"
    assert report["orders"] == 0 and report["pit_oos"] == "BLOCKED"
    check_outputs(tmp_path)
    restart = FixtureTransport(Clock())
    with pytest.raises(FileExistsError):
        run(tmp_path, admission, restart, Clock())
    shared = run(tmp_path, admission, restart, Clock(), out="different")
    assert shared["rest_calls"] == restart.calls == 0 and shared["ws_attempts"] == 0


@pytest.mark.parametrize("status", [418,429])
def test_ephemeral_shared_rest_stop(tmp_path, admission, status):
    clock = Clock()
    transport = FixtureTransport(clock, status=status)
    report = run(tmp_path, admission, transport, clock)
    assert report["stop_reason"] == "REST_STATUS_OR_HEADROOM" and not transport.connected
    check_outputs(tmp_path)


def test_ephemeral_redacts_input_failure(tmp_path, admission):
    class Rejected(FixtureTransport):
        def frame(self, connection, timeout):
            raise ValueError("RAW_SENTINEL: do not persist")
    clock = Clock()
    report = run(tmp_path, admission, Rejected(clock), clock)
    assert report["stop_reason"] == "EPHEMERAL_INPUT_OR_TRANSPORT_STOP"
    check_outputs(tmp_path)


def test_ephemeral_disconnect_stop(tmp_path, admission):
    class Disconnected(FixtureTransport):
        def frame(self, connection, timeout):
            raise TimeoutError("RAW_SENTINEL")
    clock = Clock()
    report = run(tmp_path, admission, Disconnected(clock), clock)
    assert report["quality"] == "FAIL_STOP" and report["ws_attempts"] == 1
    check_outputs(tmp_path)


def test_mode_preflight_before_transport(tmp_path, admission):
    clock = Clock()
    transport = FixtureTransport(clock)
    with pytest.raises(ValueError, match="MISSING_MEMORY_SAFETY_REF"):
        run(tmp_path, {**admission,"memory_safety_ref":""}, transport, clock)
    assert transport.calls == 0 and not (tmp_path/"out").exists()
    with pytest.raises(ValueError, match="EPHEMERAL_FLAG_REQUIRED"):
        capture(admission, tmp_path/"out", tmp_path/"quota.sqlite", transport=transport, clock=clock)


def test_bounded_memory_and_disposal():
    feed = EphemeralFeed(max_rows=2)
    feed.start(START)
    received = START+100
    raw = trade(1, received-2)
    assert feed.ingest(raw, received, lambda: received) == "STORED"
    assert feed.ingest(raw, received, lambda: received) == "DUPLICATE"
    assert feed.ingest(bbo(1), received, lambda: received) == "STORED"
    with pytest.raises(ValueError, match="EPHEMERAL_BACKPRESSURE"):
        feed.ingest(bbo(2), received, lambda: received)
    assert len(feed.identities) == 2
    feed.dispose()
    assert not feed.identities and not feed.last and not any(feed.samples.values())
    with pytest.raises(ValueError, match="EPHEMERAL_RECONNECT_REQUIRES_NEW_AUTHORIZATION"):
        feed.start(received)


@pytest.mark.parametrize("wire_record,error", [
    (lambda now: trade(3, now-2), "SEQUENCE_GAP"),
    (lambda now: trade(0, now-2), "OUT_OF_ORDER"),
    (lambda now: trade(2, now+2), "EVENT_CLOCK_FUTURE"),
    (lambda now: wire("bookTicker",dict(s="ETHUSDT")), "SOURCE_IDENTITY"),
])
def test_ephemeral_source_sequence_and_clock(wire_record, error):
    feed = EphemeralFeed()
    feed.start(START)
    received = START+100
    feed.ingest(trade(1, received-2), received, lambda: received)
    with pytest.raises(ValueError, match=error):
        feed.ingest(wire_record(received), received, lambda: received)


def test_ephemeral_partial_stays_distinct():
    feed = EphemeralFeed()
    feed.start(START)
    end=START+60_000
    feed.ingest(kline("1m",end,end-100,final=False),end-50,lambda:end-49)
    assert feed.counts["1m:partial"] == 1 and feed.metrics()["final_1m"]["n"] == 0
    feed.ingest(kline("1m",end,end+2),end+3,lambda:end+4)
    assert feed.counts["1m"] == 1 and feed.metrics()["final_1m"]["n"] == 1
    assert feed.read(end+4)["reason"] == "RAW_CUSTODY_NOT_AVAILABLE"


def test_ephemeral_stale_trade_stops_without_persistence(tmp_path, admission):
    class Stale(FixtureTransport):
        @staticmethod
        def schedule():
            yield START+5000, "text", trade(1, START+1000)

    clock = Clock()
    report = run(tmp_path, admission, Stale(clock), clock)
    assert report["stop_reason"] == "STALE_TRADE_STOP"
    check_outputs(tmp_path)
