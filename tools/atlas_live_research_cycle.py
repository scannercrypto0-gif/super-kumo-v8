"""Bounded BTCUSDT research service using the pinned #286 and #305 APIs."""
import argparse
from contextlib import ExitStack, closing, nullcontext
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from uuid import uuid4

from aql.journal.durable_journal import DurableJournal
from aql.observation.contracts import digest
from aql.observation.prospective import ProspectiveObserver, STEP
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
from tools.atlas_prospective_observe import FIXTURE, dedicated_root, read_only_g1
from tools.atlas_single_receipt import load_frame, need, parse_final, persist_frame, unique_json_keys
from tools.atlas_single_receipt_runner import ENDPOINT, BinanceReceiptTransport
from tools.atlas_research_lease import Lease
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
    path = root / "health.jsonl"
    if path.exists() and path.stat().st_size >= 256 * 1024:
        path.replace(root / "health.previous.jsonl")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(line, flush=True)


def operational_guard(root):
    need(not (root / "stop.request").exists(), "OPERATOR_STOP_REQUESTED")
    need(shutil.disk_usage(root).free >= 128 * 1024 * 1024, "DISK_RESERVE_LOW")


def consume(root, journal, store, observer, now, wait, *, slot, plan_pin):
    meta, seal, bar = load_frame(root)
    need(meta["slot"] == slot and meta["session"] == plan_pin[:24], "LIVE_RECEIPT_SESSION")
    return consume_bar(meta, seal, bar, journal, store, observer, now, wait)


def consume_bar(meta, seal, bar, journal, store, observer, now, wait):
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
    return factory_report(observer, cutoff)


def factory_report(observer, cutoff):
    factory = read_prospective_research(observer, as_of_ms=cutoff)
    need(not factory["orders_enabled"] and not factory["secretary_enqueued"], "RESEARCH_ONLY")
    return {"factory": factory, "admission": "WAIT_AUTHENTICATED_PARENTS",
            "strict_pit_oos": "BLOCKED", "lab": "NOT_EVALUATED",
            "discoverer": "NO_MATCHING_LINEAGE", "rest_requests": 0}


def run(root, plan, pin, fixture, *, verifier, clock, transport, wait=time.sleep, synthetic=False,
        stop_after_first=False, pilot_qualification=None):
    pilot = pilot_qualification is not None
    need(synthetic or type(transport) is BinanceReceiptTransport, "LIVE_TRANSPORT_REQUIRED")
    need(not synthetic or not isinstance(transport, BinanceReceiptTransport), "OFFLINE_TRANSPORT_REQUIRED")
    need(plan == make_plan(plan["slot"], fixture, plan["bar_count"], bounded_pilot=pilot)
         and digest(plan) == pin, "LIVE_PLAN_PIN")
    need(verifier is not None or pilot, "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE")
    need(not pilot or verifier is None, "PILOT_AUTHORITY_MODE_CONFLICT")
    start = clock.now()
    need(plan["slot"] <= start < plan["slot"] + plan["wall_ms"], "OUTSIDE_DECLARED_START")
    if start >= plan["slot"] + 5000:
        need((root / MARKER).is_file() and (root / "plan.json").is_file(), "OUTSIDE_DECLARED_START")
    if pilot:
        qualification = pilot_qualification
        need(qualification.get("plan_sha256") == pin and qualification.get("endpoint") == ENDPOINT
             and qualification.get("state_path") == str(root.resolve())
             and type(qualification.get("raw_retention_ms")) is int
             and qualification["raw_retention_ms"] == 0
             and all(isinstance(qualification.get(key), str) and qualification[key].strip()
                     for key in ("source_rights_ref", "region_ref", "custody_ref", "network_permission_ref")),
             "PILOT_QUALIFICATION_SCOPE")
    else:
        need(all(callable(getattr(verifier, name, None)) for name in (
            "read_verified_host", "acquire_research_lease", "renew_research_lease",
            "release_research_lease")), "RENEWABLE_AUTHORITY_REQUIRED")
        qualification = verifier.read_verified_host(plan_pin=pin, endpoint=ENDPOINT)
    checked = qualification.get("clock_checked_ms")
    uncertainty = qualification.get("clock_uncertainty_ms")
    need(type(checked) is int and 0 <= start - checked <= 60_000 and
         type(uncertainty) is int and 0 <= uncertainty <= 250 and
         all(qualification.get(k) for k in ("source_rights_ref", "region_ref", "custody_ref")),
         "HOST_QUALIFICATION_REQUIRED")
    root = dedicated_root(root, MARKER)
    scope = dict(plan_pin=pin, endpoint=ENDPOINT, state_path=str(root.resolve()),
                 connections=plan["max_connections"], rest_requests=0,
                 deadline_ms=plan["slot"] + plan["wall_ms"])
    with closing(sqlite3.connect(root / "lock.sqlite", timeout=0)) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        try:
            operational_guard(root)
            with (nullcontext() if pilot else Lease(verifier, scope, now=clock.now)) as lease:
                result = observe(root, plan, pin, fixture, clock, transport, wait, uncertainty,
                                 synthetic, stop_after_first, lease)
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc) == "OPERATOR_STOP_REQUESTED":
                emit(root, "STOPPED_BY_OPERATOR", utc_ms=clock.now())
                return {"status": "STOPPED_BY_OPERATOR"}
            status = getattr(exc, "status_code", None)
            error = str(exc) if type(exc) is ValueError and str(exc).isupper() else type(exc).__name__
            emit(root, "STOPPED_ERROR", error=error, provider_status=status if type(status) is int else None)
            if pilot:
                raise ValueError(f"PILOT_STOP_{error}" + (f"_HTTP_{status}" if type(status) is int else "")) from None
            raise
        if pilot:
            result = {**result, "egress_budget": "LOCAL_PILOT_ONLY", "shared_headroom": "UNVERIFIED",
                      "retention": "SANITIZED_RECEIPTS_ONLY", "plan_sha256": pin}
            result = {**result, "sha256": digest(result)}
            write_once(root / "pilot-summary.json", result)
        emit(root, "STOPPED", utc_ms=clock.now(), result_sha256=digest(result))
        return result


