import json
import sqlite3

import pytest

from tools.realtime_market_feed.reader import read_snapshot
from tools.realtime_market_feed.service import Store, build_report, make_url, normalize_symbols
from tools.realtime_market_feed.service import APP_MESSAGE_TIMEOUT_SECONDS, FINAL_BAR_PROGRESS_TIMEOUT_SECONDS


def test_symbol_normalization_and_bound():
    assert normalize_symbols("ethusdt,BTCUSDT,btcusdt") == ["btcusdt", "ethusdt"]
    with pytest.raises(ValueError, match="SYMBOL_COUNT_OUT_OF_RANGE"):
        normalize_symbols(",".join(f"S{i}" for i in range(65)))


def test_combined_stream_url_is_one_read_only_market_socket():
    url = make_url(["btcusdt"])
    assert url.startswith("wss://data-stream.binance.vision/stream?streams=")
    assert "btcusdt@bookTicker" in url
    assert "btcusdt@kline_1m" in url
    assert url.count("btcusdt@") == 3


def test_trade_quote_final_bar_and_gap_are_durable(tmp_path):
    store = Store(tmp_path / "market.sqlite")
    try:
        trade = {"e":"trade","s":"BTCUSDT","t":7,"p":"90000.10","q":"0.01","T":60001,"m":False}
        assert store.ingest(json.dumps({"stream":"btcusdt@trade","data":trade}), 60002) == "trade"
        quote = {"s":"BTCUSDT","u":8,"b":"90000.00","B":"1","a":"90001.00","A":"2"}
        assert store.ingest(json.dumps(quote), 60003) == "bookTicker"

        def bar(open_ms, close, final=True):
            return {"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":open_ms,"T":open_ms+59999,
                "o":"89999","h":"90002","l":"89998","c":close,"v":"12.4","n":5,"x":final}}

        assert store.ingest(json.dumps(bar(0,"90000.5",False)), 60004) == "provisional_ignored"
        assert store.ingest(json.dumps(bar(0,"90000.5")), 60005) == "final_bar"
        assert store.ingest(json.dumps(bar(120000,"90003")), 180006) == "final_bar"
        assert store.db.execute("SELECT price,trade_id FROM latest_trade").fetchone() == ("90000.10",7)
        assert store.db.execute("SELECT bid,ask FROM latest_quote").fetchone() == ("90000.00","90001.00")
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 2
        gap = store.db.execute("SELECT start_ms,end_ms,status FROM open_gap").fetchone()
        assert gap == (60000,120000,"OPEN")
    finally:
        store.db.close()


def test_duplicate_bar_is_idempotent_and_conflict_is_audited(tmp_path):
    store = Store(tmp_path / "market.sqlite")
    try:
        def raw(price):
            d={"e":"kline","s":"ETHUSDT","k":{"i":"1m","t":0,"T":59999,
                "o":"1","h":"2","l":"1","c":price,"v":"3","n":1,"x":True}}
            return json.dumps(d)
        store.ingest(raw("1.5"), 60001)
        store.ingest(raw("1.5"), 60002)
        store.ingest(raw("1.6"), 60003)
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 1
        assert store.db.execute("SELECT count(*) FROM service_event WHERE kind='FINAL_BAR_CONFLICT'").fetchone()[0] == 1
    finally:
        store.db.close()


def test_invalid_instrument_and_interval_fail_closed(tmp_path):
    store = Store(tmp_path / "market.sqlite")
    try:
        with pytest.raises(ValueError, match="MISSING_SYMBOL"):
            store.ingest(json.dumps({"e":"trade","p":"1"}))
        bad={"e":"kline","s":"BTCUSDT","k":{"i":"15m","x":True}}
        with pytest.raises(ValueError, match="UNSUPPORTED_KLINE_INTERVAL"):
            store.ingest(json.dumps(bad))
    finally:
        store.db.close()


def test_report_is_read_only_and_marks_only_observed_state(tmp_path):
    path=tmp_path/"market.sqlite"
    store=Store(path)
    store.event("CONNECTED","synthetic")
    store.db.close()
    result=build_report(path)
    assert result["schema"] == "atlas.realtime-market-feed.report.v1"
    assert result["readiness"] == "NOT_READY"
    assert result["orders"] == 0


