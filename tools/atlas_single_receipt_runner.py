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


def verify_controlled_egress(plan, pin, *, now, verifier):
    """Read a reservation from an independently trusted local egress authority.

    The injected authority must authenticate current ingress to its shared ledger,
    including the host's route and the reservation. Caller JSON is not an authority.
    """
    need(verifier is not None, "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE")
    record = verifier.read_verified_reservation(plan_pin=pin, endpoint=plan["endpoint"])
    need(isinstance(record, dict), "CONTROLLED_EGRESS_EVIDENCE_INVALID")
    need(record.get("plan_pin") == pin and record.get("endpoint") == plan["endpoint"],
         "CONTROLLED_EGRESS_SCOPE_MISMATCH")
    need(all(isinstance(record.get(key), str) and record[key].strip()
             for key in ("authority_ref", "egress_identity", "reservation_ref")),
         "CONTROLLED_EGRESS_EVIDENCE_INVALID")
    observed, expires = record.get("observed_ms"), record.get("expires_ms")
    need(type(observed) is int and type(expires) is int and
         0 <= now - observed <= 5000 and expires >= now + plan["wall_ms"],
         "CONTROLLED_EGRESS_EVIDENCE_STALE")
    used, limit = record.get("reserved_and_used"), record.get("limit")
    need(type(used) is int and type(limit) is int and 1 <= used <= limit // 2,
         "CONTROLLED_EGRESS_HEADROOM_UNVERIFIED")
    return record["reservation_ref"]


def preflight(plan, pin, *, now, clock_checked_ms, offline, egress_evidence=None,
              owner_waiver=None):
    need(plan == prepare(plan["slot"], plan["uncertainty_ms"]) and digest(plan) == pin, "PLAN_PIN")
    need(0 <= now - clock_checked_ms <= 300000, "CLOCK_STALE")
    need(plan["slot"] <= now <= plan["slot"] + 5000, "OUTSIDE_START")
    # This path records an explicit plan-bound waiver, never verified headroom.
    need(egress_evidence is None, "EGRESS_VERIFIER_UNAVAILABLE")
    if offline is True:
        need(owner_waiver is None, "OFFLINE_WAIVER_NOT_ALLOWED")
        return "SHARED_EGRESS_UNVERIFIED"
    need(offline is False and owner_waiver == pin, "SHARED_EGRESS_UNVERIFIED")
    return "OWNER_WAIVED_SHARED_IP_HEADROOM_UNVERIFIED"


def run(root, *, plan, pin, clock, clock_checked_ms, quota, transport, offline,
        owner_waiver=None):
    """One attempt; the transport must honor the supplied absolute budget."""
    start, monotonic = clock.now(), clock.monotonic_ns()
    egress = preflight(plan, pin, now=start, clock_checked_ms=clock_checked_ms,
                       offline=offline, owner_waiver=owner_waiver)
    if offline:
        need(not isinstance(transport, BinanceReceiptTransport), "OFFLINE_TRANSPORT_REQUIRED")
    else:
        need(type(transport) is BinanceReceiptTransport, "LIVE_TRANSPORT_REQUIRED")
    root = dedicated_root(root, "atlas-single-receipt-offline" if offline else "atlas-single-receipt-live")
    # Filesystem creation is atomic and keeps the run consumed across restarts,
    # including a crash or a failure before the first frame.
    with (root / "attempt.json").open("x", encoding="utf-8") as stream:
        json.dump({"plan": plan, "pin": pin, "egress": egress,
                   "started_ms": start, "clock_checked_ms": clock_checked_ms}, stream, sort_keys=True)
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

    quota_time = start
    try:
        with transport.stream(plan["endpoint"], min(5, (end - check_window()) / 1000)) as connection:
            ws_upgrade_status(connection.getstatus())
            while True:
                now = check_window()
                kind, raw = transport.frame(connection, (end - now) / 1000)
                received = check_window()
                if kind == "ping":
                    quota_time = received
                    need(quota.ws("receipt-15m", received, "PONG"), "PONG_QUOTA")
                    connection.pong(raw)
                    continue
                need(kind == "text" and type(raw) is bytes and len(raw) <= MAX_RAW,
                     "INVALID_FRAME")
                data = json.loads(raw, object_pairs_hook=unique_json_keys)
                kline = data["k"]
                if (not offline and kline["s"] == "BTCUSDT" and kline["i"] == "15m"
                        and kline["t"] == plan["slot"] - STEP and received < plan["slot"] + 5000):
                    continue
                need(kline["s"] == "BTCUSDT" and kline["i"] == "15m" and
                     kline["t"] == plan["slot"], "CANDLE_IDENTITY")
                if kline["x"] is False:
                    continue
                persist_frame(root, raw, slot=plan["slot"], received=received,
                              uncertainty=plan["uncertainty_ms"], monotonic_ns=clock.monotonic_ns(),
                              session=pin[:24])
                break
    finally:
        quota.disconnect("receipt-15m", quota_time, failed=False)
    check_window()
    materialize(root, synthetic=offline)
    cutoff = check_window()
    _, seal, _ = load_frame(root)
    return readback(root, cutoff_ms=cutoff, synthetic=offline, expected_receipt_sha256=seal)
