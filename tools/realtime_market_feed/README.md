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
- Connection, disconnect, socket error, malformed event and final-bar conflict
  events are stored locally.
- Reconnect attempts have exponential backoff and a minimum 15-second interval.
  The socket rotates before 24 hours. The observation mode is time bounded.
- On Windows, the database root must be on E:.

The system consuming SQLite must consider quotes/trades stale using their
`received_ms` and must treat every OPEN gap as missing data. The daily
historical loader should reconcile those ranges; this first vertical slice
records gaps but does not yet call or mutate the daily-loader interface.

## Deliberate limits

BTCUSDT is the default vertical slice. Symbol universe is configurable, capped
at 64 symbols (192 streams) on one socket. The implementation preserves latest
trade/quote state and finalized 1m candles, not every raw trade payload. No
REST backfill, private endpoints, order calls, market-data entitlement check,
shared-NAT quota inventory, or host deployment has been performed. Provider
terms and the current host's shared-IP usage must be independently cleared
before owner-host use. This is engineering code, not a claim that the provider
connection was tested.

## Offline tests

From repository root:

```powershell
python -m pip install -r tools/realtime_market_feed/requirements.txt
python -m pip install pytest
$env:PYTHONPATH='.'
python -m pytest tools/realtime_market_feed/test_service.py -q
```

The tests inject synthetic frames and never open a socket.

## Owner-host smoke test on E:

Use the approved Python environment and start with only BTCUSDT. First make a
bounded 10-minute observation; inspect the SQLite database and service events
before deciding whether to register an always-on scheduled task. Example:

```powershell
$env:PYTHONPATH='C:\path\to\checkout'; & 'C:\path\to\python.exe' -B -m tools.realtime_market_feed.service --root 'E:\ATLAS\realtime-market-feed' --symbols BTCUSDT --observe-seconds 600
```

A successful process start is not a successful feed. Confirm fresh rows in
`latest_trade`, `latest_quote`, and `final_bar`, no unexplained OPEN gaps,
and an advancing `service_event` history. A provider rejection or repeated
disconnect remains a failed smoke test. Do not enable this as a background
service until the repository's source-rights and owner-host gates are cleared.

## SQLite tables

- `latest_trade`: last accepted trade and its exchange/receive timestamps.
- `latest_quote`: latest best bid/ask with exchange update ID and receive time.
- `final_bar`: final 1-minute OHLCV only.
- `open_gap`: half-open missing minute ranges, initially OPEN.
- `service_event`: local connection, integrity and rejection timeline.
