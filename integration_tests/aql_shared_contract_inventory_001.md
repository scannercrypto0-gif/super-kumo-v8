# AQL-SHARED-CONTRACT-INVENTORY-001
**Inventory ID:** AQL-SHARED-CONTRACT-INVENTORY-001  
**Generated:** 2026-11-01T00:00:00Z (DECISION_CUTOFF_MS=1762041600000)  
**Branch coverage:** main + PRs #118, #119, #208, #209, #211, #213, #214, #216 + G2 drafts  
**Status labels:** MAIN_PRESENT / DRAFT_TESTED / DESIGN_ONLY / NOT_FOUND / BLOCKED_EXTERNAL_EVIDENCE

---

## (a) Capability Matrix

| CAP_ID | Name | File | Branch/PR | Status | Missing Seam |
|--------|------|------|-----------|--------|--------------|
| G1-INGEST-01 | Binance WebSocket 15m bar collector | `src/aql/collector/binance_collector.py` | main | MAIN_PRESENT | No live integration test; no independent source clock attestation |
| G1-LANE-01 | BackgroundLane daemon worker | `src/aql/lanes.py` | main | MAIN_PRESENT | No capacity overflow or crash-recovery test |
| G1-PIPE-01 | G1 pipeline orchestrator | `src/aql/pipeline.py` | main | MAIN_PRESENT | Gap-recovery sequence untested; DurableJournal/OperationalStore not verified E2E |
| G2-REGIME-01 | G2 regime taxonomy — 8 CONTEXT_KEYS + DecisionSnapshot | `src/aql/observation/contracts.py` | main | MAIN_PRESENT | No live regime signal producer wired |
| G2-POS-01 | G2 paper position lifecycle | `src/aql/observation/positions.py` | main | MAIN_PRESENT | PositionLedger volatile; requires DurablePositionJournal |
| G2-JOURNAL-01 | G2 DurablePositionJournal | `src/aql/observation/position_journal.py` | main | MAIN_PRESENT | No crash/restart or disk-full recovery test |
| G2-WORKER-01 | G2 ObservationWorker (bounded queue, fail-closed) | `src/aql/observation/worker.py` | PR#118 DRAFT | DRAFT_TESTED | Volatile admission; no retry for rejected events |
| G2-SOURCE-01 | G2 RetainedObservationSource | `src/aql/observation/retained_source.py` | PR#119 DRAFT | DRAFT_TESTED | FULL = hard admission failure; no live G2→G1 wiring |
| SF-STRAT-01 | Factory StrategyDefinition | `research_wp_r0/strategy_definition.py` | main | MAIN_PRESENT | None |
| SF-IND-02 | Factory IndicatorRegistryV2 + VectorResult | `research_wp_r0/indicator_library_v2.py` | main | MAIN_PRESENT | partial_coverage flag not validated downstream |
| SF-SYNTH-01 | Factory synthetic opportunities | `research_wp_r0/synthetic_opportunities.py` | main | MAIN_PRESENT | CONTROLLED_ONLY; independent_custody_verified=False always |
| SF-BREAKOUT-01 | SF-BREAKOUT-PILOT-01 BASE/SHADOW synthetic | `research_wp_r0/sf_breakout_pilot.py` | main | MAIN_PRESENT | Live market data seam NOT wired |
| SF-DNA-02 | Factory StrategyDNA V2 | `research_wp_r0/strategy_dna_v2.py` | main | MAIN_PRESENT | SYNTHETIC_ONLY; no G2 regime input to role evaluator |
| SF-FILL-01 | Synthetic fill model (account_long_prices) | `research_wp_r0/synthetic_execution.py` | main | MAIN_PRESENT | TTL=1 only; ambiguous fills UNRESOLVED |
| SF-LEDGER-01 | Factory AttemptLedger (SQLite, chain hash) | `research_wp_r0/attempt_ledger.py` | main | MAIN_PRESENT | SQLite WAL not power-loss certified |
| SF-PLAN-01 | Factory FrozenResearchPlan | `research_wp_r0/frozen_research_plan.py` | main | MAIN_PRESENT | Commitment ≠ trusted custody receipt |
| SF-SIM-01 | Factory OfflineSimulator (synthetic only) | `research_wp_r0/offline_simulator.py` | main | MAIN_PRESENT | Historical eval not admitted (SYNTHETIC_TEST only) |
| W1-BRIDGE-01 | Factory W1 RawParentBridge | `research_wp_r0/aql_w1_raw_parent_bridge.py` | PR#209 DRAFT | DRAFT_TESTED | **BLOCKED-1** (real P0 ZIP); **BLOCKED-2** (publication clock) |
| W1-ADAPT-01 | Factory W1 MarketWindowAdapter | `research_wp_r0/aql_w1_market_window_adapter.py` | PR#209 DRAFT | DRAFT_TESTED | External custody verifier required |
| W1-CONSUMER-01 | Factory W1 ResearchConsumer (RETROSPECTIVE_NON_PIT) | `research_wp_r0/aql_w1_factory_research_consumer.py` | PR#209 DRAFT | DRAFT_TESTED | RETROSPECTIVE_NON_PIT ≠ genuine PIT; no live F1 connection |
| W1-OUTCOMES-01 | Factory W1 OpportunityOutcomes (RetrospectiveSnapshot) | `research_wp_r0/aql_w1_opportunity_outcomes.py` | PR#209 DRAFT | DRAFT_TESTED | Outcomes require post-decision RAW bars; BLOCKED_EXTERNAL_EVIDENCE for real source |
| P0-CUSTODY-01 | P0 native Binance 15m custody (verify_native_bundle) | `research_wp_r0/aql_p0_c1_custody.py` | PR#209 DRAFT | BLOCKED_EXTERNAL_EVIDENCE | **BLOCKED-1**: Real P0 ZIP must be supplied by owner |
| P0-LEDGER-01 | P0 F4 financial ledger (idempotent replay) | `research_wp_r0/aql_p0_f4_ledger.py` | PR#209 DRAFT | DRAFT_TESTED | Full denominator required; OPEN_UNRESOLVED ≠ settled PnL |
| VAULT-01 | Raw Vault offline toolkit | `tools/raw_vault_offline/` | PR#211 DRAFT | DRAFT_TESTED | B3 bounded seam only; BLOCKED-1/BLOCKED-2 |
| CORE-F1-01 | Core F1 DecisionCapture V1 | `research_wp_r0/aql_f1_decision_capture_v1.py` | PR#216 DRAFT | DRAFT_TESTED | No trusted clock minted; IMMUTABLE_HANDOFF_CONFLICT on changed evidence |
| CORE-F1-02 | Core F1 ProspectiveHost V1 | `research_wp_r0/aql_f1_prospective_host_v1.py` | PR#216 DRAFT | DRAFT_TESTED | fcntl Linux-only; no external freeze authority |
| CORE-F1-03 | Core F1 SignalHandoff V1 (2×N rows) | `research_wp_r0/aql_f1_research_signal_handoff_v1.py` | PR#216 DRAFT | DRAFT_TESTED | **BLOCKED-2**: independent_proof_verifier must be externally trusted |
| INTEL-01 | Intel DAG (collision detection, review order) | `tools/integration_intel_offline/dag.py` | PR#213 DRAFT | DRAFT_TESTED | Candidate review order only; NOT merge decision |
| REPRO-01 | Dev-Repro V2 cross-PR harness | `integration_tests/option_b_v2_cross_pr_harness.py` | PR#214 DRAFT | DRAFT_TESTED | 22P/0F/2B; B3 bounded only; CI-GAP |
| REGIME-ROUTE-01 | Regime → strategy routing (live dispatch) | **NOT_FOUND** | — | NOT_FOUND | **Critical gap**: no routing module exists |
| OUTCOME-LIVE-01 | 4/24/72h live outcome measurement | **NOT_FOUND** | — | NOT_FOUND | Requires live RAW vault + post-decision bars |
| PAPER-PERF-01 | Paper trader performance aggregator | **NOT_FOUND** | — | NOT_FOUND | DESIGN_ONLY; no live equity/drawdown tracker |

