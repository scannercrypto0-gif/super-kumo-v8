# ATLAS Quant Lab — Data & Strategy Lifecycles
**Version:** 1.1-DRAFT | **Evidence snapshot:** 2026-10-24
**Main source baseline:** `4e4c3537036bdf2b106c1a63ec65b2a9855972a7` | **Documentation:** PR #74, Draft/unmerged.
Reviewed documentation baseline: `e4ce1c8a5d7911f52fb67e52f7e58c2e0ee5b476`; final document HEAD is in PR metadata/correction matrix, not the main-source SHA.
Evidence IDs and scope: [09_EVIDENCE_REGISTER.md](09_EVIDENCE_REGISTER.md). No production authorization or owner decision is created by this map.

---

## 1. Market Data Lifecycle

```
SOURCE → ACQUISITION → DURABILITY → PERSISTENCE → CUSTODY → RESEARCH USE
```

### Stage 1: SOURCE
- **Binance WebSocket** `wss://stream.binance.com:9443`
- Raw kline stream: `symbol`, `interval`, `open_time`, `open`, `high`, `low`, `close`, `volume`, `is_final`
- Only `is_final=True` bars are eligible for journaling and storage
- **Evidence:** `binance_collector.py` — `_on_message()` filters `kline['x']` (is_final)

### Stage 2: ACQUISITION
- `BinanceCollector` deserializes WebSocket message → `MarketBar`
- Records MarketBar.ingested_at (local receipt/ingest epoch milliseconds); no received_at_ms field is claimed
- Collector observes source event E minus local time and rejects ahead-of-host events beyond configured tolerance; also rejects a closed candle whose close is not before receipt
- Stores `gap_start_ms` on disconnect; `gap_end_ms` on reconnect
- CLOCK_UNCERTAIN is a fail-closed health/eligibility signal, not an independent time-accuracy certificate. #64 bounded report supersedes an older clock-offset failure; continuous clock reliability remains unproven.

### Stage 3: DURABILITY (WAL Commit)
- `DurableJournal.commit(bar)` → SQLite WAL write
- Bar state: `LOCAL_COMMITTED`
- ACK is never issued before journal commit
- Committed SQLite WAL/FULL records are recovered in Linux SIGKILL and cross-platform process-exit tests; this is not physical power-loss certification.
- **Evidence:** `durable_journal.py`; "Store success precedes ACK" rule in `lanes.py`

### Stage 4: PERSISTENCE (Store Write)
- `JournalConsumer.drain_once()` → `store.upsert(bar)` → `journal.mark_persisted(bar.stable_key())`
- Bar state: `PERSISTED`
- If upsert fails → state remains `LOCAL_COMMITTED` → retried on next replay
- Stable-key dedupe and UNIQUE(symbol, interval, bar_open) prevent duplicate effects; exact-repeat and conflicting-checksum cases are different, not all ignored silently.
- **Evidence:** `operational_store.py` `INSERT OR IGNORE`

### Stage 5: GAP RECOVERY
- On startup: `journal.startup_reconcile()` detects gaps between journal and store
- Per gap: `GapRecovery` calls REST `/api/v3/klines`
- Recovery sequence: journal.commit(background=True) → store.upsert → journal.mark_persisted
- Report: `FULL | PARTIAL | UNRESOLVED_DATA_GAP | HTTP_ERROR`
- Code budget MAX_SESSION_WEIGHT=1200, cost2 per kline request, max1000 bars/request in inspected source; these constants are not freshly verified provider entitlements.
- **Evidence:** pipeline._run_gap_recovery. Startup/detected/post-collection gap jobs use a bounded lane. #64's bounded live harness explicitly scheduled recovery on reconnect; it is not proof of an unattended run_pipeline deployment.

### Stage 6: CUSTODY (Historical Library)
- `HistoricalLibrary` imports bar data into versioned datasets
- Retains observation_cutoff_ms and availability_kind. Imported fixtures are RETROSPECTIVE with unknown actual receipt; close+1 is only a derived lower bound. CONFIRMED labels require truthful recorded evidence, not an automatic importer promotion.
- Computes `manifest_integrity_hash` (includes `created_at_ms` — wall clock at validate_bars time)
- Each dataset gets integer version
- HistoricalLibrary is IMPLEMENTED IN MAIN. Only the automated operational→historical artifact bridge is missing. Draft73 seals journal records; it does not feed CustodyAccessor or fabricate confirmed research receipt.
- Gap: separately approved artifact/export protocol, eligibility/missingness and retained commitments (OD-03); no synchronous core dependency.