def write_once(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def saved_pilot_summary(root, plan, expected_pin):
    need(digest(plan) == expected_pin, "LIVE_PLAN_PIN")
    path = root / "pilot-summary.json"
    need(path.is_file(), "EPHEMERAL_PILOT_NO_COMPLETED_SUMMARY")
    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_json_keys)
    need(result["sha256"] == digest({key: value for key, value in result.items() if key != "sha256"})
         and result["plan_sha256"] == expected_pin and result["retention"] == "SANITIZED_RECEIPTS_ONLY",
         "EPHEMERAL_SUMMARY_PIN")
    return result


class MemoryDatabase:
    def _connect(self):
        conn = sqlite3.connect(self.memory_uri, uri=True, isolation_level=self.isolation_level)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _connect_readonly(self):
        conn = self._connect()
        conn.execute("PRAGMA query_only=ON")
        return conn


class MemoryJournal(MemoryDatabase, DurableJournal):
    isolation_level = None


class MemoryStore(MemoryDatabase, OperationalStore):
    isolation_level = ""


class MemoryObserver(MemoryDatabase, ProspectiveObserver):
    isolation_level = ""


def observe(root, plan, pin, fixture, clock, transport, wait, uncertainty, synthetic,
            stop_after_first, lease):
    if plan.get("egress_budget") == "LOCAL_PILOT_ONLY":
        with ExitStack() as stack:
            journal, store, observer = [cls.__new__(cls) for cls in
                                        (MemoryJournal, MemoryStore, MemoryObserver)]
            for db in (journal, store, observer):
                db.memory_uri = f"file:atlas-{uuid4().hex}?mode=memory&cache=shared"
                stack.enter_context(closing(db._connect()))
            journal.__init__(str(root / "journal.sqlite"))
            store.__init__(str(root / "market.sqlite"))
            observer.__init__(root / "g2.sqlite", journal, store, fixture, synthetic=synthetic)
            return observe_cycle(root, plan, pin, fixture, clock, transport, wait, uncertainty,
                                 synthetic, stop_after_first, lease, journal, store, observer, ephemeral=True)
    journal = DurableJournal(str(root / "journal.sqlite"))
    store = OperationalStore(str(root / "market.sqlite"))
    observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture, synthetic=synthetic)
    return observe_cycle(root, plan, pin, fixture, clock, transport, wait, uncertainty,
                         synthetic, stop_after_first, lease, journal, store, observer, ephemeral=False)