---

## (b) Field-Level Mapping

```
SOURCE LAYER (G1 Binance WebSocket → raw_object.v1)
  bar fields: {open_ms:int, high:str, low:str, finalized_at_ms:int, published_at_ms:int}
  no floats; canonical Decimal strings; schema_version="raw_object.v1"
  correction_generation: required in manifest
  availability_clock: published_at_ms (exchange); independent receipt = BLOCKED_EXTERNAL_EVIDENCE
  live status: MAIN_PRESENT; independent custody = NOT_VERIFIED
        ↓
FEATURE LAYER (IndicatorRegistryV2 → VectorResult)
  provenance_hash per vector; decision_cutoff_ms=1762041600000
  bar_open_ms aligned to BAR_MS=900000; warmup_bars per indicator
  partial_coverage flag (not validated downstream)
  status: MAIN_PRESENT
        ↓
REGIME LAYER (G2 contracts.py → DecisionSnapshot)
  8 CONTEXT_KEYS (all required): btc_eth, btc_dominance, btc_trend, altseason,
    breadth, liquidity, volatility, relative_strength
  HORIZONS_MS: (14400000, 86400000, 259200000)
  DISPOSITIONS: observed/rejected/expired/no_fill
  live producer: NOT_FOUND ← CRITICAL GAP
        ↓
STRATEGY LAYER (StrategyDefinition.digest() + StrategyDNA V2)
  pair_id = digest({experiment_plan_sha256, c2_identity})
  evaluation: SYNTHETIC_ONLY in main; P0 retrospective in draft PRs
  breakout params: ENTRY_LOOKBACK=20, EXIT_LOOKBACK=10, TTL=1
  status: MAIN_PRESENT (synthetic); DRAFT_TESTED (P0 retrospective)
        ↓
OPPORTUNITY LAYER (C2 DecisionEnvelope → F1 ProspectiveHost)
  c2_fields: {trial_id, opportunity_id, producer_event_id, envelope_sha256}
  denominator: FULL — NO_SIGNAL + BLOCKED + UNKNOWN all included
  F1 states: NO_SIGNAL, WATCH, ARMED, EXPIRED, UNKNOWN, BLOCKED
  status: DRAFT_TESTED (PR#216 + PR#209)
        ↓
BASE/SHADOW ARMS (F1 SignalHandoff → 2×N rows)
  arm journals: base.jsonl / shadow.jsonl (fcntl exclusive lock, Linux only)
  IMMUTABLE_HANDOFF_CONFLICT on changed evidence
  independent_proof_verifier required for RECORDED status
  status: DRAFT_TESTED (PR#216); BLOCKED-2 for real proof
        ↓
4/24/72h OUTCOMES (W1 OpportunityOutcomes → P0 F4 Ledger)
  fill model: account_long_prices(entry_open, exit_open, fee_bps, slippage_bps)
  ambiguous fills: UNRESOLVED — never scored win/loss
  denominator: settled_equity=None if held_btc>0
  OPEN_UNRESOLVED → open_exposure ONLY (not settled PnL)
  live outcome: NOT_FOUND; retrospective: DRAFT_TESTED (PR#209)
        ↓
PAPER COST/RISK (P0 F4 Ledger — research offline only)
  INITIAL_CASH defined; POSITION_SIZE_BTC per fill
  cost_basis conservation: entry debit must match exit credit
  paper performance aggregator: NOT_FOUND (live tracker missing)
```

