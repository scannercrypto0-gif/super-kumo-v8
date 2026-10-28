# Binance independent observer — bounded technical evidence

Authority: owner request received 2026-10-28, Council #134/6462845677 and
#134/6462862444. Separate branch stacked on Core #137 at d27ddd8f; no merge.
Factory code is executed read-only at #141 fbf70afbcf3ba051a9b1522328893bf9ab7f2a67.
No alternative ObservationVersion or Factory admission contract is introduced.

## Operation and guarantees

```
PYTHONPATH=src python scripts/binance_independent_observer.py --directory /durable/path
```

Without `--seconds` the process continues until stopped; `--seconds 150` bounds
an evidence capture. Use a separate service/process and independent WS/REST
connections, never a G1 consumer thread. This is process isolation on the same
host, **not proven independent-host failure isolation**. A supervisor/durable
volume is required for deployment; this session performed bounded captures only.

SQLite WAL/FULL commits raw responses, clock references, observations and hash
links atomically. Duplicate latest content preserves its first-seen identity;
A→B→A creates a new third revision. Startup records UNKNOWN coverage; polling
cannot reconstruct missing revisions between polls. Post-COMMIT receipts are
separate records and never reconstructed after a crash. `as_of` returns only
versions locally received at or before cutoff and always returns UNKNOWN temporal
acceptance. Clock steps, disconnects, missing synchronization and repairs never
promote coverage to CONFIRMED. No revision inherits its predecessor's receipt.

Canonical common payload includes t/T, OHLC, base/quote/taker volumes and count;
WS E/f/L/x remain raw source metadata. REST snapshot differences are revisions
**observed by this watcher**, not issuer-certified correction announcements.
REST closed-bar screening uses source /time and local wall time conservatively;
it is not independently authenticated finality. Raw WS messages and REST bodies
are linked to canonical observations; the envelope remains LOCAL_ONLY_UNATTESTED.
`verify_bundle` checks pinned ledger chain, raw digest and payload binding,
revision identity/lineage, and equality with existing envelope-v1.

## Genuine capture

`evidence/binance-observer-20261028/capture_manifest.json` pins two cumulative
snapshots across close/reopen. There are six distinct versions, 24 receive records
(22 REST, two final WS messages), six source clock samples, two startup records
and two recorded gaps. Earlier REST snapshots and later WS confirmations may
refer to the same payload, so receive counts are not unique versions. No natural
content correction was observed in this short window. Correction and future-leak
proof is injected regression evidence, explicitly separate from genuine samples.

Public official endpoints:
- https://data-api.binance.vision/api/v3/klines
- https://data-api.binance.vision/api/v3/time
- wss://data-stream.binance.vision/ws/btcusdt@kline_1m
- Provider documentation: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- Event fields: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

Clock samples retain request/receive wall and monotonic times plus HTTP headers.
They are SOURCE_REPORTED_ONLY; independent UTC uncertainty is unknown. E and T
are never used as issuer publication/availability. Every version is categorized
FIRST_INDEPENDENT_OBSERVED, with UTC acceptance UNKNOWN and issuer UNATTESTED.
No historical pre-monitor PIT or issuer attestation is asserted.

## Core → Factory and validation

Eight tests cover deduplication/reversion and no future correction at cutoff,
rollback on storage failure, forced process exit and reopen, tamper/truncation,
clock drift/backwards clock/disconnect, source-event/receipt distinction, existing
pinned Factory admission, and genuine archived bundles through that same gate.
Factory accepts envelope structure but refuses empirical admission; this is a
positive transport/integrity path and a negative scientific-admission path.
A genuine **accepted empirical/issuer-PIT** positive sample does not exist.

Exact-head CI runs these tests plus Core proof, G1 WP, storage and integrity
regressions on Ubuntu and Windows; logs and results are linked in PR/Council.
An initial local broad run had 436 pass, two skip, one environment failure:
isolated child `python -I` could not see user-site websocket-client. Validation
was moved to a dedicated venv with installed runtime/dev dependencies; no test
or production code was weakened to bypass the failure.

## Limits requiring independent S/R decision

The Git commit retains off-host snapshots and pins their content. This is bounded
versioned custody, not independently authenticated receipt time or continuous
WORM storage. Before publication, host loss can lose unpublished local evidence.
A dedicated host, independently verified UTC synchronization, continuous external
immutable retention, process supervision and a naturally observed revision are
not proven by this run. The watcher is optional and not wired into G1 production.
Existing Factory fail-closed admission remains the boundary; no historical/OOS,
paper/live activation, merge or G0 closure. Request separate S and R verdicts
only for these evidenced claims; broader acceptance remains pending.
