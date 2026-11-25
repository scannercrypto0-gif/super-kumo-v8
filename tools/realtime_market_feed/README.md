# Independent realtime Spot market feed candidate

This is a separate read-only path. It does not use the legacy sustained-spot
scheduled task, its HOLD files, its quota SQLite database, or its recovery
claims. It cannot place orders.

## What it does

- One combined Binance Spot public market WebSocket per process.
- Per configured symbol: trade, best bid/ask, and finalized 1-minute candles.
- Latest trade and quote are committed to SQLite; finalized candles are
  idempotently stored with exact decimal strings.
- Missing finalized 1-minute candle ranges remain explicit OPEN gaps.
- A bounded, public REST recovery worker fetches and validates missing finalized
  candles after a gap is detected. It closes a gap only after every expected
  minute is durably present and matches; errors and conflicts leave it OPEN.
- Backfill is limited to 1,440 candles per gap and retried no more than once per
  minute per symbol. Larger gaps remain open for a separate historical repair.
- Connection, disconnect, socket error, malformed event, backfill, and final-bar
  conflict events are stored locally.
- Reconnect attempts have exponential backoff and a minimum 15-second interval.
  The socket rotates before 24 hours. The observation mode is time bounded.
- On Windows, the database root must be on E:.

The system consuming SQLite must consider quotes/trades stale using their
`received_ms` and must treat every OPEN gap as missing data. This service can
recover short 1-minute candle gaps from the public Spot REST market-data API;
it does not recover every individual trade or reconstruct a complete quote
history. The daily historical loader remains the authority for larger historical
ranges, and no daily-loader interface is called by this service.

## Deliberate limits

BTCUSDT is the default vertical slice. Symbol universe is configurable, capped
at 64 symbols (192 streams) on one socket. The implementation preserves latest
trade/quote state and finalized 1m candles, not every raw trade payload. No
private endpoints, order calls, market-data entitlement check, shared-NAT
quota inventory, or persistent host deployment has been performed. Provider
terms and the current host's shared-IP usage must be independently cleared
before persistent owner-host use. The E: smoke run proved live reception only
for its short observation window; it did not prove sustained acceptance.

## Offline tests

From repository root:

```powershell
python -m pip install -r tools/realtime_market_feed/requirements.txt
python -m pip install pytest
$env:PYTHONPATH='.'
python -m pytest tools/realtime_market_feed/test_service.py tools/realtime_market_feed/test_backfill.py -q
```

The tests inject synthetic frames and never open a socket.

## Owner-host acceptance run on E:

First run the bounded 10-minute smoke check with BTCUSDT. After it passes, use
a bounded 24-hour run to cover planned socket rotation. This remains a foreground
observation; it does not install or register a persistent task. Inspect the
report and SQLite events afterward. The acceptance run must show fresh trade,
quote, and final-bar rows, at least one rotation/reconnect cycle, no unresolved
short gaps, and no unexplained message rejections. A separate injected outage
test must prove reconnect and REST gap closure before integration.

```powershell
$env:PYTHONPATH='C:\path\to\checkout'; & 'C:\path\to\python.exe' -B -m tools.realtime_market_feed.service --root 'E:\ATLAS\realtime-market-feed' --symbols BTCUSDT --observe-seconds 600
```

After the 10-minute smoke passes, run the 24-hour rotation acceptance window:

```powershell
$env:PYTHONPATH='C:\\path\\to\\checkout'; & 'C:\\path\\to\\python.exe' -B -m tools.realtime_market_feed.service --root 'E:\\ATLAS\\realtime-market-feed' --symbols BTCUSDT --observe-seconds 86400
```

A successful process start is not a successful feed. After each run, get a
read-only local report with
`python -B -m tools.realtime_market_feed.service --root 'E:\\ATLAS\\realtime-market-feed' --report`.
Confirm fresh rows in `latest_trade`, `latest_quote`, and `final_bar`, zero
OPEN gaps after the recovery worker has settled, at least one
`PLANNED_ROTATION` followed by a new `CONNECTED` event in the 24-hour run,
and no unexplained message rejections. The separate offline injected-outage
test must pass as well. Do not enable a persistent background service until
provider-rights and owner-host gates are cleared.

## Consumer handoff

Downstream Python code can call `read_snapshot(database, symbols, now_ms=...)`
from `tools.realtime_market_feed.reader`. The read-only contract returns exact
decimal strings, exchange/receive timestamps, latest finalized candle, open gap
ranges, and per-symbol freshness blockers. It reports `LIVE_FRESH` only when
trade, quote, and finalized candle are present and within configured age limits,
with no recent open gap; otherwise it reports `HELD`. This is a data-quality
gate, not a trading signal. Consumers must still apply their required history
warmup and keep the daily source as historical authority.

The current slice does not connect this reader to the existing scanner runtime
or daily loader. Those paths have different code/config pins and need an
explicit mapping before records are shared.

## SQLite tables

- `latest_trade`: last accepted trade and its exchange/receive timestamps.
- `latest_quote`: latest best bid/ask with exchange update ID and receive time.
- `final_bar`: final 1-minute OHLCV only.
- `open_gap`: half-open missing minute ranges, initially OPEN.
- `service_event`: local connection, integrity and rejection timeline.
