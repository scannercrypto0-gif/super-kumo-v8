# ATLAS Quant Lab — Evidence Register
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## Label Key
- `[VERIFIED MAIN]` — Directly inspected in main @ `4e4c353`; code or docs present
- `[VERIFIED PR ONLY]` — Verified in a specific PR/SHA; confirm merged state before relying on it
- `[REPORTED]` — Reported by project owner or in issue/PR comments; not independently code-verified
- `[DOCUMENTED]` — Stated in architecture docs or docstrings; semantics not independently traced in code
- `[DESIGNED]` — Architecture documented; not yet in code
- `[NOT IMPLEMENTED]` — Feature/capability explicitly absent from current code
- `[NOT TESTED]` — Code exists but no live/production test performed
- `[UNKNOWN]` — Status not determinable from available evidence

---

## Architecture Documents

| Ref | File | Status | Notes |
|-----|------|--------|-------|
| E-01 | `01_CONTRACT.md` | `[VERIFIED MAIN]` | G0-PAPER, TIME, DATA, G1-ARCH-01–44 |
| E-02 | `02_ROADMAP.md` | `[VERIFIED MAIN]` | G0–G6 stage gates |
| E-03 | `03_DECISIONS.md` | `[VERIFIED MAIN]` | ADR history |
| E-04 | `04_STATE.md` | `[VERIFIED MAIN]` | Current state, outstanding gates |
| E-05 | `08_RISKS.md` | `[VERIFIED MAIN]` | R01–R10 risk register |
| E-06 | `10_TEST_POLICY.md` | `[VERIFIED MAIN]` | Test classification policy |

---

## Core Implementation Files

| Ref | File | HEAD SHA | Status | Notes |
|-----|------|---------|--------|-------|
| E-10 | `research_wp_r0/historical_library.py` | `4e4c353` | `[VERIFIED MAIN]` | 1,154 lines; `CustodyAccessor`, `DataAvailabilityKind` |
| E-11 | `research_wp_r0/indicator_library.py` | `4e4c353` | `[VERIFIED MAIN]` | SF-IND-01; SMA, EMA, RSI, ATR |
| E-12 | `research_wp_r0/indicator_library_v2.py` | `4e4c353` | `[VERIFIED MAIN]` | SF-IND-02; `VectorResult`, additive registry |
| E-13 | `research_wp_r0/strategy_definition.py` | `4e4c353` | `[VERIFIED MAIN]` | SF-STRAT-01; SHA-256 digest, canonical JSON |
| E-14 | `src/aql/pipeline.py` | `4e4c353` | `[VERIFIED MAIN]` | Full pipeline orchestration |
| E-15 | `src/aql/lanes.py` | `4e4c353` | `[VERIFIED MAIN]` | `BackgroundLane`, `JournalConsumer`, `WritePriority` |
| E-16 | `src/aql/storage/operational_store.py` | `4e4c353` | `[VERIFIED MAIN]` | `SUPABASE_STATUS = "NOT_TESTED"`, INSERT OR IGNORE |
| E-17 | `src/aql/journal/durable_journal.py` | `4e4c353` | `[DOCUMENTED]` | WAL journal — structure confirmed via pipeline imports and docs |
| E-18 | `src/aql/health/snapshot.py` | `4e4c353` | `[VERIFIED MAIN]` | `HealthSnapshot`; HEALTHY/DEGRADED/UNHEALTHY |
| E-19 | `src/aql/collector/binance_collector.py` | `4e4c353` | `[DOCUMENTED]` | WebSocket collector — referenced in pipeline imports |
| E-20 | `src/aql/recovery/gap_recovery.py` | `4e4c353` | `[DOCUMENTED]` | REST recovery — `RecoveryReport`, referenced in pipeline |
| E-21 | `research_wp_r0/_dep_guard.py` | `4e4c353` | `[VERIFIED MAIN]` | Dependency isolation guard — `_dep_guard.py` confirmed in research_wp_r0/ |

---

## Tests

