# #303 Binance Spot BTCUSDT feed readiness

## Baseline and scope

This isolated delta is stacked on #289 at `1ff3d13a3dfd1337bae0659dd03550b764c8799c`
with its existing #286 observer ancestry. G1 MarketBar and G2 DecisionSnapshot
are reused, and the optional read-only Scanner diagnostic calls its existing
Factory indicator kernel. The existing collector handles klines. The gap is a
joined four-stream wire contract, shared-IP dispatch budget, and fail-closed
reconnect and durable research visibility. No producer or observer source
or store is modified. G2 operational horizons remain separate from G4 OOS.

Governance reviewed [PM OS and G0-GOV-01](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6721828613),
[v1.1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6721846844),
[CLOSE-FIRST](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6741235513),
[the owner cost and exit decision](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6760348084)
and [the independent source Audit](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6788728290).
The current owner selection in #302/#303 prioritizes Binance Spot engineering.
The latest accessible owner-host evidence is evidence with its original grade.
The #301 signed prefreeze kit remains unmerged and source activation is separate.
Prior accepted #296/#297/#300, G4 and four-package evidence is reused.

## Official provider reference reviewed 2026-11-11

| Surface | Documented behavior and lane budget |
|---|---|
| [Public market-data REST](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#limits) | Use `data-api.binance.vision` if approved. `exchangeInfo` provides applicable rate windows, and `X-MBX-USED-WEIGHT-*` reports shared IP usage. The published 6,000 weight/min and 61,000 raw requests/5min examples are planning references, never an entitlement. The pilot must confirm all actual windows and block on an unknown smaller limit. |
| REST public weights | `time` 1, `exchangeInfo` 20, `klines` 2, `aggTrades` 4, single-symbol `ticker/bookTicker` 2, depth up to 100 levels 5, recent `trades` 25. Parameters affect weight. A raw trade ID cannot be filled with an aggregate trade ID. Orders/unfilled-order and private/authenticated limits are unused. |
| [Market WebSocket streams](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#websocket-limits) | 5 incoming-to-server frames/s including PING, PONG and JSON controls, 1,024 streams/connection, 300 connection attempts per 5 min/IP. Targets are 2/s, 4 streams, 1 active socket and 3 attempts total for the proposed pilot. Offline generic guard caps per-IP attempts at half the configured limit. |
| Lifecycle | Server ping every 20s, echo payload in pong within one minute, close before 24h and handle disconnect/shutdown. No unsolicited client ping. Separate pacing for reconnect and REST recovery, with deterministic bounded jitter. |
| Clocks | Default wire epoch milliseconds. The adapter does not request microsecond mode. Trade event and execution clocks are distinct. bookTicker carries update ID and prices/quantities, with no exchange event timestamp. Klines include open, inclusive close and final flag. For 1m/15m the documented rolling cadence is 2s. Trade/BBO are event driven. |
| Depth | Deferred from collection. The isolated sequence test checks snapshot age, U/u continuity and bounded buffers. The documented full order book procedure requires buffering deltas, acquiring the weighted snapshot, aligning IDs and restarting after gaps. |
| HTTP failure | 429 honors Retry-After and exponential backoff. 418 latches an operator-review ban. 5xx and transport loss open a cooldown with one in-flight half-open attempt. Unknown outcomes keep their charged weight. |

Rights for direct REST and WebSocket capture, automated personal noncommercial
strategy research, retention, derived use and independent review are
**UNVERIFIED**. The owner must identify the applicable Binance entity/jurisdiction,
endpoint-specific effective terms and permission, including any required written
provider clarification. The [public API description](https://www.binance.com/en/binance-api)
describes capability. [Binance Vision dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md)
apply to that archive product. Neither supplies a permission decision for this feed.
No endpoint was probed. L2, API keys, order traffic and paid subscriptions are
outside this pilot.

## Shared IP control

All scanner, capture, backfill, health and diagnostic traffic on the same IP
must route through one dispatch owner before activation. The SQLite reservation
ledger is the cross-worker authority on that host. Multiple hosts sharing a NAT
must submit to that single owner through an authenticated deployment transport
and be prevented from bypassing it. The one-shot runner contains a fixed public provider transport. No shared-IP dispatch service is deployed by this package. No SQLite file sharing over a network filesystem. Unknown
egress clients, clock authority or quotas block real use.

The sliding weighted windows are stricter than a burst-credit token bucket.
They admit at most floor(limit/2) in the configured rolling 1m weight and 5m
raw request windows. REST has one
outstanding request, persistent cooldown and 1s spacing for recovery. A
current-minute used-weight header can lower admission further. Production needs
to reconcile **all** published windows and headers before enabling egress. The
pending queue is at most 32, coalesces identical work, rejects overflow, and
reserves a slot for essential requests. A trusted dispatcher supplies its
elapsed clock. A regression fails closed. Real deployment must bind the elapsed
clock to monotonic time and reconcile persisted state across restarts.

## Capture and research boundary

Raw bytes and exact decimal fields are separate from the native MarketBar float
projection. Event/receive/data-COMMIT-return times are separate. Missing ACKs,
invalid clocks, gaps and source revisions block visibility. A restarted writer
must warm up again and keeps an unresolved ACK blocked. REST replay fills only
the expected bounded sequence range, uses current observed custody, and is not
a fresh signal. Duplicate originals do not refresh eligibility. BBO sequence
jumps are diagnostic, since update IDs are not a contiguous BBO counter.
There is no claim of an observed maker fill from quote/candle touches.

The shared [#302 interface](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/e0e08a8381a8cceaaa44d6ae2721e9cb0d004648/tools/historical_source_qa/interface.json)
is checked from its exact Git object. Its native 15m identity and half-open UTC
window align with final native WS bars. Historical, recovered and prospective
cohorts are distinct. Availability and publisher first-known-at remain unknown.
No G2 observer is instantiated, and no Factory scientific result or OOS release
is produced. A current-generation read projects the existing Core/G2 types and
can run the native read-only Scanner AST/Factory indicator kernel on an admitted
mark. Stale, finality and embargo/holdout guards produce no signal. Use #301
separate blind custody for real holdout data.

## Reproduction and pilot handoff

Use a disposable checkout with Python 3.13. Set PYTHONPATH to `src;.` on
Windows or `src:.` on Ubuntu. Install pytest 9.0.2 and websocket-client 1.9.2. Fetch only the #304 Git object
to resolve its contract test, then run:

```text
git fetch --no-tags origin e0e08a8381a8cceaaa44d6ae2721e9cb0d004648
python -B -m pytest tools/binance_live_feed/test_feed.py tools/binance_live_feed/test_run_pilot.py -q --junitxml=feed-tests.xml
python -B -m tools.binance_live_feed.simulation feed-evidence
python -B -m tools.binance_live_feed.manifest feed-evidence
```

[pilot.json](pilot.json) is the one-shot owner proposal. After rights, IP
inventory, confirmed quota windows and independent prefreeze/custody, pick an
exact UTC start on a 15m boundary and end within 20 minutes. Check stop thresholds
on every frame/request. Do not extend after a cap, outage or insufficient sample.
Record separate trade/BBO arrival intervals, trade event-to-receive, BBO local
age, close-to-receive for native 1m and 15m, receive-to-commit, clock uncertainty,
disconnects, gaps, REST header/weight and outbound WS frame counts. Report
nearest-rank p50/p95/p99, including counts and unavailable percentiles. A no-event
period is reported as observed. It never implies a fixed tick cadence.
Only a future recorded authorized pilot can establish real source quality.


### One-shot capture entry point

After independently checking the source scope and actual host, create a private
JSON preflight file. It contains integer `start_ms` on a UTC 15-minute boundary,
`clock_checked_ms` and signed `clock_error_ms` from an independent UTC check,
and evidence references `source_rights_ref`, `region_entity_ref`,
`egress_inventory_ref`, `clock_ref`, and `custody_ref`. The references are
operator assertions checked for presence. Keep their underlying receipts with
the private preflight. Supply the verified values for `rest_weight`,
`raw_requests`, `connections`, `ws_messages` and `subscriptions` under
`verified_limits`. Use a dedicated, inventoried egress and its shared SQLite
quota ledger. The REST bootstrap reconciles the provider's actual raw-request
and weight windows and current one-minute used weight before opening a socket.

At the declared start, run from the pinned checkout with the same PYTHONPATH:

```text
python -B -m tools.binance_live_feed.run_pilot preflight.json NEW_PRIVATE_OUTPUT SHARED_IP_QUOTA.sqlite
```

The output directory and quota ledger reserve the one-shot activation. Retain
both after a failure. The pilot uses a stricter envelope of one exchangeInfo
request, one WS attempt and no REST backfill. Gaps, transport failure and quota
uncertainty terminate capture. A frame cap or deadline can yield insufficient
samples. The output report distinguishes an incomplete sample, a failed stop
and quality PASS for the admitted non-PIT feed. The isolated capture journal
keeps original bytes and durable ACKs, and exposes no strategy view. Preserve
the raw journal and preflight privately under the verified retention scope.

### Opt-in ephemeral research

The same one-shot CLI accepts `--ephemeral-research`. Pin
`"capture_mode": "EPHEMERAL_RESEARCH"` in the private preflight and supply a
verified `memory_safety_ref` covering paging, crash dumps, tracing and host
access. Existing source/region, clock, egress, quota and custody references
are still required. The custody reference describes allowed aggregate receipts,
not raw-event custody.

The output contains activation and aggregate report JSON only. The shared quota
SQLite remains active and stores quota metadata, including stream names. Raw
frames and normalized prices are not written. Fixed-size material fingerprints
and timing samples are bounded to the existing frame cap and disposed at stop.
There is no reconnect or recovery under the same one-shot reservation. Timing
is memory processing time. The report exposes `RAW_CUSTODY_NOT_AVAILABLE` for
durable research consumers and `EVALUATION_PENDING` for Factory. No durable
event chain, real strategy evaluation, or PIT is asserted. The normal CLI path
retains its existing durable behavior.

Focused offline check: `python -B -m pytest tools/binance_live_feed/test_ephemeral.py -q`.
