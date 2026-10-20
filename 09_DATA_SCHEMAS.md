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