---

## (c) PR Collision / Dependency Matrix

| PR | Owner | Depends On | Blocks | Risk |
|----|-------|-----------|--------|------|
| #211 | Core/Vault | — | #209, #214, #216 | raw_object.v1 schema consumed by PR#209 bridge and PR#216 host |
| #209 | Factory/W1 | #211 | #214, #216 | W1 bridge → Vault schema; RetrospectiveSnapshot consumed by PR#216 |
| #216 | Core/F1 | #211, #209 | #214 | F1 host uses factory bridge; handoff produces Factory-shaped inputs |
| #214 | DevRepro/QA | #211, #209, #216 | — | Harness SHA pins go stale if upstream PRs advance |
| #213 | Intel/QA | — | — | Independent; no ownership conflict |
| #208 | Docs/Governance | — | — | Documentation only |
| #118 | Core/G2 | — | #119 | Adds observation/worker.py; must NOT import G1 synchronously |
| #119 | Core/G2 | #118 | — | retained_source.py reuses DurablePositionJournal exclusive writer; shared lock critical |

**Merge sequence required:** 211 → 209 → 216 → 214

---

## (d) Ranked Gaps + Recommended First Vertical Slice

| Rank | Gap | Severity | Owner Action |
|------|-----|----------|-------------|
| 1 | BLOCKED-1: Real P0 ZIP not supplied | **BLOCKER** | Owner supplies BTCUSDT-15m-2024-01-01 ZIP |
| 2 | BLOCKED-2: Independent publication clock / issuer custody missing | **BLOCKER** | Owner provides trusted external receipt service or defers all PIT claims |
| 3 | REGIME-ROUTE-01: No live regime signal producer for 8 CONTEXT_KEYS | **CRITICAL** | Authorize design + impl of regime signal producer |
| 4 | CI-GAP: Combined overlay CI workflow does not exist | **HIGH** | Owner authorizes .github/workflows/overlay-ci.yml |
| 5 | OUTCOME-LIVE-01: No live 4/24/72h outcome measurement module | **HIGH** | Design live outcome collection wired to G1 RAW vault |
| 6 | PAPER-PERF-01: No live paper performance aggregator | **HIGH** | Design live tracker consuming G2 PositionLedger |
| 7 | PRs #209/#211/#216 unmerged — capability chain draft-only | **MEDIUM** | Owner authorizes merge sequence 211→209→216 |
| 8 | G2 worker (#118) + retained source (#119) unmerged | **MEDIUM** | Authorize G2 worker merge + G1 integration wiring |

### Recommended First Genuine Strategy Vertical Slice

**Name:** SF-BREAKOUT-PILOT-01 retrospective on synthetic dataset → W1 outcomes → F4 ledger  
**Does NOT require BLOCKED-1 or BLOCKED-2.**

**Steps:**
1. SF-BREAKOUT-PILOT-01 BASE+SHADOW on IndicatorRegistryV2 synthetic bars (MAIN_PRESENT)
2. F1 ProspectiveHost capture → SignalHandoff — 2×N rows (PR#216, after merge)
3. W1 OpportunityOutcomes with synthetic RAW windows — HORIZONS (PR#209, after merge)
4. P0 F4 Ledger idempotent replay — full denominator, cost basis conservation (PR#209, after merge)
5. DevRepro V2 harness re-verification after merge (PR#214)

**Preconditions:** PRs #211→#209→#216 merged; synthetic RAW fixture supplied  
**Deliverable:** First complete 4/24/72h outcome row: strategy_digest + opportunity_id + arm + horizon_ms + gross_return + fee_fraction + net_return + denominator count — fully reproducible digest  
**PIT deferred:** Real P0 ZIP and external custody deferred to BLOCKED-1/BLOCKED-2 resolution

---

## Persistent Blockers (unchanged)

| ID | Description | Required Input |
|----|-------------|---------------|
| BLOCKED-1 | Real P0 ZIP not supplied | Owner supplies BTCUSDT-15m-2024-01-01_to_2024-01-08 ZIP |
| BLOCKED-2 | Independent publication clock / issuer custody | Owner provides trusted external receipt service |
| CI-GAP | Combined overlay CI workflow does not exist | Owner authorizes .github/workflows/overlay-ci.yml |

---

*Package 1/3 — AQL-SHARED-CONTRACT-INVENTORY-001*  
*Claude read-only inventory: no code edits to Core/Factory/G1/G2, no branch merge, no new PR, no runtime/trading, no invented data*  
*Evidence labels: MAIN_PRESENT = verified in main HEAD; DRAFT_TESTED = in PR (B3 bounded); NOT_FOUND = not in any branch; BLOCKED_EXTERNAL_EVIDENCE = requires owner/operator supply*
