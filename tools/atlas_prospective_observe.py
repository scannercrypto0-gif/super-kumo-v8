"""Bounded public BTCUSDT observation. Requires a dedicated persistent host."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
from time import monotonic, time_ns
import platform

from aql.journal.durable_journal import DurableJournal
from aql.observation.prospective import INTERVAL, MAX_BARS, SYMBOL, ProspectiveObserver
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research

FIXTURE = Path(__file__).parent / "strategy_service_offline/fixtures/strategies.json"


def dedicated_root(raw, marker):
    path = Path(raw).absolute()
    if any(item.is_symlink() or getattr(item, "is_junction", lambda: False)()
           for item in (path, *path.parents)):
        raise ValueError("State root cannot traverse a symlink or junction")
    if path.drive.upper() == "E:":
        raise ValueError("Use a separate non-original volume")
    path.mkdir(parents=True, exist_ok=True)
    owner = path / marker
    if not owner.exists():
        if any(path.iterdir()):
            raise ValueError("Initial state root must be empty")
        with owner.open("x", encoding="ascii") as stream:
            stream.write(marker)
    if any(item.is_symlink() or getattr(item, "is_junction", lambda: False)()
           for item in path.iterdir()) or owner.read_text(encoding="ascii") != marker:
        raise ValueError("Invalid dedicated state marker")
    return path


def read_only_g1(cls, path):
    # Reuse verified readers without running migrations or writer PRAGMAs.
    instance = cls.__new__(cls)

    def connect():
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return con

    instance._connect = connect
    return instance


def main():

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--public-observation", action="store_true")
    mode.add_argument("--status", action="store_true")
    p.add_argument("--seconds", type=int, default=4 * 24 * 3600)
    args = p.parse_args()
    if not 1 <= args.seconds <= 4 * 24 * 3600:
        p.error("--seconds must be within the four-day run window")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
    if args.status:
        root = Path(args.state).absolute()
        if not (root / "atlas-prospective-v1").is_file():
            p.error("Existing isolated observation state required")
        journal = read_only_g1(DurableJournal, root / "journal.sqlite")
        store = read_only_g1(OperationalStore, root / "market.sqlite")
        observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture,
                                       synthetic=False, read_only=True)
        print(json.dumps(read_prospective_research(observer, as_of_ms=time_ns() // 1_000_000),
                         sort_keys=True))
        return
    from aql.collector.binance_collector import BinanceCollector

    root = dedicated_root(args.state, "atlas-prospective-v1")
    if shutil.disk_usage(root).free < 128 * 1024 * 1024:
        p.error("Require at least 128 MiB free on the isolated state volume")
    # OS lock via SQLite keeps a second writer out and releases on process death.
    with closing(sqlite3.connect(root / "runner-lock.sqlite", timeout=0)) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        journal = DurableJournal(str(root / "journal.sqlite"))
        store = OperationalStore(str(root / "market.sqlite"))
        observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture, synthetic=False)
        journal.startup_reconcile(store, SYMBOL, INTERVAL)
        remaining = MAX_BARS - len(journal.replay(SYMBOL, INTERVAL, limit=MAX_BARS + 1))
        if remaining <= 0:
            print(json.dumps({"status": "OBSERVATION_WINDOW_EXHAUSTED"}), flush=True)
            return 0
        observer.tick()
        collector = BinanceCollector(
            SYMBOL, INTERVAL, journal, store, max_bars=remaining,
            public_market_only=True, on_persisted=observer.tick,
        )
        health = {"status": "STARTING_PUBLIC_WS", "utc_ms": time_ns() // 1_000_000,
                  "platform": platform.system(), "free_bytes": shutil.disk_usage(root).free,
                  "journal_instance": journal.instance_id,
                  "source": "wss://data-stream.binance.vision:443/ws/btcusdt@kline_15m"}
        def record_health(record):
            line = json.dumps(record, sort_keys=True)
            with (root / "health.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            print(line, flush=True)

        record_health(health)
        started = monotonic()
        metrics = collector.run(timeout_s=args.seconds)
        observer.tick()
        summary = read_prospective_research(observer, as_of_ms=time_ns() // 1_000_000)
        record_health({"status": "STOPPED", "utc_ms": time_ns() // 1_000_000,
                       "committed_this_session": metrics.journal_commit_count,
                       "errors": metrics.error_count, "first_connect_utc_ms": metrics.first_connect_at,
                       "last_commit_utc_ms": metrics.last_commit_return_observed_at, "factory": summary})
        completed_window = monotonic() - started >= args.seconds
        exhausted_budget = metrics.journal_commit_count >= remaining
        return 0 if metrics.first_connect_at and (completed_window or exhausted_budget) else 1


if __name__ == "__main__":
    raise SystemExit(main())
