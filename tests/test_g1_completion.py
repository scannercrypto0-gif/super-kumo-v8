"""Controlled non-production acceptance for the actual G1 adapters and lanes."""
import json
import threading
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
import pytest

from aql.models.bar import MarketBar
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.storage.sandbox_store import PostgresSandboxStore, SandboxReplicator, StoreUnavailable
from aql.collector.binance_collector import BinanceCollector
from aql.lanes import BackgroundLane, JournalConsumer, WritePriority
from aql.recovery.rest_budget import RestBudget
from aql.recovery.gap_recovery import recover_gap, _fetch_klines


def bar(i=0):
    return MarketBar("BTCUSDT", "1m", 60000*i, 60000*(i+1)-1,
                     10., 11., 9., 10., 1., True, "binance_ws",
                     60000*(i+1)).with_checksum()


def stores(tmp_path):
    return DurableJournal(str(tmp_path/"journal.sqlite")), OperationalStore(str(tmp_path/"store.sqlite"))


def test_stalled_background_does_not_block_ingestion_and_join_is_bounded(tmp_path):
    journal, store = stores(tmp_path)
    entered, release = threading.Event(), threading.Event()
    lane = BackgroundLane(capacity=1)
    lane.submit(lambda stop: (entered.set(), release.wait(5)))
    assert entered.wait(2)
    assert lane.submit(lambda stop: None)
    assert not lane.submit(lambda stop: None)
    try:
        journal.commit(bar())
        assert len(journal.replay()) == 1
        started = time.monotonic()
        status = lane.finish(timeout=0.05)
        assert time.monotonic()-started < 1
        assert status["pending"] and status["worker_alive"]
    finally:
        release.set()
        lane.thread.join(2)


def test_background_exception_is_contained():
    lane = BackgroundLane()
    done = threading.Event()
    def fail(stop):
        raise RuntimeError("synthetic")
    lane.submit(fail)
    lane.submit(lambda stop: done.set())
    assert done.wait(2)
    status = lane.finish()
    assert status["errors"] == ["RuntimeError"]


def test_core_waiter_precedes_next_background_writer():
    gate = WritePriority()
    order = []
    def write(label, background):
        with gate.hold(background):
            order.append(label)
    with gate.hold(background=True):
        core = threading.Thread(target=write, args=("core", False))
        core.start()
        deadline = time.monotonic()+2
        while gate.core_waiters != 1 and time.monotonic() < deadline:
            time.sleep(.001)
        assert gate.core_waiters == 1
        slow = threading.Thread(target=write, args=("background", True))
        slow.start()
    core.join(2); slow.join(2)
    assert order == ["core", "background"]


def test_failed_store_keeps_durable_backlog_and_restart_replays_duplicates(tmp_path):
    journal, store = stores(tmp_path)
    journal.commit(bar())
    consumer = JournalConsumer(journal, Mock(upsert=Mock(side_effect=ConnectionError())), "BTCUSDT", "1m")
    with pytest.raises(ConnectionError):
        consumer.drain_once()
    assert journal.count_by_state()["LOCAL_COMMITTED"] == 1
    store.upsert(bar())  # simulate crash after remote/local commit, before ACK
    consumer = JournalConsumer(DurableJournal(journal.db_path), store, "BTCUSDT", "1m")
    assert consumer.drain_once() == 1
    assert store.count() == 1
    assert journal.count_by_state()["PERSISTED"] == 1


def test_collector_callback_never_calls_slow_store_when_isolated(tmp_path):
    journal, _ = stores(tmp_path)
    store = Mock()
    store.upsert.side_effect = AssertionError("must not run in callback")
    c = BinanceCollector("BTCUSDT", "1m", journal, store)
    c.background_persistence = True
    k = dict(s="BTCUSDT", i="1m", t=0, T=59999, o="10", h="11", l="9", c="10", v="1", x=True)
    c._on_message(Mock(), json.dumps({"k": k}))
    c._on_message(Mock(), json.dumps({"k": k}))
    assert c.metrics.error_count == 0
    assert c.metrics.duplicate_count == 1
    store.upsert.assert_not_called()
    assert len(journal.replay()) == 1


@pytest.mark.parametrize("change", [{"s":"ETHUSDT"}, {"x":"false"}, {"T":9999999999999}])
def test_invalid_or_future_closed_candle_not_committed(tmp_path, change):
    journal, store = stores(tmp_path)
    c = BinanceCollector("BTCUSDT", "1m", journal, store)
    k = dict(s="BTCUSDT", i="1m", t=0, T=59999, o="10", h="11", l="9", c="10", v="1", x=True)
    k.update(change)
    c._on_message(Mock(), json.dumps({"k": k}))
    assert c.metrics.error_count == 1
    assert not journal.replay()


