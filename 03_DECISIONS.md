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

## G0 TIME and DATA provisional decisions

Project: ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`.
**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
Owner-selected option C for all 13 records; source: consolidated owner handoff dated 2026-10-20 plus mandatory completeness addendum. Legacy ADR 001–012 remain unchanged. The following records are the canonical detailed source. Each preserves its selected policy, owner rationale/conditions and deferred implementation parameters. No alternatives are invented from missing chat context. TIME-01 explicitly refines the former closed-bars-only wording while retaining point-in-time integrity; no final architecture approval is implied.

### G0-TIME-01 — Decision-Time Data Eligibility: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Closed candles are allowed.
- Intra-candle/live observations are allowed only when there is verifiable evidence that the exact data was available at the trader's decision time.
- Fallback to a qualifying completed candle is permitted only if the trader's predeclared policy explicitly allows it and availability/freshness checks pass. Otherwise block the affected decision and record the reason (INT-04).
- Prevent look-ahead, future leakage, and repainting.
- Preserve event, availability, and decision timestamps.
- Historical replay must not silently use information that became available later.

### G0-TIME-02 — Multi-Timestamp Integrity: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Distinguish market event time, system receipt/ingestion time, effective availability-to-trader time, and decision time.
- Monitor clock skew and timestamp quality.
- A market event that occurred before a decision but was received afterward cannot be treated as observed by that decision.
- Historical data lacking real receipt evidence must use explicit conservative assumptions and be labeled as modeled replay, not exact observed-live reconstruction.

### G0-TIME-03 — External News Point-in-Time Integrity: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

**Owner clarification: explicitly record both the original news publication time and the time the news was added to ATLAS.**

- Also preserve first verified observation time where available, source, evidence, content version, and subsequent edits.
- Never infer that ATLAS knew a historical news item at its publication time merely because the source displays that timestamp.
- Distinguish observed-live news, historically verified availability, and publication-time-only archives.
- Historical imported news must not receive fabricated historical ingestion timestamps.
- For edited articles, earlier decisions may only access content versions actually available then.
- Distinguish preannounced scheduled events from genuinely unexpected news.

### G0-TIME-04 — Immutable Data Versions & Corrections: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Preserve reproducible historical dataset versions and immutable experiment references.
- Corrections create new versions; do not silently rewrite prior experiment outcomes.
- Record provenance, correction reasons, and differences.
- Flag affected strategy evaluations and promotion evidence for review.
- Distinguish market-data corrections from simulator/code corrections.
- Prefer shared versioned datasets over unnecessary per-experiment full copies.

### G0-TIME-05 — Historical Research vs Forward Performance: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

**Owner clarification: the Research Lab uses available historical data to test hypotheses. A successful laboratory candidate may be nominated for a new Forward/Shadow Trader evaluation. That evaluation starts independently and has no combined performance score with the old historical evaluation. Both results must appear side by side, so ATLAS can investigate why a strategy succeeded historically and failed forward, or vice versa.**

- Freeze strategy identity, parameters, code/rule version, dataset version, and experiment configuration.
- Separate historical backtest, out-of-sample historical validation, and genuinely prospective forward observation.
- Never backdate Shadow Trader performance.
- Preserve failed experiments and the research selection history.
- Candidate nomination is not automatic promotion to a core trader; owner approval remains required.

### G0-TIME-06 — Regime-Aware Walk-Forward Validation: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

**Owner clarification: the target is NOT a strategy that performs positively in every market regime. The target is a portfolio of specialized traders, each proven effective within a specifically defined regime.**

- Use chronological walk-forward validation with genuinely later evaluation windows and an independent final holdout.
- Evaluate across multiple market regimes during development and testing.
- Test each candidate on multiple independent periods of its target regime when available.
- Measure off-regime performance as exposure/risk evidence; do not automatically reject a strong specialist solely because it performs poorly outside its declared regime.
- Prevent overlapping trade labels or future information from leaking across temporal boundaries.
- Prevent repeated tuning against the final holdout.
- Declare a candidate's target regime and eligibility criteria before prospective forward evaluation.
- Historical validation, even out-of-sample, remains separate from forward evidence.

### G0-TIME-07 — Regime Detection & Market Context Snapshot: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

**Owner clarification: each opportunity and trade should carry the richest feasible market-condition snapshot, so ATLAS can identify the exact conditions in which a strategy succeeds or fails rather than merely declaring it a winner or loser.**

Examples of context:
- BTC dominance.
- BTC trend across relevant timeframes.
- BTC/ETH relationship and ETH/BTC relative strength.
- Altseason indicators and breadth.
- Broad-market direction, volatility, liquidity, volume, and trend strength.
- Coin-specific trend, relative strength, sector, and BTC correlation.
- Additional evidence-based context fields as the research model evolves.

Requirements:
- Multi-timeframe regime detection.
- Trader-specific regime specialization and eligibility.
- Explicit unknown/uncertain regime behavior.
- Store decision-time snapshots with source, calculation version, timestamps, availability, freshness, and missing-data flags.
- Use shared snapshot references where feasible instead of duplicating large data blobs for every trade.
- Capture rejected, expired, and no-fill opportunities as well as executed paper trades.
- Separate point-in-time observed context from retrospective explanatory annotations.
- Develop and test across several market regimes; a nominated Forward Trader is authorized to enter only in its declared eligible regime.
- Evaluate the regime detector itself for lag, false classification, and changing market conditions.
- No hindsight-based regime labeling may be used as if it were a real-time entry signal.

### G0-TIME-08 — Regime Transitions During Open Trades: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Regime changes can stop new entries under the trader's predefined eligibility rules.
- An already-open paper trade follows its predeclared exit plan; no automatic retroactive closure merely because a retrospective regime label changed.
- Test regime-triggered early exit, tighter stops, or other alternatives as separate Research/Shadow policy versions.
- Compare policies after realistic fees and slippage.
- Preserve the actual detection/availability time of a regime transition.
- Remain compatible with G0-PAPER-07's flexible exit engine and counterfactual research rules.

### G0-TIME-09 — Per-Indicator Freshness & Missing Data: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Each indicator has a declared freshness policy appropriate to its source, frequency, and timeframe.
- Each trader distinguishes essential eligibility inputs from optional analytical context.
- Missing or stale essential inputs prevent affected new entries; missing optional inputs are recorded without unnecessarily stopping unrelated traders.
- Record measurement time, receipt/availability time, age, freshness state, source, and calculation version.
- Retain missed opportunities and reason codes caused by data unavailability.
- Avoid assuming a daily altseason indicator must refresh at the same cadence as intraminute prices.

**Owner extension:** Richer snapshots must not cause uncontrolled Binance API consumption. Every run requires planned, deduplicated data acquisition, caching, and budget enforcement.

## 4. Provisional G0-DATA decisions

### G0-DATA-01 — Central Data Collector, Shared Cache & API Budget: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Centralize market-data acquisition and share results across independent traders and Research Lab.
- Deduplicate equivalent requests across symbols/timeframes/sources.
- Maintain a per-run acquisition plan and freshness-aware cache.
- Calculate locally derivable indicators from already-acquired data whenever possible.
- Respect the actual Binance endpoint request weights, limits, responses, and retry rules; do not invent universal static limits.
- Maintain provider-specific budgets for non-Binance sources, including news and market-dominance feeds.
- Implement conceptual backoff, throttling, and circuit-breaker policies without prescribing unvalidated numeric settings.
- Missing required fresh data must not be replaced by fake freshness.

### G0-DATA-02 — Priority Degradation & Separate Initial Historical Backfill: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Prioritize open paper-position monitoring and essential live-market data above new entries, analytical enrichment, and background research.
- Degrade lower-priority functions first under API or resource pressure.
- Respect all exchange/provider limits even for the highest-priority jobs.
- Preserve no-fabricated-fill and recovery semantics from G0-PAPER-08.

**Owner extension:**
- Establish a historical research library through a separately scheduled **initial backfill before normal paper-trader operation**, where feasible.
- Aim for the broadest trustworthy, economically feasible historical coverage of supported market pairs and periods.
- Include market prices/candles, volumes, broad market indicators, BTC/ETH context, and historical external events/news where sources and rights permit.
- Do not assume Binance offers every indicator, news archive, or full history for every asset.
- Historical imports must preserve point-in-time limitations.
- Research jobs should primarily read the local/shared library, not repeatedly call Binance.
- After launch, append incremental new observations and separately schedule gap repairs.
- Initial backfill itself remains rate-limited, resumable, and cost-controlled.
- Prefer intelligently planned graceful degradation rather than indiscriminate shutdown.

### G0-DATA-03 — Hybrid Research Archive Storage: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

**Owner condition: fast, automatic access to needed historical information with minimal avoidable financial cost. Do not promise that storage, transfer, compute, or external data will always cost zero.**

- Use compressed partitioned archival files where appropriate, with PostgreSQL/Supabase indexing and metadata.
- Consider Parquet for analytical time-series workloads, subject to later validation.
- Index by source, symbol, timeframe, coverage period, version, and integrity status.
- Store immutable references, checksums, provenance, gap records, and correction lineage.
- Reuse common archive objects and local caches to avoid repeated downloads or duplicate storage.
- Enable selective reads of only the relevant partitions.
- Measure retrieval latency, storage footprint, transfer volume, and likely cost before finalizing implementation.
- Do not activate billable services or incur paid data-access charges without owner authorization.
- The archive is shared by Research Lab and operational pipelines while preserving workload isolation.

### G0-DATA-04 — Incremental Gap Repair, Cost Guardrails & Isolated Runs: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Identify missing/incorrect archive segments using coverage indexes.
- Fetch only missing or changed ranges where possible.
- Verify continuity, timestamps, duplicates, integrity, and source/version before publishing data to research.
- Make jobs resumable and idempotent; preserve incomplete/error states.
- Never silently approve results built on materially incomplete datasets.
- Enforce provider request budgets and infrastructure cost limits.
- Avoid full-history redownloads as the default behavior.

**Critical owner extension: isolate time-sensitive core operation from all background work.**

The owner gave an illustrative example of a core live-data run taking around 30 seconds. This is NOT an approved fixed SLA. The architectural requirement is that background historical ingestion, gap repair, news enrichment, reports, and Research Lab experiments must not block or materially slow core live-market updates.

Document a conceptual multi-run/multi-worker scheduling model inside the modular monolith:

1. **Core Live Run (highest priority):** Essential live price/market context refresh, open paper-position monitoring, and eligible paper-trading decisions.
2. **Context Update Jobs:** Slower-changing market indicators, external sources, news enrichment.
3. **Archive Maintenance Jobs:** Incremental historical ingestion, repairs, verification, and indexing.
4. **Research Jobs:** Backtests, heavy experiments, and reporting.

Design requirements:
- Independent job schedules/queues and controlled concurrency.
- Shared, coordinated provider rate-limit accounting; multiple workers must not multiply or bypass API limits.
- Priority/resource isolation for CPU, memory, I/O, database connections, and network use.
- Background workloads yield or pause when core health is threatened.
- Core jobs must not synchronously wait for historical backfill or unrelated analytics.
- Protect against overlapping or endlessly accumulating core runs.
- Track run duration, deadline misses, queue backlog, freshness lag, and provider-budget usage.
- Establish measurable targets and benchmark them before final approval; do not invent a guaranteed 30-second SLA.
- Missing critical data produces explicit degraded/unknown status, not fabricated prices, fills, or decisions.
- Keep this as architecture documentation; no worker framework or deployment infrastructure is authorized yet.

## TIME and DATA mandatory owner clarifications

These owner clarifications take precedence over less-specific TIME/DATA wording; they refine existing IDs and create no new decisions or implementation authorization.

### A — Regime-specialist trader reporting
For every candidate and forward trader, report predeclared target-regime and observed off-target performance, opportunity/trade counts, net outcomes after costs, drawdown/risk, uncertainty and sample adequacy. Separate historical development, historical out-of-sample and prospective forward sections; display side by side with NO combined historical/forward success score. Investigate divergence through regime distribution shifts, regime-detector errors, costs, data quality and possible overfitting. Label insufficient evidence as insufficient, never proven profitability. A strong specialist need not succeed globally; independently evaluate whether its regime can actually be detected at decision time.

### B — Complete point-in-time market context
Capture the richest feasible useful context for every signal opportunity, including rejected, expired, no-fill and executed opportunities. Original decision-time snapshots are immutable; context changes during an open position are separate timestamped observations/events, never replacements. Include BTC dominance/trend, BTC/ETH and ETH/BTC relationships, altseason evidence, breadth, liquidity, volatility, asset-relative strength and other justified available indicators under source-quality/cost controls. Separate demonstrably available-at-decision data, reconstruction under declared historical assumptions and retrospective explanation unavailable to the original trader. Preserve source, measurement/event/receipt/availability/decision timestamps, freshness, calculation version, missing status and shared snapshot references.

### C — Initial Research Library coverage
Initial backfill is a distinct separately scheduled PRE-OPERATIONAL preparation phase, never a synchronous/background prerequisite of Core Live Run. Aim for broadest available trustworthy economically feasible historical coverage, including market context and news/events only where reliable lawful sources exist. Inventory assets, markets, timeframes, date ranges, market indicators, news/event archives, missing periods, unsupported sources, quality limitations, backfill progress, validation status and versions. Completeness may be claimed only against a verified declared scope. After launch, incremental ingestion and gap repair update the same library asynchronously without blocking core operation.

### D — Hard core-run isolation
Core live-market monitoring and open paper-position tracking are the critical path. Archive downloads, historical repairs, news enrichment, backtests and heavy reports must NEVER be synchronous prerequisites for core completion. Document independent schedules/queues, bounded concurrency, shared provider rate-limit governance and resource reservations or equivalent CPU/memory/I/O/DB/network controls. Background jobs yield before critical operations starve; no duplicate equivalent Binance requests, multiplied API budgets or uncontrolled overlapping core cycles. Missing essential data produces explicit degraded/unknown status rather than waiting on archive jobs or fabricating data. The owner's 30-second example is illustrative; objectives follow measurement/load testing, not a guaranteed SLA.

### E — Cost and provider controls
Minimize avoidable cost through automatic reuse and fast selective retrieval; zero cost is NOT guaranteed. Monitor explicit budgets and require owner approval before any new paid data source, storage upgrade, compute resource or chargeable service. Research growth must not silently incur unapproved expenses. Each external indicator needs a defined provider or local calculation method, provenance, freshness policy, provider-specific API budget and availability limitations; unknown providers are unresolved, not assumed Binance coverage.

### F — Owner research philosophy
Build independently evaluated traders specialized for predeclared conditions. Development and historical validation examine multiple regimes and multiple independent target-regime occurrences where available. After nomination, a forward trader enters only when its predeclared regime eligibility is satisfied by information demonstrably available then. Historical success never replaces prospective forward evaluation; both remain visible for investigating historical/forward disagreement. Nomination is not promotion; owner approval remains required.

### Integration and deferred decisions
TIME-01/02 eligibility governs all context, news and recovered data. TIME-05/06/07 reporting applies A/F; TIME-07/08/09 apply B; DATA-02/03/04 apply C; DATA-01/02/04 apply D; TIME-09 and DATA-01/03/04 apply E.
G0-PAPER-01–08 are proposed in [PR #7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7), not merged at inspection: conditional/no-fill entry (01), factual ambiguity and best/worst aggregates (02), fee/notional assumptions (03/04), trader independence (05), frozen validity (06), causal exit/counterfactual isolation (07), recovery without invented decisions (08). TIME-08 complements predeclared PAPER-07 exit plans; DATA-02/04 preserve PAPER-08 continuity. No pending paper decision is silently finalized.
Deferred: exact receipt-evidence thresholds, regime algorithms/unknown-policy parameters, provider selection/rights, retention/storage format and partition sizes, budgets, queue/worker technology, concurrency/resource reservations, benchmarks and performance objectives. Parquet is a candidate only. No paid action, code, runtime settings, migration or final G0 sign-off.

## G0-GOV-01 — Work Handoff Continuity and Completeness

Status: **OWNER-APPROVED PROVISIONAL GOVERNANCE RULE — NOT FINAL G0 APPROVAL**.
Scope: every future Work handoff across ChatGPT, ChatGPT Work and Claude conversations for ATLAS Quant Lab (`AQL-CRYPTO-RESEARCH-001`). Recording this rule does not implement application code or authorize merges.

Before issuing a new handoff:
1. Identify the latest handoff the owner confirms was actually submitted, including every subsequent addendum. Do not substitute the latest draft, PR creation time or tool-received instruction for explicit owner confirmation of submission elsewhere.
2. Consult [the canonical handoff register](HANDOFF_REGISTER.md), current GitHub evidence, and available conversation records, including other chats only when actually accessible.
3. Build a delta ledger of EVERY decision, owner clarification, requirement, correction and exception agreed since that submitted baseline; capture source/reference, date, approval status and known addenda.
4. Cross-check each delta item against the new handoff and repository documentation actually verified, including unmerged branches distinguished from main.
5. Give every item exactly one accountable disposition: INCLUDED (new handoff section), ALREADY DOCUMENTED (verified file/commit/PR evidence and merge state), OWNER-DEFERRED (owner decision/reference and revisit condition), or UNRESOLVED (gap/blocker and next action). Never silently drop an item.
6. Never claim another conversation, Work execution, PR or repository change was inspected unless its evidence was actually accessed; summaries and hearsay are not execution confirmation.
7. If an earlier handoff/addendum is inaccessible, explicitly mark the coverage gap and request the missing reference/content. Do not claim full completeness; do not issue a purportedly complete handoff until material gaps are resolved or explicitly scoped/deferred by the owner.
8. Run a final completeness audit before issuing: baseline/submission evidence and addenda identified, ledger items all mapped, approvals/proposals separated, repository evidence current, gaps stated. Report PASS or COVERAGE GAP; do not relabel a gap as PASS.
9. Record new handoff ID, date, scope, owner-confirmed submission status/evidence, addenda, resulting PR and review/merge status in [HANDOFF_REGISTER.md](HANDOFF_REGISTER.md). Distinguish drafted, submitted, tool-received, PR-open and merged facts; reconcile later updates with evidence rather than guessing.
10. All decisions remain provisional until the owner explicitly grants final approval; neither handoff completeness nor a documentation merge is architecture/trading/gate approval.

Use existing protocols and [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md); register only traceability metadata and delta audit, not duplicate full decision specifications. Direct authorized-write checkpoints use the same evidence/continuity discipline and record actual actions, without generating duplicate copy/paste work.

## G0 live-data operations decisions — DATA-05–08

Project: ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`.
**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
Source: directly received owner governance/live-data handoff dated 2026-10-20. All four select C. Canonical full requirements follow; no runtime framework, deployment split, constants or implementation authorized.

