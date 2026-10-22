# Research Engineering Review and WP-R0 Acceptance Contract

**Status:** DESIGN REVIEW / FUTURE EXECUTION SPECIFICATION, not implemented, not G0 sign-off.  
**Review:** 2026-10-22; PR #17 documentation package against available main contract and proposed G0/G1 interfaces.  
**Finding:** Conceptual boundaries are coherent, but implementation must be blocked until four high-severity evidence/authority gaps are concretely tested.

## 1. Review verdict and actionable gaps

| Finding | Severity | Defect / risk | Required resolution |
|---|---|---|---|
| R-F01 | HIGH | Search over many strategies may report spurious alpha; no calibrated end-to-end null control specified | Freeze a full hypothesis-search evaluation with recorded failed trials and predeclared family-wise false-positive/FDR policy; test across multiple synthetic seeds |
| R-F02 | HIGH | Historical observability classes are named but exact access-control and usability conditions across revisions are not formalized | Freeze a time-eligibility decision table for source event/receipt/availability/correction and completed-bar vs verified intrabar; deny unknown historical availability for live-equivalent evidence |
| R-F03 | HIGH | 'Yield before operational starvation' is not measurable until operational reservation/admission and cancellation semantics are declared | Specify benchmark-derived budgets and a fail-closed admission policy; research is best-effort and must not share uncontrolled provider loops |
| R-F04 | HIGH | RIE and test selection could repeatedly peek at holdouts, adjust metrics or dynamically expand trials | Define blinded holdout custody, trial-family audit, frozen primary metric/split and explicit tainted-holdout reclassification; promotion remains owner-only |
| R-F05 | MEDIUM | Vendor news may contain untrusted/promotional text and retrospective corrections | Treat all event/article text as data, never tool or instruction authority; source allowlist/license and content hashes, sanitized ML/LLM inputs |
| R-F06 | MEDIUM | Run states lack precise idempotent publication/retry operation | Future atomic manifest/evidence publication and restart fixture; stable idempotency keys, partial runs never reported complete |
| R-F07 | MEDIUM | Counterfactual claims may hide data-dependent exits or execution assumptions | Separate factual and hypothetical trajectories; freeze original entry/rule facts, report interval ambiguity and cost stress |
| R-F08 | MEDIUM | Long-horizon/portfolio models need richer data than candle-level trader accounting | Adapter-level portfolio and rebalancing contracts; no universal intraday fills imposed |

**No critical direct contradiction identified** for docs-only research isolation; unresolved runtime details are dependencies rather than implementation-ready guarantees.

## 2. First executable work package proposed (NOT AUTHORIZED)

**WP-R0 — Research Integrity Vertical Slice**. Purpose: prove scientific and integration invariants using tiny frozen synthetic/local fixtures, **before** implementing actual momentum discovery, ML, connectors or trade analytics.

### Scope, explicitly gated on separate owner authorization / necessary G0 decisions
- In-memory or local file-based prototype of dataset manifest, cutoff/availability classifier, immutable hypothesis/protocol, run manifest, dependency edges and validity revision.
- One deliberately simple baseline experiment on small synthetic bars and event annotations.
- Deterministic fault injection: correction to one input partition, unauthorized future news, contaminated holdout, duplicate completion.
- Produce machine-readable evidence and a test report. **No Binance API, live market data, Supabase migration, real orders, operational trader modification or paid services.**
- Run in separately isolated research test job with no operational provider access; resource admission contract to be reviewed before shared execution.

### Explicit non-goals
No Alpha discovery, revenue claims, portfolio allocation, real-time news ingestion, auto-trading, simultaneous modifications to G1 code, full AI RIE, multi-family engine or deployment.

### Exact acceptance invariants

**RAI-01 — Point-in-time no-leakage**
For decision cutoff `t`, a feature/event is eligible only with source-specific verified or explicitly modeled availability <= `t`, frozen policy, correct source version, and required input coverage. At `published_at=12:00, first_ATLAS_observed=12:07, decision=12:03`, historical live-known news is ineligible. Unknown availability is UNVERIFIED, not falsely VALID. A completed candle observed later cannot be passed as intrabar state.

**RAI-02 — Frozen protocol and untouched test**
`protocol_digest` includes eligible population, target, comparison baseline, primary metric, label horizon, splits, embargo/purge, cost model, family ID and declared total-search accounting. Frozen protocol mutation fails. Opening final holdout produces an access record; any reuse for tuning marks test contaminated, disqualifying independent OOS claim.

**RAI-03 — Reproducibility**
Same deterministic fixture digest + normalized run manifest + code/config/env version + deterministic seed yields byte-identical normalized result digest (excluding non-semantic run timestamps). Partial/failed runs cannot publish successful evaluation evidence. Non-deterministic kernels must explicitly declare tolerance/test method.

**RAI-04 — Correction blast radius**
Given source partition A feeding experiment X and report Y, while partition B feeds Z, correction A must create new immutable version and transitive impacted set {X,Y} (and any actual other descendants). Preserve originals; mark known impacted evidence INVALID/DEGRADED according to reason; unaffected Z remains unchanged. Missing lineage prevents unconditional VALID.

