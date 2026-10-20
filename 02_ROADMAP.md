# Roadmap / stage gates — DRAFT
G0 GOVERNANCE: repo, signed contract, ADR log, task format and review roles. Pass: versioned docs + owner approval.
G1 MARKET FOUNDATION: Binance universe, final candles, features, adaptive scheduler, Supabase, local spool. Pass: each discovered symbol has eligible/error/unsupported record; deterministic replay; zero unverified intra-candle/future-data decisions in tests (provisional G0-TIME-01/02/09 and INT-04; completed-candle fallback only when explicitly permitted by the trader's predeclared policy, otherwise block and record why); offline idempotent recovery; measured API/DB budget.
G2 OBSERVATION: forward 4/24/72h max/min, timing, ambiguity, BTC/ALT regime, historical replay. Pass: synthetic boundary tests, mature/missing outcomes reconciled, coverage by regime; no need to wait for all market regimes to occur.
G3 MOMENTUM TRADER: versioned WATCH→ARMED→TRIGGERED→CLOSED, exits and paper fills. Pass: signal replay, fees/slippage, same-bar ambiguity, expiry/no-fill tests; operational soak without unexplained missing/duplicate signals. Profitability not required for engineering completion.
G4 RESEARCH LAB: hypotheses, shadow comparisons, temporal holdouts, trial registry. Pass: one preregistered reproducible paired experiment, independent reviewer, owner approval for promotions.
G5 EVENTS: source adapters, provenance, publication/ingest time, dedupe. Pass: leakage tests, quality and coverage report, connectors by source feasibility; unavailable feeds explicitly documented.
G6 MULTI-TRADER: second momentum trader, then pre-run, then accumulation in separate packages. Pass: new trader without modifying core, independent same-symbol results, load/restart tests.
G1→G2→G3→G4 primary path; event ingestion preparation can run in parallel. Gates remain open until signed.

## Provisional TIME/DATA preparation sequencing
See [canonical decisions](03_DECISIONS.md#g0-time-and-data-provisional-decisions). Initial Research Library backfill is a distinct rate-limited/resumable/cost-controlled pre-operational preparation activity where feasible. Declare coverage scope and verify before claiming completeness; do not make full archive completion a synchronous prerequisite of Core Live Run. Once operational, incremental ingestion/gap repair update the same library on independent schedules. Core monitoring/open-position tracking have resource priority; background enrichment/backtests/reports yield first.
All existing gates remain OPEN until approved. TIME/DATA choices remain provisional; no code or paid actions authorized. PR #6 dashboard and PR #7 paper documentation remain separate unmerged proposals at inspection; preserve both during later reconciliation.

## Future requirement — unified monitoring dashboard

Project: ATLAS Quant Lab (`AQL-CRYPTO-RESEARCH-001`).
Status: FUTURE REQUIREMENT RECORDED — implementation DEFERRED; not an approved implementation plan or final architecture decision. Existing G0–G6 gates and their acceptance criteria are unchanged. Schedule/scoping requires a later approved work package after operational data exists.

The future unified view should cover:
- Current open paper positions and signal lifecycle/history.
- Performance of independent virtual traders.
- Research Lab experiments and Shadow Trader comparisons.
- Historical outcomes and reporting.
- System health, data freshness and operational errors.

Telegram remains the notification channel. Dashboard views and Telegram notifications should consume consistent underlying records/events so status and outcomes agree; neither channel should maintain a conflicting source of truth.

Design considerations for future foundation work:
- Preserve stable signal IDs, trader IDs, timestamps, lifecycle history and outcome data, consistent with the conceptual [data contracts](09_DATA_SCHEMAS.md). This requirement does not modify those schemas.
- Initial dashboard access should be secure and read-only, with appropriate authentication and scoped access; no credentials or privileged keys exposed to clients.
- Do not select a frontend framework, API design, tables or infrastructure prematurely.
- Defer dashboard implementation until operational records exist and data coverage/quality can support the views. Access model and technical choices remain subject to review and owner approval.

No UI code, API endpoints, tables, migrations or infrastructure are authorized by recording this requirement. It does not approve architecture, authorize trading or close G0/G0-001.

## Provisional G1 preparation — secretarial data architecture
G0 is still OPEN. [G1-ARCH-01–11](03_DECISIONS.md#g1-secretarial-data-architecture--provisional-owner-clarifications) record conceptual preparation, not authorization to implement G1. Preserve the independent future dashboard requirement and all existing gates.
Future G1 documentary/acceptance preparation must cover durable Inbox receipt/commit, independent Fast/Slow consumers and crash-safe archive acknowledgment/reclaim; nonblocking office fan-out; owning-trader decision authority; common quality with policy-specific eligibility; bounded capacity/backpressure and restart/gap recovery evidence. Parameter choices and benchmarks remain separate approved work.
Initial Research Library preparation remains separately scheduled and cost-controlled; resuming eligible live data service must not await archive or deep-quality catch-up. Every decision-critical monitoring event survives any safe Scanner coalescing. Priority covers all shared resources and provider budgets, with measured hysteresis/office lag rather than fixed SLA promises.
The owner defers all merges of PRs #6–#11. This new proposal preserves #11 by ancestry without modifying it; its own merge also requires separate authorization. No automatic source-PR merge or closure is proposed.