### G0-DATA-05 — Hybrid WebSocket + REST: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves a centralized hybrid market-data ingestion architecture:

- Use Binance Spot WebSocket streams where suitable for timely live-market observations.
- Use REST for initialization, reconciliation, validation, and bounded gap recovery.
- Maintain shared market-data acquisition, caching, and request deduplication across traders and jobs.
- Coordinate WebSocket subscription/connection limits and REST request-weight budgets.
- Reconnect with controlled retry/backoff, without creating connection storms.
- Distinguish actual live-observed messages from data obtained later during REST backfill.
- Preserve event time, system receipt/availability time, processing/decision time, and source evidence.
- Do not retroactively present REST-recovered observations as though they were available to earlier live decisions.
- Use only data demonstrably available at decision time, consistent with TIME-01 and TIME-02.
- When data is unavailable or stale, apply trader-specific eligibility/freshness rules rather than fabricating current prices.

No fixed polling interval, endpoint list, stream count, or request-weight budget is approved yet. These require later validation against actual Binance Spot documentation and workload tests.

### G0-DATA-06 — Intelligent Core Run Scheduling: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves deadline-aware, non-accumulating core scheduling.

Requirements:

- Prevent uncontrolled overlapping core runs.
- Prevent an unbounded backlog of missed or duplicate scheduled runs.
- Prefer processing the latest valid market state for current scanning when intermediate display/scanning snapshots can safely be coalesced.
- **Do not discard event sequences required for paper-position monitoring, fill ambiguity analysis, chronological replay, or auditability.**
- Track run start/end, duration, lag, deadline misses, queue depth, and skipped/coalesced work.
- Set bounded execution and concurrency policies, to be determined through measurement.
- Give open-position monitoring higher priority than new-opportunity scanning.
- Keep archive backfill, news enrichment, heavy reports, and Research Lab jobs outside the critical live-run path.
- Preserve idempotency and deterministic event ordering when work is retried.
- On stale or missing essential data, block affected decisions and record why.
- Do not invent a fixed 30-second SLA: the owner's 30-second example is illustrative, not a committed performance target.
- Ensure any skipped scanning cycle is recorded accurately; do not backfill missed opportunities as if they were generated live.

### G0-DATA-07 — Independent Position Monitor & Opportunity Scanner: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves two logically independent operating paths that share a central market-data service:

**Higher-priority Position Monitor**
- Monitor open paper-position state and deliver relevant observations with high priority to the owning trader via its logical secretary. The owning trader evaluates its predeclared TP, SL, time-based, trailing and early-exit policies and retains decision authority (G1-ARCH-05); the Position Monitor/secretariat neither independently decides outcomes nor creates fills.
- Do not wait for a full-universe scan to finish.
- Preserve event chronology, point-in-time data validity, and same-bar ambiguity handling.
- Never fabricate TP/SL hits or fills based on stale or later-discovered prices.

**Lower-priority Opportunity Scanner**
- Evaluate symbols and trader entry eligibility using shared, freshness-qualified market data.
- Scan in bounded batches or adaptive schedules.
- Under load, reduce or defer new-opportunity scanning before starving open-position monitoring.
- Log skipped or delayed scans and their reasons.
- A trader requiring a stale/missing shared regime input must not open a new position.

**Shared foundation**
- Reuse centralized WebSocket/REST ingestion, caches, market-context snapshots, provider budgets, and provenance.
- Avoid duplicated per-trader API requests.
- Preserve independent trader strategy/rule state and decision identity.
- Do not let heavy Research Lab or archive tasks monopolize CPU, memory, I/O, database connections, or network resources.

Logical independence does not require separate deployed applications or services. Keep the modular-monolith architecture unless later approved otherwise.

### G0-DATA-08 — Feed Health & Selective Recovery: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves health-aware selective degradation and recovery.

Track feed health at an appropriate granularity, including source, symbol, stream, and data type.

Conceptual states:
- `HEALTHY`: Evidence supports the required freshness and integrity.
- `DEGRADED`: Delayed, incomplete, or uncertain observations; affected decision eligibility must be evaluated explicitly.
- `UNAVAILABLE`: Required data cannot be trusted for the intended decision.

Requirements:

- Monitor connection liveness, provider messages, relevant event sequencing, timestamp freshness, data continuity, and reconciliation results.
- Do not treat the absence of new trades alone as proof of a broken WebSocket connection.
- Apply source- and indicator-specific TTL/freshness policies consistent with TIME-09.
- On feed failure, block only decisions whose required data is unavailable; unaffected independent symbols/traders may continue.
- Open paper positions remain tracked as open during outages, with explicit monitoring gaps and uncertainty.
- Do not invent current prices, entry fills, exits, or retroactive real-time decisions.
- Attempt bounded reconnection, REST reconciliation, and gap recovery within provider budgets.
- Store recovery provenance and distinguish historical reconstruction from live observations.
- Replay recovered events chronologically and idempotently under PAPER-08, preserving ambiguity where the available evidence cannot resolve event order or fill outcomes.
- Log feed-state transitions, outage windows, affected traders/positions, recovery actions, and residual gaps.
- Keep independent failure domains where possible; one impaired feed should not unnecessarily stop unrelated healthy workloads.
- Do not promise uninterrupted monitoring or guaranteed recovery during provider-wide outages.
### Dependency and governance reconciliation
G0-GOV-01 above is a durable rule applying to all future cross-chat handoffs; provisional governance status does not make it optional or grant final G0 approval. Covered decision range must be recorded for every handoff. Owner confirmation in the current received handoff establishes PR #8 as the submitted baseline, updating earlier register uncertainty without rewriting its historical snapshots.
TIME-01–09 and DATA-01–04 are proposed in PR #8, not merged; PAPER-01–08 in PR #7 and dashboard in PR #6 are also proposals. These new rules preserve their point-in-time, specialist reporting, cost control, backfill/isolation, independent trader, ambiguity and recovery constraints without simplifying or replacing their owner extensions. The closed-bars-only feature default on current main is not permission to use a later-finalized candle as earlier live data: the new live-observation path requires exact available-at-decision evidence under proposed TIME-01/02. No missing or reconstructed data may be labeled live-known.
Unresolved: source/stream/endpoint selection and limits, reconnect/backoff/deadline/TTL/concurrency numbers, scheduling implementation, feed-health transition thresholds and workload objectives; actual Binance documentation/measurement required later, not invented here.

