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
