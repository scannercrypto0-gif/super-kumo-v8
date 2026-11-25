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
    build_registry_proposal, copy_to_research_store, project_feed_window,
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
    store.db.commit()
    store.db.close()
    return start, start + count * 60_000


def _daily(root, *, changed=None):
    w = HistoricalWarehouse(root, reserve=0, test_root=True)
    raw, check = daily_fixture(count=15, changed=changed)
    with w.writer():
        w.import_archive(raw, check, KEY, observed_ms=START + DAY)
    row = w.query("1m", START, START + 60_000,
                  cutoff_ms=START + DAY, include_registry=True)
    return w, row["bars"][0], row["registry"]


def _bytes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


def test_finalized_feed_to_native_research_store_is_idempotent_and_read_only(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=1)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    target = tmp_path / "research.sqlite"
    result = copy_to_research_store(source, target, symbol="BTCUSDT",
                                    start_ms=start, end_ms=end,
                                    now_ms=end + 1_000, engineering_test_only=True)
    again = copy_to_research_store(source, target, symbol="BTCUSDT",
                                   start_ms=start, end_ms=end,
                                   now_ms=end + 1_000, engineering_test_only=True)
    assert result["rows"] == again["rows"] == 1
    with ResearchBarStore(target) as store:
        row = store.read("BTCUSDT", "1m", start)
    assert row["source_class"] == "FORWARD_UNQUALIFIED"
    assert row["trading_authority"] == "NONE"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_integration_writer_is_disabled_without_test_only_switch(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source)
    with pytest.raises(ValueError, match="INTEGRATION_DISABLED"):
        copy_to_research_store(source, tmp_path / "research.sqlite",
                               symbol="BTCUSDT", start_ms=start, end_ms=end,
                               now_ms=end+1_000)
    outside = Path(__import__("tempfile").gettempdir()).parent / "forbidden.sqlite"
    with pytest.raises(ValueError, match="ISOLATED_RESEARCH_STORE_REQUIRED"):
        copy_to_research_store(source, outside, symbol="BTCUSDT",
                               start_ms=start, end_ms=end, now_ms=end+1_000,
                               engineering_test_only=True)


def test_provisional_and_missing_symbol_fail_closed(tmp_path):
    source = tmp_path / "provisional.sqlite"
    store = FeedStore(source)
    start = START
    provisional = {"e":"kline","s":"BTCUSDT","E":start+30_000,
                   "k":{"s":"BTCUSDT","i":"1m","x":False,"t":start,
                        "T":start+59_999,"o":"1","h":"2","l":"1","c":"1","v":"3","n":1}}
    assert store.ingest(json.dumps(provisional), received_ms=start+30_000) == "provisional_ignored"
    store.db.close()
    with pytest.raises(ValueError, match="SYMBOL_OR_WINDOW_MISSING"):
        _project(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=start+60_000, now_ms=start+61_000)

    source = tmp_path / "missing-symbol.sqlite"
    start, end = feed(source)
    with pytest.raises(ValueError, match="SYMBOL_OR_WINDOW_MISSING"):
        project_feed_window(source, symbol="ETHUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)


def test_stale_and_open_gap_fail_closed(tmp_path):
    source = tmp_path / "stale.sqlite"
    start, end = feed(source, stale=True)
    with pytest.raises(ValueError, match="FEED_STALE"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)
    source = tmp_path / "gap.sqlite"
    start, end = feed(source)
    db = sqlite3.connect(source)
    db.execute("""INSERT INTO open_gap(symbol,interval,start_ms,end_ms,reason,detected_ms)
                  VALUES(?,?,?,?,?,?)""", ("BTCUSDT","1m",start,end,"fixture",end))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="OPEN_HISTORY_GAP"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start, end_ms=end,
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
    assert len(project_feed_window(source, symbol="BTCUSDT", start_ms=start,
                                  end_ms=end, now_ms=end+1_000)) == 1

    source = tmp_path / "conflict.sqlite"
    start, end = feed(source)
    store = FeedStore(source)
    data["k"]["c"] = "1.5"
    store.ingest(json.dumps(data), received_ms=end+1)
    store.db.commit()
    store.db.close()
    with pytest.raises(ValueError, match="FEED_BAR_CONFLICT"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start, end_ms=end,
                            now_ms=end+1_000)


def test_missing_receipt_bad_utc_grid_and_incomplete_aggregation_fail_closed(tmp_path):
    source = tmp_path / "receipt.sqlite"
    start, end = feed(source, count=15)
    db = sqlite3.connect(source)
    db.execute("UPDATE final_bar SET payload_sha256='missing' WHERE open_ms=?", (start,))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="FEED_RECEIPT_INVALID"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start,
                            end_ms=start+60_000, now_ms=start+61_000)

    with pytest.raises(ValueError, match="UTC_WINDOW_INVALID"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=start+1,
                            end_ms=start+60_001, now_ms=end+1_000)

    source = tmp_path / "short.sqlite"
    start, end = feed(source, count=14)
    copied = tmp_path / "short-research.sqlite"
    copy_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000, engineering_test_only=True)
    with ResearchBarStore(copied) as store:
        with pytest.raises(ValueError, match="SOURCE_GAP"):
            store.project("BTCUSDT", "15m", start)