def observe_cycle(root, plan, pin, fixture, clock, transport, wait, uncertainty, synthetic,
                  stop_after_first, lease, journal, store, observer, *, ephemeral):
    first = plan["slot"]
    # A session marker binds isolated custody to this observation window.
    manifest = root / "plan.json"
    if ephemeral:
        need(not manifest.exists(), "EPHEMERAL_PILOT_ALREADY_CONSUMED")
        write_once(manifest, plan)
    elif not manifest.exists():
        write_once(manifest, plan)
    need(json.loads(manifest.read_text(encoding="utf-8")) == plan, "STATE_PLAN_MISMATCH")
    rows = [] if ephemeral else recover(root, journal, store, observer, first, clock.now, wait,
                                        count=plan["bar_count"], plan_pin=pin)
    target = 1 if stop_after_first else plan["bar_count"]
    if len(rows) >= target:
        return {**report(root, fixture, clock.now(), synthetic=synthetic), "bars": rows}

    quota = Quota(root / "quota.sqlite", Limits(rest_weight=2, connections=4))
    # The exclusive process lock proves the previous socket owner is gone.
    quota.disconnect("research-15m", clock.now(), failed=False)
    monotonic_start = clock.monotonic_ns()
    started = clock.now()
    deadline = first + plan["wall_ms"]

    def time_left():
        operational_guard(root)
        now = clock.now()
        elapsed = (clock.monotonic_ns() - monotonic_start) // 1_000_000
        need(0 <= elapsed and abs(now - started - elapsed) <= 250, "CLOCK_STEP")
        need(now < deadline and elapsed < plan["wall_ms"], "WINDOW_EXPIRED")
        if lease is None:
            return now, (deadline - clock.now()) / 1000
        remaining = lease.check()
        need(remaining > 1, "LEASE_BUDGET_TOO_SHORT")
        return now, min((deadline - clock.now()) / 1000, remaining - 1)

    for attempt in range(plan["max_connections"]):
        now, left = time_left()
        socket_id = "research-15m"
        with quota.tx() as db:
            used = quota.get(db, "research_connection_attempts")
            need(used < plan["max_connections"], "LOCAL_WS_BUDGET_STOP")
            quota.set(db, "research_connection_attempts", used + 1)
        need(quota.connect(socket_id, now, ["btcusdt@kline_15m"]), "LOCAL_WS_BUDGET_STOP")
        try:
            emit(root, "CONNECTING", utc_ms=now, attempt=used + 1, plan_sha256=pin)
            with transport.stream(ENDPOINT, min(5, left)) as connection:
                need(connection.getstatus() == 101, "WS_UPGRADE")
                heartbeat = now
                while len(rows) < target:
                    now, left = time_left()
                    expected_close = first + (len(rows) + 1) * STEP - 1
                    need(now + uncertainty <= expected_close + 300_000, "FINALIZED_SOURCE_GAP")
                    if now - heartbeat >= 30_000:
                        emit(root, "OBSERVING", utc_ms=now, committed=len(rows),
                             last_slot=rows[-1]["slot"] if rows else None,
                             last_close_age_ms=now - rows[-1]["slot"] - STEP + 1 if rows else None)
                        heartbeat = now
                    kind, raw = transport.frame(connection, min(left, 30))
                    received, _ = time_left()
                    if kind == "ping":
                        need(quota.ws(socket_id, received, "PONG"), "PONG_QUOTA_STOP")
                        connection.pong(raw)
                        continue
                    need(kind == "text", "UNEXPECTED_FRAME")
                    row = ingest(root, raw, rows, first, received, uncertainty, clock.monotonic_ns(),
                                 pin, journal, store, observer, clock.now, wait, ephemeral=ephemeral)
                    if row is not None:
                        rows.append(row)
                        emit(root, "EPHEMERAL_RESEARCH_BAR" if ephemeral else "DURABLE_RESEARCH_BAR", **row)
        except (TimeoutError, ConnectionError) as exc:
            emit(root, "TRANSPORT_INTERRUPTED", error=type(exc).__name__)
            if attempt or len(rows) == target:
                raise
        finally:
            quota.disconnect(socket_id, clock.now(), failed=len(rows) < target)
        if len(rows) == target:
            view = factory_report(observer, clock.now()) if ephemeral else report(
                root, fixture, clock.now(), synthetic=synthetic)
            return {**view, "bars": rows}
        wait(3 + int(pin[:2], 16) / 255)
    raise ValueError("SOURCE_OUTAGE")


