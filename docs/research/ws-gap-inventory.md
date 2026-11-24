# WS outage inventory and separate retrospective coverage

The native live service deliberately retains **sanitized receipts only** for
its LOCAL_PILOT_ONLY lane. These are not native retained candle bytes, a durable
market warehouse, genuine PIT/OOS, a trade or a native Core/Scanner acceptance.
The inventory reuses `atlas_live_research_cycle.read_service_receipt`; it does
not invent a parallel receipt schema or write/modify the existing receipts.

`tools/atlas_ws_gap_inventory.py` verifies the bounded native receipt chain,
slot ordering, digest, missing-slot accounting, temporal bounds and research-only
flags. It enumerates only completed UTC 15m slots in an explicitly supplied
window. A gap within confirmed capture and an expected slot beyond the latest
confirmed receipt have distinct evidence scopes. A missing chain parent,
conflicting/reordered receipt, future receipt, malformed JSON or unsafe file
fails closed. There are at most 10000 receipt objects, 256KiB per receipt and
10080 requested slots. Output is stdout only; there are no network or host task
operations.

The report always preserves `live_status=MISSING`. Optional independently
verified historical coverage goes into `retrospective_status` and `repair`:

| Retrospective status | Evidence |
| --- | --- |
| MISSING | No admitted native coverage, publication unknown or archive check not requested |
| SOURCE_NOT_YET_PUBLISHED | Hash-verified retained publisher listing lacks a qualifying source, explicitly as of that listing's observation time |
| QUARANTINED | Native query/custody/temporal validation failed, or a hash-verified rejected candidate covers the interval |
| RECOVERED_FROM_VERIFIED_ARCHIVE | Existing native warehouse query verified complete 1m membership, projected finalized 15m, original source and registry before/after read |

An optional `NativeArchiveReader` is bound to the previously reviewed #330
commit `5df7f6c9e0d6448db6aa700fa80158b443c5b3db`. It checks exact checkout and
clean relevant tracked/untracked source, then runs that existing
`HistoricalWarehouse.query(...,include_registry=True)` in an isolated process.
It outputs source class, immutable constituent identity, availability,
snapshot digest and event watermark; OHLCV and secrets are not emitted. No
caller-supplied JSON is accepted as archive authority. Production reads require
the approved Windows E: root. A private fixture-only constructor setting permits
isolated generated CI stores; it is not exposed by the command line.

Default archive checks are **zero**. Explicit checks are bounded to 16 single
15m intervals and 120s per native reader subprocess. The active #330 owner-host
backfill must not be interrupted, acquired under another writer or automatically
queried by this package; prepare the read seam only. Snapshot drift, unavailable
cutoff and source gaps stay explicit. No original archive acquisition is allowed
under WS engineering scope. This file never imports an archive, synthesizes a
candle, overwrites a live receipt, removes an outage or changes scientific
eligibility. Even verified retrospective replacement retains
`RETROSPECTIVE_NON_PIT` and downstream `WAIT_AUTHENTICATED_PARENTS`.

The known owner diagnostic can be emitted without reading private host state:

```console
python -B -m tools.atlas_ws_gap_inventory --reported-outage
```

It records the 22 Nov 2026 08:38:59 Riyadh HOLD/TimeoutError, last reported
receipt at 21 Nov 14:00:00.116 Riyadh, and `ROOT_CAUSE_NOT_PROVEN`. It intentionally
does not manufacture an exact interval count from a receipt commit timestamp:
actual immutable slot inventory requires the original hash-verified receipt
files. That original-host inventory and actual archive repairs remain pending.

The focused tests use native production receipt parsing and an isolated pinned
warehouse worktree with generated 1m data, not owner or Binance bytes. They cover
live-vs-retrospective separation, bad hashes/chain/future/overlap, UTC day/month
boundary, late/unpublished archives, native raw-checksum corruption, rejected
invalid candidates and partial files. The existing accepted warehouse 108-test
suite is reused, not repeated here. Set `ATLAS_WAREHOUSE_FIXTURE_CHECKOUT` to a
clean pinned #330 worktree to run the four native seam tests on Windows/Ubuntu.
