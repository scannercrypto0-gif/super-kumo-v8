"""Bounded BTCUSDT research service using the pinned #286 and #305 APIs."""
import argparse
from contextlib import closing
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import time

from aql.journal.durable_journal import DurableJournal
from aql.observation.contracts import digest
from aql.observation.prospective import ProspectiveObserver, STEP
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
from tools.atlas_prospective_observe import FIXTURE, dedicated_root, read_only_g1
from tools.atlas_single_receipt import load_frame, need, persist_frame, unique_json_keys
from tools.atlas_single_receipt_runner import ENDPOINT, BinanceReceiptTransport, verify_controlled_egress
from tools.binance_live_feed.quota import Limits, Quota

MARKER = "atlas-live-research-v1"


class HostClock:
    @staticmethod
    def now():
        return time.time_ns() // 1_000_000

    monotonic_ns = staticmethod(time.monotonic_ns)


def emit(root, status, **fields):
    record = {"status": status, **fields}
    line = json.dumps(record, sort_keys=True)
    with (root / "health.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(line, flush=True)


def consume(root, journal, store, observer, now, wait):
    meta, seal, bar = load_frame(root)
    remaining = bar.ingested_at - now()
    if remaining > 0:
        wait(remaining / 1000)
    need(now() >= bar.ingested_at, "SOURCE_CLOCK_NOT_READY")
    key = bar.stable_key()
    journal.commit(bar)
    ack = journal.commit_receipt(key)
    committed = ack["commit_return_observed_at_ms"]
    need(ack["status"] == "SQLITE_COMMIT_RETURN_OBSERVED" and committed >= bar.ingested_at,
         "DURABLE_ACK_UNCONFIRMED")
    store.upsert(bar)
    journal.mark_persisted(key)
    observer.tick()
    rows = observer.verified_read(as_of_ms=now())["rows"]
    match = next((row for row in rows if row["decision"]["parent"]["key"] == key), None)
    need(match and match["source_valid"] and
         match["decision"]["parent"]["g1_receipt_sha256"] == digest(ack), "SCANNER_ACK_LINEAGE")
    return {"slot": meta["slot"], "received_ms": meta["received"], "committed_ms": committed,
            "source_sha256": seal, "ack_sha256": digest(ack),
            "scanner_sha256": match["decision_sha256"], "state": match["decision"]["state"]}


def report(root, fixture, cutoff, *, synthetic=False):
    observer = ProspectiveObserver(root / "g2.sqlite",
                                   read_only_g1(DurableJournal, root / "journal.sqlite"),
                                   read_only_g1(OperationalStore, root / "market.sqlite"),
                                   fixture, synthetic=synthetic, read_only=True)
    factory = read_prospective_research(observer, as_of_ms=cutoff)
    need(not factory["orders_enabled"] and not factory["secretary_enqueued"], "RESEARCH_ONLY")
    return {"factory": factory, "admission": "WAIT_AUTHENTICATED_PARENTS",
            "strict_pit_oos": "BLOCKED", "lab": "NOT_EVALUATED",
            "discoverer": "NO_MATCHING_LINEAGE", "rest_requests": 0}


def run(root, plan, pin, fixture, *, verifier, clock, transport, wait=time.sleep, synthetic=False):
    need(synthetic or type(transport) is BinanceReceiptTransport, "LIVE_TRANSPORT_REQUIRED")
    need(not synthetic or not isinstance(transport, BinanceReceiptTransport), "OFFLINE_TRANSPORT_REQUIRED")
    need(plan == make_plan(plan["slot"], fixture) and digest(plan) == pin, "LIVE_PLAN_PIN")
    need(verifier is not None, "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE")
    start = clock.now()
    need(plan["slot"] <= start < plan["slot"] + plan["wall_ms"], "OUTSIDE_DECLARED_START")
    if start >= plan["slot"] + 5000:
        need((root / MARKER).is_file() and (root / "plan.json").is_file(), "OUTSIDE_DECLARED_START")
    reservation = verify_controlled_egress(plan, pin, now=start, verifier=verifier)
    qualification = verifier.read_verified_host(plan_pin=pin, endpoint=ENDPOINT)
    checked = qualification.get("clock_checked_ms")
    uncertainty = qualification.get("clock_uncertainty_ms")
    need(type(checked) is int and 0 <= start - checked <= 60_000 and
         type(uncertainty) is int and 0 <= uncertainty <= 250 and
         all(qualification.get(k) for k in ("source_rights_ref", "region_ref", "custody_ref")),
         "HOST_QUALIFICATION_REQUIRED")
    need(verifier.verify_observation_reservation(
        reservation_ref=reservation, plan_pin=pin, state_path=str(root.resolve()),
        connections=plan["max_connections"], rest_requests=0,
        expires_at_ms=plan["slot"] + plan["wall_ms"]) is True, "RESERVATION_SCOPE_UNVERIFIED")

    root = dedicated_root(root, MARKER)
    with closing(sqlite3.connect(root / "lock.sqlite", timeout=0)) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        try:
            result = observe(root, plan, pin, fixture, clock, transport, wait, uncertainty, synthetic)
        except Exception as exc:
            emit(root, "STOPPED_ERROR", error=type(exc).__name__,
                 provider_status=getattr(exc, "status_code", None))
            raise
        emit(root, "STOPPED", utc_ms=clock.now(), result_sha256=digest(result))
        return result


def observe(root, plan, pin, fixture, clock, transport, wait, uncertainty, synthetic):
    journal = DurableJournal(str(root / "journal.sqlite"))
    store = OperationalStore(str(root / "market.sqlite"))
    observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture, synthetic=synthetic)
    first = plan["slot"]
    # A session marker binds isolated custody to this observation window.
    manifest = root / "plan.json"
    if not manifest.exists():
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
    need(json.loads(manifest.read_text(encoding="utf-8")) == plan, "STATE_PLAN_MISMATCH")
    rows = recover(root, journal, store, observer, first, clock.now, wait)
    if len(rows) == 2:
        return {**report(root, fixture, clock.now(), synthetic=synthetic), "bars": rows}

    quota = Quota(root / "quota.sqlite", Limits(rest_weight=2, connections=4))
    # The exclusive process lock proves the previous socket owner is gone.
    quota.disconnect("research-15m", clock.now(), failed=False)
    monotonic_start = clock.monotonic_ns()
    started = clock.now()
    deadline = first + plan["wall_ms"]

    def time_left():
        now = clock.now()
        elapsed = (clock.monotonic_ns() - monotonic_start) // 1_000_000
        need(0 <= elapsed and abs(now - started - elapsed) <= 250, "CLOCK_STEP")
        need(now < deadline and elapsed < plan["wall_ms"], "WINDOW_EXPIRED")
        return now, (deadline - now) / 1000

    for attempt in range(plan["max_connections"]):
        now, left = time_left()
        socket_id = "research-15m"
        with quota.tx() as db:
            used = quota.get(db, "research_connection_attempts")
            need(used < plan["max_connections"], "LOCAL_WS_BUDGET_STOP")
            quota.set(db, "research_connection_attempts", used + 1)
        need(quota.connect(socket_id, now, ["btcusdt@kline_15m"]), "LOCAL_WS_BUDGET_STOP")
        try:
            emit(root, "CONNECTING", utc_ms=now, attempt=attempt + 1, plan_sha256=pin)
            with transport.stream(ENDPOINT, min(5, left)) as connection:
                need(connection.getstatus() == 101, "WS_UPGRADE")
                heartbeat = now
                while len(rows) < 2:
                    now, left = time_left()
                    expected_close = first + (len(rows) + 1) * STEP - 1
                    need(now + uncertainty <= expected_close + 300_000, "FINALIZED_SOURCE_GAP")
                    if now - heartbeat >= 30_000:
                        emit(root, "OBSERVING", utc_ms=now, committed=len(rows),
                             last_slot=rows[-1]["slot"] if rows else None)
                        heartbeat = now
                    kind, raw = transport.frame(connection, min(left, 30))
                    received, _ = time_left()
                    if kind == "ping":
                        need(quota.ws(socket_id, received, "PONG"), "PONG_QUOTA_STOP")
                        connection.pong(raw)
                        continue
                    need(kind == "text", "UNEXPECTED_FRAME")
                    row = ingest(root, raw, rows, first, received, uncertainty, clock.monotonic_ns(),
                                 pin, journal, store, observer, clock.now, wait)
                    if row is not None:
                        rows.append(row)
                        emit(root, "DURABLE_RESEARCH_BAR", **row)
        except (TimeoutError, ConnectionError) as exc:
            emit(root, "TRANSPORT_INTERRUPTED", error=type(exc).__name__)
            if attempt or len(rows) == 2:
                raise
        finally:
            quota.disconnect(socket_id, clock.now(), failed=len(rows) < 2)
        if len(rows) == 2:
            return {**report(root, fixture, clock.now(), synthetic=synthetic), "bars": rows}
        wait(3)
    raise ValueError("SOURCE_OUTAGE")


