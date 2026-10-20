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
