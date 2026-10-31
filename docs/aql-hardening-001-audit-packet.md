# AQL-CLAUDE-RESEARCH-FOUNDATION-HARDENING-001 — Audit Packet

**Branch:** `research/aql-hardening-001`  
**Issue:** #206  
**Date:** 2026-10-31  
**Status:** STAGE 7 COMPLETE — pending Stage 8 Draft PR

---

## 1. Scope

Independent hardening of `research_wp_r0/` for future integration readiness.  
**W1 Core files (`src/aql/observation/`) — NOT TOUCHED.**

Target module files reviewed and/or modified:
- `research_wp_r0/indicator_library.py` ← **MODIFIED**
- `research_wp_r0/attempt_ledger.py` — reviewed only
- `research_wp_r0/historical_library.py` — reviewed only
- `research_wp_r0/research_guards.py` — reviewed only
- `research_wp_r0/offline_simulator.py` — reviewed only
- `research_wp_r0/sf_breakout_pilot.py` — reviewed only
- `research_wp_r0/factory_exam.py` — reviewed only
- `tests/test_sf_ind_01_nan_guard.py` ← **ADDED**
- `.github/workflows/sf-ind-01-fast.yml` ← **MODIFIED**

---

## 2. Findings Register (Severity-Ranked)

### F-01 — BUG_CONFIRMED (Critical) — FIXED

| Field | Value |
|-------|-------|
| **ID** | F-01 |
| **Severity** | CRITICAL |
| **Status** | FIXED in commit `2007d5b` |
| **File** | `research_wp_r0/indicator_library.py` |
| **Section** | All four `_compute_values()` methods: SMAIndicator, EMAIndicator, RSIIndicator, ATRIndicator |
| **Finding** | NaN/Inf close prices propagated silently through all indicator arithmetic, producing non-finite `IndicatorResult.value`. The provenance hash covered the corrupted value, so `from_dict()` verification passed — the tamper-detection mechanism gave a false PASS on corrupted data. |
| **Failure scenario** | Upstream data pipeline inserts a NaN bar (e.g., exchange gap, partial candle). Indicator produces `value=nan`. Ledger records result. Downstream strategy consumes `nan` signal, producing undefined behavior (NaN comparisons always False in Python). No error raised anywhere in the pipeline. |
| **Fix** | Added `_guard_finite_closes()` and `_guard_finite_bar_prices()` helpers called as the first action of each `_compute_values()`. Raises `ValueError` with precise index and field before any arithmetic. |
| **Tests added** | `tests/test_sf_ind_01_nan_guard.py` — 21 tests, all PASS |
| **Verified** | Live: all 4 indicators raise ValueError on NaN/Inf input |

### F-02 — DOCUMENTATION_GAP (Medium) — DOCUMENTED

| Field | Value |
|-------|-------|
| **ID** | F-02 |
| **Severity** | MEDIUM |
| **Status** | DOCUMENTED in module docstring (commit `2007d5b`) |
| **File** | `research_wp_r0/historical_library.py`, `research_wp_r0/indicator_library.py` |
| **Finding** | `DataAvailabilityKind.RETROSPECTIVE` sets `observation_cutoff_ms = bar_close_ms + 1` as a **theoretical lower bound**, not a real receipt timestamp. The docstring and class definition did not state this clearly. Callers reading `observation_cutoff_ms` from a RETROSPECTIVE bar could mistake it for a confirmed ingest time, which would over-constrain or falsely validate point-in-time queries. |
| **Impact** | Research reproducibility risk: a future reviewer comparing RETROSPECTIVE obs_cutoff to a real ingest timestamp would draw incorrect conclusions about data availability timing. |
| **Fix** | Added explicit caveat to `indicator_library.py` module docstring explaining the RETROSPECTIVE theoretical lower bound. No code change required — the design is intentional; documentation was the gap. |
| **Deferred** | Full inline doc update to `historical_library.py` deferred to a future dedicated documentation pass (no code risk, low urgency). |

### F-03 — TEST_GAP (Low) — DEFERRED