def recover(root, journal, store, observer, first, now, wait):
    rows = []
    for slot in (first, first + STEP):
        path = root / str(slot)
        if (path / "receipt.sqlite").is_file():
            need(slot == first + len(rows) * STEP, "RECOVERY_SOURCE_GAP")
            rows.append(consume(path, journal, store, observer, now, wait))
    need([bar.bar_open for bar in journal.replay("BTCUSDT", "15m", limit=3)] ==
         [row["slot"] for row in rows], "RECOVERY_CUSTODY_MISMATCH")
    return rows


def ingest(root, raw, rows, first, received, uncertainty, monotonic_ns, pin,
           journal, store, observer, now, wait):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, "RAW_LIMIT")
    candle = json.loads(raw, object_pairs_hook=unique_json_keys)["k"]
    slot = candle["t"]
    need(candle["s"] == "BTCUSDT" and candle["i"] == "15m" and type(slot) is int,
         "FOREIGN_CANDLE")
    expected = first + len(rows) * STEP
    if slot == first - STEP and received < first + 5000:
        return None
    if candle["x"] is False:
        # A next-slot update is normal while waiting for the prior close;
        # missing finalized bars are detected by the next finalized frame.
        return None
    need(type(candle["x"]) is bool and slot <= expected, "FINALIZED_SOURCE_GAP")
    need(slot >= first, "OUTSIDE_SOURCE_WINDOW")
    path = dedicated_root(root / str(slot), "atlas-live-research-bar")
    if slot < expected:
        meta, _, _ = load_frame(path)
        need(hashlib.sha256(raw).hexdigest() == meta["payload_sha256"], "CANDLE_REVISION")
        return None
    persist_frame(path, raw, slot=slot, received=received, uncertainty=uncertainty,
                  monotonic_ns=monotonic_ns, session=pin[:24])
    return consume(path, journal, store, observer, now, wait)