### Stage 7: RESEARCH USE
- `CustodyAccessor.range_query(decision_cutoff_ms=T)` — returns only bars observable at time T
- Bars with `observation_cutoff_ms > T` are excluded → PIT safety enforced
- Indicator computation takes `decision_cutoff_ms` and propagates it through provenance hashes
- **Evidence:** `historical_library.py`, `indicator_library.py`

---

## 2. Strategy Lifecycle

```
IDEA → DEFINITION → BINDING → EVALUATION → PROMOTION → OPERATION → RETIREMENT
```

### Stage 1: IDEA
- Owner or research identifies a potential trading hypothesis
- Not recorded in any system until Stage 2
- **Status:** Unstructured (no tooling)

### Stage 2: DEFINITION (SF-STRAT-01)
- Owner creates `StrategyDefinition` JSON file
- JSON validation: no external dependencies, finite numbers, depth ≤ 24, ≤ 100KB
- `canonical()` → sorted-key JSON string for deterministic hashing
- `digest` = SHA-256 of canonical JSON → **immutable version identifier**
- **Evidence:** `strategy_definition.py`

### Stage 3: BINDING
- bind_evaluation(definition, accessor, dataset_id, version, start_ms, end_ms, decision_cutoff_ms, registry=...) returns EvaluationBinding; there is no bind_indicators/BoundStrategy API.
- Indicator versions locked at bind time
- computation_hash hashes ordered result provenance hashes, which bind dataset_manifest_hash and computation identity; no Python object id is hashed. Independent imports usually differ through manifest creation time; replay of the same retained manifest can reproduce receipts across processes.
- **Warning:** `manifest_integrity_hash` includes wall-clock `created_at_ms` → non-deterministic across library instances
- **Evidence:** `indicator_library.py`, `indicator_library_v2.py`

### Stage 4: EVALUATION (isolated code exists; accepted historical integration absent)
Canonical roadmap G4 remains the Research Lab gate; this map does not relabel G2/G5/G6. In unmerged #46 ancestry:
- Synthetic next-bar backtest/candidate foundations exist in strategy_factory.py; admissible real historical evaluation is not accepted.
- Split/purging/synthetic_validation contracts exist; no independently accepted real OOS study.
- Purged forward folds in statistics.py (R1); frozen temporal opportunity/horizon manifest in temporal_contract.py (R5).
- Paired evaluation engine (WP-R2)
- Statistical audit with fail-closed inference
- Pre-registration before holdout access

### Stage 5: HOLDOUT GATE (foundation implemented in unmerged research chain)
- Holdout data MUST be inaccessible during Stages 1–4
- integrity.HoldoutCustody tracks access/tuning; trial_holdout.TrialFamilyLedger/HoldoutEvent enforces family/selection/taint rules; durable journal persists those events in the unmerged chain. No independently segregated data service or current owner unlock is proven.
- Final holdout use must follow the frozen preregistered protocol and owner policy; a local access-log class alone does not enforce a universal one-use data-access boundary.
- Tuning/reopening invalidates an untouched confirmatory claim. Any new version/family and retirement disposition must remain explicit; do not invent a universal automatic retirement engine.
- **Gap:** no accepted-main integrated custody workflow/independent external anchor. Final holdout remains unopened in #46's synthetic batch; not an invitation to access it.

### Stage 6: PROMOTION (DESIGNED — not implemented)
- Owner signs off on evaluation evidence
- `StrategyDefinition.digest` frozen — no further parameter changes
- Strategy eligible for assignment to a Virtual Trader (Stage 7)
- **Rule:** No strategy promotion without explicit owner decision

### Stage 7: OPERATION — Paper Trading (DESIGNED — not implemented)
- Virtual Trader receives frozen strategy snapshot at trade creation
- Entry/exit based on frozen rules; no live adaptation
- Paper fills with fees, slippage, ambiguity tracking
- Trade lifecycle: `WATCH → ARMED → TRIGGERED → CLOSED`
- All records to Research Lab (F) for post-trade analysis

### Stage 8: RETIREMENT
- Strategy retired if holdout fails, performance degrades, or owner decides
- `StrategyDefinition.digest` version preserved in audit log
- **Not yet designed:** retirement workflow

---

## 3. Indicator Computation Lifecycle

```
REGISTRATION → COMPUTATION → PROVENANCE → VERIFICATION → USE
```

