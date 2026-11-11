"""One-shot Binance Spot public feed quality probe. Requires verified host preflight."""
import argparse
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import ssl
import time
from uuid import uuid4

from tools.binance_live_feed.feed import Feed, canonical, hash_bytes, need, normalize
from tools.binance_live_feed.quota import Limits, Quota, STREAMS
from tools.binance_live_feed.session import Session
from tools.binance_live_feed.simulation import distribution

REST_HOST = "data-api.binance.vision"
WS_URL = "wss://data-stream.binance.vision/stream?streams=" + "/".join(sorted(STREAMS))
CUSTODY_BYTES = 64 * 1024 * 1024


class Clock:
    def __init__(self):
        self.utc = time.time_ns() // 1_000_000
        self.monotonic = time.monotonic_ns()

    def now(self):
        projected = self.utc + (time.monotonic_ns() - self.monotonic) // 1_000_000
        need(abs(projected - time.time_ns() // 1_000_000) <= 250, "LOCAL_CLOCK_STEP")
        return projected


class PublicTransport:
    def exchange_info(self, timeout):
        conn = http.client.HTTPSConnection(REST_HOST, timeout=timeout, context=ssl.create_default_context())
        try:
            conn.request("GET", "/api/v3/exchangeInfo?symbol=BTCUSDT")
            response = conn.getresponse()
            body = response.read(65_537) if response.status == 200 else b""
            need(len(body) <= 65_536, "REST_BODY_BOUND")
            return response.status, dict((k.lower(), v) for k, v in response.getheaders()), body
        finally:
            conn.close()

    @contextmanager
    def stream(self, timeout):
        import websocket

        connection = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True})
        try:
            connection.settimeout(timeout)
            connection.connect(WS_URL, redirect_limit=0, http_no_proxy=["data-stream.binance.vision"])
            need(connection.getstatus() == 101, "WS_UPGRADE")
            receive = connection.frame_buffer.recv_strict

            def bounded_receive(size):
                need(size <= 4096, "WS_FRAME_BOUND")
                return receive(size)

            connection.frame_buffer.recv_strict = bounded_receive
            yield connection
        finally:
            connection.shutdown()

    def frame(self, connection, timeout):
        import websocket

        end = time.monotonic() + timeout
        receive = connection.frame_buffer.recv

        def timed_receive(size):
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise websocket.WebSocketTimeoutException("frame deadline")
            connection.settimeout(remaining)
            return receive(size)

        connection.frame_buffer.recv = timed_receive
        try:
            frame = connection.recv_frame()
        except websocket.WebSocketTimeoutException as exc:
            # A timeout can interrupt a frame. Stop instead of resuming mid-frame.
            raise TimeoutError("WS_READ_TIMEOUT") from exc
        finally:
            connection.frame_buffer.recv = receive
        need(frame.fin and not frame.mask_value and not (frame.rsv1 or frame.rsv2 or frame.rsv3),
             "WS_UNEXPECTED_FRAMING")
        kind = {websocket.ABNF.OPCODE_TEXT: "text", websocket.ABNF.OPCODE_PING: "ping"}.get(frame.opcode)
        need(kind is not None, "WS_CLOSED_OR_UNSUPPORTED_FRAME")
        return kind, frame.data


def validate_preflight(preflight, now):
    start = preflight["start_ms"]
    need(type(start) is int and start % 900_000 == 0 and start <= now < start + 5_000,
         "OUTSIDE_DECLARED_START")
    for field in ("source_rights_ref", "region_entity_ref", "egress_inventory_ref", "clock_ref", "custody_ref"):
        need(isinstance(preflight[field], str) and bool(preflight[field].strip()), "MISSING_" + field.upper())
    error = preflight["clock_error_ms"]
    checked = preflight["clock_checked_ms"]
    need(type(error) is int and abs(error) <= 250 and type(checked) is int
         and 0 <= now - checked <= 300_000, "UNVERIFIED_CLOCK")
    declared = preflight["verified_limits"]
    need(set(declared) == {"rest_weight", "raw_requests", "connections", "ws_messages", "subscriptions"},
         "UNVERIFIED_QUOTA_FIELDS")
    limits = Limits(**declared)
    need(limits.rest_weight >= 40 and limits.connections >= 2
         and limits.subscriptions >= 8 and limits.ws_messages >= 5, "INSUFFICIENT_QUOTA")
    return limits, start + 1_200_000


