# ATLAS Quant Lab — Capability Maturity Matrix
**Version:** 1.1-DRAFT | **Evidence snapshot:** 2026-10-24
**Main source baseline:** `4e4c3537036bdf2b106c1a63ec65b2a9855972a7` | **Documentation:** PR #74, Draft/unmerged.
Reviewed documentation baseline: `e4ce1c8a5d7911f52fb67e52f7e58c2e0ee5b476`; final document HEAD is in PR metadata/correction matrix, not the main-source SHA.
Evidence IDs and scope: [09_EVIDENCE_REGISTER.md](09_EVIDENCE_REGISTER.md). No production authorization or owner decision is created by this map.

## Scale, evidence and authorization are separate axes

- L0 CONCEPT: placeholder, no accepted component specification.
- L1 DESIGNED: requirements/contracts exist, runtime not implemented.
- L2 IMPLEMENTED: foundation or isolated code/tests exist; state main versus PR-only explicitly.
- L3 INTEGRATED: accepted runtime/software interfaces are exercised together in a declared scope. It does not require or imply production trading.
- L4 VALIDATED: accepted integrated capability has independent acceptance for that declared scope, not merely a green author run.
- L5 OPERATIONAL: explicitly authorized deployment, monitoring and sustained operating evidence.
No department is assigned L4/L5 here. Individual software acceptance may be validated without making the whole department operational. These ordinal labels are assessment aids, not scientific measurements.

## A–M departmental inventory

| ID | Functional area | Representative level | Scope |
|---|---|---|---|
| A | Historical Data Library | L2 | Main: isolated versioned historical/custody foundation |
| B | Live Market Data Center | L3 | Main: integrated bounded G1 path; reported bounded Binance acceptance |
| C | Strategy Factory | L2 | Main: indicator/definition foundations; no accepted factory runner |
| D | Strategy Explorer | L0 | Concept; no dedicated implementation/specification accepted |
| E | Asset Intelligence Lab | L1 | Owner-approved future concept under C; #72 unprioritized |
| F | Research Lab | L2 | Main foundations plus isolated unmerged research chain; not an integrated accepted Lab |
| G | Secretariat Office | L1 | Provisional design; no runtime |
| H | Opportunity Scanner | L1 | Provisional design; no runtime |
| I | Virtual Traders | L1 | Provisional lifecycle/fill design; no runtime |
| J | Market Intelligence | L1 | Documented context requirements; no runtime producer |
| K | Monitoring & Dashboard | L2 | Health snapshot code exists; unified UI/alerts deferred |
| L | Governance & Orchestration | L2 | Versioned documents/GitHub/CI tooling; approval is a separate authority axis |
| M | Shared Infrastructure & Storage | L2 | Main SQLite foundation; technically reviewed archive/backup in unmerged #73 |

Representative departmental distribution: **L0=1, L1=5, L2=6, L3=1, L4=0, L5=0 (13 total)**.
B's L3 concerns bounded integrated G1, not live trading. F's L2 recognizes actual research code across main and unmerged ancestry; it is neither zero-code nor an integrated accepted Lab.
K includes real health code, although the unified dashboard is future work. L's documents/process/CI do not warrant a project-wide validation score. No arithmetic mean is used.

## F / research: component-by-component evidence

CI references: E-82 main 216-test combined acceptance; E-83 legacy204-per-OS suite at #46's own tree; E-86 Draft78 393-per-job suite. “CI yes” means aggregate suite evidence plus inspected relevant test files, not a separately reported count for every component. No empirical profitability is established.

