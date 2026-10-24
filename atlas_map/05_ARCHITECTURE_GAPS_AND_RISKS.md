# ATLAS Quant Lab — Architecture Gaps & Risks
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## 1. Critical Gaps (Block Production Authorization)

### GAP-01: Live Integration — Bounded Binance Accepted; Supabase and Production Not Validated
- **Severity:** HIGH (downgraded from CRITICAL — bounded Binance acceptance complete)
- **Departments:** B, M
- **Description:** Issue #64 bounded acceptance passed for Binance REST + WebSocket + disconnect/reconnect/gap recovery (disposition: **ACCEPTED WITH FOLLOW-UPS**, reported in Issue #64 comment by owner, 2026-10-24). This is NOT production certification. Supabase cloud path remains untested (`SUPABASE_STATUS = "NOT_TESTED"`). Full production readiness (multi-symbol, cloud storage, 24/7 uptime) is not yet validated.
- **Impact:** Binance public-endpoint behavior under bounded conditions is confirmed. Unknown behavior under sustained production conditions — prolonged uptime, rate-limit exhaustion, Supabase cloud writes, multi-symbol concurrency.
- **Evidence:** `[REPORTED — Issue #64 owner comment]` Binance bounded PASS; `[VERIFIED MAIN]` `operational_store.py` `SUPABASE_STATUS = "NOT_TESTED"`; Issue #64 open (follow-ups pending), Issue #65 open.
- **Remediation:** Issue #64 follow-up acceptance tasks (clock, Supabase, multi-symbol). Owner authorization required before live access.

