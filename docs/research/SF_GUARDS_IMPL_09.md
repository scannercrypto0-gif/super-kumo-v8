# SF-GUARDS-IMPL-09 - bounded DEVELOPMENT policy extension

Authority: [owner order on #121](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/121#issuecomment-6411168065). Base: merged #117, main3780de3943bb02aba8a00b689358af2108eebad9. Design reference only: [separate unmerged docs Draft #121 at41c5896](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/41c589647e0d9dca29581e0bdea75161907667bb/docs/research/SF_DEC_06_08_RESEARCH_GUARDS.md). That branch is not imported or stacked into this implementation.

## Narrow entry point

`ResearchGuardPlan` stores canonical immutable JSON bytes using accepted SF-STRAT-01 canonical/digest/keys helpers. `.spec` returns a copy. This is `sf-research-guards-1`, a separate EMA development policy; it does not change StrategyDefinition JSON V1, bind_evaluation, confirmed custody or their public hashes. It supports the already accepted EMA8/21 long-only replay, not a general strategy engine or AST replacement.

```python
from research_wp_r0.research_guards import ResearchGuardPlan, run_guarded_development
plan = ResearchGuardPlan(predeclared_definition)
# expected_plan_digest must have been independently retained before outcomes.
result = run_guarded_development(development_bars, plan=plan,
                                expected_plan_digest=expected_plan_digest,
                                evidence=retrospective_input_evidence)
```

The full definition pins strategy/indicator version, data and evidence digests, development split, interval, timing mode/guard/basis, per-input criticality/role/freshness/supporting fallback, both costs, capital and protective policy. No downloads or real-data experiment were performed. Caller cannot use a hash supplied alongside changed data as evidence of an earlier freeze; authenticity/date requires external retained evidence. Inputs are bounded to10000 supplied development bars and32 declared input names. No OOS rows are admitted by this entry point.

## SF-DEC-06: consume timing in accepted replay

`replay_ema_development` has optional `guard_plan`/`input_evidence`. With no guard plan, the accepted P0 behavior and exact serialized output remain unchanged (legacy optimistic zero-latency, not observed fills). Original frozen_ema_plan and artifacts are untouched. A pre-change synthetic golden hash and original published P0 plan hash are checked; the real P0 dataset is not rerun.

With the new plan, retrospective assumed availability is close+1ms; candidate is ceil_grid(availability+guard). Default guard=execution interval. Entry AND crossover exit use it. 1m close12:00:59.999 selects12:02:00;5m close12:04:59.999 selects12:10:00. Overrides require an explicitly pinned reviewed basis and are bounded to1000 intervals/24hours; the API does not authenticate owner approval or tune delays. A missing first candidate, intervening grid gap or development boundary is UNRESOLVED; no later favorable bar is selected. Indicators use only the contiguous observed prefix. Warmup and post-gap observations are BLOCKED, not fabricated HOLD. Coverage gaps make terminal valuation/benchmark unknown and drawdown partial.

`VERIFIED_TIMESTAMPED` is an explicit FAIL-CLOSED CONTRACT ONLY. It returns UNRESOLVED / VERIFIED_RECEIPT_READY_BINDING_NOT_IMPLEMENTED, no scenarios or PnL, even if caller claims timestamps. An independently verified consumer-availability/decision-ready binding and causal execution-evidence contract are not available here. No synthetic timestamps, automatic fallback, exchange order or verified fill is manufactured. Every new replay opportunity labels actual readiness/submission unknown and fills NOT_OBSERVED.

## SF-DEC-07: two scenarios, one opportunity population

The orchestration calls the SAME accepted replay twice, using shared #108 `account_long_prices`: BASE fee10/slip5bps and STRESS fee20/slip10bps per side. Both are always emitted. Same data, evidence, strategy signals, eligible times, capital100000USDT, qty1BTC, no leverage/reinvestment, crossover exits and terminal-mark rules. No model selection.

Capital eligibility in BOTH scenarios uses the predeclared conservative STRESS cash envelope. This avoids a cost-dependent subset (BASE might otherwise afford entries that STRESS cannot). Actual cash/PnL is still charged at each scenario's own costs. The paired signature checks all opportunities, outcomes and snapshot digests; divergence raises rather than cherry-picking. Baseline buy/hold uses the same first eligible window/one-BTC notional and each scenario's costs. Terminal marks are separate from realized closes. No stop/target or observed TTL/order-fill semantics added.

## SF-DEC-08: essentials, supporting audit and protection boundary

Per-strategy immutable inputs include ESSENTIAL candles/EMA8/EMA21; their values are computed by the accepted code, never replaced by caller evidence. State overrides can invalidate them. Missing/stale/nonfinal/invalid/warmup essentials produce BLOCKED_MISSING_REQUIRED_DATA, signal=None, reasons and hash-bound snapshot. A required missing candle taints later derived EMA history; the implementation cannot silently resume with that unavailable candle.

Supporting fields support exactly AUDIT_ONLY with explicit BASE_SIGNAL_WITH_UNKNOWN_CONTEXT fallback. If missing/stale/future, value=UNKNOWN and SUPPORTING_DATA_MISSING; otherwise they are recorded without overriding base entry/exit. Weighting/ranking/confidence/sizing changes are NOT implemented. A hard veto, risk, liquidity or safety gate cannot be labeled supporting. Extra mandatory gate inputs require explicit boolean True, otherwise block. Evidence timestamps are retrospective as-of assertions, not confirmed receipt or PIT custody. Invalid data never becomes neutral/zero/favorable.

**Open-position protection gate remains OPEN.** On essential loss while a hypothetical position is held/reserved, new decisions stop, exposure remains UNRESOLVED_PROTECTION_REQUIRED, and terminal valuation is UNKNOWN; no invented protective exit or price. Subsequent price marks are not treated as trusted; only prior drawdown is reported as partial. This is an explicit fail-closed limit, NOT a protective trading engine. Owner must separately approve a protective position/evidence protocol before any future real experiment requiring that capability. Missing entry evidence never silently converts an existing position into flat or disables the disclosed protection requirement.

## Acceptance map and limits

24 focused synthetic cases cover:1m/5m/1h timing, pinned override/ceil boundary, verified missing evidence, candidate/intervening gap, split boundary, paired notional costs and common capital, stale/nonfinal/invalid/missing essential, supporting missing/conflicting data with explicit fallback, all mandatory-gate classifications, tainted EMA history, short warmup, protection unresolved, mismatched plan/data/evidence, immutable copy, and legacy synthetic/P0 plan hashes. Existing31+41 boundary JUnit gates and464-contract gate remain unchanged; focused guards add a separate24-case no-skip gate on Ubuntu/Windows Python3.10/3.11/3.12. Proposed #121 cases beyond these are not claimed tested: actual verified receipt/clock ties, tick/sub-grid/real fills, a full protective policy, generic supporting weights and live routing remain unsupported/gated.

G0-GOV-01: original owner P0 handoff and REVIEW-02/CLOSEOUT-03/TIMING-REVIEW-04/GATE-05 reconciled with posted independent-session receipt6410682200, owner-attested session separation6410744392 and verified #117 merge. Machine receipt independence fields remain unchanged; no independent human/custody claim. Accessible Factory Manager messages confirm essential vs supporting semantics, direct documentation approval and latest consolidated implementation request. Content-reference-only replies, omitted files and the external Work session itself were not directly reviewed. The current implementation order authorizes code despite older documentation-only/no-implementation orders; it does not authorize merging either PR.

No #46 imports; no Core/G1/Scanner/Secretariat/realtime feeds, journal/DB/framework, actual market backtest, profitability/OOS/holdout/COMPLETE claim, promotion, trading, main write or merge. #77/#120 stay open/blocked. One next owner decision: review this bounded implementation together with separate docs Draft #121, retaining the explicit verified-timing/protective-position gates; merging either requires explicit separate authorization.
