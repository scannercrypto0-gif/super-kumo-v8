# ATLAS Quant Lab — Master Development Roadmap
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## Priority Classification

- **P0** — Blocks production authorization or data integrity. Must be done before live operation.
- **P1** — Core platform capability. Required for primary research and trading mission.
- **P2** — Important improvement. Needed for production quality but not blocking P1 mission.
- **P3** — Future enhancement. Valuable but can be deferred to later stages.

---

## G1 Completion (Current Stage)

### P0 — Production Authorization Gates

| Task | Issue/PR | Owner | Dependency | Estimate |
|------|---------|-------|-----------|---------|
| R09: Document V7 credential revocation | `08_RISKS.md` | OWNER ACTION | None | 1 day |
| Controlled integration acceptance (live Binance) | Issue #64 | Dev | R09 | BOUNDED PASS — follow-ups open |
| Supabase sandbox acceptance | Issue #65 | Dev | Issue #64 | Open — pending Supabase cloud authorization |
| Supabase storage architecture | Issue #67 | Owner | — | **DECIDED** — Option B approved; Phase 1 #71 authorized; ADR pending |
| Windows production throughput benchmark | `04_STATE.md` gate | Dev | Issue #64 | 1–2 days |

### P1 — Phase 1 Archive & Research Data Path

| Task | Issue | Dependency | Estimate |
|------|-------|-----------|---------|
| Phase 1 local archive, PIT integrity, backup/restore | Issue #71 / PR #73 (DRAFT) | Issue #67 decision ✅ | In progress — PR #73 open, not merged |
| Operational Store → Historical Library bridge | (new) | Issue #71 | 3–5 days |

---

## Strategy Factory Foundations — COMPLETED IN MAIN

> These are merged and in main @ `4e4c353`. They are isolated research foundations — not yet integrated into a working Research Lab.

| Deliverable | PR | Merged SHA | Status |
|------------|-----|-----------|--------|
| Indicator Library V2 (6 OHLCV indicators, `VectorResult`) | PR #68 | `ea9cf19a` | **VERIFIED MAIN** |
| Strategy Definition JSON V1 + PIT provenance binding | PR #69 | `4e4c353` | **VERIFIED MAIN** |
| Historical Library (CustodyAccessor) | earlier | in main | **VERIFIED MAIN** |
| Indicator Library V1 | earlier | in main | **VERIFIED MAIN** |
| Dependency Guard (`_dep_guard.py`) | earlier | in main | **VERIFIED MAIN** |

---

## G2 — Research Foundation (Post-G1 Authorization)

### P0 — Holdout Protection (Pre-condition for any research claims)

| Task | Issue | Dependency | Estimate |
|------|-------|-----------|---------|
| WP-R6: Holdout Custody | Issue #24 | Issue #71 | 5–8 days |
| WP-R7: Pre-registered Trial Journal | Issue #25 | Issue #24 | 3–5 days |

### P1 — Core Research Engine (Batch-01)

| Task | Issue/PR | Dependency | Estimate |
|------|---------|-----------|---------|
| WP-R0: Research Environment Setup | Issue #18/PR #17 | Issue #71 | 2–3 days |
| WP-R1: Backtest Engine | Issue #19 | WP-R0, WP-R6 | 8–13 days |
| WP-R2: Paired Evaluation Engine | Issue #20 | WP-R1 | 5–8 days |
| WP-R3: No-fill Opportunity Accounting | Issue #21 | WP-R1 | 3–5 days |
| WP-R4: Statistical Audit | Issue #22 | WP-R2 | 5–8 days |
| WP-R5: Walk-Forward Analysis | Issue #23 | WP-R2 | 5–8 days |
| Strategy Batch-01 Candidates | Issue #46 | WP-R1 | 5–8 days |

### P2 — Secretariat & Scanner (G2 Architecture)

| Task | Issue | Dependency | Estimate |
|------|-------|-----------|---------|
| Secretariat Office implementation (G1-ARCH-01–11) | (new) | G1 authorization | 8–13 days |
| Opportunity Scanner implementation (G1-ARCH-12–20) | (new) | Secretariat | 8–13 days |
| Shared Indicator Box (G1-ARCH-21–44) | (new) | Secretariat | 5–8 days |

