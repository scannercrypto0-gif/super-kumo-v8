# Risk register
R01 scope creep: freeze scope per WP, ADR and gates (CRITICAL).
R02 future leakage from candles/news/regimes: point-in-time tests (CRITICAL).
R03 in-sample overfit: preregister, purged time splits, forward shadow (CRITICAL).
R04 Binance rate limits: cache, weight budgets, adaptive priority (HIGH).
R05 Supabase growth/outage: measure costs, local spool, recovery (HIGH).
R06 event licensing/coverage: source provenance, rights checks (HIGH).
R07 optimistic paper fills: conservative explicit model, ambiguity (CRITICAL).
R08 correlated observations: grouping and effective sample size (HIGH).
R09 exposed token in legacy code: rotate, environment secrets (CRITICAL).
R10 PC power/network failure: durable queue and idempotency (HIGH).

## Provisional paper-decision risk follow-up

These are residual risks under [G0-PAPER-01–08](03_DECISIONS.md#g0-paper-trading-decisions--owner-selected-provisional-rules), not resolved-risk claims.
- R07/R02: unknown within-bar order and later-discovered data can overstate execution or leak future information. Preserve factual AMBIGUOUS, legitimate finer-data provenance and aggregate best/worst bounds; isolate cost stress from order uncertainty.
- R07/R04: fee tiers/promotions/effective dates, spread/slippage and notional liquidity may be unavailable historically. Version sources and assumptions, flag missing evidence, compare reference/sensitivity notionals and never assume perfect fills.
- R08/R03: same-symbol opportunities and outcome overlap inflate effective sample size; counterfactual stopping/exit selection can introduce hindsight bias. Report correlation and preregister isolated paired variants/horizons; no anecdotal promotion.
- R10/R05: outage recovery can miss order, duplicate fills/closes/alerts or overwrite history. Persist versioned progress/idempotency evidence, replay chronologically, retain correction audit trail and UNRESOLVED_DATA_GAP exclusions.
- R01: provisional 1,000 USDT research notional and illustrative future capital numbers must not become live-trading authorization, funded-capital claims or approved portfolio risk policy.

## TIME/DATA residual risks — provisional, not resolved
See [13 decisions and owner overrides](03_DECISIONS.md#g0-time-and-data-provisional-decisions).
- R02 (TIME-01–03/07): event-before-decision but late receipt, unverified intra-candle availability, publication-only news or edited archives can leak future knowledge. Preserve all clocks/content versions and conservative replay class; immutable context must cover rejected/expired/no-fill opportunities too. Later position context appends rather than replaces original.
- R03 (TIME-04–07, owner A/F): corrected datasets/code, repeated holdout tuning, correlated temporal labels and hindsight regimes bias evidence. Version/correction lineage and purged chronological splits; separate historical-development/OOS/forward reports, no combined score. Specialist target/off-target counts, net costs, drawdown/risk, uncertainty and sample adequacy prevent global winner/loser or insufficient-evidence profitability claims.
- R02/R03/R08 (TIME-05–08): regime shifts/detector lag/errors, cost/quality changes and overfit may explain historical/forward divergence. Independently validate real-time regime detectability; require predeclared forward eligibility; isolate transition-exit alternatives from original paper trades.
- R04 (TIME-09, DATA-01/02): source-specific stale/missing context and duplicate rich-snapshot requests can starve monitoring. Provider/local-method inventory, freshness/essentiality rules, shared cache/planned dedup and actual endpoint-specific budgets; no fake freshness.
- R05/R06 (DATA-02/03, owner C/E): unavailable/unsupported indicators/news archives, rights/quality gaps and unverified “complete” coverage. Maintain explicit scoped inventory, phase/progress/version/validation; initial pre-operational backfill separate from core, incremental repairs use same library. Coverage breadth remains economically feasible, not universal.
- R05/R01 (DATA-03/04): storage/transfer/compute/provider growth can silently create cost. Minimize avoidable duplication/selective reads, monitor explicit budgets; owner approval before ANY new paid source, storage upgrade, compute or chargeable service. Zero cost is not guaranteed.
- R10/R04/R05 (DATA-01/02/04, owner D): archive/repair/news/backtest/report work may synchronously block or starve critical core monitoring/open paper positions. Independent queues/schedules, bounded concurrency and CPU/memory/I/O/DB/network reservations/equivalents; background yield first, shared API accounting/dedup, no uncontrolled overlapping core cycles. Benchmark targets rather than promise 30 seconds.
- R10 (DATA-04 with proposed PAPER-08): source outages/partial repairs must remain explicit gaps/degraded/unknown, never fictional fills or invented past decisions; resume/idempotency and integrity checks before publishing research. Data gaps and incomplete samples remain visible, not silently approved.

All mitigations are conceptual, not implemented or final G0-approved controls.

## Live-data operations residual risks — DATA-05–08
References: [provisional rules](03_DECISIONS.md#g0-live-data-operations-decisions--data-0508) and [G0-GOV-01](03_DECISIONS.md#g0-gov-01--work-handoff-continuity-and-completeness).
- R02/R10: recovered REST messages or later-finalized candles can fabricate prior knowledge/fills. Preserve observed/reconstructed classes and all clocks/source evidence; chronological idempotent replay retains ambiguity/residual gaps and no fictional live decisions.
- R04: reconnect storms, duplicate per-trader requests and multiplied WS/REST limits. Central cache/dedup, shared subscription/connection/request-weight authority, bounded backoff; constants remain unvalidated.
- R10/R05: slow overlapping core loops or heavyweight archive/news/research/report load starve positions. Bound queue/concurrency, separate Position Monitor from lower-priority batched Scanner, reserve resources/equivalents, log skipped scans without backdating.
- R02/R07: over-aggressive coalescing loses TP/SL/event order; retain all monitoring/fill/replay/audit-required sequences even when latest-state scanning safely coalesces.
- R04/R10: “no trades” falsely treated as outage, or source-wide outage unnecessarily stops independent inputs. Use evidence-based source/symbol/stream/type health and source-specific TTL; selectively block affected decisions. Positions stay open with monitoring gaps; no guaranteed uptime or recovery.
- R01: draft/received prompts mistaken for submitted baseline or unviewed cross-chat content claimed complete. Durable handoff metadata, owner confirmation, exhaustive delta dispositions and coverage-gap audit under G0-GOV-01; originating-chat access remains limited.
All controls are documentation proposals, not implemented/finally approved risk mitigation.

## Integration residual risks — INT-01–06
- R02: blanket closed-bar wording or unconditional fallback changes trader semantics. INT-04 requires proven availability, explicit provisional/completed status and trader-policy permission; otherwise block with reason. Later recovered/revised data cannot become earlier knowledge.
- R01/R10: individually clean PRs can overwrite shared STATE/LOG/decision clauses when merged sequentially. Compare decision/subrequirement coverage and source commits; merging overlapping source proposals blindly is not an integration plan.
- R01: duplicated GOV-01 branches are not duplicate real-world handoffs. Preserve clause provenance and each distinct event once; inaccessible conversations remain an explicit coverage gap.
- R01: a current-state assertion without dated evidence may masquerade as current truth. Use INT-06 evidence fields; preserve historical OPEN observations and append subsequent corrections. Material unresolved contradictions are BLOCKED, insufficient evidence UNVERIFIED.
No unresolved runtime parameter, source/provider, budget or performance objective is approved by these documentary controls. Runtime acceptance remains NOT TESTED; final independent review and owner G0 sign-off remain pending.

## Secretarial architecture residual risks — G1-ARCH-01–11
- Lost/duplicated Inbox data around receipt, durable commit, archive acknowledgment or reclaim: distinguish each boundary, preserve independent consumer checkpoints/raw archive evidence, corruption checks and idempotency. Committed records have durability requirements; messages never received during outages cannot be guaranteed recovered. Capacity/backpressure and disk-full policy remain unresolved implementation parameters, not invisible unlimited storage.
- Slow quality/archive work or resource contention starving delivery: common latency/backlog/resource/provider accounting, measured hysteresis and bounded yielding; protect open positions without turning matching into a serial gate or starving other offices. No fixed SLA or mathematically zero-delay guarantee.
- Secretariat/Position Monitor accidentally deciding strategy outcomes: owning traders retain frozen policy/exit/recovery authority; secretaries route/validate/annotate only. Keep common PAPER-07 evaluator subordinate to trader logic and preserve priority/recovery responsibilities.
- Unsafe coalescing, equal-price dedup or missed office delivery destroys TP/SL/order evidence: stable source/event identity, independent ordered fan-out, decision-critical event retention, per-office lag/gap reporting and declared coverage verification.
- Deep-quality hindsight and outage touches becoming fictional fills: append corrections/provenance; never backdate availability or equate price crossing with execution. Preserve separate historical/current facts, AMBIGUOUS and hypothetical best/worst; future exchange reconciliation is conditional and not real-trading permission.
- Scope/continuity drift: owner merge deferral applies to #6–#11; the new branch preserves unmerged #11 by ancestry. Other chats inaccessible; no exhaustive cross-chat audit or final G0 claim. No new provider, storage engine, infrastructure, paid action or application implementation chosen.

## Progressive screening/readiness residual risks — G1-ARCH-12–20
- Treating screening success/READY as complete mandatory evidence or an entry command: distinct candidate/readiness/decision records, two versioned requirement lists and trader-only authority; stale/invalid/missing mandatory secretary inputs block affected entry.
- Global or linear stage handling leaks one trader's state into another or suppresses valid direct transitions: independent (trader, symbol) states and declared edges; no compulsory BUILDING. Heavy-work cooldown is not a market/stage/position-protection delay.
- Over-eager WATCH prefetch starves live work or repeats historical computation; demotion cancels another consumer's need: shared qualified identities/results, stage-aware demand/consumer references, adaptive Slow throttling and protected Fast/position budgets. Preserve archive/history and independent demands.
- Cache/result class mistaken for freshness or availability: LIVE/HISTORICAL is planning metadata, distinct from provenance/eligibility. Share only matching definition/parameters/version/symbol/timeframe/input provenance/finality/temporal context and consumer qualification. Old results or later calculations cannot become earlier knowledge.
- HISTORICAL forced to be slow, or recovery ownership made an all-work blocking queue: eligible cached results can return without heavy waiting; preserve prior safe restart/current service independence and bounded shared budgets. No new queue technology or timing guarantee chosen.
- Upstream queue/data/history wait attributed to the trader, double-counted parallel waits, or missing clocks reported as zero: correlated interval evidence with distinct delivery/history/readiness/strategy-wait/active-processing metrics, clock-domain quality and UNVERIFIED states.
All earlier durability/health/gap/ambiguity/cost controls and final owner approval gates remain. Scope is documentation only; no new runtime/provider/storage/latency/TTL/capacity assumptions or real execution permission.

## Shared indicator box residual risks — G1-ARCH-21–28
- Central validity versus secretary eligibility confused: authoritative manager technical state, per-secretary manifest qualification and trader-only decisions must remain separate. A valid shared result may still be insufficient; invalid technical data can never be locally approved.
- Invalidation delayed by archive or eager work, or expired payload served during UPDATING: revoke active eligibility independently of Slow progress/recomputation; distinguish immutable history from current binding and disclose all reasons/versions. No invalidation-to-delivery numerical guarantee invented.
- Old execution completes after replacement, stale notification resurrects invalid data, restart loses ordering: compare current dependency/input/version/temporal context at activation, preserve revision/generation evidence, reject obsolete state and reconcile authoritative snapshots/ordered changes. Uncertain continuity blocks affected eligibility rather than assuming validity.
- Single-flight under-specified keys share incompatible inputs, duplicate provider subscriptions multiply load, cancellation harms another trader: full input-version/provenance/finality/temporal identity, independent demand references and consumer eligibility; internal subscriptions reuse the one central provider authority.
- Eager recomputation across every symbol starves Fast/positions: immediate invalidation is independent from demand-aware scheduling; shared qualified updates follow subscribed positions/READY/earlier relevant stages under resource/provider budgets. No mandatory linear stages or delay to critical fan-out.
- Active expiration destroys audit history or later historical fallback rewrites past knowledge: retain result/event/version/correction lineage via existing durable Inbox/Slow archive; separately qualify historical evidence with predeclared policy, never bypass mandatory inputs or restore a technically invalid current binding.
Remaining implementation parameters include technical dependency/rule catalogs, validation criteria, exact generation/fencing/snapshot protocol, consumer demand/cancellation mechanics, transport/storage/integrity choices and measured budgets/targets. All remain unselected and gated; runtime NOT TESTED, no paid services/real trading/final G0 approval.
