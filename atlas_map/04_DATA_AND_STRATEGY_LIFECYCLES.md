# ATLAS Quant Lab — Data & Strategy Lifecycles
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

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
- Records `received_at_ms` (wall clock of receipt)
- Detects source clock skew via `kline.close_time` vs local clock
- Stores `gap_start_ms` on disconnect; `gap_end_ms` on reconnect
- **Rule:** No bar accepted if clock divergence detected (CLOCK_UNCERTAIN state)

### Stage 3: DURABILITY (WAL Commit)
- `DurableJournal.commit(bar)` → SQLite WAL write
- Bar state: `LOCAL_COMMITTED`
- ACK is never issued before journal commit
- This step survives SIGKILL — bar is recoverable even if process dies
- **Evidence:** `durable_journal.py`; "Store success precedes ACK" rule in `lanes.py`

### Stage 4: PERSISTENCE (Store Write)
- `JournalConsumer.drain_once()` → `store.upsert(bar)` → `journal.mark_persisted(bar.stable_key())`
- Bar state: `PERSISTED`
- If upsert fails → state remains `LOCAL_COMMITTED` → retried on next replay
- Idempotent: `UNIQUE(symbol, interval, bar_open)` — duplicate ignored cleanly
- **Evidence:** `operational_store.py` `INSERT OR IGNORE`

### Stage 5: GAP RECOVERY
- On startup: `journal.startup_reconcile()` detects gaps between journal and store
- Per gap: `GapRecovery` calls REST `/api/v3/klines`
- Recovery sequence: journal.commit(background=True) → store.upsert → journal.mark_persisted
- Report: `FULL | PARTIAL | UNRESOLVED_DATA_GAP | HTTP_ERROR`
- Rate limit: `MAX_SESSION_WEIGHT=1200` per recovery run
- **Evidence:** `pipeline.py` `_run_gap_recovery()`

### Stage 6: CUSTODY (Historical Library)
- `HistoricalLibrary` imports bar data into versioned datasets
- Assigns `observation_cutoff_ms` = time bar became observable
- Computes `manifest_integrity_hash` (includes `created_at_ms` — wall clock at validate_bars time)
- Each dataset gets integer version
- **NOT YET IMPLEMENTED** — no automated pipeline from operational store → historical library
- **Gap:** Manual or future G2 automation required

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
- `definition.bind_indicators(registry)` → `BoundStrategy`
- Indicator versions locked at bind time
- `computation_hash` = hash(CustodyAccessor instance, dataset_id, bars) — NOT cross-instance stable
- **Warning:** `manifest_integrity_hash` includes wall-clock `created_at_ms` → non-deterministic across library instances
- **Evidence:** `indicator_library.py`, `indicator_library_v2.py`

### Stage 4: EVALUATION (DESIGNED — not implemented)
Per `02_ROADMAP.md` G4:
- In-sample backtest on historical data
- Out-of-sample validation
- Walk-forward analysis (WP-R5)
- Paired evaluation engine (WP-R2)
- Statistical audit with fail-closed inference
- Pre-registration before holdout access

### Stage 5: HOLDOUT GATE (DESIGNED — not implemented)
- Holdout data MUST be inaccessible during Stages 1–4
- `HoldoutCustody` (WP-R6, Issue #24) — owner unlocks explicitly
- Only ONE holdout test allowed per strategy version
- Failure → strategy retired; no parameter tweaking after holdout
- **CRITICAL:** Not yet implemented; holdout currently unprotected

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
3. **Provenance:** `IndicatorManifest.computation_hash` = hash(accessor instance, dataset_id, bars)
4. **Verification:** `manifest.verify()` checks hash consistency
5. **Use:** Research Lab or Strategy binding

### V2 (SF-IND-02)
1. **Registration:** Additive only — V1 bytes and APIs unchanged
2. New: `VectorResult` frozen dataclass with `provenance_hash`, `value: tuple`, `parameters: tuple`
3. New: `VectorResult.create(**fields)` computes `provenance_hash` from all fields
4. New: `VectorResult.verify_integrity()` re-derives hash, checks all values finite
5. V2 indicators: 6 OHLCV-based (RSI_V2, EMA_V2, SMA_V2, ATR_V2, MACD_V2, BB_V2)
6. **Evidence:** `indicator_library_v2.py` `_ema()` with SMA seed, `alpha=2/(period+1)`

### PIT Guarantee
- V1: `decision_cutoff_ms` passed to `CustodyAccessor.range_query()` inside `compute()`
- V2: same propagation via `VectorResult` chain
- No indicator computation can access bars with `observation_cutoff_ms > decision_cutoff_ms`
- **Verified:** `test_sf_data_01.py`, `test_sf_ind_01.py`, `test_sf_ind_02.py`

---

## 4. Dependency Guard (Isolation Enforcement)

`research_wp_r0/_dep_guard.py` — enforced at import time:
- Blocks any import of `src.aql` from research lane
- Prevents pip-installed external dependency use in research lane
- Ensures research lane can run independently of G1 operational lane
- **Verified:** CI test `test_dep_guard.py`

---

## 5. Lifecycle Gap Summary

| Gap | Impact | Upstream | Downstream | Mitigation |
|-----|--------|---------|------------|------------|
| No pipeline: Operational Store → Historical Library | Manual data import for research | B, M | A, C, F | Issue #71 |
| No holdout custody implementation | Holdout contamination risk | F | Strategy validity | WP-R6 Issue #24 |
| No trial registry | Reproducibility at risk | F | Research Lab | WP-R7 Issue #25 |
| No backtest engine | Can't evaluate strategies | C, F | I, Research Lab | WP-R1 Issue #19 |
| `manifest_integrity_hash` wall-clock dependency | Non-deterministic across instances | A | C | Design: document constraint |
| `computation_hash` instance-scope | Cannot compare across processes | C | F | Design: document constraint |
