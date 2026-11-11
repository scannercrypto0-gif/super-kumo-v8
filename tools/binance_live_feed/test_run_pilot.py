from contextlib import contextmanager
import json

import pytest

from tools.binance_live_feed.feed import Feed, canonical
from tools.binance_live_feed.run_pilot import capture, verify_exchange_info
from tools.binance_live_feed.simulation import bbo, kline, trade

START = 1_707_091_200_000
LIMITS = dict(rest_weight=6000, raw_requests=61_000, connections=300, ws_messages=5, subscriptions=1024)


class Clock:
    now_ms = START

    def now(self):
        return self.now_ms


class FixtureTransport:
    def __init__(self, clock, *, status=200, used="20"):
        self.clock = clock
        self.status = status
        self.used = used
        self.connected = False
        self.pongs = []
        self.calls = 0

    def exchange_info(self, timeout):
        self.calls += 1
        return self.status, {"x-mbx-used-weight-1m": self.used}, canonical({
            "rateLimits": [
                dict(rateLimitType="REQUEST_WEIGHT", interval="MINUTE", intervalNum=1, limit=6000),
                dict(rateLimitType="RAW_REQUESTS", interval="MINUTE", intervalNum=5, limit=61_000),
            ],
            "symbols": [dict(symbol="BTCUSDT", isSpotTradingAllowed=True)],
        })

    @contextmanager
    def stream(self, timeout):
        self.connected = True
        self.frames = iter(self.schedule())
        yield self

    def pong(self, payload):
        self.pongs.append(payload)

    def frame(self, connection, timeout):
        at, kind, payload = next(self.frames)
        self.clock.now_ms = at
        return kind, payload

    @staticmethod
    def schedule():
        for index in range(1, 121):
            now = START + 10_000 * index
            if index % 2 == 0:
                yield now, "ping", b"ping"
            yield now, "text", trade(index, now - 3)
            yield now, "text", bbo(index)
            if index % 6 == 0:
                yield now + 12, "text", kline("1m", now, now + 10)
            if index % 90 == 0:
                yield now + 15, "text", kline("15m", now, now + 13)


@pytest.fixture
def preflight():
    return dict(start_ms=START, source_rights_ref="fixture", region_entity_ref="fixture",
                egress_inventory_ref="fixture", clock_ref="fixture", custody_ref="fixture",
                clock_error_ms=10, clock_checked_ms=START-100, verified_limits=LIMITS)


def test_joined_capture_measures_without_pit_or_strategy_visibility(tmp_path, preflight):
    clock = Clock()
    transport = FixtureTransport(clock)
    out = tmp_path / "one-shot"
    quota = tmp_path / "shared.sqlite"
    report = capture(preflight, out, quota, transport=transport, clock=clock)
    assert report["quality"] == "PASS_FEED_QUALITY_NON_PIT", report
    assert report["pongs"] == len(transport.pongs) == 59
    assert report["rest_calls"] == report["ws_attempts"] == 1
    assert report["metrics"]["final_1m"]["n"] == 19
    assert report["metrics"]["final_15m"]["n"] == 1
    assert report["orders"] == 0 and report["pit_oos"] == "BLOCKED"
    feed = Feed(out / "capture", pilot=True)
    assert feed.read(clock.now())["reason"] == "PILOT_METRICS_ONLY"
    with feed.tx(read=True) as db:
        (raw,) = db.execute("SELECT doc FROM records LIMIT 1").fetchone()
    assert json.loads(raw)["evidence"] == "PUBLIC_WS_PILOT_NON_PIT"
    with pytest.raises(ValueError, match="UNOWNED_STORE"):
        Feed(out / "capture")
    with pytest.raises(FileExistsError):
        capture(preflight, out, quota, transport=transport, clock=Clock())
    assert transport.calls == 1


@pytest.mark.parametrize(("status", "used"), [(418, "20"), (429, "20"), (200, ""), (200, "3001")])
def test_rest_failure_blocks_ws(tmp_path, preflight, status, used):
    clock = Clock()
    transport = FixtureTransport(clock, status=status, used=used)
    report = capture(preflight, tmp_path / "out", tmp_path / "quota", transport=transport, clock=clock)
    assert report["quality"] == "FAIL_STOP"
    assert report["stop_reason"] == "REST_STATUS_OR_HEADROOM"
    assert not transport.connected


def test_missing_preflight_never_touches_transport(tmp_path, preflight):
    clock = Clock()
    transport = FixtureTransport(clock)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="MISSING_SOURCE_RIGHTS_REF"):
        capture({**preflight, "source_rights_ref": ""}, out, tmp_path / "quota",
                transport=transport, clock=clock)
    assert transport.calls == 0 and not out.exists()


def test_unknown_rate_window_stops():
    transport = FixtureTransport(Clock())
    _, _, raw = transport.exchange_info(4)
    doc = json.loads(raw)
    doc["rateLimits"].append(dict(rateLimitType="REQUEST_WEIGHT", interval="SECOND", intervalNum=10, limit=50))
    from tools.binance_live_feed.quota import Limits

    with pytest.raises(ValueError, match="REST_WINDOW_MISMATCH"):
        verify_exchange_info(canonical(doc), Limits(**LIMITS))


def test_websocket_framing_uses_real_library_without_network(monkeypatch):
    from socket import socketpair

    import websocket

    from tools.binance_live_feed.run_pilot import PublicTransport, WS_URL

    local, peer = socketpair()

    def connect(connection, url, **options):
        assert url == WS_URL and options["redirect_limit"] == 0
        connection.sock = local

    monkeypatch.setattr(websocket.WebSocket, "connect", connect)
    monkeypatch.setattr(websocket.WebSocket, "getstatus", lambda self: 101)
    transport = PublicTransport()
    with peer, transport.stream(1) as connection:
        peer.sendall(b"\x89\x04ping\x81\x02{}")
        assert transport.frame(connection, 1) == ("ping", b"ping")
        assert transport.frame(connection, 1) == ("text", b"{}")
        peer.sendall(b"\x81\x7e\x10\x01")
        with pytest.raises(ValueError, match="WS_FRAME_BOUND"):
            transport.frame(connection, 1)