## G0 Integration reconciliation decisions — INT-01–06

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.** All six select C. Source: owner's visible read-only Integration Reconciliation handoff and subsequent Execute G0 Documentation Reconciliation authorization, 2026-10-20. Previous owner-confirmed submitted baseline: PR #10 / AQL-HO-20261020-003; exactly these six subsequent decisions and their recorded clarifications, no additional post-baseline decisions/addenda reported. Inaccessible originating chats were not inspected.

### G0-INT-01 — Decision-based staged reconciliation: C
Reconcile decisions and individual requirements incrementally, not whole-document replacements. Preserve all owner-approved provisional rules/addenda, historical context, dependencies, exceptions and provenance. A replacement consolidated PR is not the default remedy. The later explicit execution authorization permits this one dedicated reconciliation branch/PR; it does not authorize altering, closing or merging source PRs #6–#10. No source rule is silently finalized.

### G0-INT-02 — Dependency-based review order: C
Logical review order: PR #7 PAPER-01–08; then PR #8 TIME-01–09/DATA-01–04 including A–G; then PR #10 GOV-01/DATA-05–08. Independently compare PR #9 as GOV-01's historical source, identify duplication and avoid double application. Preserve PR #6's independent future dashboard requirement. Assess cross-dependencies across all five PRs. Review order is neither authorized merge order nor proof of safe sequential merging. Any technical merge sequence is a proposal requiring separate owner approval after dependency/conflict assessment.

### G0-INT-03 — Coverage, semantic verification and acceptance scenarios: C
Verify every decision/mandatory owner extension, including subrequirements, exceptions, dependencies, prohibitions and provisional status. For each record capture canonical ID, source PR/commit, requirement/subrequirements, affected documentation, dependency/conflict, preservation evidence, reconciliation action, verification status and remaining blocker. Future acceptance scenarios cover failure, ambiguity, timing, recovery and operations.
States: PASS = documentary evidence verified; BLOCKED = material unresolved conflict or missing mandatory requirement; DEFERRED = explicit owner-authorized deferral with reason and revisit condition; NOT TESTED = runtime/application behavior not exercised; UNVERIFIED = insufficient factual evidence. Documentation checks never imply CI/runtime/recovery/trading/acceptance success. Mandatory missing/contradictory/unresolved requirements prevent a complete reconciliation claim unless explicitly disclosed.

### G0-INT-04 — Point-in-time eligibility and strategy-specific fallback: C
Closed completed-candle values require completion AND demonstrated availability to the trader by decision time. Live trades/prices and provisional intrabar indicators are separate observation classes; record candle completion state, source, calculation/data version, market event time, system receipt time, effective availability time and decision time. Never use final candle high/low/close before completion and availability, or backdate later-recovered/revised values. Fallback to a qualifying completed candle is permitted ONLY when the trader's predeclared policy explicitly allows it; otherwise block the affected decision and record the reason. All essential inputs must also meet trader-specific freshness policy (TIME-09).
Availability must be established for that trader at that decision, not merely inferred from event time. Preserve immutable original decision/context snapshots; recovered facts and corrected values retain provenance and separate later event/version references. Maintain TIME-01/02/09 and DATA-05/08 consistency; no new timing constant or trading assumption is introduced.

### G0-INT-05 — GOV-01 semantic deduplication and historical preservation: C
PR #9 is a historical GOV-01 source, not automatically final authoritative wording. Compare actual #9 and #10 clauses before selecting one canonical definition; retain per-clause provenance and report material differences to the owner. At the inspected commits all ten numbered clauses and the trailing integration paragraph match exactly; one definition above is retained with both source references.
HANDOFF_REGISTER.md preserves distinct submissions, addenda, dates, references and states. Do not delete a historical event because two branches contain it; do not count one real-world event twice. A new branch/PR is not by itself a new historical handoff. Unresolved semantic differences require owner input.

### G0-INT-06 — Evidence-based current state versus historical event log: C
04_STATE.md is a dated, evidence-backed current snapshot. Each changing status records status/scope, verification timestamp and timezone where available, verification source, PR/branch/commit reference and uncertainty/conflict status. 05_WORK_LOG.md preserves what was known and recorded at each time, with sources; corrections are separate later events. Never rewrite an earlier OPEN observation to MERGED because a merge occurred later. A future merge requires a current-state update plus a new historical event under separate write authorization. BLOCKED means material conflict; UNVERIFIED means insufficient evidence. Never guess. Handoff lifecycle updates follow the same historical discipline.

## GOV-01 clause provenance and deduplication
At the source commits recorded below, PR #9 and PR #10 have identical GOV-01 status/scope, numbered clauses 1–10 (source lines 23–32), and trailing existing-template/direct-write paragraph (line 34). SESSION_PROTOCOL and COMMUNICATION_PROTOCOL also match. No material semantic difference was found. The single definition above is retained; no historical event is removed or counted twice.

| Clause | Preserved requirement | Sources / result |
| --- | --- | --- |
| 1 | Owner-confirmed actually submitted baseline plus addenda, not inferred draft/tool receipt | #9:23 = #10:23; PASS |
| 2 | Canonical register, GitHub and actually accessible records | #9:24 = #10:24; PASS |
| 3 | Complete since-baseline delta ledger | #9:25 = #10:25; PASS |
| 4 | Cross-check evidence, distinguish branches from main | #9:26 = #10:26; PASS |
| 5 | Each delta has one evidenced disposition | #9:27 = #10:27; PASS |
| 6 | No false claims of access/execution | #9:28 = #10:28; PASS |
| 7 | Disclose/request inaccessible material; no false completeness | #9:29 = #10:29; PASS |
| 8 | Final completeness audit, PASS versus COVERAGE GAP | #9:30 = #10:30; PASS |
| 9 | Distinct lifecycle states and dated register evidence | #9:31 = #10:31; PASS |
| 10 | Provisional status; no implicit final architecture/gate/trading approval | #9:32 = #10:32; PASS |

