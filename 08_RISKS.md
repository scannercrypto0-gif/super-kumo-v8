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

## Live-data operations residual risks — DATA-05–08
References: [provisional rules](03_DECISIONS.md#g0-live-data-operations-decisions--data-0508) and [G0-GOV-01](03_DECISIONS.md#g0-gov-01--work-handoff-continuity-and-completeness).
- R02/R10: recovered REST messages or later-finalized candles can fabricate prior knowledge/fills. Preserve observed/reconstructed classes and all clocks/source evidence; chronological idempotent replay retains ambiguity/residual gaps and no fictional live decisions.
- R04: reconnect storms, duplicate per-trader requests and multiplied WS/REST limits. Central cache/dedup, shared subscription/connection/request-weight authority, bounded backoff; constants remain unvalidated.
- R10/R05: slow overlapping core loops or heavyweight archive/news/research/report load starve positions. Bound queue/concurrency, separate Position Monitor from lower-priority batched Scanner, reserve resources/equivalents, log skipped scans without backdating.
- R02/R07: over-aggressive coalescing loses TP/SL/event order; retain all monitoring/fill/replay/audit-required sequences even when latest-state scanning safely coalesces.
- R04/R10: “no trades” falsely treated as outage, or source-wide outage unnecessarily stops independent inputs. Use evidence-based source/symbol/stream/type health and source-specific TTL; selectively block affected decisions. Positions stay open with monitoring gaps; no guaranteed uptime or recovery.
- R01: draft/received prompts mistaken for submitted baseline or unviewed cross-chat content claimed complete. Durable handoff metadata, owner confirmation, exhaustive delta dispositions and coverage-gap audit under G0-GOV-01; originating-chat access remains limited.
All controls are documentation proposals, not implemented/finally approved risk mitigation.
