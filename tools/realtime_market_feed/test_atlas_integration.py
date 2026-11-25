"""Generated-fixture vertical acceptance; no network or owner data."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_CHECKOUT = ROOT / ".integration" / "warehouse"
sys.path.insert(0, str(WAREHOUSE_CHECKOUT / "src"))
sys.path.insert(0, str(WAREHOUSE_CHECKOUT))

from tools.realtime_market_feed.service import Store as FeedStore
from tools.realtime_market_feed.atlas_integration import (
    build_registry_proposal, project_feed_window,
    reconcile_daily_bar,
)
from aql.research_bar_store import ResearchBarStore
from aql.research_forward_core_read import forward_core_window
from aql.research_forward_scanner_boundary import inspect_forward_15m
from aql.warehouse.engine import HistoricalWarehouse, DAY
from aql.warehouse.storage import canonical
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, register_experiment, read_experiment,
)
from tests.test_warehouse import fixture as daily_fixture, KEY, START


def feed(path, *, start=START, count=1, stale=False, changed=None, symbol="BTCUSDT"):
    store = FeedStore(path)
    for i in range(count):
        opened = start + i * 60_000
        close = "2" if i == changed else "1"
        data = {"e": "kline", "s": symbol, "E": opened + 59_999,
                "k": {"s": symbol, "i": "1m", "x": True, "t": opened,
                      "T": opened + 59_999, "o": "1", "h": "2", "l": "1",
                      "c": close, "v": "3", "n": 1}}
        store.ingest(json.dumps(data, separators=(",", ":")),
                     received_ms=opened + 60_000 - (180_000 if stale else 0))
    store.db.execute("CREATE TABLE engineering_fixture(schema TEXT, fixture_id TEXT)")
    store.db.execute("INSERT INTO engineering_fixture VALUES(?,?)",
                     ("aql.realtime-feed.generated-fixture.v1", "generated-in-test-helper"))
    store.db.commit()
    store.db.close()
    return start, start + count * 60_000



def _copy_generated_fixture_to_research_store(database, research_store_path, *, symbol,
                                               start_ms, end_ms, now_ms):
    """Test-only fixture writer; its input is created by feed() below."""
    source = Path(database).resolve()
    target = Path(research_store_path).resolve()
    source.relative_to(Path(__import__("tempfile").gettempdir()).resolve())
    target.relative_to(Path(__import__("tempfile").gettempdir()).resolve())
    rows = project_feed_window(source, symbol=symbol, start_ms=start_ms,
                               end_ms=end_ms, now_ms=now_ms,
                               allow_synthetic_fixture=True)
    with ResearchBarStore(target) as store:
        store.insert_batch(rows)
        verified = [store.read(symbol, "1m", row["open_ms"]) for row in rows]
    assert all(row is not None and row["source_class"] == "FORWARD_UNQUALIFIED"
               for row in verified)
    return {"status": "SYNTHETIC_FORWARD_BARS_COPIED", "rows": len(verified),
            "evidence_class": "GENERATED_TEST_FIXTURE", "trading_authority": "NONE"}


def _project(database, **kwargs):
    return project_feed_window(database, **kwargs, allow_synthetic_fixture=True)


def _daily(root, *, changed=None):
    w = HistoricalWarehouse(root, reserve=0, test_root=True)
    raw, check = daily_fixture(count=15, changed=changed)
    with w.writer():
        w.import_archive(raw, check, KEY, observed_ms=START + DAY)
    query = w.query("1m", START, START + 60_000,
                    cutoff_ms=START + DAY, include_registry=True)
    return w, query["bars"][0], query["registry"], query


def _bytes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


def test_finalized_feed_to_native_research_store_is_idempotent_and_read_only(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=1)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    target = tmp_path / "research.sqlite"
    result = _copy_generated_fixture_to_research_store(source, target, symbol="BTCUSDT",
                                    start_ms=start, end_ms=end,
                                    now_ms=end + 1_000)
    again = _copy_generated_fixture_to_research_store(source, target, symbol="BTCUSDT",
                                   start_ms=start, end_ms=end,
                                   now_ms=end + 1_000)
    assert result["rows"] == again["rows"] == 1
    with ResearchBarStore(target) as store:
        row = store.read("BTCUSDT", "1m", start)
    assert row["source_class"] == "FORWARD_UNQUALIFIED"
    assert row["trading_authority"] == "NONE"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_production_adapter_has_no_writer_and_blocks_unverified_feed(tmp_path):
    import tools.realtime_market_feed.atlas_integration as adapter

    assert not hasattr(adapter, "copy_to_research_store")
    source = tmp_path / "feed.sqlite"
    start, end = feed(source)
    with pytest.raises(ValueError, match="FEED_SOURCE_LINEAGE_UNVERIFIED"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=end, now_ms=end+1_000)


def test_provisional_and_missing_symbol_fail_closed(tmp_path):
    source = tmp_path / "provisional.sqlite"
    store = FeedStore(source)
    start = START
    provisional = {"e":"kline","s":"BTCUSDT","E":start+30_000,
                   "k":{"s":"BTCUSDT","i":"1m","x":False,"t":start,
                        "T":start+59_999,"o":"1","h":"2","l":"1","c":"1","v":"3","n":1}}
    assert store.ingest(json.dumps(provisional), received_ms=start+30_000) == "provisional_ignored"
    store.db.execute("CREATE TABLE engineering_fixture(schema TEXT, fixture_id TEXT)")
    store.db.execute("INSERT INTO engineering_fixture VALUES(?,?)",
                     ("aql.realtime-feed.generated-fixture.v1", "generated-in-test-helper"))
    store.db.commit()
    store.db.close()
    with pytest.raises(ValueError, match="SYMBOL_OR_WINDOW_MISSING"):
        _project(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=start+60_000, now_ms=start+61_000)

    source = tmp_path / "missing-symbol.sqlite"
    start, end = feed(source)
    with pytest.raises(ValueError, match="SYMBOL_OR_WINDOW_MISSING"):
        _project(source, symbol="ETHUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)


def test_stale_and_open_gap_fail_closed(tmp_path):
    source = tmp_path / "stale.sqlite"
    start, end = feed(source, stale=True)
    with pytest.raises(ValueError, match="FEED_STALE"):
        _project(source, symbol="BTCUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)
    source = tmp_path / "gap.sqlite"
    start, end = feed(source)
    db = sqlite3.connect(source)
    db.execute("""INSERT INTO open_gap(symbol,interval,start_ms,end_ms,reason,detected_ms)
                  VALUES(?,?,?,?,?,?)""", ("BTCUSDT","1m",start,end,"fixture",end))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="OPEN_HISTORY_GAP"):
        _project(source, symbol="BTCUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)


def test_duplicate_reconnect_is_idempotent_and_conflict_is_held(tmp_path):
    source = tmp_path / "duplicate.sqlite"
    start, end = feed(source)
    store = FeedStore(source)
    data = {"e":"kline","s":"BTCUSDT","E":start+59_999,
            "k":{"s":"BTCUSDT","i":"1m","x":True,"t":start,"T":start+59_999,
                 "o":"1","h":"2","l":"1","c":"1","v":"3","n":1}}
    store.ingest(json.dumps(data), received_ms=end)
    store.db.commit()
    store.db.close()
    assert len(_project(source, symbol="BTCUSDT", start_ms=start,
                                  end_ms=end, now_ms=end+1_000)) == 1

    source = tmp_path / "conflict.sqlite"
    start, end = feed(source)
    store = FeedStore(source)
    data["k"]["c"] = "1.5"
    store.ingest(json.dumps(data), received_ms=end+1)
    store.db.commit()
    store.db.close()
    with pytest.raises(ValueError, match="FEED_BAR_CONFLICT"):
        _project(source, symbol="BTCUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)


def test_missing_receipt_bad_utc_grid_and_incomplete_aggregation_fail_closed(tmp_path):
    source = tmp_path / "receipt.sqlite"
    start, end = feed(source, count=15)
    db = sqlite3.connect(source)
    db.execute("UPDATE final_bar SET payload_sha256='missing' WHERE open_ms=?", (start,))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="FEED_RECEIPT_INVALID"):
        _project(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=start+60_000, now_ms=start+61_000)

    with pytest.raises(ValueError, match="UTC_WINDOW_INVALID"):
        _project(source, symbol="BTCUSDT", start_ms=start+1,
                            end_ms=start+60_001, now_ms=end+1_000)

    source = tmp_path / "short.sqlite"
    start, end = feed(source, count=14)
    copied = tmp_path / "short-research.sqlite"
    _copy_generated_fixture_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000)
    with ResearchBarStore(copied) as store:
        with pytest.raises(ValueError, match="SOURCE_GAP"):
            store.project("BTCUSDT", "15m", start)


def test_corrupt_database_is_held(tmp_path):
    source = tmp_path / "corrupt.sqlite"
    source.write_bytes(b"not sqlite")
    with pytest.raises(ValueError, match="FEED_DATABASE_INVALID|FEED_DATABASE_CORRUPT"):
        _project(source, symbol="BTCUSDT", start_ms=START,
                            end_ms=START+60_000, now_ms=START+61_000)


def test_daily_overlap_proposal_is_read_only_and_hash_pinned(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=15)
    target = tmp_path / "research.sqlite"
    _copy_generated_fixture_to_research_store(source, target, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000)
    with ResearchBarStore(target) as store:
        live = store.read("BTCUSDT", "1m", START)
        live_15m = store.project("BTCUSDT", "15m", START)
    wh, historical, registry, daily_context = _daily(tmp_path / "warehouse")
    daily_context_15m = wh.query("15m", START, START+900_000,
                                 cutoff_ms=START+DAY, include_registry=True)
    daily_15m = daily_context_15m["bars"][0]
    before = _bytes(wh.root)
    match = reconcile_daily_bar(live, historical)
    aggregate_match = reconcile_daily_bar(live_15m, daily_15m)
    assert match["status"] == "MATCH_IDEMPOTENT"
    assert aggregate_match["status"] == "MATCH_IDEMPOTENT"
    assert match["duplicate_insert"] is False and match["write_performed"] is False
    proposal = build_registry_proposal(aggregate_match, daily_context_15m)
    assert proposal["status"] == "PROPOSED_ONLY"
    assert proposal["evidence_class"] == "GENERATED_SYNTHETIC_FIXTURE"
    assert proposal["registry_mutation"] is False
    assert _bytes(wh.root) == before


def test_daily_ohlcv_conflict_and_missing_realtime_produce_proposals_not_repairs(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=3)
    copied = tmp_path / "research.sqlite"
    _copy_generated_fixture_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000)
    with ResearchBarStore(copied) as store:
        live = store.read("BTCUSDT", "1m", START)
    wh, historical, registry, daily_context = _daily(tmp_path / "warehouse", changed=2)
    # Same UTC key, but source OHLCV differs; originals stay untouched.
    daily_context_conflict = wh.query("1m", START+120_000, START+180_000,
                                      cutoff_ms=START+DAY, include_registry=True)
    daily_conflict = daily_context_conflict["bars"][0]
    with ResearchBarStore(copied) as store:
        live_row = store.read("BTCUSDT", "1m", START+120_000)
    conflict = reconcile_daily_bar(live_row, daily_conflict)
    assert conflict["status"] == "CONFLICT"
    missing = reconcile_daily_bar(None, historical)
    assert missing["status"] == "MISSING_REALTIME"
    assert missing["recovery"] == "AUTHORIZED_BOUNDED_RECOVERY_REQUIRED"
    assert build_registry_proposal(conflict, daily_context_conflict)["warehouse_mutation"] is False
    assert build_registry_proposal(missing, daily_context)["status"] == "PROPOSED_ONLY"


def test_missing_provenance_and_tampered_registry_fail_closed(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source)
    with ResearchBarStore(tmp_path / "research.sqlite") as store:
        live = store.insert_1m({"symbol":"BTCUSDT","interval":"1m","open_ms":start,
            "final":True,"o":"1","h":"2","l":"1","c":"1","v":"3",
            "source_sha256":"0"*64,"available_at_ms":end})
    wh, daily, registry, daily_context = _daily(tmp_path / "warehouse")
    with pytest.raises(ValueError, match="PROJECTED_ROW_INVALID"):
        reconcile_daily_bar(dict(live, constituent_sha256=[]), daily)
    bad = dict(registry, snapshot_sha256="f"*64)
    with pytest.raises(ValueError, match="RECONCILIATION_REQUIRED|RECONCILIATION_SEAL_INVALID"):
        build_registry_proposal({"status":"MATCH_IDEMPOTENT"}, daily_context)
    with pytest.raises(ValueError, match="REGISTRY_SNAPSHOT_INVALID"):
        bad_context = dict(daily_context, registry=bad)
        build_registry_proposal(reconcile_daily_bar(live, daily), bad_context)
    mutated = dict(live, c="1.5")
    with pytest.raises(ValueError, match="PROJECTED_ROW_INVALID"):
        reconcile_daily_bar(mutated, daily)
    verified = reconcile_daily_bar(live, daily)
    forged = dict(verified, status="CONFLICT")
    forged_body = {k:v for k,v in forged.items() if k != "reconciliation_sha256"}
    forged["reconciliation_sha256"] = hashlib.sha256(canonical(forged_body)).hexdigest()
    with pytest.raises(ValueError, match="RECONCILIATION_STATUS_OR_LINEAGE_INVALID"):
        build_registry_proposal(forged, daily_context)

    def resign_snapshot(snapshot):
        body = {k:v for k,v in snapshot.items() if k != "snapshot_sha256"}
        snapshot["snapshot_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
        return snapshot

    unrelated = json.loads(json.dumps(registry))
    unrelated["sources"][0]["key"] = "data/spot/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2024-01-01.zip"
    unrelated_context = dict(daily_context, registry=resign_snapshot(unrelated))
    with pytest.raises(ValueError, match="DAILY_ARCHIVE_RECEIPT_NOT_BOUND"):
        build_registry_proposal(verified, unrelated_context)

    no_receipt = json.loads(json.dumps(registry))
    no_receipt["sources"][0]["source_receipt_sha256"] = None
    no_receipt_context = dict(daily_context, registry=resign_snapshot(no_receipt))
    with pytest.raises(ValueError, match="DAILY_ARCHIVE_RECEIPT_NOT_BOUND"):
        build_registry_proposal(verified, no_receipt_context)

    contradictory = json.loads(json.dumps(registry))
    contradictory["internal_gaps"] = [[START, START+60_000]]
    gap_context = dict(daily_context, registry=resign_snapshot(contradictory))
    with pytest.raises(ValueError, match="DAILY_REGISTRY_GAP"):
        build_registry_proposal(verified, gap_context)


def test_core_scanner_and_factory_record_wait_without_running_strategy(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=180)
    research = tmp_path / "research.sqlite"
    _copy_generated_fixture_to_research_store(source, research, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000)
    with ResearchBarStore(research) as store:
        for index in range(12):
            store.project("BTCUSDT", "15m", start + index * 900_000)
    core = forward_core_window(research, start_ms=start, bar_count=12)
    assert core["status"] == "FORWARD_CORE_WINDOW_READY"
    scanner = inspect_forward_15m(research, start)
    assert scanner["scanner_e_historical_route"] == "WAIT_CORE_HISTORICAL_CONTRACT_NOT_SATISFIED"
    assert scanner["scanner_attempts"] == scanner["factory_experiments"] == 0

    sha = hashlib.sha256(canonical(scanner)).hexdigest()
    attempt = {"attempt_id":"synthetic-wait-1","candidate_id":"BTCUSDT-1m-fixture",
               "state":"UNKNOWN","source_receipt_sha256":sha}
    record = build_experiment(
        experiment_id="realtime-integration-wait", lane="SCANNER",
        source_status="HISTORICAL_SOURCE_BLOCKED", source_sha256=None,
        source_query_245_sha256=None, source_query_253_sha256=None,
        strategy_definition_sha256=None, config_sha256=None,
        code_sha256="1"*64, environment_sha256="2"*64,
        parent_receipt_sha256=sha, attempts=[attempt],
        evidence_class="TEST_ONLY", historical_pit="NOT_ATTESTED",
        holdout="SEALED_UNOPENED", trading_authority="NONE")
    factory_db = tmp_path / "factory.sqlite"
    receipt = register_experiment(factory_db, record)
    stored = read_experiment(factory_db, record["experiment_id"])
    assert stored["source_status"] == "HISTORICAL_SOURCE_BLOCKED"
    assert stored["lab_receipt_sha256"] is None and stored["paper_receipt_sha256"] is None
    assert stored["orders_created"] == 0 and receipt


def test_utc_day_boundary_and_registry_provenance(tmp_path):
    midnight = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()*1000)
    assert midnight == START
    source = tmp_path / "midnight.sqlite"
    start, end = feed(source, start=midnight, count=15)
    copied = tmp_path / "research.sqlite"
    _copy_generated_fixture_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000)
    wh, daily, registry, daily_context = _daily(tmp_path / "warehouse")
    assert registry["event_watermark"] >= 1
    assert registry["sources"][0]["source_zip_sha256"]
    assert daily_context["registry"]["snapshot_sha256"] == registry["snapshot_sha256"]
    with ResearchBarStore(copied) as store:
        realtime = store.read("BTCUSDT", "1m", START)
    assert reconcile_daily_bar(realtime, daily)["status"] == "MATCH_IDEMPOTENT"
    proposal = build_registry_proposal(reconcile_daily_bar(realtime, daily), daily_context)
    assert proposal["status"] == "PROPOSED_ONLY"


def test_unverifiable_raw_event_hash_never_admits_mutable_feed_rows(tmp_path):
    source = tmp_path / "unverified.sqlite"
    start, end = feed(source)
    db = sqlite3.connect(source)
    pin = db.execute("SELECT payload_sha256 FROM final_bar").fetchone()[0]
    assert len(pin) == 64 and all(ch in "0123456789abcdef" for ch in pin)
    db.close()
    # The persisted payload pin is raw-event SHA, while raw event bytes are absent.
    with pytest.raises(ValueError, match="FEED_SOURCE_LINEAGE_UNVERIFIED"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=end, now_ms=end+1_000)
    db = sqlite3.connect(source)
    db.execute("UPDATE final_bar SET close='1.5' WHERE open_ms=?", (start,))
    assert db.execute("SELECT payload_sha256 FROM final_bar").fetchone()[0] == pin
    db.commit()
    db.close()
    # A shape-valid unchanged pin cannot authorize changed OHLCV.
    with pytest.raises(ValueError, match="FEED_SOURCE_LINEAGE_UNVERIFIED"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=end, now_ms=end+1_000)


def test_feed_reader_uses_one_coherent_sqlite_snapshot(tmp_path, monkeypatch):
    import threading
    import tools.realtime_market_feed.atlas_integration as adapter

    source = tmp_path / "concurrent.sqlite"
    start, end = feed(source)
    snapshot_ready = threading.Event()
    writer_committed = threading.Event()
    received, failures = [], []

    def pause_between_snapshot_reads():
        snapshot_ready.set()
        if not writer_committed.wait(timeout=5):
            raise AssertionError("WRITER_DID_NOT_COMMIT")

    monkeypatch.setattr(adapter, "_SNAPSHOT_TEST_HOOK",
                        pause_between_snapshot_reads)

    def read_snapshot():
        try:
            received.extend(_project(source, symbol="BTCUSDT", start_ms=start,
                                     end_ms=end, now_ms=end+1_000))
        except Exception as exc:  # captured for assertion in the owner thread
            failures.append(exc)

    reader = threading.Thread(target=read_snapshot)
    reader.start()
    assert snapshot_ready.wait(timeout=5)
    writer = sqlite3.connect(source, timeout=5)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("""INSERT INTO open_gap(symbol,interval,start_ms,end_ms,reason,detected_ms)
                      VALUES(?,?,?,?,?,?)""",
                   ("BTCUSDT", "1m", start, end, "concurrent-fixture-gap", end))
    writer.execute("INSERT INTO service_event(at_ms,kind,detail) VALUES(?,?,?)",
                   (end, "FINAL_BAR_CONFLICT", "BTCUSDT:" + str(start)))
    writer.commit()
    writer.close()
    writer_committed.set()
    reader.join(timeout=5)
    monkeypatch.setattr(adapter, "_SNAPSHOT_TEST_HOOK", None)
    assert not reader.is_alive()
    assert not failures
    assert len(received) == 1
    # The next read observes the committed gap; the in-flight read saw pre-commit.
    with pytest.raises(ValueError, match="OPEN_HISTORY_GAP"):
        _project(source, symbol="BTCUSDT", start_ms=start,
                 end_ms=end, now_ms=end+1_000)


def test_unrelated_registry_or_daily_query_context_cannot_bind_bar(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source)
    copied = tmp_path / "research.sqlite"
    _copy_generated_fixture_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000)
    with ResearchBarStore(copied) as store:
        live = store.read("BTCUSDT", "1m", start)
    _, daily, _, context = _daily(tmp_path / "warehouse")
    reconciliation = reconcile_daily_bar(live, daily)
    wrong = dict(context, requested_window=[start+60_000, start+120_000])
    with pytest.raises(ValueError, match="DAILY_QUERY_ROW_NOT_BOUND|DAILY_QUERY_WINDOW_MISMATCH"):
        build_registry_proposal(reconciliation, wrong)
    realtime_only = reconcile_daily_bar(live, None)
    with pytest.raises(ValueError, match="NOT_VERIFIABLE_DAILY_ROW_ABSENT"):
        build_registry_proposal(realtime_only, context)
