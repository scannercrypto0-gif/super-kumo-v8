import json

import pytest
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



def _current_fixture_gap(tmp_path):
    import time
    minute = time.time_ns() // 60_000_000_000 * 60_000
    start = minute - 4 * 60_000
    store = Store(tmp_path / "mixed.sqlite")
    def ws_bar(opened):
        event = {"e":"kline","s":"BTCUSDT","E":opened+59_999,
                 "k":{"s":"BTCUSDT","i":"1m","x":True,"t":opened,
                      "T":opened+59_999,"o":"10","h":"11","l":"9.5",
                      "c":"10.5","v":"2.5","n":4}}
        store.ingest(json.dumps(event), received_ms=minute+1_000)
    ws_bar(start)
    ws_bar(start+180_000)
    return store, start, start+240_000, minute


def test_rest_recovery_has_distinct_receipt_and_mixed_window_is_admitted(tmp_path):
    import time
    from tools.realtime_market_feed.backfill import REST_LINEAGE_SCHEMA, REST_PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.atlas_integration import project_feed_window

    store, start, end, now = _current_fixture_gap(tmp_path)
    try:
        result = recover_gap(store.path, "BTCUSDT", start+60_000, start+180_000,
            fetch_json=lambda url: ({"serverTime":end+60_000} if url.endswith("/api/v3/time")
                else [_bar(start+60_000),_bar(start+120_000,"10.7")]))
        assert result == {"status":"CLOSED","bars":2}
        receipts = store.db.execute(
            "SELECT open_ms,receipt_json FROM final_bar_lineage ORDER BY open_ms").fetchall()
        assert len(receipts) == 4
        bodies = [json.loads(row[1]) for row in receipts]
        assert [body["schema"] for body in bodies] == [
            "atlas.realtime-market-feed.normalized-bar-attestation.v1",
            REST_LINEAGE_SCHEMA, REST_LINEAGE_SCHEMA,
            "atlas.realtime-market-feed.normalized-bar-attestation.v1"]
        assert all(body["source_class"] == "BINANCE_SPOT_PUBLIC_REST_MARKET_DATA"
                   and body["request"]["symbol"] == "BTCUSDT"
                   and body["request"]["startTime"] <= body["open_ms"]
                   and body["request"]["endTime"] >= body["open_ms"]
                   and len(body["response_row_sha256"]) == 64
                   for body in bodies[1:3])
        assert bodies[1]["producer_code_sha256"] == REST_PRODUCER_CODE_SHA256
        rows = project_feed_window(store.path, symbol="BTCUSDT", start_ms=start,
            end_ms=end, now_ms=max(now+2_000,time.time_ns()//1_000_000+1),
            max_age_ms=86_400_000, expected_producer_code_sha256=PRODUCER_CODE_SHA256,
            expected_rest_producer_code_sha256=REST_PRODUCER_CODE_SHA256)
        assert len(rows) == 4
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "CLOSED"
    finally:
        store.db.close()


def test_rest_receipt_failure_rolls_back_bar_and_keeps_gap_open(tmp_path):
    store=_store_with_two_minute_gap(tmp_path)
    try:
        store.db.execute("""CREATE TRIGGER reject_rest_receipt BEFORE INSERT ON final_bar_lineage
            WHEN NEW.open_ms=60000 BEGIN SELECT RAISE(ABORT,'injected receipt failure'); END""")
        store.db.commit()
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
                           fetch_json=_client([_bar(60_000),_bar(120_000,"10.7")]))
        assert result["status"] == "OPEN_FAILED"
        assert store.db.execute("SELECT count(*) FROM final_bar WHERE open_ms IN (60000,120000)").fetchone()[0] == 0
        assert store.db.execute("SELECT count(*) FROM final_bar_lineage WHERE open_ms IN (60000,120000)").fetchone()[0] == 0
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "OPEN"
    finally:
        store.db.close()


def test_legacy_existing_bar_is_not_retroactively_attested(tmp_path):
    store=_store_with_two_minute_gap(tmp_path)
    try:
        store.db.execute("""INSERT INTO final_bar VALUES
            ('BTCUSDT','1m',60000,119999,'10.0','11.0','9.5','10.5','2.5',4,120000,'legacy')""")
        store.db.commit()
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
                           fetch_json=_client([_bar(60_000),_bar(120_000,"10.7")]))
        assert result["status"] == "OPEN_FAILED"
        assert "BACKFILL_EXISTING_RECEIPT_UNVERIFIED" in result["reason"]
        assert store.db.execute("SELECT status FROM open_gap").fetchone()[0] == "OPEN"
        assert store.db.execute("SELECT count(*) FROM final_bar_lineage WHERE open_ms=60000").fetchone()[0] == 0
    finally:
        store.db.close()