def test_consumer_snapshot_requires_fresh_trade_quote_and_final_bar(tmp_path):
    path=tmp_path/"market.sqlite"
    store=Store(path)
    trade={"e":"trade","s":"BTCUSDT","t":1,"p":"100","q":"1","T":119000,"m":False}
    quote={"s":"BTCUSDT","u":2,"b":"99.9","B":"2","a":"100.1","A":"3"}
    bar={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":120000,"T":179999,
        "o":"100","h":"101","l":"99","c":"100.5","v":"10","n":4,"x":True}}
    store.ingest(json.dumps(trade),199500)
    store.ingest(json.dumps(quote),199500)
    store.ingest(json.dumps(bar),199500)
    before=store.db.execute("SELECT count(*) FROM service_event").fetchone()[0]
    store.db.close()
    result=read_snapshot(path,"BTCUSDT",now_ms=200000)
    assert result["status"] == "LIVE_FRESH"
    assert result["symbols"][0]["quote"]["bid"] == "99.9"
    assert result["symbols"][0]["latest_final_bar"]["close"] == "100.5"
    db=__import__("sqlite3").connect(path)
    assert db.execute("SELECT count(*) FROM service_event").fetchone()[0] == before
    db.close()


def test_consumer_snapshot_holds_stale_data_and_open_history_gap(tmp_path):
    path=tmp_path/"market.sqlite"
    store=Store(path)
    trade={"e":"trade","s":"BTCUSDT","t":1,"p":"100","q":"1","T":119000,"m":False}
    quote={"s":"BTCUSDT","u":2,"b":"99.9","B":"2","a":"100.1","A":"3"}
    bar={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":120000,"T":179999,
        "o":"100","h":"101","l":"99","c":"100.5","v":"10","n":4,"x":True}}
    store.ingest(json.dumps(trade),199500)
    store.ingest(json.dumps(quote),199500)
    store.ingest(json.dumps(bar),199500)
    with store.db:
        store.db.execute("""INSERT INTO open_gap
          (symbol,interval,start_ms,end_ms,reason,detected_ms)
          VALUES('BTCUSDT','1m',60000,120000,'TEST_GAP',199500)""")
    store.db.close()
    result=read_snapshot(path,"BTCUSDT",now_ms=240000,history_lookback_ms=300000)
    assert result["status"] == "HELD"
    assert "BTCUSDT:TRADE_STALE" in result["blockers"]
    assert "BTCUSDT:QUOTE_STALE" in result["blockers"]
    assert "BTCUSDT:OPEN_HISTORY_GAP" in result["blockers"]


def test_consumer_snapshot_holds_known_final_bar_conflict(tmp_path):
    path=tmp_path/"conflict.sqlite"
    store=Store(path)
    trade={"e":"trade","s":"BTCUSDT","t":1,"p":"100","q":"1","T":119000,"m":False}
    quote={"s":"BTCUSDT","u":2,"b":"99.9","B":"2","a":"100.1","A":"3"}
    bar={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":120000,"T":179999,
        "o":"100","h":"101","l":"99","c":"100.5","v":"10","n":4,"x":True}}
    store.ingest(json.dumps(trade),199500)
    store.ingest(json.dumps(quote),199500)
    store.ingest(json.dumps(bar),199500)
    store.event("FINAL_BAR_CONFLICT","BTCUSDT:120000")
    store.db.close()
    result=read_snapshot(path,"BTCUSDT",now_ms=200000)
    assert result["status"]=="HELD"
    assert "BTCUSDT:FINAL_BAR_CONFLICT" in result["blockers"]


def test_receive_watchdog_checks_message_silence_and_final_bar_progress(tmp_path):
    from tools.realtime_market_feed.service import LiveService
    store=Store(tmp_path/"watchdog.sqlite")
    service=LiveService(["btcusdt"],store)
    try:
        service._reset_receive_progress(100.0)
        assert service._receive_stall_reason(100.0+APP_MESSAGE_TIMEOUT_SECONDS-0.01) is None
        assert service._receive_stall_reason(100.0+APP_MESSAGE_TIMEOUT_SECONDS)=="APPLICATION_MESSAGE_SILENCE"
        with service._progress_lock:
            service._last_application_message=100.0+FINAL_BAR_PROGRESS_TIMEOUT_SECONDS-1
        assert service._receive_stall_reason(100.0+FINAL_BAR_PROGRESS_TIMEOUT_SECONDS)=="FINAL_BAR_PROGRESS_TIMEOUT:BTCUSDT"
    finally:
        store.db.close()


