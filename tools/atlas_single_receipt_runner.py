"""Bounded one-shot orchestration. Transport and clock are supplied by the caller."""
import json
import os

from aql.observation.contracts import digest
from tools.atlas_prospective_observe import FIXTURE, dedicated_root
from tools.atlas_single_receipt import (
    MAX_RAW, STEP, load_frame, materialize, need, persist_frame, readback,
    reserve_once, unique_json_keys, ws_upgrade_status,
)

ENDPOINT = "wss://data-stream.binance.vision/ws/btcusdt@kline_15m"


class BinanceReceiptTransport:
    """Use the pinned #305 TLS and framing implementation for one native stream."""

    def __init__(self):
        from tools.binance_live_feed.run_pilot import PublicTransport
        self.transport = PublicTransport()

    def stream(self, endpoint, timeout):
        need(endpoint == ENDPOINT, "WS_ENDPOINT_NOT_ALLOWED")
        return self.transport.stream(timeout, endpoint=endpoint)

    def frame(self, connection, timeout):
        return self.transport.frame(connection, timeout)


def prepare(slot, uncertainty_ms):
    need(type(slot) is int and slot >= 0 and slot % STEP == 0, "SLOT_GRID")
    need(type(uncertainty_ms) is int and 0 <= uncertainty_ms <= 250, "CLOCK_UNCERTAINTY")
    fixture = json.loads(FIXTURE.read_text())[0]
    return dict(endpoint=ENDPOINT, slot=slot, uncertainty_ms=uncertainty_ms,
                fixture_sha256=fixture["sha256"], strategy=fixture["payload"]["definition"]["digest"],
                config=fixture["payload"]["config_digest"], raw_cap=MAX_RAW,
                grace_ms=300000, wall_ms=1500000, rest_requests=0)


def preflight(plan, pin, *, now, clock_checked_ms, offline, egress_evidence=None):
    need(plan == prepare(plan["slot"], plan["uncertainty_ms"]) and digest(plan) == pin, "PLAN_PIN")
    need(0 <= now - clock_checked_ms <= 300000, "CLOCK_STALE")
    need(plan["slot"] <= now <= plan["slot"] + 5000, "OUTSIDE_START")
    # Until a real controlled-egress evidence verifier is integrated, there is
    # no caller input that can turn this rehearsal into a live authorization.
    need(egress_evidence is None, "EGRESS_VERIFIER_UNAVAILABLE")
    need(offline is True, "SHARED_EGRESS_UNVERIFIED")
    return "SHARED_EGRESS_UNVERIFIED"


def run(root, *, plan, pin, clock, clock_checked_ms, quota, transport, offline):
    """One attempt; the transport must honor the supplied absolute budget."""
    start, monotonic = clock.now(), clock.monotonic_ns()
    egress = preflight(plan, pin, now=start, clock_checked_ms=clock_checked_ms, offline=offline)
    need(not isinstance(transport, BinanceReceiptTransport), "OFFLINE_TRANSPORT_REQUIRED")
    root = dedicated_root(root, "atlas-single-receipt-offline")
    # Filesystem creation is atomic and keeps the run consumed across restarts,
    # including a crash or a failure before the first frame.
    with (root / "attempt.json").open("x", encoding="utf-8") as stream:
        json.dump({"plan": plan, "pin": pin, "egress": egress}, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    reserve_once(quota, start)
    end = min(start + plan["wall_ms"], plan["slot"] + STEP - 1 + plan["grace_ms"])

    def check_window():
        now = clock.now()
        elapsed = (clock.monotonic_ns() - monotonic) // 1000000
        need(0 <= elapsed < plan["wall_ms"] and start <= now < end, "DEADLINE")
        need(abs(now - start - elapsed) <= plan["uncertainty_ms"], "CLOCK_STEP")
        return now

    try:
        with transport.stream(plan["endpoint"], min(5, (end - check_window()) / 1000)) as connection:
            ws_upgrade_status(connection.getstatus())
            while True:
                now = check_window()
                kind, raw = transport.frame(connection, (end - now) / 1000)
                received = check_window()
                if kind == "ping":
                    need(quota.ws("receipt-15m", received, "PONG"), "PONG_QUOTA")
                    connection.pong(raw)
                    continue
                need(kind == "text" and type(raw) is bytes and len(raw) <= MAX_RAW,
                     "INVALID_FRAME")
                data = json.loads(raw, object_pairs_hook=unique_json_keys)
                kline = data["k"]
                need(kline["s"] == "BTCUSDT" and kline["i"] == "15m" and
                     kline["t"] == plan["slot"], "CANDLE_IDENTITY")
                if kline["x"] is False:
                    continue
                persist_frame(root, raw, slot=plan["slot"], received=received,
                              uncertainty=plan["uncertainty_ms"], monotonic_ns=clock.monotonic_ns(),
                              session=pin[:24])
                break
    finally:
        quota.disconnect("receipt-15m", clock.now(), failed=False)
    check_window()
    materialize(root, synthetic=True)
    cutoff = check_window()
    _, seal, _ = load_frame(root)
    return readback(root, cutoff_ms=cutoff, synthetic=True, expected_receipt_sha256=seal)