def test_shared_rate_budget_reserve_header_and_retry_after():
    clock = [0.]
    budget = RestBudget(limit=10, reserve=2, clock=lambda: clock[0])
    budget.acquire(8)
    with pytest.raises(RuntimeError):
        budget.acquire(2)
    budget.acquire(2, core=True)
    clock[0] = 61
    budget.observe(9)
    budget.cooldown(60)
    with pytest.raises(RuntimeError):
        budget.acquire(core=True)
    clock[0] = 122
    budget.acquire(2)


def test_429_cooldown_without_retrying_endpoint():
    from urllib.error import HTTPError
    budget = Mock()
    with patch("aql.recovery.gap_recovery.SHARED_REST_BUDGET", budget), patch(
        "aql.recovery.gap_recovery.urllib.request.urlopen",
        side_effect=HTTPError("https://api.binance.com",429,"rate",{"Retry-After":"10"},None)
    ) as http:
        with pytest.raises(RuntimeError, match="HTTP 429"):
            _fetch_klines("BTCUSDT", "1m", 0, 60000)
    assert http.call_count == 1
    budget.cooldown.assert_called_once_with(10.)


def connection(inserted=True):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [(0,)] if inserted else [None, (bar().compute_checksum(),)]
    return conn


def test_postgres_commit_duplicate_and_nonfinal_boundary():
    conn = connection()
    store = PostgresSandboxStore(lambda: conn, sandbox=True)
    assert store.upsert(bar())
    conn.commit.assert_called_once()
    sql = conn.cursor.return_value.__enter__.return_value.execute.call_args[0][0]
    assert "ON CONFLICT" in sql
    conn2 = connection(False)
    assert not PostgresSandboxStore(lambda: conn2, sandbox=True).upsert(bar())
    b = bar(); b.is_final = False
    with pytest.raises(ValueError):
        store.upsert(b)
    with pytest.raises(ValueError):
        PostgresSandboxStore(lambda: conn, sandbox=False)


def test_postgres_failure_rolls_back_redacts_and_retries_bounded():
    conns = [connection() for _ in range(3)]
    for c in conns:
        c.commit.side_effect = TimeoutError("DSN_MUST_NOT_LEAK")
    connect = Mock(side_effect=conns)
    sleep = Mock()
    store = PostgresSandboxStore(connect, sandbox=True, sleep=sleep)
    with pytest.raises(StoreUnavailable) as error:
        store.upsert(bar())
    assert "DSN_MUST_NOT_LEAK" not in str(error.value)
    assert connect.call_count == 3
    assert sleep.call_count == 2
    for c in conns:
        c.rollback.assert_called_once()
        c.close.assert_called_once()


def test_remote_cursor_independent_from_local_ack_and_restart(tmp_path):
    j, local = stores(tmp_path)
    for i in range(3):
        b = bar(i); j.commit(b); local.upsert(b); j.mark_persisted(b.stable_key())
    remote = OperationalStore(str(tmp_path/"fake-remote.sqlite"))
    path = str(tmp_path/"cursor.sqlite")
    r = SandboxReplicator(j, remote, path, batch_size=2)
    assert r.deliver_once() == 2
    r = SandboxReplicator(j, remote, path, batch_size=2)
    assert r.deliver_once() == 1
    assert r.deliver_once() == 0
    assert remote.count() == 3


def test_remote_commit_before_cursor_failure_is_idempotent_on_retry(tmp_path):
    j, local = stores(tmp_path); j.commit(bar())
    remote = OperationalStore(str(tmp_path/"fake-remote.sqlite"))
    r = SandboxReplicator(j, remote, str(tmp_path/"cursor.sqlite"))
    original = r._connect
    calls = [0]
    def connect():
        calls[0] += 1
        if calls[0] == 2:
            raise OSError("cursor unavailable after remote commit")
        return original()
    with patch.object(r, "_connect", side_effect=connect):
        with pytest.raises(OSError):
            r.deliver_once()
    assert remote.count() == 1
    assert r.deliver_once() == 1
    assert remote.count() == 1


def test_failed_remote_does_not_advance_cursor(tmp_path):
    j, _ = stores(tmp_path); j.commit(bar())
    remote = Mock()
    remote.upsert.side_effect = StoreUnavailable("offline")
    path = str(tmp_path/"cursor.sqlite")
    r = SandboxReplicator(j, remote, path)
    with pytest.raises(StoreUnavailable):
        r.deliver_once()
    remote.upsert.side_effect = None
    assert SandboxReplicator(j, remote, path).deliver_once() == 1


