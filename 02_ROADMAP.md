# Roadmap / stage gates — DRAFT
G0 GOVERNANCE: repo, signed contract, ADR log, task format and review roles. Pass: versioned docs + owner approval.
G1 MARKET FOUNDATION: Binance universe, final candles, features, adaptive scheduler, Supabase, local spool. Pass: each discovered symbol has eligible/error/unsupported record; deterministic replay; zero open-bar feature decisions in tests; offline idempotent recovery; measured API/DB budget.
G2 OBSERVATION: forward 4/24/72h max/min, timing, ambiguity, BTC/ALT regime, historical replay. Pass: synthetic boundary tests, mature/missing outcomes reconciled, coverage by regime; no need to wait for all market regimes to occur.
G3 MOMENTUM TRADER: versioned WATCH→ARMED→TRIGGERED→CLOSED, exits and paper fills. Pass: signal replay, fees/slippage, same-bar ambiguity, expiry/no-fill tests; operational soak without unexplained missing/duplicate signals. Profitability not required for engineering completion.
G4 RESEARCH LAB: hypotheses, shadow comparisons, temporal holdouts, trial registry. Pass: one preregistered reproducible paired experiment, independent reviewer, owner approval for promotions.
G5 EVENTS: source adapters, provenance, publication/ingest time, dedupe. Pass: leakage tests, quality and coverage report, connectors by source feasibility; unavailable feeds explicitly documented.
G6 MULTI-TRADER: second momentum trader, then pre-run, then accumulation in separate packages. Pass: new trader without modifying core, independent same-symbol results, load/restart tests.
G1→G2→G3→G4 primary path; event ingestion preparation can run in parallel. Gates remain open until signed.
