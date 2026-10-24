# ATLAS Quant Lab — Architecture Gaps & Risks
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## 1. Critical Gaps (Block Production Authorization)

### GAP-01: Live Integration Not Validated
- **Severity:** CRITICAL
- **Departments:** B, M
- **Description:** The entire G1 operational pipeline has only been tested with synthetic data and mock connections. No live Binance WebSocket or REST connection has been validated in production conditions.
- **Impact:** Unknown behavior under real network conditions — reconnects, rate limits, Binance API changes, WebSocket message format drift.
- **Evidence:** `operational_store.py` `SUPABASE_STATUS = "NOT_TESTED"`; Issue #64, #65 open.
- **Remediation:** Issue #64 (controlled non-production integration acceptance). Owner authorization required before live access.

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

### GAP-06: Research Lab Has Zero Implementation
- **Severity:** HIGH
- **Departments:** F
- **Description:** The Research Lab — the primary business-value-generating component — has no implemented code. All 22+ WP-R0 through WP-R40 issues are open.
- **Impact:** No backtesting, no strategy evaluation, no research reproducibility — the core purpose of the platform is not yet achievable.
- **Evidence:** Issues #17–#46 open; no research code in main.
- **Remediation:** Requires systematic WP-R0 through WP-R9 implementation (Batch-01).

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

### GAP-08: `manifest_integrity_hash` Wall-Clock Dependency
- **Severity:** MEDIUM-HIGH
- **Departments:** A, C
- **Description:** `manifest_integrity_hash` includes `created_at_ms` (wall-clock at validate_bars time). This means the hash is non-deterministic across `HistoricalLibrary` instances — two instances processing the same dataset will produce different hashes.
- **Impact:** Cannot use `manifest_integrity_hash` to verify reproducibility across processes or machines. Affects audit trail reliability.
- **Evidence:** `historical_library.py` docstring; `indicator_library.py` `computation_hash` note.
- **Remediation:** Document the constraint explicitly. Consider a `content_hash` (deterministic) alongside `manifest_integrity_hash` (instance fingerprint). See OD-01.

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
| R03 | Live data quality — gaps, duplicates, clock skew | HIGH | GAP RECOVERY implemented; not live-tested |
| R04 | Supabase capacity exhaustion | HIGH | NOT_TESTED — Issue #67 |
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