def test_large_gap_job_is_bounded_and_unresolved():
    with patch("aql.recovery.gap_recovery._fetch_klines", return_value=([],0)):
        _, report = recover_gap("BTCUSDT","1m",0,60000*1000000,set())
    assert report.unresolved > 8000
    assert len(report.missing_opens) <= 8000
    assert report.status == "UNRESOLVED_DATA_GAP"


def test_missing_bar_detected_without_disconnect_and_out_of_order_not_regressed(tmp_path):
    j, store = stores(tmp_path)
    c = BinanceCollector("BTCUSDT", "1m", j, store)
    c.background_persistence = True
    for i in (0, 3, 1):
        k = dict(s="BTCUSDT", i="1m", t=i*60000, T=(i+1)*60000-1,
                 o="10", h="11", l="9", c="10", v="1", x=True)
        c._on_message(Mock(), json.dumps({"k":k}))
    assert c.gap_start_ms == 60000
    assert c.gap_end_ms == 180000
    assert c.metrics.last_bar_open == 180000


def test_real_pipeline_enters_collection_while_startup_recovery_is_stalled(tmp_path):
    from aql.pipeline import run_pipeline
    from aql.collector.binance_collector import CollectorMetrics
    from aql.recovery.gap_recovery import RecoveryReport
    j = DurableJournal(str(tmp_path/"journal.sqlite"))
    j.commit(bar())
    entered, release = threading.Event(), threading.Event()
    def recovery(**kwargs):
        entered.set()
        assert release.wait(5)
        return [], RecoveryReport("BTCUSDT","1m",0,60000,0,0,0,0,[],
                                  "FULL",0,0,None)
    class Collector:
        def __init__(self, symbol, interval, journal, store):
            self.journal = journal
            self.gap_start_ms = self.gap_end_ms = None
        def run(self, timeout_s):
            assert entered.wait(2), "startup must run independently"
            assert not release.is_set()
            self.journal.commit(bar(1))
            release.set()
            return CollectorMetrics()
    try:
        with patch("aql.pipeline.BinanceCollector", Collector), patch(
                "aql.pipeline.recover_gap", side_effect=recovery):
            result = run_pipeline(data_dir=str(tmp_path), duration_s=0,
                                  now_ms_fn=lambda: 120000)
    finally:
        release.set()
    assert result["store_total"] == 2
    assert not result["background_recovery"]["pending"]


def test_disposable_postgres_sandbox():
    import os
    if os.environ.get("AQL_DISPOSABLE_POSTGRES_TEST") != "1":
        pytest.skip("Disposable PostgreSQL integration is CI-only; Supabase cloud not tested")
    psycopg = pytest.importorskip("psycopg")
    from pathlib import Path
    dsn = "postgresql://postgres@127.0.0.1:5432/atlas_sandbox"
    def connect():
        return psycopg.connect(dsn, connect_timeout=3)
    with connect() as conn:
        conn.execute((Path(__file__).resolve().parents[1]/
                      "migrations/sandbox/001_market_bars.sql").read_text())
        conn.execute("TRUNCATE aql_sandbox.market_bars")
        conn.execute((Path(__file__).resolve().parents[1]/
                      "migrations/sandbox/002_writer_role.sql").read_text())
    def writer():
        conn = connect()
        conn.execute("SET ROLE aql_sandbox_writer")
        return conn
    store = PostgresSandboxStore(writer, sandbox=True)
    assert store.upsert(bar())
    assert not store.upsert(bar())
    conflicting = bar()
    conflicting.close = 10.25
    conflicting.with_checksum()
    with pytest.raises(StoreUnavailable):
        store.upsert(conflicting)
    with connect() as conn:
        row = conn.execute("SELECT count(*), min(source), min(ingested_at) "
                           "FROM aql_sandbox.market_bars").fetchone()
        assert row == (1, "binance_ws", 60000)


def test_clock_ahead_source_is_fail_closed(tmp_path):
    j, store = stores(tmp_path)
    c = BinanceCollector("BTCUSDT","1m",j,store)
    with patch("aql.collector.binance_collector.time.time", return_value=1000):
        c._on_message(Mock(), json.dumps({"E":1010001,"k":{"x":False}}))
    assert c.health_state == "CLOCK_UNCERTAIN"
    assert c.metrics.error_count == 1
    assert not j.replay()

