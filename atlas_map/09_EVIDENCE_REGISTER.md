# ATLAS Quant Lab — Evidence Register
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## Label Key
- `[VERIFIED]` — Directly inspected in repository at HEAD `4e4c353`
- `[INFERRED]` — Concluded from verified evidence without direct inspection
- `[DESIGNED]` — Documented in architecture docs; not yet in code
- `[NOT TESTED]` — Exists in code but no live/production test performed
- `[OWNER STATED]` — Reported by project owner; not independently verified

---

## Architecture Documents

| Ref | File | Status | Notes |
|-----|------|--------|-------|
| E-01 | `01_CONTRACT.md` | `[VERIFIED]` | G0-PAPER, TIME, DATA, G1-ARCH-01–44 |
| E-02 | `02_ROADMAP.md` | `[VERIFIED]` | G0–G6 stage gates |
| E-03 | `03_DECISIONS.md` | `[VERIFIED]` | ADR history |
| E-04 | `04_STATE.md` | `[VERIFIED]` | Current state, outstanding gates |
| E-05 | `08_RISKS.md` | `[VERIFIED]` | R01–R10 risk register |
| E-06 | `10_TEST_POLICY.md` | `[VERIFIED]` | Test classification policy |

---

## Core Implementation Files

| Ref | File | HEAD SHA | Status | Notes |
|-----|------|---------|--------|-------|
| E-10 | `research_wp_r0/historical_library.py` | `4e4c353` | `[VERIFIED]` | 1,154 lines; `CustodyAccessor`, `DataAvailabilityKind` |
| E-11 | `research_wp_r0/indicator_library.py` | `4e4c353` | `[VERIFIED]` | SF-IND-01; SMA, EMA, RSI, ATR |
| E-12 | `research_wp_r0/indicator_library_v2.py` | `4e4c353` | `[VERIFIED]` | SF-IND-02; `VectorResult`, additive registry |
| E-13 | `research_wp_r0/strategy_definition.py` | `4e4c353` | `[VERIFIED]` | SF-STRAT-01; SHA-256 digest, canonical JSON |
| E-14 | `src/aql/pipeline.py` | `4e4c353` | `[VERIFIED]` | Full pipeline orchestration |
| E-15 | `src/aql/lanes.py` | `4e4c353` | `[VERIFIED]` | `BackgroundLane`, `JournalConsumer`, `WritePriority` |
| E-16 | `src/aql/storage/operational_store.py` | `4e4c353` | `[VERIFIED]` | `SUPABASE_STATUS = "NOT_TESTED"`, INSERT OR IGNORE |
| E-17 | `src/aql/journal/durable_journal.py` | `4e4c353` | `[INFERRED]` | WAL journal — structure seen via pipeline imports |
| E-18 | `src/aql/health/snapshot.py` | `4e4c353` | `[VERIFIED]` | `HealthSnapshot`; HEALTHY/DEGRADED/UNHEALTHY |
| E-19 | `src/aql/collector/binance_collector.py` | `4e4c353` | `[INFERRED]` | WebSocket collector — referenced in pipeline |
| E-20 | `src/aql/recovery/gap_recovery.py` | `4e4c353` | `[INFERRED]` | REST recovery — `RecoveryReport` |
| E-21 | `research_wp_r0/_dep_guard.py` | `4e4c353` | `[INFERRED]` | Dependency isolation guard |

---

## Tests

| Ref | File | Count | Status | Notes |
|-----|------|-------|--------|-------|
| E-30 | `tests/test_sf_data_01.py` | ~200+ | `[VERIFIED]` | PIT correctness, CustodyAccessor |
| E-31 | `tests/test_sf_ind_01.py` | ~100+ | `[VERIFIED]` | SF-IND-01 indicator accuracy |
| E-32 | `tests/test_sf_ind_02.py` | ~100+ | `[VERIFIED]` | SF-IND-02 VectorResult, V2 indicators |
| E-33 | `tests/test_sf_strat_01.py` | ~100+ | `[VERIFIED]` | SF-STRAT-01 strategy definitions |
| E-34 | `tests/test_g1_wp01_*.py` | 129+ | `[VERIFIED]` | G1 WP01–WP04 pipeline tests |
| E-35 | Test run output | 506 pass, 2 skip | `[VERIFIED]` | `pytest -x` executed at HEAD `4e4c353` |

---

## CI Evidence

| Ref | Workflow | Matrix | Status |
|-----|---------|--------|--------|
| E-40 | `.github/workflows/` | ubuntu-latest, windows-latest | `[VERIFIED]` — workflows exist |
| E-41 | Last CI run | Unknown — gh auth failed | `[NOT TESTED]` — unauthenticated API used |

---

## GitHub Issues

| Ref | Issue # | Title | Status | Verified? |
|-----|---------|-------|--------|-----------|
| E-50 | #1 | G0 Independent Review | Open | `[VERIFIED]` via API |
| E-51 | #17–#46 | WP-R0 through WP-R40 | Open | `[VERIFIED]` via API |
| E-52 | #64 | Controlled integration acceptance | Open | `[VERIFIED]` via API |
| E-53 | #65 | Supabase sandbox acceptance | Open | `[VERIFIED]` via API |
| E-54 | #67 | Supabase capacity decision | Open | `[VERIFIED]` via API |
| E-55 | #71 | Phase 1 local archive | Open | `[VERIFIED]` via API |
| E-56 | #72 | Asset Intelligence Lab | Open | `[VERIFIED]` via API |

---

## Merged PRs (Post-G0)

| Ref | PR # | Title | Merged | Status |
|-----|------|-------|--------|--------|
| E-60 | #62 | BackgroundLane + JournalConsumer + WritePriority | Yes | `[VERIFIED]` — `lanes.py` in main |
| E-61 | #63 | Pipeline integration of lanes | Yes | `[VERIFIED]` — `pipeline.py` imports lanes |
| E-62 | #68 | SF-IND-02 indicator_library_v2 | Yes | `[VERIFIED]` — file in main |
| E-63 | #69 | SF-STRAT-01 strategy_definition | Yes | `[VERIFIED]` — file in main |
| E-64 | #60 | (prior session merge approval) | Yes | `[OWNER STATED]` |

---

## Risk Items

| Ref | Risk | Source | Status |
|-----|------|--------|--------|
| E-70 | R09 V7 credential revocation | `08_RISKS.md` | `[DESIGNED]` — OWNER ACTION REQUIRED |
| E-71 | Live Binance integration untested | Issue #64 | `[NOT TESTED]` |
| E-72 | Holdout custody not implemented | Issue #24 | `[DESIGNED]` |
| E-73 | Supabase NOT_TESTED | `operational_store.py` | `[NOT TESTED]` |
| E-74 | WritePriority unused in pipeline | `lanes.py` | `[VERIFIED]` — class exists, not wired |