def verify_exchange_info(body, limits):
    doc = json.loads(body)
    windows = {(item["rateLimitType"], item["interval"], item["intervalNum"]): item["limit"]
               for item in doc["rateLimits"]}
    expected = {
        ("REQUEST_WEIGHT", "MINUTE", 1): limits.rest_weight,
        ("RAW_REQUESTS", "MINUTE", 5): limits.raw_requests,
    }
    need(all(windows.get(key) == cap for key, cap in expected.items())
         and all(key in expected or key[0] == "ORDERS" for key in windows), "REST_WINDOW_MISMATCH")
    need(len(doc["symbols"]) == 1 and doc["symbols"][0]["symbol"] == "BTCUSDT"
         and doc["symbols"][0]["isSpotTradingAllowed"] is True, "REST_SPOT_IDENTITY")


def metrics(feed):
    series = {key: [] for key in ("trade_latency", "trade_interarrival", "bbo_interarrival",
                                 "bbo_commit_age", "final_1m", "final_15m", "commit")}
    previous = {}
    with feed.tx(read=True) as db:
        rows = db.execute("SELECT raw,doc,ack,ack_sha,digest,generation FROM records ORDER BY rowid")
        for raw, doc, ack, ack_sha, digest, generation in rows:
            record = json.loads(doc)
            received = record["receive_ms"]
            need(ack is not None and ack >= received and digest == hash_bytes(doc)
                 and hash_bytes(raw) == record["raw_sha256"]
                 and ack_sha == hash_bytes(canonical([digest, generation, ack])),
                 "UNVERIFIED_PILOT_RECORD")
            series["commit"].append(ack - received)
            channel = record["channel"]
            if channel in ("trade", "bbo"):
                if channel in previous:
                    series[channel + "_interarrival"].append(received - previous[channel])
                previous[channel] = received
            if channel == "trade":
                series["trade_latency"].append(received - record["event_ms"])
            elif channel == "bbo":
                series["bbo_commit_age"].append(ack - received)
            elif channel in ("1m", "15m"):
                series["final_" + channel].append(received - record["material"]["end_ms_exclusive"])
    return {key: distribution(values) for key, values in series.items()}