def make_plan(slot, fixture):
    need(type(slot) is int and slot > 0 and slot % STEP == 0, "SLOT_GRID")
    return {"endpoint": ENDPOINT, "slot": slot, "bar_count": 2, "wall_ms": 2 * STEP + 300_000,
            "max_connections": 2, "rest_requests": 0, "strategy_fixture_sha256": fixture["sha256"],
            "config_sha256": fixture["payload"]["config_digest"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "live", "status", "recover"))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--slot", type=int)
    parser.add_argument("--pin")
    parser.add_argument("--authority-module", help="Trusted operator-installed local authority module")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
    now = lambda: time.time_ns() // 1_000_000
    if args.mode == "plan":
        plan = make_plan(args.slot, fixture)
        result = {"plan": plan, "sha256": digest(plan)}
    elif args.mode == "status":
        need(args.state is not None and (args.state / MARKER).is_file(), "STATE_REQUIRED")
        result = report(args.state, fixture, now())
    elif args.mode == "recover":
        need(args.state is not None and (args.state / MARKER).is_file(), "STATE_REQUIRED")
        root = dedicated_root(args.state, MARKER)
        with closing(sqlite3.connect(root / "lock.sqlite", timeout=0)) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
            need(digest(plan) == args.pin and plan == make_plan(plan["slot"], fixture), "LIVE_PLAN_PIN")
            journal = DurableJournal(str(root / "journal.sqlite"))
            store = OperationalStore(str(root / "market.sqlite"))
            observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture, synthetic=False)
            rows = recover(root, journal, store, observer, plan["slot"], now, time.sleep)
            result = {**report(root, fixture, now()), "bars": rows}
    else:
        need(args.authority_module is not None, "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE")
        need(args.state is not None, "STATE_REQUIRED")
        authority = importlib.import_module(args.authority_module)
        plan = make_plan(args.slot, fixture)
        delay_ms = plan["slot"] - now()
        need(delay_ms <= STEP, "START_TOO_FAR_AHEAD")
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        result = run(args.state, plan, args.pin, fixture, verifier=authority, clock=HostClock(),
                     transport=BinanceReceiptTransport())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
