import json
from urllib.parse import parse_qs, urlparse

from tools.realtime_market_feed.backfill import recover_gap
from tools.realtime_market_feed.service import Store


def _bar(open_ms, close="10.5"):
    return [open_ms,"10.0","11.0","9.5",close,"2.5",open_ms+59_999,"25.0",4,"1.0","10.0","0"]


def _store_with_two_minute_gap(tmp_path):
    store=Store(tmp_path/"market.sqlite")
    first={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":0,"T":59_999,
        "o":"10","h":"11","l":"9.5","c":"10.5","v":"2.5","n":4,"x":True}}
    after={"e":"kline","s":"BTCUSDT","k":{"i":"1m","t":180_000,"T":239_999,
        "o":"10","h":"11","l":"9.5","c":"10.5","v":"2.5","n":4,"x":True}}
    store.ingest(json.dumps(first),60_000)
    store.ingest(json.dumps(after),240_000)
    return store


def _client(rows):
    def fetch(url):
        if url.endswith("/api/v3/time"):
            return {"serverTime": 300_000}
        query=parse_qs(urlparse(url).query)
        assert query["symbol"] == ["BTCUSDT"]
        assert query["interval"] == ["1m"]
        return rows
    return fetch


def test_verified_backfill_commits_all_minutes_and_closes_gap(tmp_path):
    store=_store_with_two_minute_gap(tmp_path)
    try:
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
                           fetch_json=_client([_bar(60_000),_bar(120_000,"10.7")]))
        assert result == {"status":"CLOSED","bars":2}
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 4
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "CLOSED"
        event=store.db.execute("SELECT kind,detail FROM service_event WHERE kind='GAP_BACKFILL_COMPLETED'").fetchone()
        assert event[0] == "GAP_BACKFILL_COMPLETED"
        assert "source=REST" in event[1]
    finally:
        store.db.close()


def test_incomplete_backfill_keeps_gap_open_and_writes_no_partial_bars(tmp_path):
    store=_store_with_two_minute_gap(tmp_path)
    try:
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
                           fetch_json=_client([_bar(60_000)]))
        assert result["status"] == "OPEN_FAILED"
        assert result["reason"].startswith("ValueError:BACKFILL_KLINES_INCOMPLETE")
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 2
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "OPEN"
        assert store.db.execute("SELECT count(*) FROM service_event WHERE kind='GAP_BACKFILL_FAILED'").fetchone()[0] == 1
    finally:
        store.db.close()


def test_conflicting_existing_bar_keeps_gap_open_and_rolls_back(tmp_path):
    store=_store_with_two_minute_gap(tmp_path)
    with store.db:
        store.db.execute("""INSERT INTO final_bar VALUES
            ('BTCUSDT','1m',60000,119999,'10','11','9.5','99','2.5',4,120000,'conflict')""")
    try:
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
                           fetch_json=_client([_bar(60_000),_bar(120_000,"10.7")]))
        assert result["status"] == "OPEN_FAILED"
        assert "BACKFILL_EXISTING_BAR_CONFLICT" in result["reason"]
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "OPEN"
        assert store.db.execute("SELECT count(*) FROM final_bar").fetchone()[0] == 3
    finally:
        store.db.close()


def test_unfinalized_rest_rows_are_rejected(tmp_path):
    store=_store_with_two_minute_gap(tmp_path)
    client=lambda url: {"serverTime":120_000} if url.endswith("/api/v3/time") else [_bar(60_000),_bar(120_000)]
    try:
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,fetch_json=client)
        assert result["status"] == "OPEN_FAILED"
        assert "BACKFILL_RANGE_NOT_CLOSED" in result["reason"]
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "OPEN"
    finally:
        store.db.close()
