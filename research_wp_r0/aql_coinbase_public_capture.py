"""One-shot Coinbase Exchange public candle capture, isolated evidence only.

No credentials, trades, Binance impersonation, journal writes, or automatic retries.
Explicit operator invocation required; importing this module does not use network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from research_wp_r0.aql_coinbase_public_candles import (
    BAR_SECONDS, CoinbaseSourceError, normalize_response,
)

BASE = "https://api.exchange.coinbase.com"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_BARS = 21


def encode(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_once(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def capture(*, product_id, folder, request, now_ms):
    """Capture one bounded public response with raw bytes and truthful local evidence.

    `request` is injected to permit completely offline tests.
    """
    from research_wp_r0.aql_coinbase_public_candles import PRODUCT_RE
    if not PRODUCT_RE.fullmatch(product_id):
        raise CoinbaseSourceError("INVALID_PRODUCT")
    if type(now_ms) is not int or now_ms <= 0:
        raise CoinbaseSourceError("INVALID_CAPTURE_TIME")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    end_s = (now_ms // 1000 // BAR_SECONDS) * BAR_SECONDS
    start_s = end_s - MAX_BARS * BAR_SECONDS
    from datetime import datetime, timezone
    def utc(s):
        return datetime.fromtimestamp(s, timezone.utc).isoformat().replace("+00:00", "Z")
    from urllib.parse import urlencode
    url = BASE + "/products/" + product_id + "/candles?" + urlencode({
        "granularity": BAR_SECONDS, "start": utc(start_s), "end": utc(end_s),
    })
    schedule = dict(schema_version="aql.coinbase-public-capture.v1", product_id=product_id,
                    source="coinbase_exchange_public_rest", endpoint=url,
                    request_count_cap=1, max_response_bytes=MAX_RESPONSE_BYTES,
                    execution="DISABLED", source_custody="UNVERIFIED",
                    external_pit="NOT_ESTABLISHED", planned_at_local_ms=now_ms)
    write_once(folder / "schedule.json", encode(schedule))
    try:
        raw = request(url)
        if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
            raise CoinbaseSourceError("INVALID_OR_OVERSIZED_RAW_RESPONSE")
        write_once(folder / "raw-response.json", raw)
        rows = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(
            CoinbaseSourceError("NONFINITE_JSON")))
        bars = normalize_response(rows, product_id=product_id, received_at_ms=now_ms)
        if len(bars) > MAX_BARS or bars[-1].open_time_ms >= end_s * 1000:
            raise CoinbaseSourceError("OUTSIDE_REQUEST_WINDOW")
        if bars[0].open_time_ms < start_s * 1000:
            raise CoinbaseSourceError("OUTSIDE_REQUEST_WINDOW")
        result = dict(status="UNVERIFIED_CAPTURED", source="coinbase_exchange_public_rest",
                      product_id=product_id, interval="15m", bars=len(bars),
                      raw_sha256=digest(raw), first_open_ms=bars[0].open_time_ms,
                      last_close_ms=bars[-1].close_time_ms,
                      source_custody="LOCAL_UNVERIFIED", execution="DISABLED",
                      binance_execution_price_verified=False,
                      collector_journal_connected=False, external_pit="NOT_ESTABLISHED")
    except Exception as exc:
        result = dict(status="NOT_ESTABLISHED", reason=type(exc).__name__ + ": " + str(exc)[:160],
                      source="coinbase_exchange_public_rest", execution="DISABLED",
                      collector_journal_connected=False, external_pit="NOT_ESTABLISHED")
    write_once(folder / "result.json", encode(result))
    return result


def public_request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AQL-public-research/1.0",
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10, context=ssl.create_default_context()) as response:
        if response.status != 200:
            raise CoinbaseSourceError("HTTP_NON_200")
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise CoinbaseSourceError("RESPONSE_TOO_LARGE")
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", default="BTC-USD")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if os.environ.get("AQL_COINBASE_PUBLIC_CAPTURE") != "OWNER_APPROVED_ONE_SHOT":
        parser.error("ONE_SHOT_NETWORK_AUTHORIZATION_REQUIRED")
    result = capture(product_id=args.product, folder=args.out, request=public_request,
                     now_ms=int(time.time() * 1000))
    print(encode(result).decode(), end="")
    raise SystemExit(0 if result["status"] == "UNVERIFIED_CAPTURED" else 2)


if __name__ == "__main__":
    main()