def test_rest_retry_is_idempotent_and_consumer_rejects_unpinned_missing_or_tampered_receipts(tmp_path):
    import time
    from tools.realtime_market_feed.backfill import REST_PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.atlas_integration import project_feed_window

    store=_store_with_two_minute_gap(tmp_path)
    try:
        fetch=_client([_bar(60_000),_bar(120_000,"10.7")])
        first=recover_gap(store.path,"BTCUSDT",60_000,180_000,fetch_json=fetch)
        assert first == {"status":"CLOSED","bars":2}
        second=recover_gap(store.path,"BTCUSDT",60_000,180_000,fetch_json=fetch)
        assert second == {"status":"GAP_NO_LONGER_OPEN","bars":0}
        now=max(time.time_ns()//1_000_000+1,240_000)
        with pytest.raises(ValueError,match="FEED_PRODUCER_IDENTITY_MISMATCH"):
            project_feed_window(store.path,symbol="BTCUSDT",start_ms=60_000,
                end_ms=180_000,now_ms=now,max_age_ms=86_400_000,
                expected_producer_code_sha256=PRODUCER_CODE_SHA256)
        with pytest.raises(ValueError,match="FEED_PRODUCER_IDENTITY_MISMATCH"):
            project_feed_window(store.path,symbol="BTCUSDT",start_ms=60_000,
                end_ms=180_000,now_ms=now,max_age_ms=86_400_000,
                expected_producer_code_sha256=PRODUCER_CODE_SHA256,
                expected_rest_producer_code_sha256="0"*64)
        store.db.execute("DELETE FROM final_bar_lineage WHERE open_ms=60000")
        store.db.commit()
        with pytest.raises(ValueError,match="FEED_SOURCE_LINEAGE_UNVERIFIED"):
            project_feed_window(store.path,symbol="BTCUSDT",start_ms=60_000,
                end_ms=180_000,now_ms=now,max_age_ms=86_400_000,
                expected_producer_code_sha256=PRODUCER_CODE_SHA256,
                expected_rest_producer_code_sha256=REST_PRODUCER_CODE_SHA256)
    finally:
        store.db.close()


def test_rest_receipt_source_claim_and_bar_content_tampering_are_rejected(tmp_path):
    import hashlib
    import time
    from tools.realtime_market_feed.backfill import REST_PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.atlas_integration import project_feed_window

    store=_store_with_two_minute_gap(tmp_path)
    try:
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
                           fetch_json=_client([_bar(60_000),_bar(120_000,"10.7")]))
        assert result["status"] == "CLOSED"
        now=max(time.time_ns()//1_000_000+1,240_000)
        body_text, = store.db.execute(
            "SELECT receipt_json FROM final_bar_lineage WHERE open_ms=60000").fetchone()
        body=json.loads(body_text)
        original_receipt_sha=hashlib.sha256(body_text.encode()).hexdigest()
        body["source_class"]="WEBSOCKET"
        canonical=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=True)
        store.db.execute("""UPDATE final_bar_lineage SET receipt_json=?,receipt_sha256=?
            WHERE open_ms=60000""",(canonical,hashlib.sha256(canonical.encode()).hexdigest()))
        store.db.commit()
        with pytest.raises(ValueError,match="FEED_PRODUCER_IDENTITY_MISMATCH"):
            project_feed_window(store.path,symbol="BTCUSDT",start_ms=60_000,
                end_ms=180_000,now_ms=now,max_age_ms=86_400_000,
                expected_producer_code_sha256=PRODUCER_CODE_SHA256,
                expected_rest_producer_code_sha256=REST_PRODUCER_CODE_SHA256)
        # Restore the untouched valid REST lineage before testing bar tampering,
        # so this assertion proves row/receipt binding rather than the source-claim failure.
        store.db.execute("""UPDATE final_bar_lineage SET receipt_json=?,receipt_sha256=?
            WHERE open_ms=60000""",(body_text,original_receipt_sha))
        store.db.execute("UPDATE final_bar SET close='99' WHERE open_ms=60000")
        store.db.commit()
        with pytest.raises(ValueError,match="FEED_LINEAGE_ROW_MISMATCH"):
            project_feed_window(store.path,symbol="BTCUSDT",start_ms=60_000,
                end_ms=180_000,now_ms=now,max_age_ms=86_400_000,
                expected_producer_code_sha256=PRODUCER_CODE_SHA256,
                expected_rest_producer_code_sha256=REST_PRODUCER_CODE_SHA256)
    finally:
        store.db.close()


def test_rest_lineage_rejects_receipt_timestamp_at_or_before_final_close(tmp_path):
    import hashlib
    import time
    from tools.realtime_market_feed.backfill import REST_PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256
    from tools.realtime_market_feed.atlas_integration import project_feed_window

    store=_store_with_two_minute_gap(tmp_path)
    try:
        result=recover_gap(store.path,"BTCUSDT",60_000,180_000,
            fetch_json=_client([_bar(60_000),_bar(120_000,"10.7")]))
        assert result["status"]=="CLOSED"
        receipt_text=store.db.execute(
            "SELECT receipt_json FROM final_bar_lineage WHERE open_ms=60000").fetchone()[0]
        body=json.loads(receipt_text)
        body["available_at_ms"]=body["close_ms"]
        normalized={key:body[key] for key in
            ("provider","market","source_class","symbol","interval","open_ms","close_ms",
             "available_at_ms","finality","ohlcv","trades","response_row_sha256")}
        body["normalized_row_sha256"]=hashlib.sha256(json.dumps(normalized,
            sort_keys=True,separators=(",",":"),ensure_ascii=True,
            allow_nan=False).encode()).hexdigest()
        canonical=json.dumps(body,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False)
        store.db.execute("UPDATE final_bar SET received_ms=close_ms WHERE open_ms=60000")
        store.db.execute("""UPDATE final_bar_lineage SET receipt_json=?,receipt_sha256=?
            WHERE open_ms=60000""",(canonical,hashlib.sha256(canonical.encode()).hexdigest()))
        store.db.commit()
        with pytest.raises(ValueError,match="FEED_LINEAGE_IDENTITY_MISMATCH"):
            project_feed_window(store.path,symbol="BTCUSDT",start_ms=60_000,
                end_ms=180_000,now_ms=time.time_ns()//1_000_000+1,
                max_age_ms=86_400_000,expected_producer_code_sha256=PRODUCER_CODE_SHA256,
                expected_rest_producer_code_sha256=REST_PRODUCER_CODE_SHA256)
    finally:
        store.db.close()
