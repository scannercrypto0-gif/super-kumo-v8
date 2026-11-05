# ATLAS Core D — same synthetic source, canonical strategy Secretary (TEST ONLY)

Owner-approved provisional D: [Core #261 comment #6651425793](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/261#issuecomment-6651425793). This is a **new Core D Draft branch**, stacked on the unmerged Core C #261. Prior B/C branches and the independently accepted B Audit #256 verdict are unchanged. Discoverer #258 is non-blocking.

## Purpose and source truth

A genuine original-format historical Core source and an unrelated Scanner synthetic JSON were **not** same-source proven in Package C. Their correct preexisting wire contract remains:

- `decision=WAIT`
- `reason=SOURCE_LINEAGE_NOT_CONNECTED`
- `owner_facing_wait_status=WAIT_SOURCE_PROVENANCE_NOT_CONNECTED`
- `blocking_conditions` contains `SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED`
- zero Factory strategy consumer ACK, Lab/Paper activation, orders or fills.

Do not silently rename the wire reason. Core D updates the canonical disconnected C read-only seam on **D branch only** to restore `SOURCE_LINEAGE_NOT_CONNECTED` and emit the **separate** owner-facing label. It does not reclassify old historical ZIPs or invent historical point-in-time availability.

For a **new synthetic-only test fixture**, Core D generates exactly **10 15-minute bars from one local numerical set**. A local **AAA-15m-2024-02.zip** contains the native 12-column mock CSV; a separate canonical Scanner C JSON contains the same AAA OHLCV and bar timestamp values with synthetic `available_ms=close+1`. The locally generated ZIP and `.CHECKSUM` are clearly **TEST_ONLY fixtures, NOT vendor/publisher original data or a publisher-issued checksum**. A test-only pin, generation, exact CSV/member sha, SHA-bound locally generated checksum, exact UTC grid, RAW #211 immutable admission+readback, Core #245 native price query, Core #253 `query_local` and independently signed dual-query mapping are checked.

Critically, `scanner_raw_sha256` **does not equal** the ZIP's SHA; these are distinct encodings of precisely matched 10 rows, not a hash alias. The verifier independently replays the pinned Scanner B native 15m kernel against the actual Scanner JSON bytes and matches its recomputed `ScannerRun Frozen sha256`, complete per-strategy denominator, exact Scanner C nomination and approval/request Frozen parents, source/manifest/universe SHA, symbol/timeframe/cutoff, and **each** byte-derived CSV OHLCV/time row to Core indexed query. It rejects drift even when the entire canonical Scanner JSON/run/nomination/request chain is independently resealed around a modified bar.

The synthetic Scanner market is `fixture`, while Core's historical-format test adapter retains `BINANCE:SPOT:USDT`. This is recorded as an **explicit synthetic-only namespace boundary** and is NOT evidence that a historical production market route is connected. No exchange network request is made.

## Exact owner receipt/identity contract

| Owner | Canonical receipt | Seal/field |
|---|---|---|
| Scanner C #259 | `aql.scanner-c.strategy-approval.v1` | Work235 `Frozen {payload,sha256}`; explicit `APPROVE_TEST_ONLY` |
| Scanner C #259 | `aql.scanner-c.strategy-route-request.v1` | Work235 `Frozen {payload,sha256}`; `ROUTE_CANDIDATE_TEST_ONLY` is **not** a queue ACK |
| Core B #226 | `aql.core.historical-dual-query-identity-map.v1` | separate `core_245_native_price_query_sha256`, `core_253_query_local_sha256` |
| Core B #226 | `aql.core.secretary-offline-ack.v1` | durable `receipt_sha256`, **SOURCE_ACK only** |
| Core D | `aql.core.d.synthetic-same-source-proof.v1` | `same_source_proof_sha256` |
| Core D | `aql.core.d.canonical-scanner-strategy-binding.v1` | `canonical_bridge_sha256` |
| Core C #261 reused | `aql.core.c.strategy-secretary-route.v1` | separate Core projected policy approval and durable `PENDING_CONSUMER` / RETRY / QUARANTINE / explicit ACK |
| Core D | `aql.core.d.factory-canonical-strategy-offer.v1` | `factory_offer_sha256`; **no Factory ACK yet** |

No implicit `artifact_sha256` ↔ `sha256` renaming; no Core245↔Core253 SHA equality; and no Scanner Frozen approval expiry/independently verified issuer invented. Core D creates an **explicitly labeled internal research-only projection** of the externally supplied valid Scanner C TEST_ONLY approval. The new `issued_at_ms` / `expires_at_ms` describe **Core D's bounded research route TTL**, not an original Scanner approval time or independent policy authority. The projection includes original Scanner approval SHA, route SHA and independently derived `same_source_proof_sha256` in the persisted signed request and approval. An existing B SOURCE_ACK is independently looked up in its durable SQLite outbox; its own native `AQL-SCANNER-V1 UNKNOWN` nomination SHA stays distinct from Scanner C's synthetic `SELECTED` research nomination.

After strict replay and proof, the only action Core may take is enqueue **TEST_ONLY `PENDING_CONSUMER`**, with `factory_consumer_ack_sha256=None`. Core never manufactures the Factory ACK or calls Lab/Paper. Factory must independently verify the D offer and produce its own separate consumer receipt and ACK; only then can existing Core C route state transition according to its own versioned rules. Isolated TEST_ONLY Paper always remains non-operational/zero orders; no G0, trading or holdout.

## Reproducible one-cohort positive and negative examples

New test fixture: `tests/test_aql_core_d_same_source_strategy_route_v1.py::CoreDSameSource`.

After the D workflow pins and stages upstream code, run the **new D delta plus the 6 C wire-compatibility cases only**:

```bash
PYTHONPATH=.:tests:_pinned_raw_211:_pinned_scanner_227 python -m unittest discover -s tests -p 'test_aql_core_d_same_source_strategy_route_v1.py' -v
PYTHONPATH=.:tests:_pinned_raw_211:_pinned_scanner_227 python -m unittest discover -s tests -p 'test_aql_core_c_scanner_reconciliation_v1.py' -v
```

The TEST_ONLY positive path:

```python
from research_wp_r0.aql_core_d_same_source_strategy_route_v1 import (
    verify_same_source_research,
    connect_canonical_test_only_strategy,
    read_factory_canonical_strategy_offer,
)

# "fixture" is the complete source/Scanner/Core/RAW parent constructor in
# CoreDSameSource.setUp(); no authentic Binance originals are loaded.
proof = verify_same_source_research(fixture.root, **fixture.args)
assert proof["proof_state"] == "VERIFIED_TEST_ONLY"
assert proof["bar_count"] == 10
assert proof["publisher_checksum_attested"] is False
assert proof["historical_known_at_ms"] is None
assert proof["core_245_native_query_sha256"] != proof["core_253_local_query_sha256"]

bridge = connect_canonical_test_only_strategy(
    fixture.root, same_source_inputs=fixture.args,
    now_ms=fixture.now, expires_at_ms=fixture.now+60000,
    route_id="D_STRATEGY_ONE")
assert bridge["status"] == "PENDING_FACTORY_CONSUMER_TEST_ONLY"
assert bridge["factory_consumer_ack_sha256"] is None
offer = read_factory_canonical_strategy_offer(
    fixture.root, same_source_inputs=fixture.args,
    canonical_bridge_receipt=bridge, now_ms=fixture.now)
assert offer["status"] == "READY_FOR_EXPLICIT_FACTORY_RESEARCH_CONSUMER_ONLY"
assert offer["lab_invoked"] is False and offer["paper_invoked"] is False
assert offer["orders_created"] == 0
```

The complete runnable `CoreDSameSource` test creates the actual source bytes, #211 vault, #245/#253 queries and Scanner C Frozen parent evidence; the code above illustrates use **inside that fixture**, not a self-contained script.

Focused new tests include full RAW-readback and replay, explicit approval separate from source ACK, durable restart/idempotent pending state, full **resealed** altered-Scanner-bar refusal, wrong native ZIP or checksum, denied approval/forged route, missing/forged source ACK, bounded route expiry, and read-only Factory offer never faking consumer ACK. The existing C disconnected-historical tests verify `reason=SOURCE_LINEAGE_NOT_CONNECTED` + owner-facing `WAIT_SOURCE_PROVENANCE_NOT_CONNECTED`; no old B 96, accepted Feb/Aug 5,760 real bars or 106 reports rerun.

## Factory and Scanner handoff / next gate

**Scanner #259**: consume the exported original-format synthetic Core query in a read-only feed; bind its exact 10 bars to native15m JSON via the D proof and retain original Scanner `Frozen` receipt schemas unchanged. This is **one test-only cohort**; never convert old historical original data by aliasing source hashes.

**Factory #260**: consume `read_factory_canonical_strategy_offer(...)` only after Core's `verify_same_source_research` succeeds and `PENDING_CONSUMER` is durable. Verify strategy id/version/config/definition, Scanner policy/approval/nomination/run, source ACK, independent Core 245/253 SHA domains, cutoff and scope. Then create **Factory-owned signed TEST_ONLY consumer ACK** under an explicitly agreed contract, independently passed back to Core C `acknowledge_strategy_consumer` (do not synthesize from Core, and do not call Lab on historical-disconnected WAIT). Run one **combined D new-delta software integration gate** that proves Lab actual invocation vs route-only evidence, and isolated Paper WAIT/REJECT with orders/fills/positions zero. Audit then reviews the one new delta only.

**Still blocked**: new authentic third 2024 BTCUSDT Spot native 15m monthly original ZIP+publisher CHECKSUM (`SOURCE_UNAVAILABLE`), independent issuer/PIT/known-at proof, Work235 operational native 15m route, approved trading and G0. Discoverer non-blocking; all PRs remain Draft/unmerged.
