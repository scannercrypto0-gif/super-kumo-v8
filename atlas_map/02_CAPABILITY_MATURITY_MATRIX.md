# ATLAS Quant Lab — Capability Maturity Matrix
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

**Maturity Levels:**
- L0 Concept — idea only, no design artifact
- L1 Architecture — documented design, no code
- L2 Implemented — code exists, synthetic tests passing
- L3 Integrated — components work together with live data
- L4 Validated — independent validation, CI green, live tests
- L5 Operational — production-ready, monitored, proven stable

---

## A. Historical Data Library (`research_wp_r0/historical_library.py`)

| Dimension | Level | Evidence | Gap | Required Work |
|-----------|-------|----------|-----|--------------|
| Requirements | L4 | SF-DATA-01 spec, Issue #47 closed | None | — |
| Architecture | L4 | CustodyAccessor contract, PIT design | None | — |
| Interfaces/Contracts | L4 | `range_query()`, `DataAvailabilityKind`, `BarQuality` | None | — |
| Code Implementation | L2 | 1,154 lines, `historical_library.py` merged in main | No live data path | — |
| Tests | L2 | `test_sf_data_01.py` 2,564 lines, 506 passing | No live-data integration test | — |
| Integration | L1 | Used by indicator_library; no live pipeline link | Not connected to operational store | Link needed for G2 |
| Data Integrity | L3 | `manifest_integrity_hash`, `require_complete`, `DataAvailabilityKind` | No correction/repair workflow | Phase 1 archive work |
| PIT Correctness | L4 | `decision_cutoff_ms`, `require_confirmed_availability=True` | — | — |
| Reliability/Recovery | L1 | Immutable library design; no repair workflow | Gap detection/repair missing | Issue #71 |
| Performance/Scale | L1 | Design only; no benchmarks | No Parquet/large-scale test | Deferred |
| Monitoring | L0 | None | No freshness or coverage metrics | Future |
| Documentation | L3 | Docstrings, Issues | No coverage inventory | — |
| Production Readiness | L2 | Research use only; no production path | Supabase/cloud storage not designed | — |

**Overall: L2** — Solid research-lane foundation; not production-ready; missing live pipeline connection.

---

## B. Live Market Data Center (`src/aql/collector/`, `src/aql/journal/`)

| Dimension | Level | Evidence | Gap | Required Work |
|-----------|-------|----------|-----|--------------|
| Requirements | L3 | G1-WP01–WP04 specs, DATA-05–08 | None | — |
| Architecture | L3 | G1-ARCH-01–11 documented | Fast/Slow Lane not fully distinct in code | — |
| Interfaces/Contracts | L3 | `BinanceCollector`, `DurableJournal`, bar model | No published API contract | — |
| Code | L2 | `binance_collector.py`, `durable_journal.py`, `lanes.py` | No live Binance test | — |
| Tests | L2 | G1 WP01–WP04 suites, 129+ passing, synthetic only | Live Binance blocked by proxy | `BINANCE_LIVE_TEST=1` |
| Integration | L2 | Pipeline integrates all components | No live integration test | Issue #64 |
| Data Integrity | L2 | Idempotent upsert, WAL, `UNIQUE(symbol,interval,bar_open)` | Dedup unverified in live scenario | — |
| PIT Correctness | L2 | `is_final` flag, `bar_close` timestamp | Live WebSocket finality not live-tested | — |
| Reliability/Recovery | L2 | `GapRecovery`, backoff, journal replay | SIGKILL recovery synthetic only | — |
| Performance/Scale | L1 | 5 bars/s floor on Windows; no production SLA | No Linux production benchmark | — |
| Monitoring | L2 | `HealthSnapshot` (WP03) | No Telegram alerts; dashboard deferred | — |
| Documentation | L3 | Docstrings, work package docs | — | — |
| Production Readiness | L1 | G1 merged ≠ production authorized | Supabase NOT_TESTED; no live validation | Issue #64, #65 |

**Overall: L2** — Complete synthetic implementation; not production-authorized; live validation pending.

---

## C. Strategy Factory (`research_wp_r0/`)

| Dimension | Level | Evidence | Gap | Required Work |
|-----------|-------|----------|-----|--------------|
| Requirements | L3 | Issues #47, #59, #66, #72 | Batch-01 candidates pending | Issue #46 |
| Architecture | L3 | SF-DATA-01, SF-IND-01/02, SF-STRAT-01 | No backtest engine designed | — |
| Interfaces/Contracts | L3 | `CustodyAccessor`, `IndicatorResult`, `VectorResult`, `StrategyDefinition` | No cross-factory orchestration | — |
| Code | L2 | 4 modules merged: historical_library, indicator_library (V1+V2), strategy_definition | No runner/engine | — |
| Tests | L2 | test_sf_data_01, test_sf_ind_01, test_sf_ind_02, test_sf_strat_01: 506 passing | No backtesting | — |
| Integration | L1 | Modules integrated; no pipeline to Research Lab | No connection to Research Lab | — |
| Data Integrity | L3 | SHA-256 provenance hashes, `computation_hash`, canonical JSON | No correction propagation | — |
| PIT Correctness | L4 | `decision_cutoff_ms`, CustodyAccessor enforces no future bars | — | — |
| Reliability/Recovery | L1 | Immutable objects; no mutable state recovery | — | — |
| Performance | L1 | No benchmarks | — | — |
| Monitoring | L0 | None | — | — |
| Documentation | L3 | Docstrings, Issues, canonical contracts | — | — |
| Production Readiness | L1 | Research lane only; not connected to live data | — | — |

