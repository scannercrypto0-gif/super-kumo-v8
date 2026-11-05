# ATLAS D — Core final canonical source→strategy Secretary handoff (TEST ONLY)

Owner Package D: [Core C #261 owner request](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/261#issuecomment-6651425793). Factory D follow-up [Core D #264/6652584828](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/264#issuecomment-6652584828). No B rerun, original Feb/Aug rerun, G0, PR merges, holdout or trading.

## New and exactly bounded synthetic cohort

The existing Core B original-archive intake `run_authorized_original_intake` remains **strictly BTCUSDT Feb/Aug**. Do **not** use it for made-up AAA original exchange data. New Core D `create_permitted_synthetic_cohort` builds one **clearly declared generated TEST_ONLY native-format ZIP/CHECKSUM** with symbol `AAA`, timeframe 15m, 8 bars, no genuine Binance publisher provenance. Uses existing generic Core `admit_local_original`+pinned #211 `RawVault` immutable bytes/readback and actual independent #245 `query_price_custody` and #253 `query_local` SHA-sealed receipts; `bind_dual_query_identities` requires exact bar checksum, coverage, source ZIP SHA, manifest SHA and cutoff. No new historical market acquisition, source truth or PIT claim.

It consults **unchanged pinned Work #235 actual StrategyScreeningSpecs**: candidate `AAA` is allowed by both frozen strategies `test_momentum` and `test_reversion`, `market=fixture`, `source_id=generator`, `generation_id=fixture_v1`. Synthetic source has `scope=TEST_ONLY` and `historical_known_at_ms=None`. It refuses `BTCUSDT` in this lane, source-bounds drift, foreign policy venue, bad clocks and anything outside one source/test symbol.

```python
# In disposable CI runner with pinned Work235, Scanner B/C/D and RawVault:
from research_wp_r0.aql_core_d_permitted_cohort_v1 import create_permitted_synthetic_cohort
cohort=create_permitted_synthetic_cohort(core_root, raw_root, work_specs, symbol="AAA")
warehouse,native,local,mapping,witness=(
    cohort[k] for k in ("warehouse","native","local","mapping","witness"))
assert warehouse["vault"]["vault"]=="EXISTING_PINNED_RAW_VAULT"
assert warehouse["test_only"] is True
assert warehouse["bar_count"]==8
assert native["price_query_sha256"] != local["query_sha256"]
assert witness["payload"]["historical_known_at_ms"] is None
```

Then Scanner D #262 `scan_same_core_source(core_root,warehouse,native,local,mapping,witness,work_specs,governance_actions=explicit_actions,symbol_budget=1)` uses **the exact same Core source**; its `aql.scanner-d.same-core-source-handoff.v1` Frozen carries `research_same_source_projection_receipt` and original canonical Scanner C `Frozen {payload,sha256}` approvals, nominations and route requests. The source ZIP SHA and Scanner JSON SHA **are distinct**. Actual scanner native15m computation generates `SELECTED` for an eligible test strategy under these exact fixture bars. Do not rewrite or fake status; tests assert real `SELECTED` exists.

## Canonical Secretary API and evidence distinctions

`research_wp_r0/aql_core_d_same_source_route_v1.py::verify_scanner_d_for_core_route` validates Scanner D bytes-to-Core-query source proof, original Scanner C Frozen approval/route + Work235 spec/policy SHA, denominator/run/nomination and original #245 vs #253 SHA. For accepted software-only candidate returns **`aql.core.d.same-source-strategy-route-gate.v1` with `decision=RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY`**. For ineligible policy, still WAIT, not PENDING. That gate is a Core SHA-sealed research receipt, not an external operational approval.

Core D **does not alter Core C provisional `aql.scanner.c.strategy-approval.v1` wire**. It uses **actual Scanner C canonical** `aql.scanner-c.strategy-approval.v1` and `aql.scanner-c.strategy-route-request.v1` with Work235 `Frozen {payload,sha256}` unchanged.

Core D new strategy-level durable outbox `research_wp_r0/aql_core_d_canonical_secretary_v1.py` has:
- `enqueue_scanner_d_strategy(root,gate=...,source_ack=...,source_nomination_sha256=...,route_id=...,now_ms=...,expires_at_ms=...)` requires actual **Core B source-only ACK** independently present in original durable source outbox, rechecked via `_verify_source_ack`; explicit canonical Scanner C approval must already be separately validated in Core D gate. Creates `PENDING_CONSUMER`, **never auto-ACK**.
- `strategy_d_snapshot(root,route_id,now_ms=...)` produces sealed `aql.core.d.canonical-strategy-secretary-snapshot.v1` with `route_receipt_sha256`, parent `gate_sha256`, `source_ack_sha256`, **`scanner_c_approval_sha256`**, `scanner_c_nomination_sha256`, `scanner_d_handoff_sha256`, `core_d_witness_sha256`, strategy identity/version/config/definition, symbol/timeframe/cutoff, Core245 and Core253 independent query SHA, `event_tail_sha256`, `historical_pit=NOT_ATTESTED`, `trading_authority=NONE`. Snapshot reports `route_ready_for_factory_test_only=False` until explicit consumer ACK, or after expiry.
- `ack_scanner_d_strategy_consumer(root,route_id,consumer_ack,now_ms=...)` requires **Factory-owned externally submitted** sealed `aql.factory.d.canonical-strategy-consumer-ack.v1` with `consumer_ack_sha256`, `route_id`, `decision=ACCEPTED_TEST_ONLY_RESEARCH`, `strategy_gate_sha256`, `scanner_c_approval_sha256`, `source_ack_sha256`, strategy ID/version/config, original ZIP SHA, two independent Core query SHA, cutoff, `accepted_at_ms`, zero order/position/fill fields, Paper/trading NONE. The Core API validates/records actual consumer ACK with idempotency and tamper-resistant event chain. **Only Factory owns issuing this in an actual integration**, not Core.
- Bound expiry and restart/replay are enforced, tampered/resealed persisted consumer status fails closed.

**Actual test fixture:** `tests/test_aql_core_d_canonical_secretary_v1.py::CoreDCanonicalSecretary` explicitly generates an illustrative Factory-owned-format ACK **inside the fixture only**, to prove Core consumes a distinct ACK; this is **NOT actual Factory #260 execution**, Lab or Paper consumption. Do not claim a real ACK or Lab in the live project.

**Strict scope:** The original historical BTCUSDT ZIP with unrelated Scanner synthetic JSON remains `WAIT_SOURCE_PROVENANCE_NOT_CONNECTED` — no crossover, no retrospective PIT, no source relabel. Real Work235 operational 15m remains `NOT_CONNECTED_15M_UNSUPPORTED`. No profit, market opportunity universe, broker, actual orders/fills/positions, G0, holdout or genuine market provenance.

## Factory ONE pinned cross-owner D delta

Factory #260 should stage Core D #264+Scanner D #262+Core C #261+Scanner C #259 exact heads read-only and perform **one** new-delta integration: call `create_permitted_synthetic_cohort`, run Scanner D canonical positive+negative, Core D route gate, Core B actual durable source-only ACK, Core D `PENDING_CONSUMER`, then **Factory's own real consumer** validates all seals and submits its own `consumer_ack_sha256`; independently execute actual Factory Lab/evaluation and isolated Paper WAIT/REJECT zero orders/positions/fills, with separate evidence proving Lab was actually called. Negative tests: absent approval, denied governance, wrong raw/source/ZIP/manifest/query SHA, wrong strategy version/config, expired/mismatched consumer ACK, replay/route-id conflict, disconnected original BTCUSDT source. Only after the completed Factory gate request one read-only Audit D new-delta verdict; do not repeat accepted B 96/Feb/Aug/106 suites. Discoverer non-blocking.
