"""Map capture records to the #302 shared evidence envelope."""
from tools.binance_live_feed.feed import INTERVALS, canonical, hash_bytes, need

HISTORICAL_HEAD = "e0e08a8381a8cceaaa44d6ae2721e9cb0d004648"
MARKET = ["BINANCE", "SPOT", "BTCUSDT", "BTC", "USDT", "UTC"]
SOURCE_MANIFEST = {
    "schema": "aql.binance.spot.offline-source-manifest.v1",
    "market": MARKET, "wire_time_unit": "epoch_ms",
    "rights": "FIXTURE_ONLY", "collection": "NOT_ACTIVATED",
    "native_intervals": ["1m","15m"], "cohort": "LIVE_FEED_REHEARSAL_303",
}


def envelope(record):
    material = record["material"]
    is_candle = "interval" in material
    need(record["first_known_at_ms"] is None and record["evidence"] == "OFFLINE_FIXTURE",
         "SOURCE_EVIDENCE_BOUNDARY")
    need(record["receive_ms"] <= record["commit_ms"]
         and (record["event_ms"] is None or record["event_ms"] <= record["receive_ms"]),
         "CLOCK_BINDING")
    return dict(
        schema="aql.binance-spot.source-envelope.v1", market=MARKET,
        product="BINANCE_SPOT_WS" if record["transport"] == "WS" else "BINANCE_SPOT_REST",
        interval=material["interval"] if is_candle else None,
        open_ms=material["open_ms"] if is_candle else None,
        end_exclusive_ms=material["end_ms_exclusive"] if is_candle else None,
        is_final=material["final"] if is_candle else None,
        exchange_event_at_ms=record["event_ms"], received_at_ms=record["receive_ms"],
        committed_at_ms=record["commit_ms"], publisher_first_available_at_ms=None,
        availability="UNKNOWN", evidence_class="TEST_ONLY",
        source_version=record["source_version"], source_manifest_sha256=hash_bytes(canonical(SOURCE_MANIFEST)),
        pit="NOT_ATTESTED", missingness="NONE", actual_fill=None)


def check_contract(reference, sample):
    need(reference["schema"] == sample["schema"]
         and reference["market"] == sample["market"]
         and set(reference["required_fields"]) | {"schema"} == set(sample)
         and all(sample[k] == v for k,v in reference["unknown_availability"].items())
         and sample["evidence_class"] == reference["mock_evidence"]
         and sample["product"] in reference["mock_live_products"]
         and reference["canonical_time_unit"] == "epoch_ms"
         and reference["kline_window"] == "[open_ms,end_exclusive_ms)", "HISTORICAL_INTERFACE_DRIFT")
    if sample["interval"] in INTERVALS:
        step = INTERVALS[sample["interval"]]
        need(sample["open_ms"] % step == 0 and sample["end_exclusive_ms"] == sample["open_ms"]+step,
             "INTERVAL_SEMANTICS")