**Overall: L2-L3** — Best-implemented area. Contracts are strong. Missing: backtesting engine, Research Lab connection.

---

## D. Strategy Explorer

| All Dimensions | L0 | No code, no Issues, no design | All | Future work package |

---

## E. Asset Intelligence Lab

| All Dimensions | L0 | Issue #72 open (unprioritized) | All | Owner decision required first |

---

## F. Research Lab

| Dimension | Level | Evidence | Gap | Required Work |
|-----------|-------|----------|-----|--------------|
| Requirements | L1 | Issues #17–#46, PRs #17–#43 (open) | None designed | — |
| Architecture | L1 | PR #17 docs, WP-R0 through WP-R40 | No consensus design | — |
| Code | L1 | Strategy Factory foundations merged in main (PRs #68, #69 @ `4e4c353`): `historical_library.py`, `indicator_library.py`, `indicator_library_v2.py`, `strategy_definition.py`, `_dep_guard.py` — isolated; no integrated Research Lab | backtest engine, holdout, trial registry, runner not implemented | Issues #18–#46 |
| Tests | L1 | SF foundation tests pass (506 local, CI #40085463732); no Research Lab integration tests | Everything at Lab level | — |
| PIT Correctness | L1 | Designed in contracts; `decision_cutoff_ms` in CustodyAccessor | Not live-tested in backtest pipeline | — |
| Holdout Custody | L0 | WP-R6 designed (Issue #24) | Not implemented | — |
| Trial Registry | L0 | WP-R7 designed (Issue #25) | Not implemented | — |

**Overall: L1** — Isolated Strategy Factory foundations (PRs #68, #69) merged in main; integrated Research Lab (backtest engine, holdout custody, trial registry) not implemented. Largest implementation gap in the project.

---

## G. Secretariat Office

| All Dimensions | L1 | G1-ARCH-01–11 in `01_CONTRACT.md`; no code | All | Future G1 work |

---

## H. Opportunity Scanner

| All Dimensions | L1 | G1-ARCH-12–20 in `01_CONTRACT.md`; no code | All | Future G2+ work |

---

## I. Virtual Traders

| All Dimensions | L1 | Lifecycle states designed; G3 = first trader | All | Future G3 work |

---

## J. Market Intelligence

| All Dimensions | L0 | Referenced in contracts only | All | Future work |

---

## K. Monitoring & Dashboard

| All Dimensions | L0 | Deferred in `02_ROADMAP.md` | All | After operational data exists |

---

## L. Governance & Orchestration

| Dimension | Level | Evidence |
|-----------|-------|----------|
| Requirements | L5 | All G0–G6 gates defined |
| Architecture | L4 | G1-ARCH-01–44 documented |
| Process | L4 | PR history, stage gates, ADRs |
| CI | L3 | 5 workflows, ubuntu+windows matrix |
| Test Policy | L4 | `10_TEST_POLICY.md` |
| Risk Register | L4 | `08_RISKS.md` |

**Overall: L4** — Best-maintained department.

---

## M. Shared Infrastructure & Storage

| Dimension | Level | Evidence | Gap |
|-----------|-------|----------|-----|
| SQLite Operational Store | L2 | `operational_store.py`, 129+ synthetic tests | No live test |
| Durable Journal | L2 | `durable_journal.py`, SIGKILL tests | No live test |
| Supabase | L0 | `SUPABASE_STATUS = "NOT_TESTED"` | All — Issue #65, #67 |
| Phase 1 Archive | L0 | Issue #71 open | All |
| Backup/Restore | L0 | Not designed | All |
| Resource Reservations | L1 | Designed in contracts | Not implemented |

**Overall: L1-L2** — Local SQLite path solid; everything else not started.

---

## Summary Across All 13 Departments

```
Dept  Name                          Overall
A     Historical Data Library        L2
B     Live Market Data Center        L2
C     Strategy Factory               L2-L3
D     Strategy Explorer              L0
E     Asset Intelligence Lab         L0
F     Research Lab                   L1
G     Secretariat Office             L1
H     Opportunity Scanner            L1
I     Virtual Traders                L1
J     Market Intelligence            L0
K     Monitoring & Dashboard         L0
L     Governance & Orchestration     L4
M     Shared Infrastructure          L1-L2
```

**Project average:** L1.5 — The governance and three implemented modules (A, B, C, M) pull above L1; everything else is design-only.