def test_conflicting_postgres_duplicate_is_not_acknowledged():
    conn = connection(False)
    conn.cursor.return_value.__enter__.return_value.fetchone.side_effect = [None, ("other-hash",)]
    with pytest.raises(StoreUnavailable):
        PostgresSandboxStore(lambda:conn, sandbox=True).upsert(bar())
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()


def test_journal_identity_survives_restart_and_replacement_denies_cursor(tmp_path):
    import os
    j, local = stores(tmp_path)
    identity = j.instance_id
    j.commit(bar())
    assert DurableJournal(j.db_path).instance_id == identity
    remote = OperationalStore(str(tmp_path/"remote.sqlite"))
    path = str(tmp_path/"cursor.sqlite")
    consumer = SandboxReplicator(j, remote, path)
    assert consumer.deliver_once() == 1
    replacement = DurableJournal(str(tmp_path/"replacement.sqlite"))
    replacement.commit(bar(7))
    os.replace(replacement.db_path, j.db_path)
    with pytest.raises(ValueError, match="replaced"):
        consumer.deliver_once()
    with pytest.raises(ValueError, match="different journal"):
        SandboxReplicator(j, remote, path)
    assert remote.count() == 1


def test_delivery_cursor_detects_journal_rollback(tmp_path):
    j, remote = stores(tmp_path)
    j.commit(bar())
    consumer = SandboxReplicator(j, remote, str(tmp_path/"cursor.sqlite"))
    assert consumer.deliver_once() == 1
    conn = j._connect()
    try:
        conn.execute("DELETE FROM journal_entries")
    finally:
        conn.close()
    with pytest.raises(ValueError, match="rollback"):
        consumer.deliver_once()


def test_commit_failure_does_not_advance_gap_watermark(tmp_path):
    j, store = stores(tmp_path)
    c = BinanceCollector("BTCUSDT","1m",j,store)
    c.background_persistence = True
    def receive(i):
        k = dict(s="BTCUSDT",i="1m",t=i*60000,T=(i+1)*60000-1,
                 o="10",h="11",l="9",c="10",v="1",x=True)
        c._on_message(Mock(),json.dumps({"k":k}))
    receive(0)
    with patch.object(j,"commit",side_effect=OSError("synthetic unavailable journal")):
        receive(1)
    assert c.metrics.last_bar_open == 0
    receive(2)
    assert c.metrics.error_count == 1
    assert c.gap_start_ms == 60000
    assert c.gap_end_ms == 120000


def test_clock_fault_survives_socket_close(tmp_path):
    j, store = stores(tmp_path)
    c = BinanceCollector("BTCUSDT","1m",j,store)
    with patch("aql.collector.binance_collector.time.time",return_value=1000):
        c._on_message(Mock(),json.dumps({"E":1010001,"k":{"x":False}}))
    c._on_close(Mock(),1000,"synthetic close")
    assert c.clock_uncertain
    assert c.health_state == "DISCONNECTED"


def test_pipeline_cannot_report_healthy_after_collector_error(tmp_path):
    from aql.pipeline import run_pipeline
    from aql.collector.binance_collector import CollectorMetrics
    class Collector:
        def __init__(self,symbol,interval,journal,store):
            self.journal,self.store=journal,store
            self.gap_start_ms=self.gap_end_ms=None
        def run(self,timeout_s):
            b=bar();self.journal.commit(b);self.store.upsert(b)
            self.journal.mark_persisted(b.stable_key())
            return CollectorMetrics(error_count=1)
    with patch("aql.pipeline.BinanceCollector",Collector):
        result=run_pipeline(data_dir=str(tmp_path),duration_s=0,now_ms_fn=lambda:60000)
    assert result["health_snapshot"]["status"]=="UNHEALTHY"
    assert result["health_snapshot"]["reconcile_error"]


def test_sqlite_write_lock_is_bounded_and_uncommitted_bar_not_claimed(tmp_path):
    j, store = stores(tmp_path)
    c=BinanceCollector("BTCUSDT","1m",j,store)
    c.background_persistence=True
    conn=j._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        started=time.monotonic()
        k=dict(s="BTCUSDT",i="1m",t=0,T=59999,o="10",h="11",l="9",c="10",v="1",x=True)
        c._on_message(Mock(),json.dumps({"k":k}))
        assert time.monotonic()-started<2
        assert c.metrics.error_count==1
        assert c.metrics.journal_commit_count==0
        assert c.metrics.last_bar_open is None
    finally:
        conn.execute("ROLLBACK");conn.close()
    assert not j.replay()
