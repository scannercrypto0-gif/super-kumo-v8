# AQL-P2-PORTFOLIO-001 — Owner Option C: independently scored overlapping opportunities

**Authoritative latest owner decision:** [#77/6603278584](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6603278584) supersedes the **never-approved** full-cash, one-position policy proposed in [#77/6603221382](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6603221382). **Current approved-provisional architecture is Option C**: evaluate every independently eligible modeled Breakout trade, INCLUDING overlapping holdings, WITHOUT a funded portfolio, common cash account, position sizing or constraint, leverage, position cap, or skip-while-occupied rule. No additional private scoring under an unapproved option A; code/test paths are replaced by Option C on the **same Factory Draft PR #222**.

The previously completed [#77/6602979507](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6602979507) source-backed Feb/Aug ten-bar model is **already a real bounded technical result** from previously exposed development data, NOT unseen/PIT/OOS/scientifically accepted alpha. Reuse original Factory `aql.p2.factory.breakout-modeled-trades.v1` receipts only. Never regenerate Binance archive/source bars, market windows, Core decisions, or trade engine; Core #221 and Work #223 frozen.

## One architectural decision — why C wins for this research stage

**Goal:** quantify each original independently eligible opportunity, its return distribution and concurrency, without turning overlapping unit-trade returns into an impossible funded capital curve.

- **A — superseded, NOT approved:** one-position, full-cash chronological portfolio, overlapping candidates skipped. Makes a chosen arbitration policy and artificial capital process central to already observed results.
- **B — not adopted:** fractional allocation/portfolio positions/risk constraints. Requires further funding/risk assumptions and new analytical degrees of freedom.
- **C — latest owner-approved provisional:** every BASE and SHADOW `TRIGGERED+MODELED_COMPLETE` opportunity counted, even on overlapping timestamps; no cash, account balance, skip priority, funding feasibility, margin, leverage, portfolio equity or drawdown output. Keep all NO_SIGNAL/REJECTED/UNKNOWN and censored original slots as NULL. Descriptive overlapping opportunity counts/time-weighted concurrency; no trade-selection optimization.

**Recommendation:** implement C only now, as approved. This is an **exploratory** opportunity study, separate from the frozen original trade pre-registration. Since past development trade results are known, do NOT claim the new policy was registered before those old results. The externally timestamped Option C GitHub code-policy anchor must exist BEFORE the NEW private Option C scoring.

## Exact Factory API / contract

`research_wp_r0.aql_p2_factory_portfolio.frozen_option_c_policy()`

Returns immutable canonical `aql.p2.factory.independent-opportunity-policy.v1` approved-provisional envelope including the exact GitHub owner decision URL and `artifact_sha256`. It has no capital/cash/allocation/sizing assumptions; no strategy parameter to tune. During CI, the workflow saves the canonical frozen policy JSON as a **GitHub-timestamped metadata-only** artifact named `p2-option-c-owner-policy-pre-score-anchor`; that is a policy fingerprint, NOT approval of trading or an already completed private run.

`build_independent_opportunity_package(trade_reports, policy, cohort_bounds, *, test_only=False, owner_decision_verified=False, before_scoring_anchor_verified=False, independent_parent_receipts_verified=False, policy_anchor_raw_sha256=None)`

Inputs:
- `trade_reports`: **original unchanged** per-cohort private receipts with independently authenticated source/protocol/prereg/cost/arm/window lineage and exact ten-bar `open[i+1]` → `open[i+11]` modeled arithmetic and frozen additive 30bps modeled costs. This consumer checks complete parent SHA, reference to original schedule and descriptive artifact, full `2 × pairs` denominator, both arms, identical same-pair prices, entry/exit 10×900000ms, cost component/policy integrity and NULL vs COMPLETE disjointness. It does NOT fetch bars or invent a fill.
- `policy`: exact `frozen_option_c_policy()` **unchanged**. No arbitrary scenario or reinterpretation via self-rehash. Every field and digest must match the canonical approved-provisional C envelope.
- `cohort_bounds`: existing independently authenticated source-specific `{source_id: {source_id, source_package_sha256, start_ms, end_exclusive_ms}}`; no cross-Feb/Aug borrowing, no joined continuous timeline. Correct original P2 cohorts: Feb2784 bars→2763 pairs, Aug2976 bars→2955 pairs, total **5718 scheduled pairs and 11436 BASE/SHADOW slots**.
- Real/private execution requires Work's independent verification of exact owner C comment, downloaded GitHub policy-anchor bytes and creation time *before* this new Option C scoring, plus original immutable parent receipt bytes; caller must supply `owner_decision_verified=True`, `before_scoring_anchor_verified=True`, `independent_parent_receipts_verified=True` and the actual verified raw policy-anchor SHA256. These are assertions by the authorized external private runner, NOT proof merely because boolean arguments exist; they are NEVER inferred from fixtures. If absent, **fail closed**. `test_only=True` is permitted only for explicitly `TEST_ONLY_` synthetic cohort IDs; never label genuine source results TEST_ONLY.

## Reproducible descriptive outputs

For each original cohort and each arm **independently**:
- One immutable opportunity row per original pair: original pair/arm, original arm-decision SHA, 4h source-window SHA, signal/disposition, missingness/censor reason, modeled eligibility, exact original modeled gross/net **per-unit** returns only when complete, NULL otherwise. No eligibility changes or zero-imputation.
- Per-arm descriptive **conditional** distribution on *complete eligible opportunities only*: count, positive/zero/negative net counts, mean, nearest-rank p25/median/p75, min/max. These are dependent overlapping unit observations, not independent IID trials, fund returns or statistical inference.
- Original `[entry_open_ms,exit_open_ms)` half-open intervals for complete opportunities. Strict chronological sweep with **EXIT before ENTRY** at the same millisecond, deterministic `pair_id` ordering, max simultaneous eligible opportunities, number of eligible opportunities overlapping at least one other, time with any active, time with 2+ active, and time integral/average of independent opportunity count over the source cohort. Concurrency numbers are **not capital/leverage exposures**.
- One paired BASE/SHADOW row for every original pair. Both complete have exactly the same source-backed modeled prices and return; SHADOW rejected/missing returns remain NULL, not 0%, and no uplift is inferred from selected populations.
- Output `aql.p2.factory.independent-opportunity-study.v1` records parent receipts, policy SHA, external anchor SHA, per-cohort full census, descriptive overlap timeline, and `common_cash_account=None`, `funded_equity=None`, `drawdown=None`, `leverage_assumption=None`, `position_cap=None`, `execution_status=NOT_OBSERVED`, `alpha_claim=NOT_ESTABLISHED`, `pit_status/oos_status=NOT_ATTESTED`, `holdout_status=SEALED_UNOPENED`.
- Internal deterministic receipt `artifact_sha256=digest(report excluding artifact_sha256)`. `canonical_opportunity_receipt_bytes(report)` emits sorted compact UTF-8 JSON with trailing newline; `raw_opportunity_receipt_sha256(report)` hashes the *actual bytes*. `render_opportunity_research_report(report)` produces a clearly nonfunded descriptive report. Keep full receipts and original prices **private in Work**; GitHub can receive limited non-sensitive counts/SHA/technical status.

No funded equity curve, feasible drawdown, account PnL, strategy portfolio CAGR, leverage or actual exchange execution can be inferred or claimed. Do NOT sum overlapping independent unit returns and call it funded profit.

## One consolidated Work-private gate after exact-head CI + external policy anchor

**G0-GOV-01 checkpoint:** establish last *actual* owner-sent Work delivery, currently [#77/6602979507](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6602979507) if no newer verified delivery, then review all accessible #77/#180/#205/#134 and owner decisions; never assume inaccessible sessions have been read. Work already retains the immutable original source and earlier P2 trade receipts in its authorized private environment.

Only once the new C code and CI are green and independently timestamped, Work can invoke this **read-only** exact Factory Draft HEAD with original verified Feb/Aug ten-bar modeled trade reports. Rehash original receipts/source evidence, verify GitHub owner C comment and new policy artifact timestamp before the *first* Option C outcome score, then run separately per month twice and compare byte-identical output SHAs. Fail closed on source, cost, policy, temporal anchor, identity or missingness mismatch. Preserve 5718 / 11436 original denominator. No source acquisition, new ten-bar model or post-hoc tuning. Request bounded independent technical/scientific gate only at the correct later stage; no broad Audit loop at each development test.

**Not allowed:** PR merge, final G0, opening November 2025 holdout, prospective/PIT/OOS/alpha certification, deployment, orders, Paper/Live trading.