---

## G3 — First Virtual Trader

### P1 — Momentum Trader (G3 per roadmap)

| Task | Dependency | Estimate |
|------|-----------|---------|
| Trader base lifecycle (WATCH→TRIGGERED→CLOSED) | G2 Secretariat+Scanner | 8–13 days |
| Paper fill engine (fees, slippage, ambiguity) | Trader base | 5–8 days |
| Position Monitor implementation (DATA-07 compliant) | Trader base | 5–8 days |
| Momentum Trader v1 (first concrete strategy) | Strategy Batch-01, Trader base | 8–13 days |

### P2 — Research Integration

| Task | Dependency | Estimate |
|------|-----------|---------|
| Trade → Research Lab pipeline | Trader base | 3–5 days |
| Paper trading performance reporting | Trade pipeline | 5–8 days |

---

## G4 — Strategy Promotion & Validation

### P1

| Task | Dependency | Estimate |
|------|-----------|---------|
| Out-of-sample holdout validation workflow | WP-R6 + Trader | 5–8 days |
| Strategy promotion authorization workflow | OOS validation | 3–5 days |
| Live shadow testing framework | Strategy promotion | 8–13 days |

---

## G5 — Multi-Asset & Intelligence

### P2–P3

| Task | Dependency | Estimate |
|------|-----------|---------|
| Market Intelligence (J) — BTC trend, ETH/BTC | G3 operational | 8–13 days |
| Asset Intelligence Lab (E) — BTC/PAXG specialist | Market Intelligence | 5–8 days |
| Multiple virtual traders | G3 Momentum Trader | 8–13 days |
| Events/News Intelligence | G5 | 13–21 days |

---

## G6 — Monitoring, Dashboard & Scale

### P2–P3

| Task | Dependency | Estimate |
|------|-----------|---------|
| Monitoring & Dashboard (K) | Operational records exist | 13–21 days |
| Telegram notifications | Dashboard | 3–5 days |
| Multi-symbol production scale | G5 | 8–13 days |
| Supabase production migration | Multi-symbol | 3–5 days |

---

## Time Estimates Summary

> **⚠️ Uncertainty Notice:** These estimates are based on task-count and per-task heuristics only. They do NOT reflect measured historical velocity, parallel work capacity, review/integration overhead, or owner decision latency. Treat as directional order-of-magnitude guidance, not a project schedule. Critical dependencies (R09, live integration acceptance, owner decisions on OD-01–07) are not factored into the lower bounds.

| Stage | Conservative | Base | Optimistic | Key Assumptions |
|-------|-------------|------|-----------|----------------|
| G1 Completion (P0 gates) | 8–10 days | 6–8 days | 4–5 days | R09 done; Issue #64 follow-ups clear; no blockers |
| G2 Research Foundation | 55–75 days | 40–55 days | 30–40 days | WP-R0→R7 sequential; one engineer; no scope changes |
| G3 First Trader | 30–50 days | 25–40 days | 20–30 days | Secretariat+Scanner+Trader sequential |
| G4 Strategy Promotion | 20–30 days | 15–25 days | 10–18 days | OOS validation framework in place |
| G5 Multi-Asset | 40–60 days | 30–45 days | 20–30 days | Multi-symbol infrastructure designed |
| G6 Dashboard & Scale | 30–45 days | 22–35 days | 15–25 days | Operational records available |
| **TOTAL** | **183–270 days** | **138–208 days** | **99–148 days** | **All assumptions hold simultaneously** |

*Velocity assumption: one focused engineer, sequential implementation, no major rework. Parallel work between Research and G1 completion may reduce total by 10–20%. Owner decision latency not included.*

---

## Critical Path

```
R09 (Owner) → Issue #64 (live integration) → Issue #71 (archive)
    ↓
WP-R6 (holdout) → WP-R1 (backtest) → Strategy Batch-01
    ↓
G2 Secretariat → G2 Scanner
    ↓
G3 Momentum Trader → Paper Trading
    ↓
G4 OOS Validation → Strategy Promotion
```

**Shortest path to first paper trade:** ~100–140 days (optimistic-base) from G1 authorization.