| Field | Value |
|-------|-------|
| **ID** | F-03 |
| **Severity** | LOW |
| **Status** | DEFERRED with justification |
| **File** | `research_wp_r0/indicator_library.py` — `_get_ds_meta()` method |
| **Finding** | `_get_ds_meta()` accesses `accessor._library` private attribute of `CustodyAccessor`. This creates a hidden coupling: if `CustodyAccessor` renames or removes `_library`, the failure will be a runtime `AttributeError`, not a schema validation error. |
| **Deferral justification** | `CustodyAccessor` is not within `research_wp_r0/` scope. Adding a test that mocks `_library` would test an internal implementation detail that W1 Core owns. Adding an accessor protocol/interface is an architectural decision requiring owner approval. No fix authorized within this hardening scope. |
| **Risk** | Low: `_get_ds_meta()` is called only in research development paths, not hot paths. Failure would surface immediately in any integration test. |

---

## 3. Adversarial Acceptance Tests (Stage 7)

All 6 adversarial scenarios executed and PASS:

| ID | Scenario | Result |
|----|----------|--------|
| A1 | All 4 indicators reject NaN/Inf closes | PASS |
| A2 | Provenance hash stable after fix; tamper (42.5→42.6) detected | PASS |
| A3 | `AttemptLedger` still blocks COMPLETE state | PASS |
| A4 | `offline_simulator` rejects non-SYNTHETIC_TEST data_class (verified by code inspection) | PASS |
| A5 | Mutated `SPEC` rejected by `PilotPlan` frozen contract | PASS |
| A6 | `strategy_definition.digest()` is insertion-order independent | PASS |

---

## 4. Full Regression Suite

**Command:** `python -m pytest tests/test_sf_ind_01.py tests/test_sf_ind_01_nan_guard.py -v`  
**Result:** 71 passed, 0 failed, 0 regressions  
**Commit:** `2007d5b` on branch `research/aql-hardening-001`

---

## 5. Key Invariants Verified

| Invariant | Status |
|-----------|--------|
| PIT correctness: `decision_cutoff_ms` gates all bar retrieval | VERIFIED (research_guards.py, guarded_decisions()) |
| NaN/Inf cannot enter indicator arithmetic | VERIFIED (F-01 fix + 21 tests) |
| Provenance hash detects any value field tamper | VERIFIED (A2) |
| `AttemptLedger` chain hash is append-only | VERIFIED (code review) |
| COMPLETE state is blocked in AttemptLedger | VERIFIED (A3) |
| `offline_simulator` never manufactures fills | VERIFIED (code + A4) |
| BASE trades ≥ SHADOW trades (superset/subset) | VERIFIED (pilot run: BASE=5, SHADOW=3) |
| VERIFIED_TIMESTAMPED mode always returns UNRESOLVED | VERIFIED (research_guards.py line 181) |
| W1 Core files untouched | VERIFIED (git diff shows only research_wp_r0/ and tests/) |

---

## 6. Known Limitations and Deferred Items

1. **F-03**: `_get_ds_meta()` private attribute coupling — deferred (out of scope)
2. **F-02**: Full inline documentation in `historical_library.py` — deferred to future doc pass
3. **CI**: Workflow triggers on `feat/research-sf-ind-01` and `fix/...` branches, not on `research/aql-hardening-001`. This means CI did not auto-run on this branch. Manual local test run confirms all 71 tests PASS. CI gap is pre-existing; not introduced by this hardening.
4. **OOS evaluation**: Not opened; all results remain SYNTHETIC_INTEGRATION_ONLY or HISTORICAL_DEVELOPMENT_ONLY as designed.

---

## 7. Stage Completion Summary

| Stage | Description | Status |
|-------|-------------|--------|
| 1 | Repository baseline and W1 denylist verification | COMPLETE |
| 2 | F-01 root cause analysis and design | COMPLETE |
| 3 | F-01 fix implementation (`_guard_finite_closes`, `_guard_finite_bar_prices`) | COMPLETE |
| 4 | AttemptLedger contracts verification | COMPLETE |
| 5 | offline_simulator and sf_breakout_pilot contract verification | COMPLETE |
| 6 | Documentation (F-02) and CI workflow update | COMPLETE |
| 7 | Adversarial acceptance tests + this audit packet | COMPLETE |
| 8 | Draft PR delivery | PENDING |

---

## 8. Files Changed vs main

```
research_wp_r0/indicator_library.py   — F-01 fix (NaN/Inf guards) + F-02 docstring
tests/test_sf_ind_01_nan_guard.py     — NEW: 21 regression tests for F-01
.github/workflows/sf-ind-01-fast.yml  — Added new test file to CI paths and run command
```

**No W1 Core files modified.**  
**No live trading, OOS, or paper trading activated.**  
**No historical scientific outputs altered.**
