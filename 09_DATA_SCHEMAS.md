# Initial schema contracts — conceptual
UniverseSnapshot: scan_id, symbol, discovered_at, as_of, eligibility_status [ELIGIBLE, UNSUPPORTED, DATA_ERROR], reason, source_version.
MarketBar: symbol, interval, bar_open, bar_close, OHLCV, is_final, ingested_at, source; only final bar_close<=decision_cutoff usable.
FeatureSnapshot: symbol, as_of, data_cutoff, feature_set_version, values, missing_flags, input_digest.
Observation: observation_id, symbol, decision_at, reference_price/source, feature_snapshot_ref, regime_ref, reasons; immutable.
Outcome: observation_id, horizon [4h,24h,72h], due_at, max_return, min_return, time_to_target, order_resolution [KNOWN, AMBIGUOUS, MISSING], maturity [PENDING, COMPLETE, MISSING].
ExternalEvent: event_id, type, source, event_time, published_at, observed_at, affected_assets, provenance, license, correction_ref.
Trader/Signal/Trade: trader_id, immutable strategy_version, signal_id, state transitions with timestamps, conditional entry, invalidation, expiry, fill_model_version, paper fills, costs, net return and R.
Experiment: hypothesis_id, frozen parent/shadow, primary metric, trial count, selection/test windows, results, owner decision.
Keep forward outcomes separate from decision snapshots. UTC timestamps, schema version and idempotency key throughout.

## Proposed governance and live-data records — GOV-01 / DATA-05–08
**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
Conceptual fields/relationships only, no database tables/migrations/operational constants. [Canonical decisions](03_DECISIONS.md#g0-live-data-operations-decisions--data-0508). Existing enums and base conceptual definitions preserved; physical types/interfaces remain deferred.

- Handoff metadata: unique handoff_id, date, project ID/repository, scope/covered_decision_range, owner-confirmed submitted baseline and confirmation evidence, direct receipt separately, addendum IDs/precedence/source, accessed/unavailable records, audit outcome, resulting PR/head, review/merge status and dated update evidence.
- Delta item: source/baseline/item ID, decision/clarification/correction/requirement/exception/owner-deferral kind, approval status, disposition INCLUDED/ALREADY_DOCUMENTED/OWNER_DEFERRED/UNRESOLVED, exact handoff section or verified file/commit/PR+merge state, gap/requested reference and next action. A draft is not owner-submitted; unknown coverage is not PASS.
- Acquisition/feed: provider/source, symbol, stream/data type, live WebSocket vs REST initialization/recovery classification, event_at/received_at/available_at/processed_at/decision_at and evidence, shared cache key/version, freshness policy/age and provider budget authority. Distinct live observations require exact temporal eligibility; never substitute later finalized bars.
- Health: conceptual HEALTHY/DEGRADED/UNAVAILABLE, state transition at observed/detected time, liveness/provider message/sequence/continuity/reconciliation evidence, per-source/indicator TTL, affected traders/positions/required inputs, uncertainty/reason and residual gaps. Lack of recent trades is not sufficient outage evidence.
- Run/job: core/position-monitor/scanner/context/archive/research identity, priority/deadline, actual start/end/duration/lag/deadline miss, queue depth, non-overlap/concurrency/ownership controls, skipped/coalesced scanner cycle evidence and reason, retained monitoring/fill/ambiguity/replay/audit sequence references. Monitoring must not depend on universe scan completion.
- Recovery: outage window, affected scope/position, reconnection attempts/backoff evidence, REST range/reconciliation source, budget usage, gap/coverage result, chronological event identity/idempotency progress, unresolved order/ambiguity and correction lineage. Positions remain open with explicit monitoring gaps until legitimate policy/outcome evidence supports change.
- Shared workload/budget: WS connection/subscription and REST endpoint-weight usage governed jointly across loops, deduplicated acquisition/cache provenance, resource reservations/equivalents for CPU/memory/I/O/DB/network, background yield actions and lag. No fixed endpoint/TTL/polling/cadence/concurrency or SLA adopted.
- Future read-only dashboard may reference health/run-lag/missingness records consistently with Telegram; no UI/API/schema implementation or live authority. Keep initial historical preparation/incremental maintenance isolated under pending DATA-01–04 and independent trader/exit/recovery semantics under pending PAPER-01–08.

Register policy is in HANDOFF_REGISTER.md; this is only the conceptual data relationship, not a second metadata register.
