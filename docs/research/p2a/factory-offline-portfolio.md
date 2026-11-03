# AQL-P2-PORTFOLIO-001 — Offline portfolio simulation (proposal-gated)

**Owner authorization:** [Factory #77/6603221382](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6603221382) permits **building code** on existing Draft PR #222 while Core #221 stays frozen. No owner approval of a concrete portfolio policy is implied. Governance execution pattern: AQL-EXEC-01 [#205/6602265245](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6602265245).

**Boundary:** This is an *exploratory* portfolio layer, explicitly **not** part of the previously frozen Breakout BASE/SHADOW trade pre-registration. The Feb/Aug 2024 development results have already been observed. A new policy approved now can be explored transparently, not retrospectively described as confirmed or unobserved.

## Architecture decision awaiting owner (A/B/C)

**Goal:** model a feasible cash-limited selection of overlapping, previously source-verified Breakout opportunities, without rebuilding Core policy or Factory's ten-bar engine.

- **A — proposed research baseline (recommended, NOT YET OWNER-APPROVED):** max one open position, no leverage, fully reserve modeled available cash on entry, skip all competing/occupied signals, deterministic lexicographic `pair_id` tie-break, same-clock exit processed before entry; run BASE/SHADOW as *separate* portfolios. This is a simple constrained first comparison, but has no risk diversification and uses full available modeled capital.
- **B — fractional fixed allocation:** e.g. 25% per entry with max positions >1. Could reveal concurrency effects, but requires new sizing/risk/concurrency choices and is NOT implemented/approved in this initial scenario.
- **C — sophisticated portfolio/risk weighting:** volatility target, stops or liquidity rules. Could better reflect operations but creates multiple new degrees of freedom on already observed development data. Defer.

A is packaged via `propose_portfolio_policy(initial_capital="10000")`, with `approval_status=PROPOSED_NOT_OWNER_APPROVED`. **No real/private portfolio scoring will run until the owner explicitly approves the exact frozen envelope and an independent GitHub anchor has been recorded/verified before *that portfolio scoring*.** Only `TEST_ONLY_SYNTHETIC` fixture execution is permitted meanwhile. No auto-approval, no holdout, no PR merge, no orders.

## Frozen consumer interface

`research_wp_r0.aql_p2_factory_portfolio.build_offline_portfolio_package(trade_reports, policy, cohort_bounds, *, test_only=False, owner_approval_verified=False, pre_score_anchor_verified=False, independent_parent_receipts_verified=False)`

Input `trade_reports`: original full deterministic `aql.p2.factory.breakout-modeled-trades.v1` reports from the existing **real Work-private** ten-bar technical execution, NOT a regenerated strategy or transformed 4/24/72h cutoff-reference horizon outcome. Parent SHA, trial/schedule/source/prereg/cost, all original arm decisions and per-pair 4h window hash, execution status, modeled costs and every BASE/SHADOW slot must pass fail-closed checks. Original authenticated Feb/Aug source and ten-bar private receipts documented in [#77/6602979507](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6602979507): real technical results complete, scientific acceptance deferred.

`cohort_bounds`: verified `source_id → {source_id, source_package_sha256, start_ms, end_exclusive_ms}` from unchanged original Work/Core source pins. No cross-month position or price borrowing. Feb and Aug are **separate capital-reset experiments**, NOT a continuous live equity curve.

`policy`: immutable `aql.p2.factory.portfolio-policy.v1` self-hash, explicitly separate scope, precise initial modeled capital, arbitration, sizing, accounting, data restrictions and approval status. A self-hash alone does **not** demonstrate owner approval or existence before scoring. Real scoring gate requires exactly `OWNER_APPROVED_PROVISIONAL`, a real owner issue-comment URL, a verified external pre-score policy-anchor receipt, `owner_approval_verified=True`, `pre_score_anchor_verified=True`, and `independent_parent_receipts_verified=True` in the Work-private execution. Those flags are an *interface*, not independently verified external facts; Work must perform independent verification.

`test_only=True` is restricted to a separately self-hashed `TEST_ONLY_SYNTHETIC` scenario. No re-labeling that fixture as real market evidence.

## Chronological ledger and cash model

- Pair/arm opportunity census retains **every original** `NO_SIGNAL`, `REJECTED`, `UNKNOWN` and complete opportunity, including original decision SHA, source window SHA, disposition, censor flag, missingness reason and whether portfolio took/skipped it. Missing/censored returns remain NULL, NEVER 0% loss/zero-return imputed, and do not become trades.
- For each `source_id` / BASE or SHADOW, eligible events are sorted by authenticated modeled `entry_open_ms`, then `pair_id`. Single position: an entry reserves **100% of available modeled cash**, cash shows 0 during holding; one trade closes exactly at the original modeled `exit_open_ms` (10 completed 15m bars), and cash is credited upon exit. **Exit precedes entry at the same timestamp.** Occupied signals and lower-priority simultaneous entries are recorded as SKIPPED rather than traded.
- Only original frozen modeled LONG unit gross/net return enters the ledger; no additional per-bar exchange simulation, stop, take-profit, fill, balance-curve interpolation or independent inference of prices. Source parent must prove `gross=exit/entry−1` and `net=gross−0.003` with original 0.10% per-side fees and 0.05% per-side slippage (total **30bps**). Settlement cash = entry capital × (1 + original net). Fee/slippage contributions are deducted **once** under the *pre-existing additive model*. To preserve that specific return convention with 100% notional, the initial side cost is modeled as deferred to the exit settlement; it is **not executable cash-flow/fill accounting**, and should not be marketed as an implementable real account order ledger.
- Each cohort starts with independent arbitrary research notional `initial_capital`. No leverage or negative modeled cash; non-positive exit balance fails closed. No cross-cohort compounding.
- Outputs: ordered entry/exit events and cash before/after, per-position notional and modeled units, modeled gross/net return and cost amount, complete opportunity census/skips, terminal *realized settlement cash-equity*, **realized-exit-only** drawdown/highwater and **time occupancy/exposure** relative to the separately authenticated full cohort clock.
- **No intratrade mark-to-market equity, max intratrade drawdown, balance liquidation, exchange execution, tail risk measure or actual fill** can be claimed from the parent ten-bar summaries alone. Parent held-bar extrema are NOT a substitute for a sequential account valuation. Such metrics remain explicitly NOT AVAILABLE. Report is a *modeled* capital accounting thought experiment only.
- Paired BASE and SHADOW each have **independent** cash streams, one per source cohort. Their terminal cash difference is a descriptive scenario comparison affected by different selected/occupied signals; **NOT a causal alpha uplift or statistically validated result**.

## Deterministic receipts and stop conditions

Output `aql.p2.factory.offline-portfolio.v1`: entire ordered ledger, source/window/decision lineage, null and skip census, policy SHA + external anchor identifier, per-arm and per-cohort capital/exposure metrics, paired comparison and limitation flags. `artifact_sha256` hashes the canonical JSON object. `canonical_portfolio_receipt_bytes` writes sorted compact UTF-8 JSON + newline; `raw_portfolio_receipt_sha256` hashes those actual bytes. `render_portfolio_report` produces descriptive text only. Preserve full private original price/trade details in Work's authorized private environment, **never GitHub public issues**.

Negative paths fail closed on forged owner approval, altered or rehashed portfolio parameters, parent trade SHA mismatch, forged prices/costs, duplicates, identity/clock drift, cross-cohort trades, invalid capital, missing/extra source bounds or duplicate cohorts. Fast TEST_ONLY tests during development, one consolidated source→Core→Factory trade→portfolio integration gate **after** owner approves and actual external policy anchor is independently established. Do not request the owner to resend old files.

**Project status:** BUILD/CODE/FOCUSED TESTS can complete under current authorization; **real private portfolio scoring is BLOCKED until explicit policy-parameter approval and pre-score anchor**. No retrospective claim that a new exploratory scenario was preregistered before previous ten-bar results. No broad Audit/G0/holdout/paper/live/trading.
