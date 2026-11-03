# Factory Research Consumer Seam V1 — TEST_ONLY

Owner: Factory. Branch based on Factory #222 at `6b93abf975648d3ce5ee9c28c7b33c72686f4e6b`. Existing Option C files unchanged. Core Bridge #226 and Work Harness #228 are unmerged and **not imported**.

## Scope and mapping

`build_research_handoff(schedule, envelope)` invokes existing Factory `validate_schedule` (real schedule validator, no new evaluator). Input envelope `aql.factory.research-consumer-seam.v1` binds a frozen paired schedule to exactly one row per pair/BASE or pair/SHADOW. Each row carries opportunity_id, attempt_id, cohort_id, strategy_version, source manifest/source package SHA256, decision_cutoff_ms, feature_available_ms, feature_snapshot_sha256, status, and no evaluation/return or trade authority. All row identities, cutoffs and source pins are validated. Return `aql.factory.research-consumer-receipt.v1` contains exact census, immutable digest, and explicit NOT_EVALUATED/NOT_OBSERVED status.

Status partition: NOMINATED, NO_SIGNAL, REJECTED, UNKNOWN, NULL, UNSCANNED, UNRESOLVED. Each row has exactly one status. Sum of status_counts == arm_slots == scheduled_pairs*2. `NULL` is not a zero return. `UNKNOWN` and ambiguous intrabar outcomes are never converted to wins/losses. Missing slots fail closed. A real source-level universe denominator *outside* the paired schedule is **NOT_CONNECTED**: this adapter cannot claim to have counted symbols never supplied by the upstream Scanner/Discoverer. Full upstream universe census requires independently verified upstream contract before activation.

Descriptive 4/24/72h outcomes remain in existing Factory `build_lab`/`prepare_real_development`; modeled ten-bar trades remain in existing `build_modeled_trade_package`; neither is invoked by this handoff. This avoids pretending a candidate has already been evaluated or that a trade occurred.

## Limitations and integration requirements

- TEST_ONLY and retrospective contract checking only; no private data, PIT/OOS, alpha, funded PnL, holdout, trading, execution or new evaluator.
- Core #226 read-only packet can supply provenance only after separately approved adapter, not assumed available on main.
- Work #228 currently projects Factory receipts, not a real evaluator call. Work must integrate against this versioned input only with separate authorization and full upstream universe/attempt census.
- No standalone complete Core-style query→opportunity→Factory evaluation proof yet; focused adversarial tests are a narrower F3 gate. F4 must run against an authentic synthetic Core schedule fixture, with no mocked validator.

## Focused test

`python -m unittest tests.test_aql_factory_research_consumer_seam -v`

No change to frozen Option C policy, original private scoring, Core/Scanner/Discoverer/Work branches.