| Capability | Code exists / main? | Relevant tests / CI | Integration actually demonstrated | Independent validation | Ready for what? |
|---|---|---|---|---|---|
| Historical custody/versioning | Yes/main | test_sf_data_01.py;141 in unchanged-source portion of E-86 | Offline data→indicators | Software cases inspected; external origin/receipt custody not independently authenticated | Accepted isolated historical library |
| Indicators V1/V2 | Yes/main #60/#68 |50 V1+58 V2; E-82 | Native registry→binding; six cross-module tests | Software acceptance; no trading edge claim | Offline calculation only |
| Strategy definitions and grids | Yes/main #69 |57 strategy tests; E-82 | Definition→bind_evaluation; bounded candidate_grid | Contract acceptance; no strategy execution | Declarative frozen definitions |
| Backtest foundations/candidates | Yes/#46 only, not main | test_research_wp_r42_batch01.py; E-83 | Synthetic strategy_factory.execute/run_batch composes legacy components | No accepted-main/real-data acceptance | Isolated synthetic exploration, not a reconciled historical engine |
| Statistical tests/purged folds | Yes/statistics.py in #46 ancestry, not main | test_research_wp_r1.py plus downstream cases; E-83 | Used inside legacy synthetic batch | Synthetic contract checks, not calibrated real-market inference | Methodological foundation |
| Paired evaluation/outcome accounting | Yes/evaluation.py, opportunity_clusters.py, not main | R2/R3 suites; E-83 | Synthetic NO_SIGNAL/NO_FILL/ambiguity, pair/cluster sensitivity | No complete real opportunity population accepted | Synthetic accounting/evaluation only |
| Trial registry/family accounting | Yes/ExperimentRegistry + TrialFamilyLedger in #46 ancestry; main only AttemptRecorder port | R0/R6/R7/R9/R19 suites; E-83, main strategy cases | Legacy in-memory ledger + separate durable journal; main port is incompatible without adapter | No accepted-main family lifecycle/restart reconciliation | Existing isolated implementations; reconciliation required |
| Holdout custody/contamination | Yes/HoldoutCustody, HoldoutEvent, trial-family gate; not main | R0/R6/R9 suites; E-83 | Access-event/tuning/selection guards in legacy synthetic path | No independently segregated real holdout, OS custody or owner-operated service verified | Contract/guard foundation, never permission to open final holdout |
| Experiment tracking/reproducibility | Yes/integrity, durable_journal, owner_checkpoints, external_custody; not main | R7/R10/R11/R19/R40; E-83 | Synthetic hash-chain/replay/checkpoint/export and store test double | External store protocol/test double is not independent custody | Isolated software/restart foundations |
| OOS/walk-forward | Split/temporal/purging code exists in #46; no accepted empirical OOS runner | R1/R5/R42; E-83 | Development versus synthetic_validation separation | No admissible real split/untouched empirical study | Synthetic validation only, not profitability |
| Historical input bridge | Yes/Draft78, not main |36 new+357 inherited=393; E-86 | Accepted-main definitions+custody+native V1/V2 prefix, no legacy engine | Contract review; full milestone #77 BLOCKED | Input adapter/contracts ready for owner review |
| Shadow/prospective testing | Authority guards and design exist; forward Shadow runtime not implemented in inspected main/#46 | Guard tests/design, not a forward-run result | #46 explicitly says forward_shadow=NOT_STARTED_NOT_TESTED | None for prospective operation | Future implementation/approval |
| Operational outcome/decision capture | Synthetic records in #46; PIT serialization in Draft73; no live trader lifecycle capture | Synthetic outcome/contract tests only | No paper trader→durable decision/outcome pipeline | None | Future runtime; schema alone is not capture |

Legacy research PRs #18–#31/#33–#39/#41/#43/#46 remain OPEN/unmerged. #32/#40/#42/#45 are the merged G1 line, not evidence that the research chain merged. #48 closed without merge; isolated historical library arrived through #57. Compare main...#46:115 ahead/55 behind, ancestor ed188f1902d397fe74613dd966c5a3e88b32f8c0. Do not import the entire chain silently.

## Counted capability catalogue

This explicitly bounded catalogue is not an exhaustive count of every function.
Counts refer to these25 IDs only, not independent statistical evidence or a weighted maturity score. Shared code may support different interface capabilities.

| ID | Capability unit | Level | Presence / evidence |
|---|---|---|---|
| CAP-01 | Historical versioned custody | L2 | Main; E-10 |
| CAP-02 | Scalar indicators V1 | L2 | Main; E-11 |
| CAP-03 | Typed indicators V2 | L2 | Main; E-12 |
| CAP-04 | Strategy JSON/grid | L2 | Main; E-13 |
| CAP-05 | Native definition/indicator PIT binding | L3 | Main bounded software integration; E-82 |
| CAP-06 | G1 ingestion/recovery pipeline | L3 | Main; E-15/E-71 |
| CAP-07 | Journal→local persistence/replay | L3 | Main; E-15/E-85 |
| CAP-08 | G1 health snapshots | L3 | Main integrated health; E-15 |
| CAP-09 | Sealed local archive | L2 | Unmerged73; E-84 |
| CAP-10 | Verified backup/restore | L2 | Unmerged73; E-84 |
| CAP-11 | Statistical helpers | L2 | Unmerged46; E-80/E-83 |
| CAP-12 | Paired opportunities/outcomes | L2 | Unmerged46; E-80/E-83 |
| CAP-13 | Holdout access/taint gates | L2 | Unmerged46; E-80/E-83 |
| CAP-14 | Trial-family ledger/journal | L2 | Unmerged46; E-80/E-83 |
| CAP-15 | Experiment/checkpoint reproducibility | L2 | Unmerged46; E-80/E-83 |
| CAP-16 | Synthetic candidate/backtest batch | L2 | Unmerged46; E-80/E-83 |
| CAP-17 | Historical input adapter | L2 | Unmerged78; E-81/E-86 |
| CAP-18 | Prospective Shadow workflow | L1 | Contract only; no running Shadow |
| CAP-19 | Secretariat runtime | L1 | Contract only |
| CAP-20 | Scanner runtime | L1 | Contract only |
| CAP-21 | Paper trader runtime | L1 | Contract only |
| CAP-22 | AssetOutlook producer/watch | L1 | Owner-approved future concept #72 |
| CAP-23 | Unified dashboard/alerts | L1 | Future requirement, not health snapshot code |
| CAP-24 | Sandbox PostgreSQL adapter | L2 | Main adapter/migrations; local disposable CI, cloud untested |
| CAP-25 | Dedicated Strategy Explorer | L0 | Concept placeholder |

Catalogue distribution: **L0=1, L1=6, L2=14, L3=4, L4=0, L5=0 (25 total)**.
Foundation presence, isolated implementation, integration and readiness must not
be collapsed into one score. Department C/F remain L2 despite one accepted
binding interface at L3; that interface is not a full Factory/Lab runtime.
