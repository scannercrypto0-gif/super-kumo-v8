# Roadmap / stage gates — DRAFT
G0 GOVERNANCE: repo, signed contract, ADR log, task format and review roles. Pass: versioned docs + owner approval.
G1 MARKET FOUNDATION: Binance universe, final candles, features, adaptive scheduler, Supabase, local spool. Pass: each discovered symbol has eligible/error/unsupported record; deterministic replay; zero open-bar feature decisions in tests; offline idempotent recovery; measured API/DB budget.
G2 OBSERVATION: forward 4/24/72h max/min, timing, ambiguity, BTC/ALT regime, historical replay. Pass: synthetic boundary tests, mature/missing outcomes reconciled, coverage by regime; no need to wait for all market regimes to occur.
G3 MOMENTUM TRADER: versioned WATCH→ARMED→TRIGGERED→CLOSED, exits and paper fills. Pass: signal replay, fees/slippage, same-bar ambiguity, expiry/no-fill tests; operational soak without unexplained missing/duplicate signals. Profitability not required for engineering completion.
G4 RESEARCH LAB: hypotheses, shadow comparisons, temporal holdouts, trial registry. Pass: one preregistered reproducible paired experiment, independent reviewer, owner approval for promotions.
G5 EVENTS: source adapters, provenance, publication/ingest time, dedupe. Pass: leakage tests, quality and coverage report, connectors by source feasibility; unavailable feeds explicitly documented.
G6 MULTI-TRADER: second momentum trader, then pre-run, then accumulation in separate packages. Pass: new trader without modifying core, independent same-symbol results, load/restart tests.
G1→G2→G3→G4 primary path; event ingestion preparation can run in parallel. Gates remain open until signed.

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
