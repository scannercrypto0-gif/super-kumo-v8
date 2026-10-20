# ADR register — PROPOSED, not yet approved
001 new V8, legacy V7.3 read-only reference
002 modular monolith
003 Binance Spot USDT only
004 Supabase central, optional object storage and local spool
005 independent paper trades without capital portfolio
006 momentum first
007 independent same-symbol traders, correlated evidence
008 external events research-first
009 owner approves shadow promotion
010 point-in-time immutable decisions
011 4/24/72h forward horizons, max/min
012 gate evidence and owner signoff required
New ADR: ID | problem | options | decision | tradeoffs | affected interfaces | migration | approval.
Never overwrite approved decisions; supersede explicitly.

## G0 Paper Trading decisions — owner-selected provisional rules

Project: ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`.
**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
Selection source: owner-provided G0 Paper Trading documentation handoff dated 2026-10-20; option C was selected for each item. Alternatives are not reconstructed from missing conversation context. Existing ADR 001–012 entries are preserved; these uniquely prefixed IDs refine the paper/research/recovery draft without promoting it to final approval. No code, schema migration, live execution, strategy promotion or G0 closure is authorized.

Canonical detailed rules and owner extensions follow. Contract, risks, conceptual schema requirements and test expectations reference this register; they are not independent competing decisions. Affected interfaces: signal/trader identity, paper fill/exit accounting, outcome/research reporting and recovery event processing. Migration: documentation only; any future implementation requires reviewed versioned interfaces and an approved work package.

### G0-PAPER-01 — Entry & Fill Policy: C

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

Use conditional entry and fill rules rather than automatically assuming execution at the signal price.

- A signal may remain unfilled and eventually expire.
- For immediate market-like entry, use the first eligible observable price **after** signal availability, subject to execution assumptions.
- For conditional orders, require the actual entry conditions to be met.
- Track `NO_FILL`, expiration, and rejection as distinct outcomes/reasons where appropriate.
- Do not manufacture fills or use future information to decide an earlier entry.

**Rationale, tradeoffs and open parameters:** Conditional fills avoid assuming a recommendation was executable; the tradeoff is honest no-fill/expiry coverage. Exact eligibility sources, latency and order conditions remain strategy/model-specific.

### G0-PAPER-02 — Same-Bar TP/SL Ambiguity: C, with owner extension

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

When a candle touches both TP and SL and ordering cannot be established:

- Inspect finer-grained historical data where legitimately available.
- If order remains unknown, preserve `AMBIGUOUS` as an unresolved factual outcome.
- Report two separate research scenarios:
  - **Worst case:** assume the stop was reached first.
  - **Best case:** assume the target was reached first.
- Propagate these assumptions to aggregate trader performance, not merely individual trade rows.
- Do not present the best-case estimate as realized or verified performance.
- Apply the same temporal integrity rules to recovered historical data.
- Distinguish outcome uncertainty from trading-cost uncertainty.

**Rationale, tradeoffs and open parameters:** Unknown event ordering must remain factual uncertainty; best/worst bounds quantify rather than conceal its effect. Finer-data availability and scenario aggregation mechanics need implementation review.

### G0-PAPER-03 — Fees, Slippage & Execution Costs: C

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

Use a hybrid cost model:

- Record gross price return.
- Record a net baseline result after applicable fees and execution assumptions.
- Where suitable point-in-time market data exists, use dynamic estimates for spread, slippage, liquidity, and hypothetical order size.
- Add a separate stress-cost scenario.
- Store the model version, assumptions, fee source, and applicable effective date.
- Never silently replace missing execution data with an unrealistically perfect fill.

**Binance fee note:** The owner asked whether Binance Spot fees are 0.01%. Do not hard-code that figure. Check the official Binance fee schedule when implementing, accounting for VIP tier, BNB discounts, symbol-specific promotions, maker/taker distinctions, and historical effective dates. Any example fee percentages in discussions are illustrative, not an immutable contract rate.

**Rationale, tradeoffs and open parameters:** Separate gross, baseline-net and stressed results expose execution sensitivity. Historical cost-source availability and fallback bounds remain open.

### G0-PAPER-04 — Reference Order Size: C

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Use **1,000 USDT** as the provisional reference notional for comparable paper-trading results.
- Support sensitivity tests at smaller and larger notionals; proposed examples include **100 USDT** and **10,000 USDT**, subject to data quality and practicality.
- Distinguish reference-notional research from actual portfolio sizing.
- Flag insufficient liquidity evidence rather than inventing reliable fills.

**Important owner context, NOT a final decision:** A possible future real-trading capital allocation is approximately **10,000 USD**, with an illustrative **10% per trade**, suggesting **1,000 USD** as a possible maximum trade size. These figures are brainstorming assumptions only, **not approved risk policy, funded capital, or authorization to trade live**. Do not implement real execution or portfolio simulation on this basis.

**Rationale, tradeoffs and open parameters:** A common reference notional supports comparable liquidity/cost research without inventing portfolio allocation. Sensitivity examples depend on data quality; future real capital assumptions are not risk policy.

### G0-PAPER-05 — Independent Traders & Duplicate Control: C

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Each trader has independent paper opportunities and outcomes, even when multiple traders trade the same symbol.
- Deduplicate materially identical active opportunities **within** one trader under explicit identity rules.
- Do not globally block a symbol merely because another trader has a position.
- Shadow Traders remain independent research variants and must not mutate original trader behavior.
- Report overlapping symbol exposure/opportunity correlation so that correlated trades are not misleadingly counted as independent evidence.
- Telegram may consolidate notifications without merging underlying trader records.

**Rationale, tradeoffs and open parameters:** Independent trader evidence permits paired strategy research, while within-trader deduplication prevents duplicated opportunities. Material-identity key details and correlation grouping remain to be specified.

### G0-PAPER-06 — Signal Expiration: C

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Define strategy-specific maximum entry validity windows and early-invalidation conditions.
- Distinguish **entry expiration** from **position holding duration** after a fill.
- Preserve expired/unfilled opportunities for research.
- Store the policy version applicable when each signal was issued.
- Do not retroactively change old signal validity because a strategy's current configuration changed.
- **Do not invent or freeze a universal Momentum expiration duration now**; defer numerical parameters to strategy-specific testing.

**Rationale, tradeoffs and open parameters:** Frozen strategy-specific entry validity prevents retroactive relabeling; it does not cap holding duration. Numeric expiry and invalidation rules require strategy testing.

### G0-PAPER-07 — Position Exit Policy: C, with owner research extensions

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

Use a common exit-evaluation engine supporting predeclared, strategy-specific rules, potentially including:

- Take profit and stop loss.
- Time-based exit.
- Early exit on loss of strategy conditions.
- Rule-driven trailing stops or stop adjustments.
- Future staged profit-taking and partial exits, with exact mechanics deferred.

Requirements:

- Snapshot/version exit rules at trade creation.
- Any permitted adjustment while open must follow a predeclared rule and be timestamped.
- Record exit reason separately from modeled execution price and costs.
- Resolve conflicting events chronologically where possible; otherwise use the ambiguity policy.
- Do not retroactively optimize actual paper-trader results using later market information.

**Owner-requested Research Lab extensions:**

1. **Post-exit tracking:** Continue observing the original hypothetical opportunity for a predeclared research horizon after early closure. Report whether original TP levels would later have been touched. Never reopen or rewrite the original closed paper trade.
2. **Fixed vs raised stop:** Compare the original stop policy against moving the stop to TP1 after TP1 is achieved.
3. **Missed upside:** Measure cases where the raised stop was triggered and price later reached TP2, as well as cases where raising the stop protected profits from further downside.
4. Maintain separate, reproducible counterfactual paths or Shadow Trader variants using the same initial conditions and point-in-time information.
5. Evaluate aggregate risk-adjusted outcomes with fees, slippage, ambiguity, and sample size rather than declaring a policy superior based on anecdotes.

Exact TP1/TP2 percentages, stop-adjustment timing, partial-exit quantities, post-exit monitoring horizons, and promotion criteria remain **UNDECIDED**.

**Rationale, tradeoffs and open parameters:** Versioned exits preserve causal paper accounting; isolated counterfactuals test alternatives without rewriting the original path. TP levels, adjustments, partial exits, horizons and promotion criteria remain open.

### G0-PAPER-08 — Outage Recovery & Position Continuity: C

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Persist enough durable state to recover open paper positions, pending opportunities, policy versions, and event processing progress.
- On restart, retrieve the missing market-data interval and reconstruct eligible market events in chronological order.
- Ensure replay/recovery is idempotent and does not duplicate fills, closes, alerts, or accounting records.
- Preserve market event time separately from ingestion/discovery/recovery time.
- Do not close positions at stale last-known prices solely because the system was offline.
- Where data gaps prevent reliable ordering or outcome determination, mark results as unresolved (e.g., `UNRESOLVED_DATA_GAP`) and exclude them from confirmed performance until resolved or transparently scenario-analyzed.
- Reconstructed historical facts may correct paper accounting, but must **not** be used to fabricate real-time decisions the trader could not have made.
- Preserve the `AMBIGUOUS` best/worst policy if recovered bars still cannot establish TP/SL ordering.

**Rationale, tradeoffs and open parameters:** Durable chronological recovery prevents stale-price exits and duplicate accounting. Recovery can reconstruct observable facts but cannot fabricate decisions made during downtime; gap-resolution procedures remain open.