def capture(preflight, output, quota_path, *, transport=None, clock=None):
    evidence_mode = "PUBLIC_WS_PILOT_NON_PIT" if transport is None else "INJECTED_TRANSPORT_TEST_ONLY"
    transport = transport or PublicTransport()
    clock = clock or Clock()
    limits, deadline = validate_preflight(preflight, clock.now())
    # A stable output path is the single-use reservation. A crash leaves it occupied.
    output.mkdir(mode=0o700)
    (output / "activation.json").write_bytes(canonical({
        "preflight_sha256": hash_bytes(canonical(preflight)), "start_ms": preflight["start_ms"]
    }))
    feed = Feed(output / "capture", pilot=True)
    quota = Quota(quota_path, limits)
    session = Session(feed, quota)
    report = dict(evidence_mode=evidence_mode, status="STOPPED", rest_calls=0, rest_weight=0, ws_attempts=0, frames=0,
                  pongs=0, raw_bytes=0, spend_usd=0, orders=0, trading_authority="NONE",
                  pit_oos="BLOCKED", bbo_exchange_latency="NOT_ESTIMABLE")
    price = {}
    finals = {}
    try:
        with quota.tx() as db:
            need(not quota.get(db, "pilot_start"), "PILOT_ALREADY_RESERVED")
            quota.set(db, "pilot_start", preflight["start_ms"])
        token = quota.rest("exchangeInfo", clock.now())
        need(token is not None, "REST_BUDGET_DENIED")
        report.update(rest_calls=1, rest_weight=20)
        try:
            status, headers, body = transport.exchange_info(4)
        except Exception:
            quota.result(token, clock.now(), 0)
            raise
        weight = headers.get("x-mbx-used-weight-1m", "")
        retry = headers.get("retry-after", "")
        used = int(weight) if weight.isascii() and weight.isdecimal() and len(weight) <= 10 else None
        retry_ms = int(retry) * 1000 if retry.isascii() and retry.isdecimal() and len(retry) <= 10 else None
        quota.result(token, clock.now(), status, used_weight=used, retry_after_ms=retry_ms)
        report.update(rest_status=status, used_weight_1m=used)
        need(status == 200 and used is not None and 20 <= used <= limits.rest_weight // 2,
             "REST_STATUS_OR_HEADROOM")
        verify_exchange_info(body, limits)
        now = clock.now()
        need(now < deadline, "DEADLINE")
        need(session.connect(uuid4().hex, now), "WS_BUDGET_DENIED")
        report["ws_attempts"] = 1
        opened = now
        with transport.stream(min(4, (deadline - now) / 1000)) as connection:
            while report["frames"] < 4096:
                now = clock.now()
                if now >= deadline:
                    break
                need(all(now - price.get(channel, opened) < 30_000 for channel in ("trade", "bbo")),
                     "STALE_PRICE_STOP")
                need(all(now < max(opened, finals.get(interval, opened)) // step * step + step + 5000
                         for interval, step in (("1m", 60_000), ("15m", 900_000))),
                     "MISSING_FINAL_STOP")
                try:
                    kind, raw = transport.frame(connection, min(4, (deadline - now) / 1000))
                except TimeoutError:
                    if clock.now() >= deadline:
                        break
                    raise
                received = clock.now()
                report["frames"] += 1
                report["raw_bytes"] += len(raw)
                if received >= deadline:
                    break
                if kind == "ping":
                    payload = session.ping(raw, received)
                    need(payload is not None, "PONG_BUDGET_DENIED")
                    connection.pong(payload)
                    report["pongs"] += 1
                    continue
                record = normalize(raw, received)
                channel = record["channel"]
                if channel == "trade":
                    need(received - record["event_ms"] <= 2000, "STALE_TRADE_STOP")
                if channel in ("1m", "15m"):
                    need(received - record["material"]["end_ms_exclusive"] <= 5000, "STALE_FINAL_STOP")
                # Use a conservative pre-write reserve for SQLite and its journal.
                need(sum(p.stat().st_size for p in feed.path.parent.iterdir()) <= CUSTODY_BYTES - 1_048_576,
                     "CUSTODY_CAP")
                if session.receive(raw, received, clock.now) == "STORED":
                    if channel in ("trade", "bbo"):
                        price[channel] = received
                    if channel in ("1m", "15m"):
                        finals[channel] = record["material"]["end_ms_exclusive"]
        report["stop_reason"] = "FRAME_CAP" if report["frames"] == 4096 else "DEADLINE"
        report["status"] = "COMPLETE"
    except Exception as exc:
        report["stop_reason"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    finally:
        try:
            if session.socket is not None:
                session.disconnect(clock.now(), failed=report["status"] != "COMPLETE")
            report["metrics"] = metrics(feed)
        except Exception as exc:
            report.update(status="STOPPED", custody_error=type(exc).__name__)
        report["quality"] = quality(report)
        (output / "report.json").write_bytes(canonical(report))
    return report


def quality(report):
    if report["status"] != "COMPLETE":
        return "FAIL_STOP"
    m = report["metrics"]
    if not (m["trade_latency"]["n"] >= 100 and m["bbo_commit_age"]["n"] >= 100
            and m["final_1m"]["n"] >= 15 and m["final_15m"]["n"] >= 1):
        return "INCONCLUSIVE_SAMPLE"
    passed = (m["trade_latency"]["p95_ms"] <= 500 and m["trade_latency"]["p99_ms"] <= 1500
              and m["bbo_commit_age"]["p95_ms"] <= 1000
              and m["final_1m"]["max_ms"] <= 5000 and m["final_15m"]["max_ms"] <= 5000)
    return "PASS_FEED_QUALITY_NON_PIT" if passed else "FAIL_FRESHNESS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preflight", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("shared_quota_db", type=Path)
    args = parser.parse_args()
    report = capture(json.loads(args.preflight.read_text(encoding="utf-8")), args.output, args.shared_quota_db)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["quality"] == "PASS_FEED_QUALITY_NON_PIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
