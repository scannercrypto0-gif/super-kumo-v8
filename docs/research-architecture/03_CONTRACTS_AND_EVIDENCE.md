# Logical Contracts, Evidence Lineage and State Semantics — v1.0

**Status:** provisional interface proposal, not SQL schema, migration, public API, application code, nor a change to operational trader state. See [architecture](01_ARCHITECTURE.md).

## 1. Cross-cutting contract envelope

Every research record carries `schema_version`, immutable `record_id`, `created_at_utc`, `producer_version`, `idempotency_key` when generated through a job, provenance references and a content digest, where applicable. The timestamps `event_at`, `published_at`, `observed_at`, `ingested_at`, `available_at`, `decision_at`, `corrected_at` have **different meanings** and must not be collapsed. Record uncertainty/error provenance; never infer observed-before-known from archived publication.

References identify immutable versions, not mutable 'latest' pointers. Stable logical IDs may point to successive versions via append-only supersession edges. Any physically stored schema/indices/retention are separately reviewed ADRs.

## 2. Proposed logical schemas (minimum fields and invariants)

### ResearchDatasetManifest

- `dataset_id, version, source_versions[], partition_refs[], partition_digests[], coverage_scope, universe_membership_asof, timeframe_scope, temporal_policy_version, data_quality_ref, missing_coverage[], provenance, license_constraints, created_at`.
- Immutable manifest of a **specific declared scope**, never blanket 'complete history'. Each observation has temporal eligibility class and reason. Data corrections create a new version, retain old digest, and link affected output objects. Local archive/raw canonical objects referenced rather than duplicated per experiment.

### ResearchFeatureDefinition / FeatureSnapshot (reuse existing)

- Existing FeatureSnapshot: `symbol, as_of, data_cutoff, feature_set_version, values, missing_flags, input_digest`.
- Proposed extension references: `definition_id/version, input_snapshot_refs, calculation_method, source_lookback_window, earliest_usable_at, finality/freshness_policy, uncertainty_flags`.
- Shared G1 indicator manager remains sole operational validity authority. Research may compute experiment-specific variants but cannot publish them as authoritative live indicator values.

### ResearchObservation (reuse existing Observation and Outcome)

- Existing Observation/Outcome fields preserved: `observation_id, symbol, decision_at, feature_snapshot_ref, regime_ref`; outcomes `4h/24h/72h` and additional future horizon contracts may be proposed separately.
- Research attachments: `sampling_scheme, selection_probability_or_weight, opportunity_eligibility, comparison_cohort, forward_label_ref, historical_visibility_class, symbol_universe_asof`.
- Forward labels may only attach after maturity and may never feed the original decision features.

### HypothesisRecord

- `hypothesis_id, origin [human|rule|RIE], origin_evidence_refs, created_at, textual_claim, falsifiable_prediction, null_hypothesis, eligible_population, target_horizon, primary_metric, minimum_economic_effect, trial_family_id, scope, owner_review_state`.
- Hypothesis registration freezes required assumptions before confirmatory testing; exploratory revisions carry a new version.

### ExperimentProtocol (extends existing Experiment)

- Existing `hypothesis_id, frozen parent/shadow, primary metric, trial count, selection/test windows, results, owner decision`.
- Additional `experiment_id, protocol_digest/version, declared_data_manifest_ref, train/development/holdout/forward_window_refs, chronological_purging_rules, multiplicity_plan, comparator_refs, fees_slippage_policy, eligible_population, loss_function, failure_policy, model_spec_ref, randomization/seed_policy, resource_budget_envelope`.
- All candidate trials including stopped/failed discarded attempts logged. Sealed holdout access has separate authorization/audit record.

### ResearchRunManifest

- `run_id, experiment_id, dataset_manifest_digest, code_commit_digest, config_digest, environment_digest, random_seed_if_applicable, model_version, start/end times, worker_budget, runtime_result_digest, logs_ref, outcome_status, integrity_check_ref`.
- Repeated deterministic runs with same execution inputs require identical normalized outputs. Document inherent nondeterminism and prohibit exact-reproducibility claim for it.

### StrategyCandidate / SimulationSpecification

- `candidate_id, family_adapter_version, parent_candidate_id?, frozen_rule_digest, entry/exit/risk_spec_refs, required_feature_refs, declared_regime_scope, snapshot_visibility_policy, simulator_version, feasibility_constraints`.
- `simulation_id, fill_model_version, fee_schedule_effective_at, slippage/spread/liquidity source, notional, gap/no-fill policy, same-bar ambiguity policy, cost_stress_scenarios, no_lookahead_assertions`.
- StrategyCandidate is not an authority to create live/trader orders. Paper fills and realized paper accounting remain owned by the trader and paper execution model.

### ResearchEvidence / EvaluationReport

