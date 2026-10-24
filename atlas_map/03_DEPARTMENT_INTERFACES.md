# ATLAS Quant Lab — Department Interfaces & Responsibility Boundaries
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## 1. Data Ownership Map

| Data Type | Canonical Owner | Source | Consumers |
|-----------|----------------|--------|-----------|
| Raw OHLCV bars (live) | Live Market Data Center (B) | Binance WS | G1 Operational Store → future Secretariat |
| Raw OHLCV bars (historical) | Historical Data Library (A) | G1 Store or bulk download | Strategy Factory (C), Research Lab (F) |
| Versioned indicator results | Strategy Factory (C) | Historical Library | Research Lab (F), future Scanner (H) |
| Strategy definitions | Strategy Factory (C) | Owner-declared | Research Lab (F), Virtual Traders (I) |
| Paper trade records | Virtual Traders (I) | Trader decisions | Research Lab (F), Monitoring (K) |
| Health snapshots | Shared Infrastructure (M) | Journal + Store | Monitoring (K) |
| Architecture decisions | Governance (L) | Owner approvals | All departments |

---

## 2. Verified Interface Contracts (VERIFIED IN MAIN)

### A → C: CustodyAccessor
```python
accessor.range_query(
    dataset_id: str,
    start_ms: int,
    end_ms: int,
    decision_cutoff_ms: int,
    *,
    version: int = 1,
    require_complete: bool = True
) -> list[HistoricalBar]
```
- `require_confirmed_availability=True` enforced internally
- Bars with `observation_cutoff_ms > decision_cutoff_ms` are excluded
- `require_complete=False` allows partial-window queries

### B → M: DurableJournal write
```python
journal.commit(bar: MarketBar) -> None        # WAL commit before ACK
journal.replay(symbol, interval, pending_only, limit) -> list[MarketBar]
journal.acknowledge(symbol, interval, bar_open) -> None
```

### M → M: OperationalStore upsert
```python
store.write_bar(bar: MarketBar) -> None       # UNIQUE(symbol,interval,bar_open)
store.get_bars(symbol, interval, limit) -> list[MarketBar]
store.get_latest_bar(symbol, interval) -> Optional[MarketBar]
```

### B → M: GapRecovery
```python
recover_gap(
    symbol, interval, gap_start_ms, gap_end_ms,
    journal, store, session_weight_used
) -> RecoveryReport  # status: FULL|PARTIAL|UNRESOLVED_DATA_GAP|HTTP_ERROR
```

### C → C: IndicatorLibrary (V1)
```python
indicator.compute(
    accessor: CustodyAccessor,
    dataset_id: str,
    start_ms: int,
    end_ms: int,
    decision_cutoff_ms: int,
    version: int = 1
) -> tuple[list[IndicatorResult], IndicatorManifest]
```

### C → C: StrategyDefinition (SF-STRAT-01)
```python
StrategyDefinition.from_json(raw: str) -> StrategyDefinition  # validates + canonicalizes
definition.digest  # SHA-256 of canonical JSON
definition.bind_indicators(registry) -> BoundStrategy
```

---

## 3. Responsibility Boundaries

### B ↔ M: Durability Boundary
- **B owns:** WebSocket connection lifecycle, bar ingestion, gap detection
- **M owns:** durable commit (journal), idempotent store write, health state
- **Rule:** B never writes directly to operational store; always via journal → consumer → store
- **Evidence:** `lanes.py` `JournalConsumer` pattern; "Store success (including an existing key) precedes ACK"

### A ↔ C: PIT Boundary
- **A owns:** bar custody, availability metadata, `manifest_integrity_hash`
- **C owns:** indicator computation, provenance hashing, strategy binding
- **Rule:** C never constructs `CustodyAccessor` with bars from the future; `decision_cutoff_ms` enforced
- **Evidence:** `historical_library.py` `require_confirmed_availability=True`

### G ↔ I: Decision Authority Boundary (DESIGNED — not implemented)
- **G (Secretariat) owns:** routing observations to the correct trader's secretary
- **I (Trader) owns:** entry/exit decisions based on frozen strategy rules
- **Rule:** Secretariat does NOT decide fills, exits, or strategy outcomes
- **Evidence:** `01_CONTRACT.md` DATA-07: "The owning trader evaluates and decides; the monitor/secretariat does not independently decide outcomes or create fills (G1-ARCH-05)"

### H ↔ I: Candidate vs. Decision Boundary (DESIGNED — not implemented)
- **H (Scanner) owns:** candidate qualification, stage management (WATCH→ARMED→READY)
- **I (Trader) owns:** final entry decision with complete mandatory evidence
- **Rule:** Scanner READY ≠ trade permission; trader decides independently

### C ↔ F: Research Isolation Boundary (DESIGNED — not implemented)
- **C owns:** strategy definitions, indicator results, provenance
- **F owns:** experiment registration, paired evaluation, holdout custody
- **Rule:** Holdout data must never be accessible during strategy development
- **Rule:** Historical development / OOS / forward sections must remain separate

---

## 4. Circular Dependency Check

| Dependency | Direction | Risk |
|-----------|----------|------|
| `research_wp_r0` → `src/aql` | NONE — verified by dep_guard | ✅ Safe |
| `src/aql` → `research_wp_r0` | NONE | ✅ Safe |
| Secretariat → Trader | Secretariat routes TO Trader | ✅ One-way |
| Scanner → Trader | Scanner routes TO Trader | ✅ One-way |
| Trader → Research Lab | Trader produces data FOR Lab | ✅ One-way |
| Research Lab → Strategy Factory | Lab consumes FROM Factory | ✅ One-way |

**No circular dependencies identified** in existing code or designed interfaces.

---

## 5. Version Compatibility Rules

| Contract | Version Policy | Evidence |
|---------|---------------|----------|
| `CustodyAccessor` dataset versions | Integer version parameter | `historical_library.py` |
| `IndicatorLibrary` V1 | Additive only; V1 bytes/APIs unchanged | `indicator_library_v2.py` docstring |
| `StrategyDefinition` | SHA-256 digest pins version | `strategy_definition.py` |
| Bar schema | `09_DATA_SCHEMAS.md` versioned | `01_CONTRACT.md` |

**Rule:** All schema changes require ADR (per `01_CONTRACT.md`). No breaking changes to existing contracts without version bump.

---

## 6. Who Owns What Decision

| Decision | Owner | Evidence |
|---------|-------|----------|
| Strategy promotion | Project owner only | `02_ROADMAP.md` G4 |
| Holdout release | Project owner only | `01_CONTRACT.md` TIME-05 |
| Architecture changes | Project owner (ADR) | `01_CONTRACT.md` |
| Paid service activation | Project owner | `01_CONTRACT.md` DATA-03 |
| Merge to main | Project owner | Governance protocol |
| Entry/exit trade decision | Owning Virtual Trader | `01_CONTRACT.md` DATA-07 |
| Indicator technical validity | Shared Indicator Box manager | G1-ARCH-21 (designed) |
| Strategy-manifest eligibility | Trader's Secretary | G1-ARCH-22 (designed) |