| Ref | File | Count | Status | Notes |
|-----|------|-------|--------|-------|
| E-30 | `tests/test_sf_data_01.py` | ~200+ | `[VERIFIED MAIN]` | PIT correctness, CustodyAccessor; scope: synthetic only |
| E-31 | `tests/test_sf_ind_01.py` | ~100+ | `[VERIFIED MAIN]` | SF-IND-01 indicator accuracy; synthetic |
| E-32 | `tests/test_sf_ind_02.py` | ~100+ | `[VERIFIED MAIN]` | SF-IND-02 VectorResult, V2 indicators; synthetic |
| E-33 | `tests/test_sf_strat_01.py` | ~100+ | `[VERIFIED MAIN]` | SF-STRAT-01 strategy definitions; synthetic |
| E-34 | `tests/test_g1_wp01_*.py` | 129+ | `[VERIFIED MAIN]` | G1 WP01–WP04 pipeline tests; scope: G1 only |
| E-35 | CI run #40085463732 | success | `[VERIFIED MAIN]` | Branch `453a14d`; workflow: G1 WP01–WP04; synthetic scope only |
| E-36 | Local test report (owner) | 506 pass, 2 skip | `[REPORTED]` | Owner-local run; Windows Python 3.14.3; scope: full suite; not independently reproducible via CI |
| E-37 | CI run #40071051636 | success | `[REPORTED]` | Post-PR #62 merge Ubuntu/Windows/disposable PostgreSQL; referenced in Issue #64 |

---

## CI Evidence

| Ref | Workflow | Matrix | Status |
|-----|---------|--------|--------|
| E-40 | `.github/workflows/` | ubuntu-latest, windows-latest | `[VERIFIED MAIN]` — workflows exist |
| E-41 | CI run #40085840893 | in_progress (SF66 combined-main acceptance) | `[REPORTED]` — running at time of review; not yet complete |

---

## GitHub Issues

| Ref | Issue # | Title | Status | Verified? |
|-----|---------|-------|--------|-----------|
| E-50 | #1 | G0 Independent Review | Open | `[VERIFIED MAIN]` via API |
| E-51 | #17–#46 | WP-R0 through WP-R40 | Open | `[VERIFIED MAIN]` via API |
| E-52 | #64 | Controlled integration acceptance | Open — ACCEPTED WITH FOLLOW-UPS | `[REPORTED]` — bounded Binance PASS per owner comment |
| E-53 | #65 | Supabase sandbox acceptance | Open | `[VERIFIED MAIN]` via API |
| E-54 | #67 | Supabase capacity decision | Open — Option B OWNER APPROVED | `[REPORTED]` — per owner comment in Issue #67 |
| E-55 | #71 | Phase 1 local archive | Open — Phase 1 authorized, PR #73 Draft | `[VERIFIED MAIN]` via API |
| E-56 | #72 | Asset Intelligence Lab | Open — future backlog, architecturally under Strategy Factory | `[DOCUMENTED]` |

---

## Merged PRs (Post-G0)

| Ref | PR # | Title | Merged | Status |
|-----|------|-------|--------|--------|
| E-60 | #62 | BackgroundLane + JournalConsumer + WritePriority | Yes | `[VERIFIED MAIN]` — sha `ea9cf19a` → `4e4c353` |
| E-61 | #63 | `fix(ci): SF-IND-01 dep-guard all-aliases fix + Ubuntu+Windows matrix` | Yes @ `72a183c4` | `[VERIFIED MAIN]` — CI dep-guard fix; NOT pipeline integration; confirmed via GitHub API |
| E-62 | #68 | SF-IND-02 indicator_library_v2 | Yes @ `ea9cf19a` | `[VERIFIED MAIN]` — file confirmed in `research_wp_r0/` |
| E-63 | #69 | SF-STRAT-01 strategy_definition | Yes @ `4e4c353` | `[VERIFIED MAIN]` — file confirmed in `research_wp_r0/` |
| E-64 | #60 | (prior session merge approval) | Yes | `[OWNER STATED]` |

---

## Risk Items

| Ref | Risk | Source | Status |
|-----|------|--------|--------|
| E-70 | R09 V7 credential revocation | `08_RISKS.md` | `[DESIGNED]` — OWNER ACTION REQUIRED |
| E-71 | Binance bounded acceptance (Issue #64) | Issue #64 | `[REPORTED]` — ACCEPTED WITH FOLLOW-UPS; production NOT certified |
| E-72 | Holdout custody not implemented | Issue #24 | `[DESIGNED]` |
| E-73 | Supabase NOT_TESTED | `operational_store.py` | `[NOT TESTED]` |
| E-74 | WritePriority unused in pipeline | `lanes.py` | `[VERIFIED MAIN]` — class exists in `lanes.py`, not imported in `pipeline.py` |