def test_receive_watchdog_closes_silent_socket_and_records_reason(tmp_path,monkeypatch):
    import threading
    import tools.realtime_market_feed.service as service_module
    from tools.realtime_market_feed.service import LiveService
    store=Store(tmp_path/"silent.sqlite")
    service=LiveService(["btcusdt"],store)
    attempts=[]

    class SilentSocket:
        def __init__(self,url,on_open,on_message,on_error,on_close):
            self.on_open=on_open;self.on_close=on_close
            self.closed=threading.Event()
        def close(self):
            if not self.closed.is_set():
                self.closed.set()
                service.stop=True
                self.on_close(self,1006,"watchdog")
        def run_forever(self,**kwargs):
            assert kwargs["ping_interval"]==service_module.PING_INTERVAL_SECONDS
            assert kwargs["ping_timeout"]==service_module.PING_TIMEOUT_SECONDS
            self.on_open(self)
            assert self.closed.wait(1),"silent socket was not closed by watchdog"
            attempts.append(1)

    monkeypatch.setattr(service_module.websocket,"WebSocketApp",SilentSocket)
    monkeypatch.setattr(service_module,"APP_MESSAGE_TIMEOUT_SECONDS",0.02)
    monkeypatch.setattr(service_module,"WATCHDOG_POLL_INTERVAL_SECONDS",0.005)
    monkeypatch.setattr(service_module,"MIN_RECONNECT_INTERVAL_SECONDS",0)
    monkeypatch.setattr(service_module,"MAX_SOCKET_AGE_SECONDS",60)
    monkeypatch.setattr(service_module.time,"sleep",lambda _seconds:None)
    try:
        service.run()
        kinds=[row[0] for row in store.db.execute("SELECT kind FROM service_event ORDER BY id")]
        assert len(attempts)==1
        assert "RECEIVE_WATCHDOG_CLOSED" in kinds
    finally:
        store.db.close()


def test_live_service_dispatches_final_bar_to_gap_recovery_worker(tmp_path, monkeypatch):
    import threading
    from tools.realtime_market_feed import backfill
    from tools.realtime_market_feed.service import LiveService

    called=threading.Event()
    observed=[]
    def recover(path,symbol,run_id=None):
        observed.append((path,symbol))
        called.set()
    monkeypatch.setattr(backfill,"recover_open_gaps",recover)
    store=Store(tmp_path/"market.sqlite")
    service=LiveService(["btcusdt"],store)
    bar={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":0,"T":59_999,
        "o":"10","h":"11","l":"9","c":"10.5","v":"2.5","n":4,"x":True}}
    try:
        service._on_message(json.dumps(bar))
        assert called.wait(2)
        assert observed == [(store.path,"BTCUSDT")]
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 1
    finally:
        store.db.close()



def test_live_service_reconnects_after_transport_close(tmp_path, monkeypatch):
    import tools.realtime_market_feed.service as service_module
    from tools.realtime_market_feed.service import LiveService

    attempts=[]
    service_holder={}
    class FakeSocket:
        def __init__(self,url,on_open,on_message,on_error,on_close):
            self.on_open=on_open
            self.on_close=on_close
        def close(self):
            self.on_close(self,1000,"timer")
        def run_forever(self,**kwargs):
            assert kwargs["ping_interval"] == service_module.PING_INTERVAL_SECONDS
            assert kwargs["ping_timeout"] == service_module.PING_TIMEOUT_SECONDS
            self.on_open(self)
            self.on_close(self,1006,"injected-drop")
            attempts.append(1)
            if len(attempts) == 2:
                service_holder["service"].stop=True

    monkeypatch.setattr(service_module.websocket,"WebSocketApp",FakeSocket)
    monkeypatch.setattr(service_module.time,"sleep",lambda _seconds: None)
    store=Store(tmp_path/"market.sqlite")
    service=LiveService(["btcusdt"],store)
    service_holder["service"]=service
    try:
        service.run()
        kinds=[row[0] for row in store.db.execute("SELECT kind FROM service_event ORDER BY id")]
        assert len(attempts) == 2
        assert kinds.count("CONNECTING") == 2
        assert kinds.count("CONNECTED") == 2
        assert kinds.count("DISCONNECTED") == 2
        assert "RECONNECT_WAIT" in kinds
    finally:
        store.db.close()



