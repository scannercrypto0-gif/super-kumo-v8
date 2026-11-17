# PKG03: actual-component offline operational integration

This package closes the missing **joint executable seam test**, not a component
implementation gap. It adds only a disposable staging harness, scenario, tests
and CI. No component branch is merged or patched, and no running observer is
opened by this harness. The fixed source matrix lives in
`tools/atlas_pkg03_stage.py`; every resulting file has its role, exact commit,
Git blob and SHA-256 in `source-overlay.json`. The combined overlay identity is
a SHA-256 over that complete final file matrix, **not a merged Git commit**.

The source matrix includes #271 Integration, read-only #235 fixtures and Scanner
B dependencies, #275 Core import dependencies, actual #277 Scanner, #286
prospective G2, #287 G1 readiness/journal/store, #288 G3, and #289 stacked forward
evidence. #289's parent remains #286. None depends on the mutable PKG01/02 lanes.

## Reproduce

Python 3.11+ and `websocket-client` are required for the actual component imports.
The objects are fetched separately from execution; fetching Git source is not a
market-data acquisition. From this branch in a disposable checkout:

```text
python -B tools/atlas_pkg03_stage.py /new/disposable/fetch --fetch
python -B tools/atlas_pkg03_smoke.py --output /new/disposable/result
python -B -m pytest tests/test_atlas_pkg03_offline.py -q
```

The smoke command needs a new destination and never deletes an existing output.
It starts three actual Python processes: prepare, deliberate post-COMMIT exit
73, and replay. No live market endpoint is used; socket connection attempts are
denied during each worker. Git object staging is bounded to specified Python
and JSON paths; no original March/April/owner-private bytes are accessed.

## Executed pipeline and invariants

1. Actual #287 G1 `DurableJournal`, `OperationalStore` and `assess`: 24 finalized
   synthetic bars; source receipts and readiness are required before evaluation.
2. Actual #277 plug-in/evaluator through #286 `ProspectiveObserver.tick`: 24
   retained decisions, including warmup UNKNOWN. No fabricated signal component
   or transplanted module mock is used. The observer tick count is distinct from
   evaluator-invocation/performance instrumentation.
3. Actual #289 `read_forward_evidence` on a read-only observer produces a report
   bound to the G2 and existing Factory read report. Synthetic 4h coverage can
   mature; synthetic 24h/72h stays pending. Earlier-as-of visibility is checked.
4. Actual #288 `signals_from_prospective` uses the sealed source decision report;
   no G2 horizon values enter simulation decisions. Same eligible finalized G1
   bars feed `PaperSimulator` with declared synthetic liquidity assumptions.
5. The first causal ENTRY is selected by a frozen bounded smoke rule; other
   projected signals remain in the census and are not claimed as simulated.
   Three commands create two assumed fills. An actual process exits immediately
   after the native durable journal commit but before the in-memory ACK. A new
   process replays all three events, retries every command, and confirms byte
   identical journal/state, zero skipped commands and zero duplicate fills.

Bounded negatives reject tampered/resealed source identities, revised source,
future cutoff, forged live scope, provisional/future/foreign-symbol bars,
unverified clock, skipped first eligible bar and conflicting duplicate commands. Separate harness tests
reject extra importable Python sources, source-byte tampering, manifest drift
and reuse of an existing destination. Parent-retained manifest SHA protects the
worker from a locally resealed replacement manifest.

Read-only SQLite WAL readers can create/update volatile SHM cache/lock metadata.
The source isolation assertion covers durable SQLite bytes and any nonempty WAL;
it does not falsely assert that SHM lock bytes never change. Only disposable
synthetic stores are instantiated. A live owner source must never be passed to
this harness; its constructors would initialize/migrate stores.

## Evidence and truthful limits

`delivery.json` binds source pins, combined overlay SHA, module import paths and
digests, three process exit codes, deterministic result, negative codes and
coverage. The focused Windows/Linux CI uses the exact PR head and uploads this
receipt, provenance, command/replay artifacts and JUnit results.

The reused external G1 receipt is
[#205/6760701161](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6760701161);
no Supabase/provider probe is repeated. The harness's owner-host status is
`NOT_ACCESSED_NO_LATER_REAL_MATURITY_ASSERTED`. Parent Integration may attach a
separate bounded readback; it must not turn synthetic time or the result's
checksum into real elapsed 4/24/72h proof, source continuity, source rights,
independent custody, a real PIT/OOS claim or stage signoff.

Exit: `PASS_ENGINEERING_INTEGRATED_OFFLINE` only. Real G2 horizon acceptance,
independent Audit review and owner stage approval remain separate. No G0,
broker/paper/live orders, market download, private E: or merge authority.