### GAP-02: Holdout Custody Not Implemented
- **Severity:** CRITICAL
- **Departments:** F
- **Description:** The Research Lab has no holdout custody mechanism. Holdout data (unseen test set) is architecturally unprotected — a researcher could inadvertently access it during strategy development.
- **Impact:** All strategy evaluation results are potentially contaminated; no valid out-of-sample evidence.
- **Evidence:** WP-R6 (Issue #24) open; no `HoldoutCustody` code exists.
- **Remediation:** Implement WP-R6 before any strategy claims OOS validity.

### GAP-03: No Operational Store → Historical Library Pipeline
- **Severity:** HIGH
- **Departments:** A, B, M
- **Description:** Live market data collected by the G1 pipeline cannot be automatically fed to the Historical Library for research use. The two lanes are isolated but have no bridge.
- **Impact:** Researchers must manually import data; operational and research datasets can diverge.
- **Evidence:** `_dep_guard.py` enforces isolation; no automated bridge designed.
- **Remediation:** Issue #71 Phase 1 local archive work.

### GAP-04: R09 — V7 Credential Revocation Pending
- **Severity:** CRITICAL — OWNER ACTION REQUIRED
- **Departments:** L, M
- **Description:** Legacy V7 Binance API credentials must be explicitly revoked before any V7 code path is reused. This is not yet documented as complete.
- **Impact:** Security risk — stale API credentials remain valid.
- **Evidence:** `08_RISKS.md` R09; `04_STATE.md` Outstanding gates.
- **Remediation:** Owner must document V7 credential revocation and confirm in `04_STATE.md`.

---

## 2. High-Severity Gaps

### GAP-05: Supabase NOT_TESTED
- **Severity:** HIGH
- **Departments:** M
- **Description:** Supabase cloud storage path is completely untested. Capacity, write throughput, Free-tier limits, and connection reliability are all unknown.
- **Evidence:** `SUPABASE_STATUS = "NOT_TESTED"` in `operational_store.py`; Issue #67 open.
- **Remediation:** Issue #65 (Supabase sandbox acceptance), Issue #67 (capacity decision).

### GAP-06: Research Lab — Synthetic Foundations Merged; Integrated Operational Research Not Implemented
- **Severity:** HIGH (revised — isolated research foundations exist in main; not yet integrated or accepted)
- **Departments:** F
- **Description:** `research_wp_r0/` contains 5 merged Python modules in main (`4e4c353`): `historical_library.py`, `indicator_library.py`, `indicator_library_v2.py` (PR #68, merged `ea9cf19a`), `strategy_definition.py` (PR #69, merged `4e4c353`), `_dep_guard.py`. These are isolated research foundations — PIT-correct CustodyAccessor, typed Indicator Library V1+V2, Strategy Definition with SHA-256 provenance. They are NOT an integrated Research Lab with backtesting, holdout custody, or trial registry. WP-R6 (holdout), WP-R7 (trial journal), WP-R1 (backtest engine), and Strategy Batch-01 are not implemented.
- **Impact:** No backtesting, no out-of-sample validation, no holdout protection, no pre-registered trials — the end-to-end research workflow is not yet achievable. The core strategic gap remains.
- **Evidence:** `[VERIFIED MAIN @ 4e4c353]` — `research_wp_r0/*.py` present; PRs #68, #69 merged. `[NOT IMPLEMENTED]` — WP-R1, WP-R6, WP-R7, Batch-01; Issues #17–#46 open.
- **Remediation:** WP-R6 (holdout) is the critical prerequisite before any OOS claim. Then WP-R1 (backtest engine), WP-R7 (trial registry).

### GAP-07 (Issue #75): `WritePriority` Not Wired in Pipeline

- **Severity:** LOW (current scale) / MEDIUM (SC-03+ multi-symbol)
- **Departments:** B, M
- **Description:** `WritePriority` class exists in `src/aql/lanes.py` (lines 110–141) but is not imported or used in `pipeline.py`. The cooperative-yield mechanism for core vs. background SQLite writes is inactive.
- **Impact:** Under high concurrent write load, background `JournalConsumer` writes may delay core ingestion commits without the intended priority guard.
- **Evidence:** `lanes.py` line 110 — class defined; `pipeline.py` line 19 — `WritePriority` not in import list. `[VERIFIED]`
- **Remediation:** Wire when multi-symbol work (SC-03) begins. See OD-06.

---

### GAP-07b: Windows Production Performance Unverified
- **Severity:** HIGH
- **Departments:** B, M
- **Description:** CI runs on both Ubuntu and Windows, but production-level throughput on Windows is not benchmarked. Minimum 5 bars/s floor is synthetic only.
- **Evidence:** `04_STATE.md` Outstanding gates — Windows production throughput.
- **Remediation:** Dedicated Windows production throughput test.

### GAP-08: `manifest_integrity_hash` — Probable Wall-Clock Dependency (Hypothesis, Not Confirmed)
- **Severity:** MEDIUM (revised from MEDIUM-HIGH — pending independent code verification)
- **Departments:** A, C
- **Description:** Based on docstring evidence in `historical_library.py`, `manifest_integrity_hash` appears to include `created_at_ms` (wall-clock at validate_bars time), which would make it non-deterministic across `HistoricalLibrary` instances. This is inferred from documentation, not independently verified by tracing the hash computation code path.
- **Impact (if confirmed):** Cannot use `manifest_integrity_hash` to verify reproducibility across separate processes or machines. Affects cross-session audit trail.
- **Evidence:** `[DOCUMENTED — docstring in historical_library.py; NOT independently code-verified]` — hash semantics stated in documentation; `computation_hash` in `indicator_library.py` scoped to CustodyAccessor instance per docstring. Precise code semantics require independent verification before treating as confirmed defect.
- **Remediation:** Independent code trace of `manifest_integrity_hash` computation path (owner action). If confirmed non-deterministic: add `content_hash` (deterministic, SHA-256 of bar content only) without changing existing field. See OD-01.

---

## 3. Medium-Severity Gaps

### GAP-09: No Trial Registry
- **Severity:** MEDIUM
- **Departments:** F
- **Description:** No pre-registered trial journal exists. Researchers can run experiments without registering intent first, enabling HARKing (Hypothesizing After Results are Known).
- **Evidence:** WP-R7 (Issue #25) open.
- **Remediation:** Implement WP-R7 before any formal strategy evaluation claimed.

### GAP-10: No Monitoring / Dashboard
- **Severity:** MEDIUM
- **Departments:** K
- **Description:** No operational monitoring, health dashboard, or alerting system exists. Health snapshots are generated but only readable programmatically.
- **Evidence:** `02_ROADMAP.md` "Future requirement — unified monitoring dashboard deferred."
- **Remediation:** Deferred until operational records exist (G3+).

### GAP-11: No Multi-Symbol Production Scale Test
- **Severity:** MEDIUM
- **Departments:** B, M
- **Description:** All tests use single-symbol (BTCUSDT 1m) configuration. Multi-symbol, multi-interval production scale is untested.
- **Evidence:** `pipeline.py` single-symbol parameterization; no multi-symbol test.
- **Remediation:** Issue #64 integration acceptance to cover multi-symbol scenarios.

### GAP-12: Secretariat, Scanner, Traders — All Design Only
- **Severity:** MEDIUM
- **Departments:** G, H, I
- **Description:** Three major architectural components (G1-ARCH-01–44) have zero code. These represent the core trading workflow.
- **Evidence:** `01_CONTRACT.md` — all three documented as designs only.
- **Remediation:** Sequential implementation: Secretariat (G2) → Scanner (G2) → First Trader (G3).

---

## 4. R01–R10 Risk Register Mapping

| Risk ID | Description | Severity | Mitigation Status |
|---------|-------------|----------|-------------------|
| R01 | PIT leakage — future bars in research | CRITICAL | Mitigated by `decision_cutoff_ms`; not live-tested |
| R02 | DATA-07 violation — Secretariat making trade decisions | HIGH | Designed against; not yet implemented |
| R03 | Live data quality — gaps, duplicates, clock skew | HIGH | GAP RECOVERY implemented; bounded Binance acceptance PASS (Issue #64) |
| R04 | Supabase capacity exhaustion | HIGH | Architecture Option B owner-approved (Issue #67); Phase 1 #71 authorized; Supabase cloud NOT_TESTED |
| R05 | Holdout contamination | CRITICAL | Architecture designed; WP-R6 not implemented |
| R06 | Overfitting — no OOS validation | CRITICAL | Designed; not implemented |
| R07 | Strategy promotion without evidence | HIGH | Governance protocol designed; no enforcement code |
| R08 | Windows SQLite WAL performance | MEDIUM | Synthetic tests pass; production unverified |
| R09 | V7 legacy credential exposure | CRITICAL | Owner action REQUIRED |
| R10 | Binance API rate limit in recovery | MEDIUM | `MAX_SESSION_WEIGHT=1200` designed; not live-tested |

---

## 5. Conflicts Between Architecture Decisions

| Conflict | ADR References | Status |
|---------|---------------|--------|
| G1-ARCH-21 (Indicator Box) vs C Strategy Factory ownership | G1-ARCH-21–44 vs SF-IND-01/02 | UNRESOLVED — see OD-02 |
| E (Asset Intelligence Lab) vs J (Market Intelligence) boundary | Issue #72 vs design intent | UNRESOLVED — see OD-05 |
| TIME-01 fallback to completed candles policy | TIME-01 in `01_CONTRACT.md` | RESOLVED in design; not tested live |
| DATA-07 trader-owned exit vs Position Monitor responsibility | DATA-07 in `01_CONTRACT.md` | RESOLVED in design; not implemented |