def test_final_bar_and_lineage_receipt_commit_atomically(tmp_path):
    store=Store(tmp_path/"atomic.sqlite")
    store.db.execute("DROP TABLE final_bar_lineage")
    store.db.commit()
    bar={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":0,"T":59_999,
        "o":"10","h":"11","l":"9","c":"10.5","v":"2.5","n":4,"x":True}}
    try:
        with pytest.raises(sqlite3.OperationalError):
            store.ingest(json.dumps(bar),received_ms=60_000)
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 0
    finally:
        store.db.close()


def test_observation_run_events_are_bound_and_full_evidence_is_versioned(tmp_path):
    from tools.realtime_market_feed.observation_evidence import build_observation_evidence

    path=tmp_path/"run.sqlite"
    store=Store(path)
    run_id=store.begin_run(["btcusdt"],86_400)
    store.event("PLANNED_ROTATION")
    store.event("CONNECTED","symbols=1")
    store.event("SERVICE_STOP")
    store.end_run(run_id)
    store.db.close()

    evidence=build_observation_evidence(path,run_id)
    assert evidence["schema"]=="atlas.realtime-market-feed.observation-evidence.v2"
    assert evidence["events_complete"] is True
    assert evidence["events"]
    assert all(event["run_id"]==run_id for event in evidence["events"])
    assert all(type(event["monotonic_ms"]) is int for event in evidence["events"])
    assert evidence["verification"]["method"]=="READ_ONLY_SQLITE_REOPEN_AND_RECOMPUTE"
    assert evidence["verification"]["event_count"]==len(evidence["events"])
    assert evidence["clock_validation"]["start_skew_ms"] is not None
    assert evidence["clock_validation"]["stop_skew_ms"] is not None
    assert evidence["coverage"]["expected_closed_bars"]==0

    ordinary=build_report(path)
    assert ordinary["schema"]=="atlas.realtime-market-feed.report.v1"
    assert "events_complete" not in ordinary


def test_duplicate_conflict_and_old_final_do_not_feed_progress_watchdog(tmp_path, monkeypatch):
    from tools.realtime_market_feed import service as module
    now=[100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda:now[0])
    store=Store(tmp_path/'progress.sqlite')
    service=module.LiveService(['btcusdt'],store)
    queued=[]
    monkeypatch.setattr(service,'_queue_gap_recovery',queued.append)
    def packet(opened, close='10.5'):
        return json.dumps({'e':'kline','s':'BTCUSDT','k':{'i':'1m','t':opened,
            'T':opened+59999,'o':'10','h':'11','l':'9','c':close,'v':'2.5','n':4,'x':True}})
    try:
        service._on_message(packet(60000))
        baseline=service._last_final_bar['BTCUSDT']
        for raw in (packet(60000),packet(60000,'10.6'),packet(0)):
            now[0]+=module.FINAL_BAR_PROGRESS_TIMEOUT_SECONDS/2
            service._on_message(raw)
            assert service._last_final_bar['BTCUSDT']==baseline
            assert service._last_application_message==now[0]
        assert service._receive_stall_reason()=='FINAL_BAR_PROGRESS_TIMEOUT:BTCUSDT'
        class Socket:
            closed=False
            def close(self):self.closed=True
        class Tick:
            def wait(self,seconds):return False
        socket=Socket();result={}
        service._watch_receive_progress(socket,Tick(),result)
        assert socket.closed and result['reason']=='FINAL_BAR_PROGRESS_TIMEOUT:BTCUSDT'
        assert queued==['BTCUSDT']
        # Durable real advance refreshes the final timer; committed old data did not.
        service._on_message(packet(120000))
        assert service._receive_stall_reason() is None
        assert queued==['BTCUSDT','BTCUSDT']
    finally:
        store.db.close()


def test_failed_final_commit_cannot_refresh_progress(tmp_path,monkeypatch):
    from tools.realtime_market_feed import service as module
    store=Store(tmp_path/'failed-progress.sqlite')
    service=module.LiveService(['btcusdt'],store)
    before=dict(service._last_final_bar)
    store.db.execute('DROP TABLE final_bar_lineage');store.db.commit()
    try:
        service._on_message(json.dumps({'e':'kline','s':'BTCUSDT','k':{'i':'1m','t':0,
            'T':59999,'o':'10','h':'11','l':'9','c':'10.5','v':'2.5','n':4,'x':True}}))
        assert service._last_final_bar==before
        assert store.db.execute('SELECT count(*) FROM final_bar').fetchone()[0]==0
    finally:store.db.close()