### V1 (SF-IND-01)
1. **Registration:** SMA, EMA, RSI, ATR registered in `IndicatorLibrary`
2. **Computation:** `compute(accessor, dataset_id, start_ms, end_ms, decision_cutoff_ms)` → `(list[IndicatorResult], IndicatorManifest)`
3. **Provenance:** IndicatorManifest.computation_hash = SHA256(ordered result provenance_hash values)
4. **Verification:** manifest.verify(results) checks result-count/hash consistency
5. **Use:** Research Lab or Strategy binding

### V2 (SF-IND-02)
1. **Registration:** Additive only — V1 bytes and APIs unchanged
2. New: `VectorResult` frozen dataclass with `provenance_hash`, `value: tuple`, `parameters: tuple`
3. New: `VectorResult.create(**fields)` computes `provenance_hash` from all fields
4. New: `VectorResult.verify_integrity()` re-derives hash, checks all values finite
5. V2 indicators: 6 OHLCV-based (MACD_v2, BBANDS_v2, ADX_v2, STOCH_v2, ROC_v2, OBV_v2)
6. **Evidence:** `indicator_library_v2.py` `_ema()` with SMA seed, `alpha=2/(period+1)`

### PIT Guarantee
- V1: `decision_cutoff_ms` passed to `CustodyAccessor.range_query()` inside `compute()`
- V2: same propagation via `VectorResult` chain
- No indicator computation can access bars with `observation_cutoff_ms > decision_cutoff_ms`
- **Verified:** `test_sf_data_01.py`, `test_sf_ind_01.py`, `test_sf_ind_02.py`

---

## 4. Dependency Guard (Isolation Enforcement)

research_wp_r0/_dep_guard.py — explicit static AST check in CLI/tests/CI:
- Blocks any import of `src.aql` from research lane
- Flags imports outside its stdlib/verified first-party policy; does not sandbox dynamic code or installed packages at runtime.
- Ensures research lane can run independently of G1 operational lane
- Verified test file: tests/test_sf_dep_guard.py (45 cases within E-82).

---

## 5. Lifecycle Gap Summary

| Gap | Impact | Upstream | Downstream | Mitigation |
|-----|--------|---------|------------|------------|
| No pipeline: Operational Store → Historical Library | Manual data import for research | B, M | A, C, F | Issue #71 |
| No accepted-main integrated holdout custody | Isolated access/taint code is insufficient for an independent real holdout | F | Strategy validity | Reconcile #24/#46 before real confirmatory use |
| No accepted-main durable family registry integration | Existing unmerged registries/journal need contract reconciliation | F | Research Lab | #25/#46 and #77 |
| Synthetic engine exists only in unmerged #46 | Historical/OOS acceptance absent | C,F | Research evidence | #77 staged reconciliation, not a fresh duplicate engine |
| `manifest_integrity_hash` wall-clock dependency | Non-deterministic across instances | A | C | Design: document constraint |
| Computation receipt binds retained dataset manifest | Independent imports differ; retained-manifest replay can match across processes | C | F | #76/#77; preserve semantic and temporal identity |

## 6. Outlook, archival and prospective lifecycle boundaries

AssetOutlook (#72, future under C): owner request→immutable initial version→lightweight trigger/deadline watch→REASSESSMENT_REQUIRED/STALE→bounded idempotent reassessment→new linked version. Confirmation, contradiction, non-occurrence and material-change triggers are reasons to reassess, not proof of predictive success. Missing evidence is UNKNOWN; no silent TTL extension or trading command.

Draft73 market envelope: event/receipt/ingest/recorded journal commit remain distinct; source_event_ms/available_ms/fsync_completed_ms are null where missing. availability_lower_bound_ms is explicitly derived, not confirmed. Schema decision_context is plumbing, not a runtime trader event recorder.

Draft78: prepare_inputs produces INPUTS_ONLY_NOT_EVALUATED for one cutoff. prepare_candidate uses the accepted AttemptRecorder port; successful preparation remains PENDING, input failure FAILED, malformed definition INVALID, explicit stop ABANDONED. Sink durability/restart/idempotency/family completeness belong to an unreconciled ledger, not a memory sink.

Prospective Shadow/outcome operation needs frozen parent/variant versions, complete opportunity denominators, independently observed visibility, preregistration and later owner approval. Synthetic outcomes and purged folds do not establish forward evidence. Retrospective explanation never rewrites an original decision.
