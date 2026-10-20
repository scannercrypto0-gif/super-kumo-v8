# ATLAS Quant Lab Architecture & Engineering Contract v1.0 — DRAFT
Project ID: `AQL-CRYPTO-RESEARCH-001`. Former project name: SUPER KUMO V8. This identity-only heading update does not alter the technical contract.
Goal: Binance Spot USDT research platform, momentum first, then pre-run and accumulation; independent paper traders; news/event intelligence; controlled shadow experiments.
Architecture: Python modular monolith, shared market-data adapter/cache, point-in-time feature engine, observation and outcome tracker, versioned trader plug-ins, deterministic paper fill engine, event adapters, research lab, scheduler, Supabase operational storage, durable local offline spool. Bulk historical datasets may live in object storage.
Trader output: WATCH / ARMED / TRIGGERED / CLOSED, plus EXPIRED / CANCELLED. Conditional entry, invalidation, stops, targets and expiry. Independent same-symbol trades; flag correlated outcomes.
Paper accounting: no portfolio or capital allocation initially; record realistic fill assumptions, fees, slippage, R, MFE/MAE, no-fill and ambiguous-bar cases. No live execution.
Research: observe executed, rejected, expired and non-selected opportunities; forward 4/24/72h returns; historical replay where point-in-time data exists. No retrospective leakage. Register every experiment; freeze parent and shadow versions; paired comparisons and untouched forward test; owner approves promotion.
Events: unified adapters for macro/Fed, token unlocks, news, social, search; record event_time, published_at, observed_at, provenance and licensing. Source access/cost may limit initial coverage.
Data: only closed bars at decision cutoff, UTC times, versioned features and schemas, immutable decisions, separate future labels. Errors not reclassified as trading rejects.
Operations: adaptive API-weight-aware scans, cache, retry/backoff, idempotency, offline spool, restore tests, telemetry, secrets in environment, migration control.
Change control: all interface/schema changes require ADR; every work package needs scope, non-goals, measurable tests, evidence, rollback, reviewer verdict and owner signoff.
Known unknowns: API budgets, Supabase retention/cost, provider rights, PC restart reliability, exact paper fill model. These are work packages, not assumptions.
