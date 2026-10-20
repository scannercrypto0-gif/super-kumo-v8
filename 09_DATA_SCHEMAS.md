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

## Proposed paper/research state requirements — no implementation

**Status: PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
References: [G0-PAPER-01–08](03_DECISIONS.md#g0-paper-trading-decisions--owner-selected-provisional-rules). The following are conceptual record/event requirements, not SQL tables, migrations or finalized new enum contracts. Existing state/order_resolution/maturity enums above are preserved; future enum mapping requires interface review.

- Opportunity/entry context: trader_id, strategy_version, signal_id, opportunity identity/dedup policy version, symbol, signal availability time, entry conditions, first eligible observable price/time/source, validity window, early-invalidation rule/version, expires_at and terminal reason. Distinguish NO_FILL, expiration, rejection and data errors without conflating signal lifecycle with accounting outcomes.
- Frozen trade policy: trade identity, reference_notional/currency (provisional 1,000 USDT), entry/fill/exit policy snapshots and versions, event-time lifecycle history, permitted rule-driven adjustments with timestamp/reason, fill/exit modeled price and source, exit reason independent of price/cost.
- Execution estimate: gross return, baseline net, independent stress-cost scenario, fee source/tier/maker-taker/discount/promotion assumptions and effective date, spread/slippage/liquidity evidence, notional sensitivity and unavailable-data flags. No immutable example fee percentage.
- Outcome uncertainty: factual order_resolution AMBIGUOUS remains distinct from hypothetical worst/best scenario resolution and stress costs; preserve finer-data provenance and visibility. Trader aggregate reports include best/worst performance, assumptions, confirmed/ambiguous/unresolved denominators and correlation grouping. Never count scenario bounds as verified outcomes.
- Lab/counterfactual: original signal/trade reference, independent variant/path identity, frozen initial conditions and policy versions, preregistered research horizon, observations after original exit, original-target touches/times, TP1 activation/stop-adjustment/stop-hit/TP2 chronology and protected-downside/missed-upside metrics. Keep counterfactual records separate; do not reopen/mutate the original closed trade.
- Recovery/event progress: durable pending/open state plus policy snapshots, event identity/idempotency key, processing checkpoint, market event time, observed/ingested time and recovered_at, source interval/gap coverage, unresolved reason (e.g. UNRESOLVED_DATA_GAP), accounting correction lineage and audit evidence. Replay must not duplicate execution, accounting or alert records.
- Restored historical facts may label outcomes/correct accounting with traceable revisions; decision-time feature visibility and immutable original decisions stay unchanged. Price-based intrabar reconstruction must not manufacture strategy evaluations made while offline.

Exact field types, physical storage, identity keys, retention and policy parameters remain deferred to later reviewed specifications. Existing conceptual event timestamps/IDs and trader independence remain intact.