- `evidence_id, run_refs[], manifest_hashes, source_quality_coverage, outcome_denominators, primary_effect_estimate, interval/uncertainty, risk_and_cost_report, robustness_matrix, baseline_comparison, regime_slices, multiplicity_accounting, diagnostics_refs, evaluation_stage [development|historical_oos|prospective_forward], review_signoff?, validity_revision`.
- Historical forward max/min vs actual paper PnL always separated. Missing/ambiguous outcomes and selection exclusions explicitly counted. No combined historical/forward performance headline.

### DiagnosticFinding

- `finding_id, detector_version, detected_at, finding_class, severity, confidence_or_uncertainty, evidence_refs[], affected_dependency_refs[], suspected_causes[], proven_causes[], status, remediation_proposal_refs[]`.
- Monitoring signals cannot assert causal reason without validated evidence. Critical finding may suspend research evidence eligibility, not alter historical trade decisions.

### ImprovementProposal and PromotionDecision

- `proposal_id, origin_finding_or_hypothesis, frozen_parent_strategy_version, candidate_variant_ref, matched_comparison_refs, risk_delta, trade_count_delta, net_effect_and_interval, adverse_findings, proposed_scope, owner_decision_ref?`.
- `promotion_decision_id, human_authority, signed_at, approval_scope, supporting_evidence_refs, constraints, rejection_or_defer_reason`.
- Promotion requires separate actual G0/appropriate gate approval and authorized implementation work; research recommendation alone cannot promote.

## 3. Evidence dependency graph and invalidation semantics

Versioned directed edges:
```text
source raw/version -> dataset manifest -> feature snapshots -> observations
                                         -> hypotheses -> experiment protocol
                                          -> run result -> evaluation report
                                                     -> recommendation
```
Event source revisions and simulation/code corrections are **distinct** upstream revision classes.

On correction/integrity finding:
1. Emit immutable CorrectionEvent with source, affected time/symbol/version scope and verified evidence.
2. Traverse downstream version-specific references transitively; generate impact set with confidence/completeness.
3. Append EvidenceValidityRevision per affected research artifact. Conservative UNKNOWN when lineage incomplete.
4. Block affected candidate promotion; preserve original results and trade/accounting records.
5. Schedule only authorized bounded recomputation; produce superseding versions plus a before/after impact diff.
6. Validate post-recompute lineage, temporal eligibility and diagnostics before any evidence state recovers.

Valid states: `UNVERIFIED`, `VALID`, `DEGRADED`, `INVALID`; status transitions are **append-only revisions**. An experiment `COMPLETED` is orthogonal and does not imply `VALID`. The G1 manager's `VALID/UPDATING/UNAVAILABLE` refers to active indicator validity and is not replaced.

## 4. Required job/isolation behaviors

Research run envelopes: `job_id, class=RESEARCH, source_data_snapshot, requested_resources, deadline, max_retries, checkpoint, cancellation_token, run_generation, idempotency_key, priority`. Admission depends on shared provider budget and protected operational reservations, not only total CPU idle. Research never independently subscribes to provider streams.

Cancel/restart must not double-publish immutable evidence, create duplicate trial IDs, or overwrite an approved version. Non-available provider/source events are explicit failure data. Archive ACK and Backup Verified are separate obligations; research cannot reclaim G1 Inbox or archive outside accepted retention gates.

## 5. Logical interface examples (not executable JSON schema)

- `DatasetBuilder.build(request, temporal_policy) -> DatasetManifest | CoverageError`
- `HypothesisRegistry.freeze(hypothesis, protocol) -> FrozenExperimentRef`
- `ResearchRunner.execute(frozen_ref, budget) -> ResearchRunManifest | InterruptedRun`
- `ValidationCore.evaluate(run_refs, protocol_ref) -> EvaluationReport`
- `IntegrityGuardian.assess(evidence_refs) -> DiagnosticFinding[] + ValidityRevision[]`
- `ResearchIntelligence.recommend(evidence_graph, approved_limits) -> ResearchProposal[]`
- `CandidateRegistry.nominate(evidence_ref) -> ProposalForOwnerReview` (never operational activate)

Any method has explicit failure result, idempotency, version semantics, authorization boundary and provenance.

## 6. Validation traces (future fixtures, NOT executed)

| Case | Required observable trace |
|---|---|
| News published at 12:00, first observed at 12:07, decision at 12:03 | No live-known news feature at 12:03 |
| Candle finalized later than decision | Final OHLCV rejected as old intrabar context |
| Dataset correction touches subset of partitions | Impact graph marks only known dependents and conservatively flags unknown lineage |
| Experiment completed then data found invalid | Experiment execution remains COMPLETED, evidence validity becomes INVALID |
| Duplicate job delivery/crash during publication | Exactly one logical run evidence publication by idempotency/unique key; no claim of literal exactly-once process |
| Same bar TP and SL without finer ordering | AMBIGUOUS factual resolution and separate scenario bounds |
| 2,000 related observations from same event/sector | Effective independence and uncertainty not inflated by naive per-trade sampling |
| Source unavailable during replay | UNKNOWN/missing coverage, not fabricated paper fill |
| Research job saturates machine | Research yields/cancels while protected position monitoring retains budget |
| RIE requests operational strategy change | Denied without owner-approved separate gate |
