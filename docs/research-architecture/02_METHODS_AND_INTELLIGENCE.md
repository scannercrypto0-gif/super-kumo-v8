# Quantitative Methodology and Research Intelligence — v1.0

Status: PROPOSAL ONLY. See [architecture](01_ARCHITECTURE.md). Statistical thresholds are **not** invented; calibrate with frozen simulation/benchmark protocols.

## 1. Scientific workflow

`Observation -> CandidatePattern -> FalsifiableHypothesis -> PreRegisteredProtocol -> Training/Discovery -> Historical OOS -> Prospective Forward -> Owner Promotion Decision`.

For each hypothesis specify: exposure/eligible population, reference alternative, null hypothesis, primary metric, effect direction and practical minimum effect, inference unit (trade, independent event or calendar block), sample/power limitations, decision horizon, treatment of missingness, multiplicity family, permissible tuning/search budget and data selection plan. Keep *all* trials (including failures) and preserve denominators for selected, rejected, unfilled, expired, unknown and missing opportunities.

**Discovery** is allowed to explore freely on the development partition, but no reported p-value from reused development data establishes confirmatory success. Nomination time and immutable candidate/protocol precede holdout or prospective validation. A contaminated holdout becomes development data and requires a genuinely untouched later validation set.

## 2. Core estimands

Net expected payoff must be assessed on a fixed normalization and consistent fee treatment. If `R_gross` denotes pre-cost return, `C` cost, then:
`E[R_net] = E[R_gross] - E[C]`.
For mutually exclusive win/loss outcomes under the same return definition, `E[R_gross] = P(W)E[R_gross|W] + P(L)E[R_gross|L]`; include no-fill/flat events explicitly if part of the opportunity-level estimand. Gross historical max forward return is *not* realized strategy PnL.

Track: net expectancy and dispersion, uncertainty intervals, Sharpe/Sortino when meaningful, max drawdown with path dependence, turnover, execution feasibility, MFE/MAE, expected shortfall/tail risk, capacity/market impact limits, opportunity count/coverage, regime-conditional behavior, position/time correlation and sensitivity to notional, costs and missing data. Portfolio metrics require an explicit future portfolio allocation model, not assumed from independent trader trades.

For calibrated probability models evaluate reliability/calibration curves, proper scoring rules (Brier/log loss), discrimination and downstream cost-aware utility. `P(success | features, regime)` is a conditional estimate with model/coverage uncertainty, not a guarantee.

## 3. Statistical validation controls

1. **Temporal selection**: train/validation/holdout ordered by availability, not outcome timestamp; purging for overlapping label intervals and embargo where necessary. Use walk-forward folds. Count truly independent time/regime occurrences; do not treat overlapping bars or correlated assets as independent.
2. **Selection bias**: use event-based plus clock-based controls, condition on observable eligibility and matched negatives; track weights, missing opportunity population, delisted assets and historical sector memberships. Discovery of momentum winners alone is descriptive, not predictive.
3. **Multiplicity**: record candidate-generation family and *total* tested variants, including discarded runs; apply FDR/FWER/selection-aware methods appropriate to predeclared confirmatory questions. Avoid pretending a naive Sharpe or ordinary p-value corrects selection.
4. **Dependence**: moving/stationary block bootstrap or grouped resampling when justified; blocks respect serial/cross-asset dependence. Document assumptions and unstable small-sample coverage.
5. **Robustness**: parameter perturbation, sensitivity to market regime, fees/slippage/spread, trade clustering, portfolio concentration, missing intervals and source corrections.
6. **Ablations**: compare features/groups (news, sector regime, volatility, relative strength, model complexity), always using matched periods/opportunities and same simulation rules.
7. **Baselines**: random-policy under comparable trade-frequency/risk, buy/hold where meaningful, and simple frozen momentum/rule baselines. Stronger complexity must earn measured out-of-sample improvement.
8. **Causal language**: historical association and explanatory feature importance are not causal identification. Counterfactual strategy variants use common ex-ante eligibility and fixed path assumptions; specify unobserved execution and market-impact confounding. Never claim a historical edit truly caused the counterfactual outcome.
9. **Prospective evaluation**: shadow and paper results separate from historical OOS; cohort/regime and target/off-target denominators shown side-by-side. When evidence is thin, status INSUFFICIENT_EVIDENCE rather than a false pass.

## 4. Strategy research specifics

**Initiation:** prospectively definable anchor times (e.g., regular sampling), label a *future* tradable momentum opportunity, and preserve all negative/flat controls. Event studies can enrich discovery but cannot replace base-rate population. Define event threshold/horizons before confirmatory tests.