def test_corrupt_database_is_held(tmp_path):
    source = tmp_path / "corrupt.sqlite"
    source.write_bytes(b"not sqlite")
    with pytest.raises(ValueError, match="FEED_DATABASE_INVALID|FEED_DATABASE_CORRUPT"):
        project_feed_window(source, symbol="BTCUSDT", start_ms=START,
                            end_ms=START+60_000, now_ms=START+61_000)


def test_daily_overlap_proposal_is_read_only_and_hash_pinned(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=15)
    target = tmp_path / "research.sqlite"
    copy_to_research_store(source, target, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000, engineering_test_only=True)
    with ResearchBarStore(target) as store:
        live = store.read("BTCUSDT", "1m", START)
        live_15m = store.project("BTCUSDT", "15m", START)
    wh, historical, registry = _daily(tmp_path / "warehouse")
    daily_15m = wh.query("15m", START, START+900_000,
                         cutoff_ms=START+DAY)[0]
    before = _bytes(wh.root)
    match = reconcile_daily_bar(live, historical)
    aggregate_match = reconcile_daily_bar(live_15m, daily_15m)
    assert match["status"] == "MATCH_IDEMPOTENT"
    assert aggregate_match["status"] == "MATCH_IDEMPOTENT"
    assert match["duplicate_insert"] is False and match["write_performed"] is False
    proposal = build_registry_proposal(aggregate_match, registry)
    assert proposal["status"] == "PROPOSED_ONLY"
    assert proposal["registry_mutation"] is False
    assert _bytes(wh.root) == before


def test_daily_ohlcv_conflict_and_missing_realtime_produce_proposals_not_repairs(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=3)
    copied = tmp_path / "research.sqlite"
    copy_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000, engineering_test_only=True)
    with ResearchBarStore(copied) as store:
        live = store.read("BTCUSDT", "1m", START)
    wh, historical, registry = _daily(tmp_path / "warehouse", changed=2)
    # Same UTC key, but source OHLCV differs; originals stay untouched.
    daily_conflict = wh.query("1m", START+120_000, START+180_000,
                              cutoff_ms=START+DAY)[0]
    with ResearchBarStore(copied) as store:
        live_row = store.read("BTCUSDT", "1m", START+120_000)
    conflict = reconcile_daily_bar(live_row, daily_conflict)
    assert conflict["status"] == "CONFLICT"
    missing = reconcile_daily_bar(None, historical)
    assert missing["status"] == "MISSING_REALTIME"
    assert missing["recovery"] == "AUTHORIZED_BOUNDED_RECOVERY_REQUIRED"
    assert build_registry_proposal(conflict, registry)["warehouse_mutation"] is False


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


def test_core_scanner_and_factory_record_wait_without_running_strategy(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = feed(source, count=180)
    research = tmp_path / "research.sqlite"
    copy_to_research_store(source, research, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000, engineering_test_only=True)
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
    copy_to_research_store(source, copied, symbol="BTCUSDT", start_ms=start,
                           end_ms=end, now_ms=end+1_000, engineering_test_only=True)
    wh, daily, registry = _daily(tmp_path / "warehouse")
    assert registry["event_watermark"] >= 1
    assert registry["sources"][0]["source_zip_sha256"]
    assert daily_context["registry"]["snapshot_sha256"] == registry["snapshot_sha256"]
    with ResearchBarStore(copied) as store:
        realtime = store.read("BTCUSDT", "1m", START)
    assert reconcile_daily_bar(realtime, daily)["status"] == "MATCH_IDEMPOTENT"
