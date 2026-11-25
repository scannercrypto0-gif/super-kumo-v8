import json

import pytest

from tools.realtime_market_feed.service import Store, build_report, make_url, normalize_symbols


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