**Continuation:** identify momentum state from past-only available observations; evaluate forward continuation over independent horizon and incremental payoff **after** recognition/entry costs. Separate continuation from initiation label definitions and trials.

**Regime hierarchy:** compare pooled model to stratification by BTC/market risk state, asset cap/liquidity tier, sector, asset relative strength and cross-sectional breadth; shrink/suppress unstable specialty estimates. Regime detector output must have detection/availability timestamp and calibrated UNKNOWN state; no hindsight labeling for entry. Sample count and regime transitions must be disclosed.

**Cross-family:** intraday emphasizes order/latency/fees; swing gap and liquidity dynamics; long-term investment needs portfolio and universe survivorship analysis, time-varying fundamentals/tokenomics, benchmark and rebalance assumptions. Do not reuse one trade-frequency default for all.

## 5. Research Intelligence Engine (RIE)

RIE is a planner/recommender, not an adjudicator of empirical truth or an operational strategy writer.

**Inputs:** immutable experiment summaries and hashes, DiagnosticFindings, feature/regime catalog versions, resource-budget ledger, information about candidate overlap, evidence confidence and permitted work scope.

**Outputs:** HypothesisProposal, AdversarialChallenge, ExperimentPriority recommendation, DiagnosticSummary, or ImprovementProposal with rationale, testability, expected cost, prior related failures and dependency references.

**Permitted abilities (future gated):**
- Generate alternate explanatory models and competing hypotheses, not only profitable-looking features.
- Detect hypothesis duplication and compare with failures held in Research Memory.
- Rank candidate experiments by estimated expected information gain divided by total constrained resource cost, with novelty/diversity and exploration safeguards.
- Propose falsification tests e.g. permutation, source perturbation, leakage traps, false-discovery null-simulations, stress-cost, alternate regimes and holdout controls.
- Calibrate its own research *recommendation quality* on outcomes of independently evaluated experiments; no automatic modification of live policy or test criteria after viewing results.

The utility score is a heuristic until calibrated. Its inputs/weights/versions are logged. An AI-generated hypothesis is not a positive finding.

## 6. Self-diagnostics and safe improvement

RIG owns detection proposals; operational data/indicator authority remains with G1. Possible findings:
- DATA: temporal inversion, missing/duplicate/corrected bar, outage, stale news, unexpected source discontinuity, symbol membership drift.
- RESEARCH: future feature reference, leakage via normalization/label/protocol, nonreproducible result, repeated holdout access, invalid numerical precision, simulation ambiguity.
- STATISTICS: excessive trial search, weak sample/power, historical/forward divergence, miscalibration, drift (distribution shift vs conditional relationship shift).
- OPERATIONS: CPU/RAM/IO/provider request-pressure, stalled research work, excessive cloud cost.
- MODEL: degradation after controlling for regime/cost, unexpected behavior, sensitivity cliff.

**Response policy:** diagnose first, classify evidence UNVERIFIED/DEGRADED/INVALID with append-only reason, trace dependency graph to impacted derived evidence, block affected promotion, propose bounded reruns, preserve old immutable manifests and annotate supersession. Do not claim a drift alarm proves the cause; distinguish data break, market change, execution model, multiple testing and overfit hypotheses.

**Research cycle:** Observe -> Diagnose -> Generate competing hypotheses -> Register & freeze -> Run bounded test -> Adversarial challenge -> Estimate uncertainty -> Recommend/Reject -> Record failure/learning. Evidence-first evolution; operational strategy remains unchanged unless separately owner approved.

## 7. Approval and falsification tests

- Synthetic null/noise batches over repeated selection cycles: measure family-wise false positives or false discovery rate under predeclared target, with uncertainty across seeds.
- Exact-boundary temporal fixtures: event before decision but receipt after decision; later corrected OHLCV vs historical intrabar source.
- Time-varying universe fixture: delisted assets and historical sector recategorization.
- Holdout contamination fixture: repeated peeking is logged and disqualifies 'untouched' claim.
- Correlated-trade fixture: grouping prevents inflated effective sample size.
- Cost/no-fill and ambiguous same-bar TP/SL fixture: bounds and unknown statuses, not best-case fill.
- Drift-vs-corruption fixture: distinguish synthetic shifts from missing or revised data and report classification uncertainty.
- Variant comparison: paired original/counterfactual, identical ex-ante information and frozen exit policy; original trade immutable.
- Authorized RIE recommendation may not mutate approved trader or bypass data eligibility.

No tests executed: this is the future acceptance protocol, not PASS evidence.
