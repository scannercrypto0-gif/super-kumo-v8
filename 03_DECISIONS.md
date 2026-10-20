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

## G0 TIME and DATA provisional decisions

Project: ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`.
**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
Owner-selected option C for all 13 records; source: consolidated owner handoff dated 2026-10-20 plus mandatory completeness addendum. Legacy ADR 001–012 remain unchanged. The following records are the canonical detailed source. Each preserves its selected policy, owner rationale/conditions and deferred implementation parameters. No alternatives are invented from missing chat context. TIME-01 explicitly refines the former closed-bars-only wording while retaining point-in-time integrity; no final architecture approval is implied.

### G0-TIME-01 — Decision-Time Data Eligibility: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

- Closed candles are allowed.
- Intra-candle/live observations are allowed only when there is verifiable evidence that the exact data was available at the trader's decision time.
- Otherwise fall back to closed candles.
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