def recover(root, journal, store, observer, first, now, wait, *, plan_pin, count=2):
    rows = []
    for slot in range(first, first + count * STEP, STEP):
        path = root / str(slot)
        if (path / "receipt.sqlite").is_file():
            need(slot == first + len(rows) * STEP, "RECOVERY_SOURCE_GAP")
            rows.append(consume(path, journal, store, observer, now, wait,
                                slot=slot, plan_pin=plan_pin))
    need([bar.bar_open for bar in journal.replay("BTCUSDT", "15m", limit=count + 1)] ==
         [row["slot"] for row in rows], "RECOVERY_CUSTODY_MISMATCH")
    return rows


def ingest(root, raw, rows, first, received, uncertainty, monotonic_ns, pin,
           journal, store, observer, now, wait, *, ephemeral=False):
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
    if ephemeral:
        payload_sha = hashlib.sha256(raw).hexdigest()
        if slot < expected:
            need(rows[(slot - first) // STEP]["payload_sha256"] == payload_sha, "CANDLE_REVISION")
            return None
        event, bar = parse_final(raw, slot, received, uncertainty)
        meta = dict(slot=slot, received=received, event=event, uncertainty=uncertainty,
                    session=pin, payload_sha256=payload_sha)
        row = consume_bar(meta, digest(meta), bar, journal, store, observer, now, wait)
        return {**row, "event_ms": event, "payload_sha256": payload_sha}
    path = dedicated_root(root / str(slot), "atlas-live-research-bar")
    if slot < expected:
        meta, _, _ = load_frame(path)
        need(meta["slot"] == slot and meta["session"] == pin[:24], "LIVE_RECEIPT_SESSION")
        need(hashlib.sha256(raw).hexdigest() == meta["payload_sha256"], "CANDLE_REVISION")
        return None
    persist_frame(path, raw, slot=slot, received=received, uncertainty=uncertainty,
                  monotonic_ns=monotonic_ns, session=pin[:24])
    return consume(path, journal, store, observer, now, wait, slot=slot, plan_pin=pin)


def make_plan(slot, fixture, count=2, *, bounded_pilot=False):
    need(type(slot) is int and slot > 0 and slot % STEP == 0, "SLOT_GRID")
    need(type(count) is int and 2 <= count <= 96, "BAR_COUNT_LIMIT")
    need(not bounded_pilot or count == 4, "PILOT_REQUIRES_FOUR_BARS")
    plan = {"endpoint": ENDPOINT, "slot": slot, "bar_count": count, "wall_ms": count * STEP + 300_000,
            "max_connections": 2, "rest_requests": 0, "strategy_fixture_sha256": fixture["sha256"],
            "config_sha256": fixture["payload"]["config_digest"]}
    if bounded_pilot:
        plan["egress_budget"] = "LOCAL_PILOT_ONLY"
        plan["retention"] = "SANITIZED_RECEIPTS_ONLY"
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "live", "status", "recover", "stop", "rearm", "preflight"))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--slot", type=int)
    parser.add_argument("--bars", type=int, default=2)
    parser.add_argument("--pin")
    parser.add_argument("--authority-module", help="Trusted operator-installed local authority module")
    parser.add_argument("--bounded-pilot", action="store_true")
    parser.add_argument("--pilot-qualification", type=Path)
    parser.add_argument("--pilot-qualification-sha256")
    parser.add_argument("--stop-after-first", action="store_true")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
    now = lambda: time.time_ns() // 1_000_000
    if args.mode == "plan":
        plan = make_plan(args.slot, fixture, args.bars, bounded_pilot=args.bounded_pilot)
        result = {"plan": plan, "sha256": digest(plan)}
    elif args.mode in ("stop", "rearm"):
        need(args.state is not None and (args.state / MARKER).is_file(), "STATE_REQUIRED")
        root = dedicated_root(args.state, MARKER)
        stop = root / "stop.request"
        if args.mode == "stop":
            try:
                with stop.open("x", encoding="ascii"):
                    pass
            except FileExistsError:
                pass
        else:
            with closing(sqlite3.connect(root / "lock.sqlite", timeout=0)) as lock:
                lock.execute("BEGIN EXCLUSIVE")
                stop.unlink(missing_ok=True)
        result = {"status": "STOP_REQUESTED" if args.mode == "stop" else "REARMED"}
    elif args.mode == "preflight":
        need(args.authority_module is not None, "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE")
        authority = importlib.import_module(args.authority_module)
        need(all(callable(getattr(authority, name, None)) for name in (
            "read_verified_host", "acquire_research_lease", "renew_research_lease",
            "release_research_lease")), "RENEWABLE_AUTHORITY_REQUIRED")
        result = {"status": "AUTHORITY_INTERFACE_READY", "live_lease_checked": False}
    elif args.mode == "status":
        need(args.state is not None and (args.state / MARKER).is_file(), "STATE_REQUIRED")
        manifest = args.state / "plan.json"
        plan = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
        if plan.get("retention") == "SANITIZED_RECEIPTS_ONLY":
            print(json.dumps(saved_pilot_summary(args.state, plan, args.pin), sort_keys=True))
            return
        result = report(args.state, fixture, now())
        log = args.state / "health.jsonl"
        if log.is_file():
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 4096))
                lines = stream.read(8192).splitlines()
            if lines and lines[-1].startswith(b"{") and lines[-1].endswith(b"}"):
                result["health"] = json.loads(lines[-1])
    elif args.mode == "recover":
        need(args.state is not None and (args.state / MARKER).is_file(), "STATE_REQUIRED")
        root = dedicated_root(args.state, MARKER)
        with closing(sqlite3.connect(root / "lock.sqlite", timeout=0)) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
            need(digest(plan) == args.pin and plan == make_plan(
                plan["slot"], fixture, plan["bar_count"], bounded_pilot=plan.get("egress_budget") == "LOCAL_PILOT_ONLY"),
                 "LIVE_PLAN_PIN")
            if plan.get("retention") == "SANITIZED_RECEIPTS_ONLY":
                print(json.dumps(saved_pilot_summary(root, plan, args.pin), sort_keys=True))
                return
            journal = DurableJournal(str(root / "journal.sqlite"))
            store = OperationalStore(str(root / "market.sqlite"))
            observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture, synthetic=False)
            rows = recover(root, journal, store, observer, plan["slot"], now, time.sleep,
                           count=plan["bar_count"], plan_pin=args.pin)
            result = {**report(root, fixture, now()), "bars": rows}
    else:
        need(args.authority_module is not None or args.bounded_pilot, "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE")
        need(args.state is not None, "STATE_REQUIRED")
        qualification = None
        if args.bounded_pilot:
            need(args.authority_module is None and args.pilot_qualification is not None
                 and args.pilot_qualification_sha256, "PILOT_QUALIFICATION_REQUIRED")
            with args.pilot_qualification.open("rb") as stream:
                raw = stream.read(16_385)
            need(len(raw) <= 16_384, "PILOT_QUALIFICATION_BOUND")
            qualification = json.loads(raw, object_pairs_hook=unique_json_keys)
            need(isinstance(qualification, dict) and digest(qualification) == args.pilot_qualification_sha256,
                 "PILOT_QUALIFICATION_PIN")
        authority = importlib.import_module(args.authority_module) if args.authority_module else None
        plan = make_plan(args.slot, fixture, args.bars, bounded_pilot=args.bounded_pilot)
        delay_ms = plan["slot"] - now()
        need(delay_ms <= STEP, "START_TOO_FAR_AHEAD")
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        result = run(args.state, plan, args.pin, fixture, verifier=authority, clock=HostClock(),
                     transport=BinanceReceiptTransport(), stop_after_first=args.stop_after_first,
                     pilot_qualification=qualification)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