**RAI-05 — Null-discovery guard**
A registered synthetic null strategy-search harness must record all proposed/selected/rejected candidates, selection rule, correlations, and repeated seeds. Measure actual false-alarm rate against the selected family-level statistical procedure's preregistered target and simulation uncertainty. Numerical tolerances and number of replicates must be chosen *before test execution*, from desired power/precision and CPU budget. Do not call a single successful null run a pass.

**RAI-06 — Resource isolation**
Research worker has no direct Binance subscription/operational trader write permission. Under injected CPU/IO contention and simulated provider quota pressure, admission denies/deprioritizes research while monitored core priority/availability remains intact. Define latency/CPU/DB quotas by **measurement**, not invented numbers.

**RAI-07 — No unauthorized promotion**
RIE/research user attempts to alter live strategy, paper exit, approved indicator validity, production database or gate status fail via permission boundary. Mere text prompt constraints are not a sufficient security control.

**RAI-08 — Non-hindsight counterfactual**
Factual trade result and research variant have distinct IDs/immutable parents. Same-bar order unknown => AMBIGUOUS bounds, no fabricated fills. A counterfactual variation cannot rewrite original trader's decided policy or closed event stream.

**RAI-09 — Source/document trust**
Untrusted news and retrieved repository prose are stored/referenced as content; they cannot instruct permissions, change experiment acceptance criteria, trigger external services or alter the architecture policy.

### Trace fixtures (design specifications, not test execution)

| Fixture | Inputs | Expected |
|---|---|---|
| FUTURE_NEWS | publish 12:00; observed 12:07; cutoff 12:03 | live-equivalent feature rejected |
| FINAL_BAR_LATE | close 12:05; available 12:05:02; cutoff 12:04:59 | finalized OHLCV rejected |
| UNKNOWN_RECEIPT | event timestamp known, receipt unavailable | no claim of verified historical knowledge |
| DATA_REVISION | A->X->Y, B->Z; correction A | X/Y flagged, Z retained |
| HOLDOUT_PEEK | freeze model, open holdout, retune | untouched status revoked |
| EXP_RETRY | fail before atomic publish, retry | one completed logical artifact; partial retained |
| NULL_SEARCH | multiple selection attempts on null labels | calibrated false-discovery rate with uncertainty |
| PAPER_AMBIGUOUS | TP and SL same bar, no finer order | factual AMBIGUOUS, scenario bounds separate |
| RIE_PROMOTION | auto-agent invokes operational change | denied, auditable finding |

## 3. Research workload controls

- Conceptual permission separation: `research:read_market_versions`, `research:write_own_experiment`, `research:propose_candidate`; **no** `trader:modify`, `operations:modify`, `gate:approve`, `billing:purchase`.
- Job admission: source snapshot pinned, bounded resources, policy version, cancellation/checkpoint, idempotency key, dependency declaration, and explicit owner of any externally visible effects.
- Safe-stop records a structured interruption reason; do not report incomplete outputs as statistically validated.
- Pending G1 Fast/Slow and shared indicator manager stay authoritative. The future resource envelope must be reconciled with them before integration.

## 4. Formal statistical questions the first review must close

1. **Unit of independence:** trade vs opportunity vs market/time cluster. Determine effective sample size and prevent multiple related trades masquerading as independent evidence.
2. **Research family:** explicit definition of one test family including parameter sweeps/feature selection/AI suggestions. Family-aware correction applies to complete search, not final shortlist.
3. **Effect estimand:** conditional trade PnL vs opportunity expected net value; count no-fill and unselected opportunities explicitly when answering opportunity-level questions.
4. **Baseline and cost:** specify frozen comparator/risk budget and fee/slippage assumptions before observation of confirmatory results.
5. **Model calibration:** when probabilities used, proper scoring + reliability under OOS; attach uncertainty and missing-data coverage.
6. **Holdout and prospective:** separate historical development/OOS/prospective forward with no blended score, and record opening access.
7. **Regime specialist:** demonstrate incremental OOS value over pooled baseline with minimum independent regime occurrences; otherwise report insufficient evidence.

## 5. Future work sequencing and permission checkpoints

- **Now**: Docs-only spec and independent reviewer findings in Draft PR #17.
- **Before R0 code**: explicit owner authorization for a separate WP, review of available G0 decisions, freeze exact test vectors and scope, ensure no collision with G1 branches.
- **WP-R0 implementation**: exclusively synthetic/local, research-specific module namespace, no runtime operational modifications.
- **Later**: adapt to G1 historical datasets only after authoritative contracts are approved and source licences/resource budgets addressed.

**G0 remains OPEN. No runtime code written/tested. No assertion that a ChatGPT Work session was submitted.**

## 6. Next reviewer output required

`CURRENT GATE | EXACT MAIN/PR BASE | FINDINGS SEVERITIES | OWNER DECISIONS | FROZEN R0 SCOPE | TEST IDENTIFIERS & EVIDENCE | CONFLICTS/BLOCKERS | RECOMMENDED NEXT WP | NO MERGE`.

Owner-facing decision: accept architecture as **provisional documentation basis** and separately decide whether to authorize the isolated synthetic WP-R0 implementation. This review document does not make that decision for the owner.