## Reconciliation coverage and integration evidence
Source main: `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. Source PRs remained OPEN/unmerged at `2026-10-20T10:47:11Z (13:47:11 Asia/Riyadh, UTC+03:00)`; the following branch content preserves their requirements, not their merge state. Source references are pinned so historical evidence is reproducible. DECISIONS contains full mandatory subrequirements; contract, risks, schemas and test policy retain their separate source sections.

| Source PR | Inspected source commit |
| --- | --- |
| [#6](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/6) | [93a1a537866fc20059d80f86061676e26fcd971e](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/93a1a537866fc20059d80f86061676e26fcd971e) |
| [#7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7) | [79bf0d902fab8fe766962425ca58d0d0528c152c](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/79bf0d902fab8fe766962425ca58d0d0528c152c) |
| [#8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8) | [19c5a747a568c727deb4cf7eb1320e30a7857241](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/19c5a747a568c727deb4cf7eb1320e30a7857241) |
| [#9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9) | [8886e69562b880e35c989009961959d4c9163791](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/8886e69562b880e35c989009961959d4c9163791) |
| [#10](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/10) | [8f33b50dbec18ff472a59c3505c2dbf6d43b104d](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/8f33b50dbec18ff472a59c3505c2dbf6d43b104d) |

The rows below use D=03_DECISIONS.md and T=10_TEST_POLICY.md at the source commit above. Local preservation evidence is the correspondingly named canonical heading and source addendum sections in this branch. C=01_CONTRACT, R=08_RISKS, S=09_DATA_SCHEMAS; all retain their PAPER/TIME-DATA/live-data sections. PASS is documentary only; runtime for every row is NOT TESTED.

| ID | Mandatory requirement / source D lines | Affected docs; source T evidence | Dependencies / conflict and action | Verification / blocker |
| --- | --- | --- | --- | --- |
| PAPER-01 | Conditional fill; no-fill/expiry/rejection; first eligible price after signal availability; #7 D25–38 | C/R/S; #7 T17–18 | TIME-01/02, INT-04; preserve causality | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-02 | Factual AMBIGUOUS; legitimate finer data; separate best/worst aggregates and cost uncertainty; #7 D39–56 | C/R/S; #7 T19,31 | DATA-06/08 event preservation; no scenario-as-realized | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-03 | Gross/net/stress, versioned fee provenance/effective dates; no fixed 0.01%; #7 D57–73 | C/R/S; #7 T20 | DATA-03/04 cost evidence; preserve missingness | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-04 | Provisional 1000 USDT, sensitivity examples, no approved live capital/risk policy; #7 D74–86 | C/R/S; #7 T21 | Liquidity evidence; no live authorization | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-05 | Independent traders/Shadows; within-trader dedup; overlap correlation; #7 D87–99 | C/R/S; #7 T22 | DATA-01/05/07 shared acquisition not shared strategy state | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-06 | Frozen strategy-specific validity; expiry differs from holding; #7 D100–112 | C/R/S; #7 T23 | TIME-08/PAPER-07; numeric expiry unresolved | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-07 | Predeclared/versioned exits; timestamp adjustments; independent counterfactual/TP1-stop/TP2 paths; #7 D113–144 | C/R/S; #7 T24–27,31 | TIME-08/DATA-07; partial quantities/horizons remain undecided | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| PAPER-08 | Durable pending/open state; chronological idempotent recovery; residual gaps/ambiguity; #7 D145–160 | C/R/S; #7 T28–31 | DATA-06/08; no fabricated live decisions | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-01 | Verified decision-time availability and no look-ahead; #8 D23–32 | C/R/S/roadmap; #8 T16 | INT-04 resolves unconditional fallback in D29 and blanket closed-bar wording | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-02 | Event/receipt/availability/decision clocks; explicit modeled replay; #8 D34–41 | C/R/S; #8 T16 | DATA-05/08; late recovery is not old live knowledge | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-03 | News publication versus ATLAS addition, observed/version/edit evidence; #8 D43–54 | C/R/S; #8 T17 | DATA-02/03; no fabricated historical ingestion | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-04 | Immutable shared data versions; corrections separate from simulator/code corrections; #8 D56–65 | C/R/S; #8 T18 | DATA-03/04/08; prior results preserved | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-05 | Separate development/OOS/forward; no combined score; nomination not promotion; #8 D67–77 | C/R/S; #8 T19,21 | Owner A/F; retain failed/selection history | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-06 | Regime-aware chronological walk-forward, untouched holdout, independent target occurrences; #8 D79–92 | C/R/S; #8 T20 | Owner A/F; off-target weakness not global rejection | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-07 | Rich all-opportunity immutable context, detector reliability, declared forward eligibility; #8 D94–119 | C/R/S; #8 T20–22 | Owner B/F; TIME-09/DATA-01 cost/freshness | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-08 | Later regime changes append; frozen exits/counterfactual isolation; #8 D121–130 | C/R/S; #8 T23 | PAPER-07; no retroactive closure | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| TIME-09 | Per-indicator freshness, essential/optional inputs, missed reasons; #8 D132–143 | C/R/S; #8 T24 | DATA-07/08 and INT-04 fallback must pass policy | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-01 | Shared collector/cache/planned dedup; local calculation; provider-specific budgets; #8 D147–158 | C/R/S; #8 T25 | DATA-05/07, owner E; no invented limits | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-02 | Monitoring priority; separate pre-operational resumable backfill; #8 D160–178 | C/R/S/roadmap; #8 T26,31 | Owner C/D; no synchronous archive dependency | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-03 | Hybrid shared archive/index/provenance/selective retrieval; #8 D180–194 | C/R/S; #8 T27 | Owner C/E; Parquet candidate only, paid gates | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-04 | Incremental idempotent repair, budgets, independent queues/resource isolation; #8 D196–229 | C/R/S/roadmap; #8 T28–31 | DATA-06/07; no fixed 30-second SLA | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-05 | Central WS/REST/cache budgets and live/recovered provenance; #10 D42–60 | C/R/S; #10 T19–20,24 | TIME-01/02/09 and INT-04; no retroactive live facts | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-06 | Bounded nonaccumulating runs; safe scanner coalescing retains required events; #10 D61–81 | C/R/S; #10 T21–22 | PAPER-08/DATA-04/08; monitor/audit sequences retained | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-07 | Independent higher-priority monitor, lower-priority scanner; shared foundation; #10 D82–108 | C/R/S; #10 T23–26,28 | PAPER ambiguity/exits; modular monolith unchanged | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| DATA-08 | Scoped health/TTL, selective block, positions open with gaps, bounded recovery; #10 D109–135 | C/R/S; #10 T25–29 | TIME-09/PAPER-08; no guaranteed recovery or fictitious fills | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| GOV-01 | Ten clauses and durable continuity; #9/#10 D17–34 | Startup/session/communication/template/register/C/R/S; #10 T16–18 | INT-05 semantic equality; distinct events preserved once | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner A | Specialist target/off-target counts/net costs/risk/uncertainty/sample adequacy; no combined score; #8 D235–236 | C/R/S; #8 T19–21 | TIME-05–07; insufficient evidence never proven profit | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner B | Complete feasible all-opportunity immutable context; three provenance classes; #8 D238–239 | C/R/S; #8 T22–24 | TIME-01/02/07–09; later changes append | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner C | Separate pre-operational library; scope/coverage/gaps/versions; same incremental library; #8 D241–242 | C/R/S/roadmap; #8 T26 | DATA-02–04; completeness requires scoped verification | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner D | Hard isolation, independent queues/bounded concurrency/shared budgets/resource reservations; #8 D244–245 | C/R/S; #8 T29–30 | DATA-01/02/04/06/07; background yields first | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner E | Budget monitoring, prior paid approval, provider/local method/freshness/limitations; #8 D247–248 | C/R/S; #8 T27 | TIME-09/DATA-01/03/04; no zero-cost guarantee | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner F | Independent specialists, multiple regimes/occurrences, forward eligible at actual time; #8 D250–251 | C/R/S; #8 T19–21 | TIME-05–07; historical never substitutes forward | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Owner G | Pre-PR cross-document completeness and traceability; #8 LOG73–78 and current matrix | D/C/R/S/T; this documentary audit | A–F verified; runtime NOT TESTED; no new decision ID | PASS documentary; runtime NOT TESTED; unresolved implementation parameters disclosed |
| Dashboard | Positions/lifecycle/traders/Lab/Shadow/history/health; shared Telegram records; secure read-only; #6 roadmap10–34 | Roadmap; #10 S23 | Requirement preserved independently; frontend/API/infra not selected | DEFERRED implementation by owner until operational data; documentary PASS |
| INT-01 | Visible owner handoff and Execute authorization; full canonical INT-01 section above | D; C/R/S/T as applicable; STATE/LOG/register/protocols | Included; six-decision delta, provisional status and prohibitions retained | PASS documentary; runtime NOT TESTED |
| INT-02 | Visible owner handoff and Execute authorization; full canonical INT-02 section above | D; C/R/S/T as applicable; STATE/LOG/register/protocols | Included; six-decision delta, provisional status and prohibitions retained | PASS documentary; runtime NOT TESTED |
| INT-03 | Visible owner handoff and Execute authorization; full canonical INT-03 section above | D; C/R/S/T as applicable; STATE/LOG/register/protocols | Included; six-decision delta, provisional status and prohibitions retained | PASS documentary; runtime NOT TESTED |
| INT-04 | Visible owner handoff and Execute authorization; full canonical INT-04 section above | D; C/R/S/T as applicable; STATE/LOG/register/protocols | Included; six-decision delta, provisional status and prohibitions retained | PASS documentary; runtime NOT TESTED |
| INT-05 | Visible owner handoff and Execute authorization; full canonical INT-05 section above | D; C/R/S/T as applicable; STATE/LOG/register/protocols | Included; six-decision delta, provisional status and prohibitions retained | PASS documentary; runtime NOT TESTED |
| INT-06 | Visible owner handoff and Execute authorization; full canonical INT-06 section above | D; C/R/S/T as applicable; STATE/LOG/register/protocols | Included; six-decision delta, provisional status and prohibitions retained | PASS documentary; runtime NOT TESTED |

### Reconciliation dispositions and future integration
- Resolved documentary conflicts: blanket closed-bar prohibition replaced by exact point-in-time eligibility; unconditional fallback replaced by trader-policy-specific permission; one identical GOV-01 definition retained; source log events combined once; stale current STATE replaced by a dated evidence snapshot. Original source branches remain unchanged and OPEN.
- Current limitation: Issue #1 contains an outdated sentence describing PR #2 as unmerged. It is disclosed in STATE and not edited: separate Issue-write approval required. Other chats remain inaccessible; no exhaustive cross-chat completeness claim. Providers, constants, implementation acceptance and final G0 review remain unresolved, not silently decided.
- Review dependencies are #7 -> #8 -> #10 with independent #9 comparison and #6 preservation. The owner now explicitly authorizes one dedicated reconciliation PR incorporating source clauses; this is not a merge/rebase of those source PRs, nor a default replacement policy for future work.
- Proposed next sequence: independently review this PR's decision/subrequirement coverage against the pinned sources; obtain separate owner authorization for a merge/disposition plan. If approved as the integration vehicle, merge this documentation PR only, then obtain explicit owner direction for each overlapping original PR (no blind sequential merging or automatic closure). Alternative source-PR sequencing would require separately approved updates and renewed overlap review. Nothing here authorizes either path.
- No substantive unresolved owner-policy contradiction was found after applying INT-01–06; any later material contradiction is BLOCKED and must be referred to the owner, never filled by an invented rule. Runtime acceptance, recovery/load tests, CI and strategy performance are NOT TESTED by this task. G0/Issue #1 remain OPEN.

## G1 secretarial data architecture — provisional owner clarifications
Project: ATLAS Quant Lab / AQL-CRYPTO-RESEARCH-001. **All G1-ARCH-01–11 decisions are PROVISIONAL until final G0 owner approval. G0 remains OPEN; a G1-prefixed decision does not authorize entry into implementation.**
Source: owner-submitted "ATLAS Quant Lab — G1 Secretarial Data Architecture Consolidation" attachment received 2026-10-20; normalized-text SHA-256 `47129ebbdf7d89b256f55faf6968692281fae3575f8f4efc159224c0164f4961`. The source sections below retain every supplied decision and correction verbatim. Option C is recorded where the source explicitly states it; no missing alternative is invented. Previous returned Work result: AQL-HO-20261020-004 / PR #11, OPEN/unmerged at `fb79e13b58c91c6b53a7e0489114adcdcc577d15`. The supplied post-result delta is G1-ARCH-01–11 plus the owner merge-deferral instruction; other chats are inaccessible, not inspected.

### G1-ARCH-01 — Shared Data Inbox and two secretarial departments

Use the owner's **secretarial office** architecture inside the Python modular monolith.

A shared market-data collector acquires Binance Spot USDT data centrally, with deduplicated WS/REST access, cache and provider budgets.

Data enters a common **Data Inbox** once.

Two logically independent departments consume it:

- **Fast Lane:** copies/routes current market observations to specialist office secretaries without waiting for archival review.
- **Slow Lane:** preserves raw observations, organizes historical records, conducts deeper quality assessment, and attaches quality annotations.

Do not serialize Fast Lane behind Slow Lane. Do not build redundant independent Binance collectors for each office. Neither department makes strategy decisions.

The Fast Lane still performs minimal safety, timing, provenance and eligibility checks before making data usable for decisions.

### G1-ARCH-02 — Adaptive resource priority

Provisional option C.

Monitor Fast Lane response latency, resource pressure and queue/backlog metrics together.

Throttle, pause or yield Slow Lane's heavy processing when needed to protect Fast Lane; resume with hysteresis after stability.

Priority applies to CPU, memory, I/O, network, database and shared provider budgets, not just CPU.

Protect open-position data delivery above broad-universe scanning. Avoid starving other office deliveries unnecessarily.

Do not invent numerical thresholds, latency guarantees, concurrency settings or fixed SLAs; document them as parameters requiring measurement.

### G1-ARCH-03 — Durable, reusable Data Inbox

The Inbox must survive process restarts and power loss for records **successfully committed to durable storage**.

The owner requires a reusable temporary holding box:

1. Receive and durably register observations.
2. Make them available to Fast Lane immediately after the necessary receipt/commit boundary.
3. Keep them available for Slow Lane independently of Fast Lane consumption.
4. Slow Lane archives raw observations and quality/provenance information.
5. Delete or reclaim Inbox records **only after confirmed durable archival**, with crash-safe acknowledgment and idempotent recovery.
6. Reuse reclaimed capacity for new records.

Pausing Slow Lane must not stop lightweight Inbox reception. Specify bounded capacity, disk-full/backpressure behavior, corruption checks, recovery checkpoints and alerting.

Avoid claiming zero data loss under all failure conditions. Explicitly distinguish received-and-committed records from messages never received during an internet outage.

Choose no storage engine or physical schema without separate authorization.

### G1-ARCH-04 — Shared Trader Secretariat with one logical secretary per trader

Provisional option C.

Use one shared coordination/data-service layer and a dedicated **logical secretary for each independent trader**.

Each secretary knows its trader's declared inputs, timing/freshness requirements, subscriptions, current positions, and data-quality status.

No duplicate provider collection, no shared mutable strategy decisions, no cross-trader blocking, and no secretary deciding entries/exits.

Logical isolation does not require one process/server per trader.

### G1-ARCH-05 — Open-position data first, with nonblocking fan-out

This decision includes mandatory owner corrections.

Maintain an indexed list of open positions, their owning traders, and the current data fields required by each position's frozen/versioned strategy and exit rules.

As market observations arrive, quickly match them to open positions and deliver updated relevant values to **the owning trader's secretary**, then to that trader.

**The trader itself evaluates and decides** whether to hold, close, adjust, respond to TP1, stop-loss or changing market conditions.

Neither the secretariat nor a centralized Position Monitor may independently decide a trade outcome or create a fill. Any existing Position Monitor must be reconciled as a high-priority data/state/observation function that supports the owning trader's decision logic, while preserving previously agreed monitoring and recovery responsibilities.

Crucial: matching/extracting open-position data is a **high-priority branch, not a blocking gate**.

The same observation must be available to Scanner, other traders and other offices through independent, nonblocking fan-out without waiting for position matching, trader analysis or exit decisions.

Preserve ordering and all decision-critical events; never coalesce away potential TP/SL touches, fills, ambiguity or replay evidence. Measure per-office delivery lag and surface degradation rather than promise mathematically zero delay.

If multiple traders hold the same symbol, reuse one market observation while preserving independent policies and position states.

### G1-ARCH-06 — Adaptive Scanner Secretariat

Provisional option C.

Scanner's secretary distributes data according to each declared scan stage:

- Immediate updates where the scan requires actual live observations.
- Bounded aggregation or scheduled updates where the stage only needs completed candles or other slower inputs.

Scanner independently evaluates opportunities. Its secretary does not generate trading signals.

Keep scan workloads bounded/adaptive, with lower priority than open-position service, while avoiding unnecessary delivery delays to other offices.

No provisional intrabar observation may masquerade as a completed candle.

### G1-ARCH-07 — Research Lab Secretariat

Provisional option C.

Provide two distinct research inputs:

- **Historical:** versioned archive data, quality annotations, provenance, coverage, gaps and recovery history.
- **Forward/Shadow:** genuinely available live observations, with actual observation and receipt/availability times.

Preserve historical development, historical OOS and prospective forward results as distinct evidence classes, never a blended score or backdated Shadow result.

Heavy historical research must yield to live workloads. Forward/Shadow experiments must record interruption, lag and missing observations honestly rather than invent continuous coverage.

### G1-ARCH-08 — Data quality and office-specific eligibility

Provisional option C.

Secretariat performs common validation and annotates data with source, version, quality, freshness, finality, event time, receipt time, availability time and relevant gap/health status.

Each trader/office applies its own **predeclared, versioned eligibility policy**.

Invalid/stale inputs are not presented as healthy. A qualifying last completed-candle fallback is allowed only if that trader's frozen policy explicitly permits it and freshness/availability checks pass; otherwise block the affected decision and record the reason.

Late deeper quality assessments may add corrections/annotations with lineage but must never retroactively alter what was known to a past decision.

### G1-ARCH-09 — Safe restart and recovery

Provisional option C with explicit owner requirements:

- No duplicate data or duplicated fills, closes, accounting or alerts.
- Detect every identifiable coverage gap and attempt to recover every recoverable gap.
- Recover durable Inbox state and archival acknowledgment/checkpoints idempotently.
- Restore open positions and reconcile authoritative execution state where applicable before taking actions dependent on that state.
- Reconnect/validate current market feeds and resume eligible live data service without waiting for historical archival catch-up.
- Resume Slow Lane's backlog and quality work under resource limits.
- Record irrecoverable gaps explicitly; never falsely mark a dataset complete.

Recovered historical observations cannot be treated as if they were available during the outage.

### G1-ARCH-10 — Gap ledger and budgeted recovery

Provisional option C.

Slow Lane owns the gap ledger and manages bounded, resumable, selective recovery through the **shared provider-budget/acquisition authority**.

Track missing symbol/stream/time range, source, attempts, evidence, recovered coverage, remaining gaps and quality status.

Deduplicate using stable source/event identity appropriate to the data type, not merely equal price values.

Verify completeness against declared coverage before clearing a gap. Some historical candles may be recoverable while some exact tick/trade sequences are not.

Gap recovery must yield to live needs, respect Binance limits and preserve original availability timelines.

### G1-ARCH-11 — Stop-loss crossing discovered after an outage

Provisional option C, explicitly separated by execution mode.

**Current paper phase:**

If recovered data shows a TP/SL threshold was crossed while ATLAS was disconnected, record the factual crossing, uncertainty and monitoring gap. Do **not** invent a historical fill, pretend the trader observed it live, or backdate a strategy decision.

On recovery, deliver current market and recovered historical facts separately to the owning trader. The trader applies its predeclared recovery/exit policy to information actually available at that time.

Preserve PAPER-02 factual `AMBIGUOUS` outcomes and isolated best/worst research scenarios when sequence or execution cannot be established.

**Future real execution (not authorized now):**

Prefer dual protection where supported: exchange-side protective orders plus trader-level monitoring/recovery. After reconnect, reconcile actual order states, trades, fills and partial fills with Binance before updating execution truth.

A historical price touch alone does not prove an exchange order executed.

No real trading, live order placement or funded account authorization is implied.

### Explicit compatibility interpretation — recovery and responsibility
The owner clarification G1-ARCH-05 refines DATA-07's earlier "evaluate" wording: the high-priority monitor retains state, observation delivery, ordering, gaps and recovery responsibilities; the owning trader alone applies its frozen strategy/exit/recovery policy. Shared PAPER-07 exit-evaluation logic may be used by that trader; a common engine is not a second strategy decision-maker. Secretaries do common validation, routing and quality annotation, not entry/exit decisions. Open-position routing is a high-priority independent branch, never a gate before Scanner/other offices receive the same observation.
PAPER-08/DATA-08 recovery preserves facts, known policy versions, event identities, gaps and idempotency; G1-ARCH-11 forbids treating a recovered TP/SL touch alone as a historical fill or backdated strategy decision. Previously recorded accounting may be reconciled only against legitimate evidence, not an invented price-touch fill. Separate hypothetical best/worst PAPER-02 research remains labeled hypothetical, not confirmed execution. Current/recovered information reaches the owning trader in separate evidence classes; its predeclared policy governs decisions at the actual recovery-time availability. Future exchange-state reconciliation describes a conditional future mode and authorizes no real execution.
The durable Inbox commit boundary precedes decision-usable Fast Lane delivery; it does not require completion of deep quality review or archival work. Fast Lane still performs minimal safety/timing/provenance/eligibility checks, including trader-specific fallback constraints. Lightweight reception can continue while heavy Slow Lane work is paused, subject to bounded durable capacity: no promise of unlimited reception, zero latency, or lossless delivery of never-received/uncommitted messages is made. Storage engine, physical schema, capacity/pressure thresholds, arbitration details and hysteresis parameters remain unselected.

## G1 delta ledger, compatibility and exact destination traceability
Verified sources: #11 `fb79e13b58c91c6b53a7e0489114adcdcc577d15` and main `ed188f1902d397fe74613dd966c5a3e88b32f8c0` at 2026-10-20T13:38:18Z / 16:38:18 Asia/Riyadh (UTC+03:00). Source line references below are pinned to #11, not future line numbers. Every source requirement remains canonical alongside the explicitly authorized role clarifications. No substantive contradiction remains unresolved within the supplied decisions; missing implementation parameters are disclosed, not invented. Other-chat coverage is not established.

### Branch/base choice and merge deferral
Candidate main `ed188f1902d397fe74613dd966c5a3e88b32f8c0` alone lacks #11's reconciled content; recreating it risks omissions. Candidate pinned #11 `fb79e13b58c91c6b53a7e0489114adcdcc577d15` preserves complete prior content and history by ancestry. Selected new isolated branch from #11, PR target main: nine-file G1 delta against #11, thirteen-file cumulative diff against main including the inherited prior reconciliation. Existing PRs #6–#11 and their branch refs remain unchanged. This is an owner-authorized new documentation proposal, not proof #11 is merged. All source merges remain owner-deferred; no PR is automatically superseded, closed or approved.

| Delta item | Mandatory owner requirement/correction | Earlier source and compatibility judgment | Exact destination section | Disposition / evidence / owner resolution |
| --- | --- | --- | --- | --- |
| G1-ARCH-01 | Shared Inbox; independent Fast/Slow lanes, minimal safety; no duplicate collector | DATA-01/05/07, #11 D426–492; Compatible refinement; shared acquisition and no lane strategy authority preserved | DECISIONS: G1-ARCH-01 — Shared Data Inbox and two secretarial departments; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-01 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-02 | Latency+backlog+all-resource adaptive priority, hysteresis, no numeric SLA | DATA-02/04/06/07, #11 D303–372,445–492; Compatible; all-resource budgets and monitoring priority retained | DECISIONS: G1-ARCH-02 — Adaptive resource priority; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-02 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-03 | Committed-only durability; independent consumers; archive ack before reclaim; bounded capacity | PAPER-08/DATA-04/06/08, #11 D145–158,339–372,445–519; Compatible refinement; lightweight reception distinct from heavy pause; no storage engine selected | DECISIONS: G1-ARCH-03 — Durable, reusable Data Inbox; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-03 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-04 | One logical secretary per trader, shared coordination, independent strategy states | PAPER-05/DATA-05/07, #11 D87–98,426–492; Compatible; no process-per-trader or secretary strategy decisions | DECISIONS: G1-ARCH-04 — Shared Trader Secretariat with one logical secretary per trader; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-04 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-05 | Indexed owning positions/required fields; trader decides; nonblocking fan-out; retain events | DATA-07 #11 D466–492; C57; T71; Explicit owner correction resolves monitor-evaluate ambiguity; three minimal source clauses refined; no unresolved authority conflict | DECISIONS: G1-ARCH-05 — Open-position data first, with nonblocking fan-out; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-05 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-06 | Stage-specific live versus completed-candle routes; bounded Scanner; no secretary signals | TIME-01/02/09/INT-04/DATA-06/07, #11 D166–184,275–286,445–492,539–541; Compatible; no intrabar-to-final relabel or global fan-out gate | DECISIONS: G1-ARCH-06 — Adaptive Scanner Secretariat; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-06 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-07 | Separate historical and live Forward/Shadow input/evidence; interruptions explicit | TIME-04–08/owner A/F, #11 D199–273,378–395; Compatible; no blended historical/forward score or backdating | DECISIONS: G1-ARCH-07 — Research Lab Secretariat; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-07 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-08 | Common quality plus predeclared versioned office eligibility; qualified fallback; late lineage | TIME-01/02/09/INT-04, #11 D166–184,275–286,539–541; Compatible; original snapshots immutable and only policy-authorized fresh/available fallback | DECISIONS: G1-ARCH-08 — Data quality and office-specific eligibility; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-08 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-09 | Idempotent restart; restore positions/authoritative state; current feeds before archive catch-up | PAPER-08/DATA-05–08, #11 D145–158,426–519; Compatible refinement; current eligible service independent of backlog; no invented continuity | DECISIONS: G1-ARCH-09 — Safe restart and recovery; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-09 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-10 | Slow-owned gap ledger, shared budget, stable event identity, scoped completeness | DATA-01–04/08/owner C–E, #11 D290–372,384–392,493–519; Compatible; recoverable candles do not prove exact tick/trade order | DECISIONS: G1-ARCH-10 — Gap ledger and budgeted recovery; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-10 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| G1-ARCH-11 | Recovered paper crossing not fill; trader recovery policy; AMBIGUOUS; future actual execution evidence | PAPER-02/08/DATA-08, #11 D39–55,145–158,493–519; S23; Explicit owner clarification; facts/accounting evidence distinguished from invented fills, no real execution permission | DECISIONS: G1-ARCH-11 — Stop-loss crossing discovered after an outage; CONTRACT: Provisional secretarial data-service invariants; SCHEMAS: Conceptual secretarial data lifecycle; RISKS: Secretarial architecture residual risks; TEST_POLICY: matching G1-ARCH-11 acceptance row | INCLUDED / PASS documentary; runtime NOT TESTED. No further owner policy resolution required for this clarification; implementation separately gated. |
| Owner merge deferral | Defer all merges #6–#11; do not modify/close/rebase/retarget/overwrite their branches | Source owner instruction section 2; governance instruction, no extra ADR | STATE: Current evidence ledger; HANDOFF_REGISTER: handoff 005 owner merge deferral; ROADMAP: Provisional G1 preparation | INCLUDED / DEFERRED by owner; ACTIVE until separate explicit authorization; no source mutation |

Destination paths: DECISIONS=03_DECISIONS.md, CONTRACT=01_CONTRACT.md, SCHEMAS=09_DATA_SCHEMAS.md, RISKS=08_RISKS.md, TEST_POLICY=10_TEST_POLICY.md, STATE=04_STATE.md. Exact canonical headings identify sections despite future line shifts. Each G1 canonical section preserves the entire supplied decision, including every sub-bullet, exception and prohibition.

### Preservation and unresolved evidence
PAPER-01–08, TIME-01–09, DATA-01–08, GOV-01, INT-01–06, owner A–G, independent future dashboard, handoffs 001–004 and every prior WORK_LOG observation are retained from #11. Owner clarifications G1-ARCH-05/11 refine responsibility and evidence interpretation openly; they do not silently remove monitoring, recovery, ambiguity or accounting safeguards. Full clause-level provenance remains in the inherited #11 matrix. Three existing monitor-authority clauses in DECISIONS/CONTRACT/TEST_POLICY were minimally corrected; historical source descriptions and source commit references are retained as provenance.
Documentary verification states: PASS for checked requirements; BLOCKED for material unresolved contradiction; DEFERRED only for owner-authorized deferral with revisit condition; UNVERIFIED for unseen submissions/chats or insufficient factual evidence; NOT TESTED for runtime behavior. No runtime/CI success follows from documentation consistency.
Remaining unselected parameters: Inbox storage engine/physical schema, durability implementation details, bounded capacity/disk-full/backpressure response, corruption/recovery mechanics, thresholds/hysteresis/concurrency/latency targets, exact source limits and quality policies. Separate implementation approval and measurement required. Source Issue #1 stale PR #2 sentence remains disclosed and unchanged. No paid resource or real execution authorized.
Next: owner reviews this new documentation PR and the twelve delta dispositions. All merges remain deferred pending separate explicit authorization; no G0 closure, strategy promotion, deployment, source PR action or application implementation follows automatically.

## G1 central screening, progressive evidence and computation reuse — ARCH-12–20
Project: ATLAS Quant Lab / AQL-CRYPTO-RESEARCH-001. **PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.** Source: directly received owner Consolidated G1 Architecture Handoff, 2026-10-21. Previous owner-submitted handoff: AQL-HO-20261020-005 / PR #12, head `1948132315ee6a5b3174c56f767c84d1063251cd`, independently verified OPEN/unmerged. The reported subsequent delta is G1-ARCH-12–20 and the cross-cutting constraints supplied with these decisions; no missing options or unreported addenda are invented. Other originating conversations are inaccessible, not inspected. G0 remains OPEN; no G1 implementation is authorized.

### G1-ARCH-12 — Personalized central scanner screening
One central Scanner evaluates trader-specific preliminary filters and routes relevant candidates. Shared market collection is not duplicated. Each trader's secretary supplies further data. Only the trader decides whether to trade.

### G1-ARCH-13 — Two strategy-defined data lists
Each trader declares mandatory Scanner screening filters and additional secretary-provided decision inputs. Additional inputs may themselves be mandatory for entry. Missing, stale or invalid mandatory evidence cannot be treated as passing. Version the rules and preserve historical decision context.

### G1-ARCH-14 — Stage-aware progressive prefetch
Begin preparing trader-specific data from the earliest qualifying candidate stage, not only after READY. Increase preparation as the candidate develops, reuse shared results, protect the Fast Lane and open-position monitoring, and preserve point-in-time correctness.

### G1-ARCH-15 — Trader-specific Scanner stages
Each trader defines its own stages, qualification criteria and transitions. The central Scanner maintains independent `(trader, symbol)` candidate states while sharing identical computations. Stages are not necessarily linear or mandatory in sequence.

### G1-ARCH-16 — Fast/Slow service routing and latency accountability
The Fast Lane protects live market-data delivery and open-position monitoring. The Slow Lane owns heavy historical analysis, archival work, recovery and historical-performance requests. Already-available historical results may be returned from an eligible cache without unnecessary Slow Lane waiting. Trader secretaries coordinate requests without blocking live fan-out.

Measure separately: ingestion-to-delivery latency, historical-request latency, mandatory-data readiness, strategy waiting time and trader decision-processing latency. Do not attribute upstream data or analysis delays to the trader.

### G1-ARCH-17 — Historical precomputation from WATCH
The Slow Lane progressively prepares historical evidence from the earliest relevant candidate stage, reuses common results and updates them when required. On candidate exit or demotion, reduce unnecessary prefetch while preserving shared data, archival integrity and other traders' requirements.

### G1-ARCH-18 — Progressive evidence delivery and readiness
Deliver available data progressively. Track readiness, freshness and eligibility per trader, symbol and decision. READY in the Scanner does not mean mandatory entry evidence is complete, nor does it authorize a trade. Only the trader decides, under its versioned strategy requirements.

### G1-ARCH-19 — Deduplicate identical computations
Share results only when symbol, timeframe, calculation definition, parameters, version, input provenance, candle finality and temporal context match. Preserve independent trader decisions and avoid cross-strategy mutable state.

### G1-ARCH-20 — Computation classification and non-linear transitions
Classify each calculation/result as `LIVE` or `HISTORICAL` for update and reuse planning, with explicit timestamps, validity, input range, provenance, completeness and version. Classification alone is not a freshness guarantee, and historical does not necessarily mean slow.

Allow direct transitions such as WATCH → READY whenever the trader's actual Scanner rules permit. Do not require passage through BUILDING or delay genuine Scanner state transitions. Adjust prefetch priorities immediately, reuse valid results, and apply any cooldown only to unnecessary heavy scheduling—not to market-data delivery, position protection or strategy-defined state transitions.


### Compatibility interpretation and authority boundaries
The central Scanner owns preliminary screening and candidate transitions for each (trader, symbol); this refines the generic independent Scanner wording in DATA-07 and G1-ARCH-06 without granting trade authority. A secretary supplies/co-ordinates inputs and quality/readiness evidence; the owning trader alone applies its versioned strategy for entry, hold, adjustment and exit. A screening pass or Scanner READY does not satisfy a missing mandatory secretary input, nor require the trader to open a position. Candidate state is not the existing WATCH/ARMED/TRIGGERED/CLOSED trade lifecycle; identical names do not merge those state machines.
Two lists distinguish screening requirements from decision-time inputs, not mandatory from optional. The strategy explicitly marks mandatory entry evidence, its version/freshness/quality/finality/availability requirements and permissible fallback; missing, stale, invalid or unproven mandatory evidence cannot pass. INT-04's explicit trader-policy fallback restriction is unchanged. Earlier prefetched data cannot be presented as fresh or available merely because preparation started earlier; later results/recovered facts never become past knowledge.
The earliest relevant stage is trader-defined: WATCH is a supplied example, not a universal mandatory stage. Direct WATCH -> READY is valid only when that trader's actual screening rules allow it; BUILDING is not compulsory. Real stage transitions are recorded when they occur and priorities adapt immediately. Work-reduction/cooldown applies only to unnecessary heavy scheduling, never to data fan-out, position protection or genuine strategy-defined transitions. Demotion/exit changes one consumer's demand; shared objects, other active consumers, archive integrity and history remain preserved.
Slow Lane owns historical analysis, archive, recovery and historical-performance service orchestration. Ownership does not require eligible cached historical results to wait for heavy work, or eligible live feed delivery/restart to wait for historical catch-up. Preserve G1-ARCH-09's required safety restoration, current-feed validation and independent live resumption; recovery work remains budgeted/prioritized according to its operational dependency, not an all-work serial Slow queue. Exact internal scheduling/ownership handshakes remain implementation parameters, not new architecture selections.
LIVE/HISTORICAL is a calculation/result update-and-reuse classification, distinct from actual observed-live/reconstructed/retrospective provenance and physical lane identity. It grants no freshness, speed, finality, completeness or eligibility. Reuse requires all matching keys in ARCH-19 plus the intended consumer's temporal/eligibility checks; equal values or a shared symbol alone do not establish equivalence. Preserve independent trader/candidate decisions and immutable original context.

## ARCH-12–20 delta ledger and consistency review
Sources: current visible owner Consolidated G1 Architecture Handoff; pinned prior PR #12 `1948132315ee6a5b3174c56f767c84d1063251cd`, itself descending from #11 `fb79e13b58c91c6b53a7e0489114adcdcc577d15`; main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. Source line numbers below refer to #12, not future files. Canonical decision sections above retain each supplied requirement; every item has disposition INCLUDED. No unprovided owner option/decision is invented.

| Decision | Mandatory intent / clarification | Earlier source / compatibility or conflict review | Exact destination sections | Outcome / owner resolution |
| --- | --- | --- | --- | --- |
| G1-ARCH-12 | Central personalized screening and trader-only trade authority | DATA-07; G1-ARCH-04/06 (source #12 D466,683,715); Compatible refinement: Scanner candidate rules are not trader entry/exit decisions | DECISIONS: G1-ARCH-12 — Personalized central scanner screening; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-12 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-13 | Two versioned lists; secretary inputs may be mandatory; no stale/missing/invalid pass | TIME-09/INT-04; G1-ARCH-08 (source #12 D275,539,743); Compatible; lists separate responsibility, not mandatory/optional status | DECISIONS: G1-ARCH-13 — Two strategy-defined data lists; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-13 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-14 | Prepare from earliest qualifying stage, increase with development, share and protect live path | DATA-01–04/06/07; G1-ARCH-02/06/07; Compatible; prefetch is no entry permission or past availability evidence | DECISIONS: G1-ARCH-14 — Stage-aware progressive prefetch; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-14 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-15 | Independent (trader,symbol) stages/edges, sharing computations, no mandatory linear order | PAPER-05; DATA-07; G1-ARCH-04/06; Compatible; candidate stages explicitly separate from trade lifecycle | DECISIONS: G1-ARCH-15 — Trader-specific Scanner stages; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-15 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-16 | Fast/Slow routing, prompt eligible cache history, five distinct latency attributions | DATA-04–08; G1-ARCH-01–03/05/07/09/10; Compatible with ownership clarification: historical recovery does not impose archival queue on eligible live restart; exact scheduling unselected | DECISIONS: G1-ARCH-16 — Fast/Slow service routing and latency accountability; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-16 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-17 | Early historical precomputation, refresh and demand reduction without harming shared consumers/archive | DATA-02–04; G1-ARCH-02/07/10; Compatible; WATCH is applicable strategy stage, not universal imposed stage | DECISIONS: G1-ARCH-17 — Historical precomputation from WATCH; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-17 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-18 | Progressive evidence, per-decision readiness; Scanner READY is neither completeness nor trade command | TIME-09/INT-04; G1-ARCH-05/08; Compatible; explicit mandatory-evidence gate belongs to versioned trader policy | DECISIONS: G1-ARCH-18 — Progressive evidence delivery and readiness; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-18 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-19 | Full computation identity and temporal/finality match, independent strategy state | DATA-01/05/07; TIME-01/02/04; PAPER-05; Compatible; matching identity plus consumer eligibility required, equal price not identity | DECISIONS: G1-ARCH-19 — Deduplicate identical computations; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-19 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |
| G1-ARCH-20 | LIVE/HISTORICAL planning metadata; direct transitions; cooldown only unnecessary heavy work | TIME-01/02/09; INT-04; G1-ARCH-02/06/08; Compatible; planning class distinct from provenance/freshness, no new universal stage or speed guarantee | DECISIONS: G1-ARCH-20 — Computation classification and non-linear transitions; CONTRACT: Provisional central screening and progressive evidence; SCHEMAS: Conceptual Scanner, readiness and reuse records; RISKS: Progressive screening/readiness residual risks; TEST_POLICY: matching G1-ARCH-20 row | PASS documentary / INCLUDED; runtime NOT TESTED. No unresolved policy contradiction; implementation parameters require later approval. |

Paths: DECISIONS=03_DECISIONS.md; CONTRACT=01_CONTRACT.md; SCHEMAS=09_DATA_SCHEMAS.md; RISKS=08_RISKS.md; TEST_POLICY=10_TEST_POLICY.md. Measurement-specific destination: SCHEMAS "Proposed latency measurement specification — G1-ARCH-16/18/20", with five distinct timestamp/attribution rows and corresponding negative scenarios. Roadmap preparation, STATE evidence snapshot, append-only WORK_LOG and HANDOFF_REGISTER record lifecycle and scope.

### Conflict dispositions, preservation and approval gates
No prior canonical rule is removed or silently superseded. Generic Scanner opportunity wording is refined as preliminary screening, preserving trader-only strategy/entry/exit authority. Previous secretary input routing is refined into two lists without optionalizing mandatory evidence. Earlier bounded Scanner/coalescing allows safe work sharing but never loses decision-critical events or forces a linear stage graph. Prior recovery ownership/independent live resumption remains intact; a service owner is not a mandatory heavy-queue dependency. Cache reuse is qualified, not a universal historical-speed or freshness guarantee.
PAPER-01–08, TIME-01–09, DATA-01–08, GOV-01, INT-01–06, G1-ARCH-01–11, owner A–G, future deferred dashboard and all prior handoff/log history are preserved. Cross-cutting constraints: trader-only authority; no fabricated data/backdated availability/fills; independent nonblocking Fast fan-out; adaptive Slow throttling; durable Inbox and independent consumers/crash-safe replay; monitoring priority; immutable provenance/quality/gaps/versioned eligibility; no invented numeric targets/TTLs/thresholds/capacity guarantees; all approvals remain provisional until final owner G0 approval.
Branch alternatives: main alone would require recopying essential unmerged #12 documentation; chosen isolated branch inherits pinned #12 unchanged by ancestry and targets main. Nine new-task Markdown files above #12, thirteen cumulative Markdown files above main. This is not a merge of #12; all source PRs/branches remain untouched. Review/merge decisions require separate owner authority; prior merge deferral is not lifted.
Evidence gaps: other originating chats/unseen submissions UNVERIFIED; coverage bounded to supplied handoff and accessed GitHub. Existing Issue #1 stale PR #2 description disclosed, unchanged. Implementation specifics (per-strategy filter/stage/input rules, cache eligibility/validity, request/cancellation mechanics, instrumentation/clock policy, scheduler/resources and measured objectives) remain unselected. Any later substantive contradiction is BLOCKED and escalated rather than invented; current document consistency is not runtime/CI/acceptance success. Runtime/CI/performance/recovery NOT TESTED. G0/Issue #1 OPEN; no code/paid action/real execution or final approval authorized.

## G1 shared indicator box — ARCH-21–28
Project: ATLAS Quant Lab / AQL-CRYPTO-RESEARCH-001. **PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.** Source: directly received owner Consolidated G1 Shared Indicator Box Architecture handoff, 2026-10-21. Last owner-confirmed actually submitted handoff: AQL-HO-20261021-001 / PR #13, pinned `4a9bd25672d462f6b6b66beae55716942bb4a183`, verified OPEN/unmerged. Reported delta: G1-ARCH-21–28, their cross-decision checks and documentation/authorization constraints. No extra option, submission or unreported addendum is invented. Direct submission requests one documentation proposal; it authorizes no runtime, source-PR action, merge or final approval. Other originating chats inaccessible; coverage is bounded to accessed evidence and supplied scope.

### G1-ARCH-21 — Event/dependency-aware validity
Each shared computation has explicit input dependencies, provenance, version, finality and validity rules. Reuse only when technically valid and eligible for the requesting trader's decision. Do not invent universal TTL values.

### G1-ARCH-22 — Single-flight computation
Identical concurrent computations share one execution when their full computation identities match. Each consumer receives independently qualified results. Cancellation by one consumer must not cancel work still required by others.

### G1-ARCH-23 — Shared active data box and historical preservation
Maintain a shared active results box between the central data services and trader secretaries.

Each result has an explicit invalidation event, such as a qualifying market update, a new completed 5-minute candle, an hourly candle close or an underlying data correction.

When that event occurs, immediately remove the affected result from active eligibility. Preserve historical records through the existing durable Inbox/Slow archival responsibilities. Never make Fast invalidation wait for Slow archival processing. Preserve replay, audit and point-in-time semantics.

### G1-ARCH-24 — Result lifecycle
Use explicit `VALID`, `UPDATING` and `UNAVAILABLE` states, with reasons and version information.

An expired result cannot remain active while replacement computation runs. Only validated replacement results may become active. Historical fallback requires a predeclared trader-specific eligibility policy; mandatory evidence must not be silently bypassed.

### G1-ARCH-25 — Central box manager
Introduce one logical central manager responsible for:

- Indicator definitions and validity rules.
- Tracking relevant market events and dependencies.
- Active result state and invalidation.
- Scheduling qualified updates according to demand and priority.
- Sharing eligible computations and results.
- Communicating state changes to subscribed trader secretaries.

The manager provides data, not trading decisions.

### G1-ARCH-26 — Subscription-based communication
Trader secretaries declare their required data, indicator definitions, timeframes, parameters and decision context. The manager delivers the current state and automatically pushes relevant changes to subscribed secretaries. Avoid indiscriminate broadcasts and repeated polling.

### G1-ARCH-27 — Clear validity ownership
The manager is the authoritative owner of **technical validity** and continuously tracks subscribed indicators, invalidating and notifying secretaries when their states change.

Each trader secretary owns **decision-specific eligibility assessment** against the trader's versioned input manifest. A secretary may reject technically valid data as insufficient, request additional information or ask for an eligible refresh, but cannot override technical invalidity.

The owning trader alone makes entry, hold and exit decisions.

Include notification sequencing and reconnect/state reconciliation safeguards so missed or delayed messages cannot silently restore stale results.

### G1-ARCH-28 — Demand-aware update scheduling
Immediately invalidate technically expired active results, but do not automatically recompute every indicator across every symbol.

Schedule required updates according to actual subscriptions, open-position monitoring, READY candidates and progressive prefetch from qualifying earlier stages such as WATCH.

Preserve Fast live delivery and open-position priorities. Slow historical work, archival and recovery must remain independently controlled and budgeted. Do not assume a mandatory linear WATCH → BUILDING → READY sequence.


### Shared box compatibility and authority interpretation
The box is a logical shared active-results/data-service responsibility inside the existing Python modular monolith, between central data services and trader secretaries. A logical manager does not select a new deployment, database, queue, provider or runtime module implementation. It refines G1-ARCH-04/08 and ARCH-19/20: central technical validity and per-secretary decision eligibility are distinct, not duplicated technical invalidation engines. Secretaries can reject a technically valid result or request more/refresh; they cannot relabel central invalidity as valid. Only the owning trader decides entry/hold/exit.
Full computation/single-flight identity includes symbol, timeframe, definition/calculation version, parameters, every relevant input identity/version/provenance, input range, candle finality and temporal context. The shared execution has independent consumer demand/qualification references, not shared mutable strategy decisions. Removing one consumer cannot cancel another's required execution; different identities never share an in-flight computation merely because price/indicator name matches. Existing centralized WS/REST/subscription budgets remain one authority: internal secretariat subscriptions are not independent Binance subscriptions.
The active binding to a result version is mutable current state; historical result payload/provenance and original decision references remain immutable. Declared dependency events invalidate the affected binding when observed/established by ATLAS, preserving event/receipt/availability/invalidation times; 'immediate' is an ordering/safety obligation, not a numerical latency guarantee or knowledge before receipt. Candle examples are triggers only where the indicator rule actually declares them; 5-minute/hour examples are not universal TTLs. An underlying correction appends lineage and changes current eligibility without rewriting what earlier decisions actually knew.
Technical invalidation removes active eligibility independently of whether any recomputation is requested or archive has caught up. No stale active payload survives under UPDATING. A replacement must pass technical validation AND be applicable to the still-current dependency/version/temporal context at activation; an older in-flight completion or delayed notification cannot overwrite/resurrect a newer binding. If current validity cannot be established after restart/message gaps, do not grant active eligibility until authoritative state is reconciled. Details of revision/generation fencing and storage synchronization are implementation parameters, not selected technologies.
Historical fallback is a separately referenced candidate under a predeclared trader-specific policy, INT-04 availability/freshness and technical validity in its declared historical context; it is never permission to reactivate a current-invalid result or bypass mandatory evidence. LIVE/HISTORICAL planning class, feed HEALTHY/DEGRADED/UNAVAILABLE, result VALID/UPDATING/UNAVAILABLE and decision-specific readiness are separate dimensions. Scanner READY remains neither mandatory-evidence completeness nor trade authority.

## ARCH-21–28 reconciliation matrix and approval gates
Source commits: prior PR #13 `4a9bd25672d462f6b6b66beae55716942bb4a183` -> parent #12 `1948132315ee6a5b3174c56f767c84d1063251cd`, prior #11 `fb79e13b58c91c6b53a7e0489114adcdcc577d15`; main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. All are inspected proposal/history evidence, not proof of merge. New source: current visible owner Shared Indicator Box handoff, 2026-10-21. Earlier canonical IDs/sections below are in pinned #13 03_DECISIONS.md; inherited matrices retain earlier file/commit/line provenance.

| Decision | Complete mandatory intent summarized | Earlier source / compatibility or conflict judgment | Exact destination sections | Disposition / verification / owner input |
| --- | --- | --- | --- | --- |
| G1-ARCH-21 | Dependencies/provenance/version/finality-aware validity; no universal TTL | G1-ARCH-08/19/20; TIME-01/02/04/09; INT-04; Compatible refinement: technical validity and consumer-specific temporal eligibility both required | DECISIONS: G1-ARCH-21 — Event/dependency-aware validity; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-21 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-22 | One identical execution, independent consumer qualification and safe cancellation | G1-ARCH-17/19; DATA-01/05; PAPER-05; Compatible: full input-version/context key; no shared mutable strategy state or duplicate provider collector | DECISIONS: G1-ARCH-22 — Single-flight computation; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-22 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-23 | Immediate active invalidation, immutable history and no Slow archive gate | G1-ARCH-03/08/09/10; TIME-04/07; DATA-06/08; Compatible: active binding removal differs from deletion of durable historical evidence | DECISIONS: G1-ARCH-23 — Shared active data box and historical preservation; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-23 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-24 | VALID/UPDATING/UNAVAILABLE; no expired active result; validated replacement; qualified fallback | G1-ARCH-08/13/18/20; TIME-09/INT-04; Compatible: result state separate from readiness/feed health; no mandatory-data bypass | DECISIONS: G1-ARCH-24 — Result lifecycle; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-24 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-25 | One logical technical manager for definitions/dependencies/state/demand/sharing/notifications | G1-ARCH-01/04/08; DATA-01/05/07; Compatible logical role in existing monolith; no new physical deployment/engine/trading authority | DECISIONS: G1-ARCH-25 — Central box manager; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-25 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-26 | Declared scoped subscriptions, initial state and relevant automatic pushes | G1-ARCH-04/05/13/16; DATA-01/05/07; Compatible: internal data-service subscriptions reuse provider collection, avoid broadcasts/poll duplication | DECISIONS: G1-ARCH-26 — Subscription-based communication; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-26 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-27 | Manager technical authority, secretary eligibility, trader-only decision; sequencing/reconnect | G1-ARCH-08/09/18/19; TIME-01/02/04/09; PAPER-08; Explicit ownership refinement: secretary cannot override invalidity; missed/reordered/old-epoch evidence reconciled before use | DECISIONS: G1-ARCH-27 — Clear validity ownership; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-27 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |
| G1-ARCH-28 | Invalidate now, recompute by actual demand/positions/READY/earlier qualifying stages | G1-ARCH-02/14/15/17/20; DATA-02/04/06/07; Compatible: no eager all-symbol recomputation, compulsory BUILDING or delay to Fast/position protection | DECISIONS: G1-ARCH-28 — Demand-aware update scheduling; CONTRACT: Provisional shared active indicator box; SCHEMAS: Conceptual active-result and subscription model; RISKS: Shared indicator box residual risks; TEST_POLICY: matching G1-ARCH-28 row | INCLUDED / PASS documentary; runtime NOT TESTED. No unresolved substantive owner-policy contradiction identified; implementation parameters require later approval. |

Paths: DECISIONS=03_DECISIONS.md, CONTRACT=01_CONTRACT.md, SCHEMAS=09_DATA_SCHEMAS.md, RISKS=08_RISKS.md, TEST_POLICY=10_TEST_POLICY.md. SCHEMAS subheadings "Result-state semantics and publication safeguards", "Subscription sequencing, reconnect and restart safeguards" and "Example event sequences" hold the lifecycle/ordering model and eight event examples. STATE current evidence ledger and append-only LOG/REGISTER record exact lifecycle/scope evidence.

### Cross-decision check dispositions
- Full computation/single-flight identity includes every relevant input version/finality/provenance/temporal context; independent consumers qualify separately. Earlier ARCH-19/20 is preserved, not replaced by a short indicator-name key.
- In-flight activation checks current dependency/context/version and validated replacement evidence; obsolete completions and late VALID messages cannot overwrite newer state. Notification snapshot/change ordering and reconnect/restart reconciliation explicitly block uncertain eligibility.
- Active invalidity is not historical deletion. Existing durable Inbox/Slow archival, crash-safe acknowledgment/replay, immutable snapshot/correction lineage and no backdated paper fills remain. Fast invalidation never waits for archive catch-up; no universal TTL or unmeasured timing guarantee invented.
- READY remains a Scanner candidate state, not evidence completeness or authorization. Central technical validity is authoritative; per-secretary eligibility may reject but never repair invalidity. Only trader decides. LIVE/HISTORICAL planning label, feed health and result lifecycle remain distinct.
- Shared service subscriptions do not create per-trader Binance subscriptions/collectors or shared mutable strategy state. Demand-aware updates preserve Fast fan-out/open-position priority, independently controlled Slow history/archive/recovery, shared budgets and non-linear stages.
- No prior canonical requirement is silently removed or finalized. All G0 PAPER/TIME/DATA/GOV/INT, ARCH-01–20, owner A–G, deferred dashboard, histories and prior matrices are preserved. Technical ownership clarifies prior common validation/office eligibility wording without duplicate invalidation logic or new trading authority.

### Baseline alternatives, limitations and next action
Main alone lacks #13's reconciled proposals; recopying them risks omissions. Chosen new isolated branch inherits pinned #13, targets main: nine incremental Markdown changes, thirteen cumulative Markdown changes including prior proposal commits. Existing PRs/branches #6–#13 stay unchanged/open; no merger, overwrite, retarget, rebase or automatic closure implied. Current direct handoff requests one documentation proposal; no runtime or merge authority follows.
Unresolved implementation parameters: actual indicator dependency/validity catalogs; validation/evidence rules; full identity representation; single-flight/demand/cancellation mechanics; publication revision/generation fencing; notification ordering/snapshot/reconnect protocol; storage/transport/durable integrity and recovery details; strategy manifests/fallback; measured latency/throughput/budgets/capacity policies. No technologies, universal TTLs, numeric thresholds or guarantees chosen.
Inaccessible originating chats/unseen external changes remain UNVERIFIED; audit bounded to supplied scope. Existing Issue #1 stale PR #2 sentence remains disclosed, unchanged. No substantive unresolved policy contradiction found within the supplied decisions; any later such conflict is BLOCKED and escalated, not invented. Runtime/concurrency/notification/recovery/performance/CI NOT TESTED. Next owner review and separate explicit merge/implementation/final G0 decision. G0 and Issue #1 OPEN.


## G1 indicator catalog, quality and observability — owner provisional decisions ARCH-29–44 (2026-10-21)

**Authority:** owner explicitly approved ARCH-29/C, ARCH-30–34/C, ARCH-35–39/C, ARCH-40–44/C in the accessible conversation; all provisional until final G0. **Baseline:** last actually owner-submitted `AQL-HO-20261021-002` / PR #14 head `275c856c61452fb2fdee2c3de30a2ae9907646a8` (OPEN, unmerged at verification). This documentation proposal is not a Work submission by the owner and does not change the last-owner-submitted baseline. Other originating chats are inaccessible; unseen submissions remain UNVERIFIED. No runtime/CI tests or final G0 approval.

### G1-ARCH-29 — Versioned indicator catalog (C, PROVISIONAL)

Central manager owns versioned technical indicator definitions: formula, parameters, input identity, timeframe, finality, quality requirements, temporal context, provenance, output identity and exact event/dependency invalidation triggers. Secretaries reference definitions via versioned strategy manifests and cannot redefine technical validity. Rule changes produce new versions without rewriting past point-in-time evidence.

**Inherited compatibility:** G1-ARCH-21–28;19; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS;01_CONTRACT. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-30 — Central dependency graph (C, PROVISIONAL)

Model directed source/intermediate/result dependencies, detect cycles, propagate qualified changes and revoke only affected ACTIVE bindings; reuse unaffected valid computations, preserve full version/provenance identity.

**Inherited compatibility:** G1-ARCH-19;21–23;29; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-31 — Demand-driven dynamic subscriptions (C, PROVISIONAL)

Versioned per-secretary demand tracks trader, symbol, stage, open position and mandatory/optional manifest inputs; shared computation survives cancellation by one consumer while another still needs it. WATCH/READY transitions need no forced BUILDING; no duplicate provider feed.

**Inherited compatibility:** G1-ARCH-12–18;22;26;28; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-32 — Protected priority computation (C, PROVISIONAL)

Prioritize live source delivery and open-position monitoring; then decision-critical readiness and eligible stage-aware prefetch. Slow history/enrichment yields under measured provider/CPU/memory/backlog pressure. Do not choose fixed worker counts or numeric latency guarantees.

**Inherited compatibility:** G1-ARCH-01–03;05;16–18;28; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;02_ROADMAP. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-33 — Revisioned notification and state reconciliation (C, PROVISIONAL)

Authoritative revision/generation, scoped ordered notifications and snapshot-plus-changes reconciliation prevent missed, reordered, duplicated or late messages from restoring obsolete ACTIVE results. Unreconciled gaps block affected eligibility. Storage/transport/fencing mechanism remains unselected.

**Inherited compatibility:** G1-ARCH-24–27; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS;10_TEST_POLICY. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-34 — Cause-aware computation failures (C, PROVISIONAL)

Publish reasoned UPDATING/UNAVAILABLE state; retry recoverable failures only with bounded demand-, priority- and resource-aware policy; avoid retry storms and stale active fallbacks. Mandatory evidence remains blocked unless predeclared qualified alternative applies.

**Inherited compatibility:** G1-ARCH-08;18;24;28; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;08_RISKS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-35 — Input technical quality validation (C, PROVISIONAL)

Technical manager checks required source, availability time, finality, completeness, quality and provenance against versioned indicator definition before VALID. Secretary independently evaluates per-manifest consumer suitability; no look-ahead or silent quality downgrade.

**Inherited compatibility:** G1-ARCH-08;18–21;27; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-36 — Historical sufficiency and warm-up (C, PROVISIONAL)

Catalog defines lookback, warm-up/initialization and eligible history range for each computation. Inadequate data yields explicit non-ready state; Slow progressively fills required gaps without full archive completion as a live prerequisite.

**Inherited compatibility:** G1-ARCH-03;07;16–18;29; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-37 — Selective historical correction propagation (C, PROVISIONAL)

Corrected historical input invalidates affected ACTIVE dependencies and triggers demand-aware recomputation; preserve immutable original evidence, knowable-at-time snapshots, correction lineage and original consumer decisions. No retroactive rewriting.

**Inherited compatibility:** G1-ARCH-08–10;19;21–23;30; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-38 — Manifest-scoped decision evidence readiness (C, PROVISIONAL)

Secretary verifies all mandatory technically valid and consumer-eligible evidence for a specific trader/symbol/decision/manifest revision, with explicit missing/stale reasons. Scanner READY is not decision readiness or trade authorization; owning trader alone decides.

**Inherited compatibility:** G1-ARCH-05–06;12–18;27; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-39 — Safe reconciliation after data repair (C, PROVISIONAL)

Reconcile input completeness, versions, gaps, current revisions and subscriptions after outage/correction. Reject stale computations and restore demanded current results progressively, protecting Fast and open positions. Preserve Inbox ACK/reclaim safety and never invent retrospective paper fills.

**Inherited compatibility:** G1-ARCH-02–03;09–11;23–28; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;10_TEST_POLICY. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-40 — Stage-attributed latency telemetry (C, PROVISIONAL)

Correlate source receive/Inbox commit, Fast office delivery, computation queue/execute/publish, targeted secretary delivery, mandatory readiness, strategy waiting and trader processing. Account for clock domains/uncertainty and overlapping intervals; avoid double counting or fabricated SLA.

**Inherited compatibility:** G1-ARCH-16;25–28; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-41 — Demand-aware indicator box health (C, PROVISIONAL)

Report scoped VALID/UPDATING/UNAVAILABLE counts and reasons, technical revisions, quality, subscriptions, evidence age and consumer eligibility distinctly. Unrequested dormant indicators are not failures simply because no recomputation was scheduled.

**Inherited compatibility:** G1-ARCH-24–28;31; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-42 — Adaptive resource-pressure diagnosis (C, PROVISIONAL)

Measure provider budgets, backlog/queue age, computation resource contention and Fast/position impact; hysteretic load shedding delays optional Slow work before critical streams, then resumes safely. Numeric thresholds and technology require measured approval.

**Inherited compatibility:** G1-ARCH-02;16;28;32; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;08_RISKS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-43 — Per-secretary/trader latency attribution (C, PROVISIONAL)

Separate shared manager compute, targeted delivery, secretary eligibility evaluation, mandatory-data wait, strategy wait and trader active processing using traceable context; slow consumers cannot block other consumers.

**Inherited compatibility:** G1-ARCH-04–06;16;26–27;40; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;09_DATA_SCHEMAS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

### G1-ARCH-44 — Impact-aware operational alerts (C, PROVISIONAL)

Deduplicate/escalate sustained incidents by affected positions, mandatory evidence, subscriptions and priority; record recovery and resolution. Telegram is notification only, not trading authority. Future dashboard remains deferred and read-only planning only.

**Inherited compatibility:** G1-ARCH-05;16;24;41–43; earlier G0 TIME/DATA/PAPER/INT, owner addenda A–G, research-library phase and deferred dashboard preserved. **Destination cross-reference:** 03_DECISIONS;02_ROADMAP;08_RISKS. **Status:** conceptual, no chosen physical technology, thresholds, paid actions, code or merge.

**Boundary reconciliation:** Technical VALID belongs to manager; manifest eligibility belongs to secretary; entry/exit/hold belongs to owning trader. Invalidation revokes ACTIVE eligibility immediately upon observed qualifying trigger independently of Slow archival ACK, while immutable historical evidence and durable Inbox/reclaim constraints survive. Recompute is demand-aware; late computation, missed notifications, replay and reconnection must not resurrect stale results. READY is not permission to trade. Fast/open-position delivery always protected. Historical repair never creates retrospective paper fills. These decisions refine rather than supersede ARCH-01–28.

**Decision coverage matrix:**

| Decision | Choice | Inherited decisions | Documentation destinations | Evidence |
|---|---|---|---|---|
| G1-ARCH-29 | C / provisional | 21–28;19 | 03_DECISIONS;09_DATA_SCHEMAS;01_CONTRACT | Owner visible approval; documentary only |
| G1-ARCH-30 | C / provisional | 19;21–23;29 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-31 | C / provisional | 12–18;22;26;28 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-32 | C / provisional | 01–03;05;16–18;28 | 03_DECISIONS;02_ROADMAP | Owner visible approval; documentary only |
| G1-ARCH-33 | C / provisional | 24–27 | 03_DECISIONS;09_DATA_SCHEMAS;10_TEST_POLICY | Owner visible approval; documentary only |
| G1-ARCH-34 | C / provisional | 08;18;24;28 | 03_DECISIONS;08_RISKS | Owner visible approval; documentary only |
| G1-ARCH-35 | C / provisional | 08;18–21;27 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-36 | C / provisional | 03;07;16–18;29 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-37 | C / provisional | 08–10;19;21–23;30 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-38 | C / provisional | 05–06;12–18;27 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-39 | C / provisional | 02–03;09–11;23–28 | 03_DECISIONS;10_TEST_POLICY | Owner visible approval; documentary only |
| G1-ARCH-40 | C / provisional | 16;25–28 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-41 | C / provisional | 24–28;31 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-42 | C / provisional | 02;16;28;32 | 03_DECISIONS;08_RISKS | Owner visible approval; documentary only |
| G1-ARCH-43 | C / provisional | 04–06;16;26–27;40 | 03_DECISIONS;09_DATA_SCHEMAS | Owner visible approval; documentary only |
| G1-ARCH-44 | C / provisional | 05;16;24;41–43 | 03_DECISIONS;02_ROADMAP;08_RISKS | Owner visible approval; documentary only |

**Open implementation choices:** catalog representation/validation, dependency graph engine, physical state store, snapshot/change protocol, revision fencing, subscription transport, concurrency/single-flight mechanics, bounded retry policy, priority/hysteresis measurements, history warm-up rules by actual indicator, instrumentation clock quality, alert thresholds, provider budgets, numerical SLA. Escalate conflicts; do not silently select.

## G1-OPS-20261024 - Controlled non-production completion implementation

Authority: owner's 2026-10-24 Final Execution Mission, G0/G1-only feature branch.
This records implementation choices under that scope, not production approval.
- Keep SQLite FULL/WAL as core durable truth. Move startup recovery and operational
  delivery out of the critical callback; bounded admission and explicit pending/error
  evidence, cooperative core-first writes, no forced cancellation of an fsync.
- Add optional sandbox PostgreSQL adapter and separate remote ACK cursor. Remote
  delivery never shares or overwrites the local persistence acknowledgement.
- Public read-only Binance connectivity is authorized once within bounded scope.
  Transport PASS is separate from temporal acceptance; observed clock divergence
  is fail-closed and must not be hidden by auto-backdating.
- Retain R09 and deferred full Inbox/off-device backup requirements. PR16's MVP
  plan is superseded; its deferred obligations remain. No PR closure is executed.
Parameters and measured evidence/limits are in docs/operations/G1_COMPLETION_20261024.md.

## CORE-TIME-PROOF-01/B — independent Binance observation (2026-10-28)

Owner-authorized implementation scope, reference Council #134/6462845677:
reuse ObservationVersion and envelope-v1; separate-process public Binance Spot
WS final-kline observations plus REST snapshot comparison. Append raw content,
wall/monotonic clocks, source-reported E, identity/session, digest and revision
ancestry. FIRST_INDEPENDENT_OBSERVED is a transport receipt observation, never
ISSUER_ATTESTED publication. REST content changes are observed snapshot revisions;
no completeness between polls or backdated correction knowledge is asserted.
Local/transport/source clock evidence without independently validated UTC bounds
keeps temporal status UNKNOWN. Gaps and restarts remain UNKNOWN; Factory's
existing empirical refusal is preserved. Hash chain plus Git commit pin provides
bounded tamper evidence, not WORM custody, independent timestamp authority, or
proof of host-loss survival before off-host publication. No G0 closure/merge.
