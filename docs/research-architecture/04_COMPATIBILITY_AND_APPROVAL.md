# G0/G1 Compatibility, Decision Ledger, Acceptance and Owner Review

**Status:** documentation proposal only. Handoff `AQL-RESEARCH-HO-20261022-001` (owner-authorized **direct GitHub action**, not submitted ChatGPT Work evidence).  
**Audit scope:** accessible current ATLAS conversation; main contract/schemas/tests/roadmap/state; register on PR #15 branch; PR #16 provisional plan; live GitHub PR list on 2026-10-22. Other chats and unseen owner submissions were not directly accessible.

## 1. G0-GOV-01 continuity

- Last **owner-actually-submitted Work handoff explicitly evidenced** by available register/PR #14 is `AQL-HO-20261021-002` — PR #14. Confirm with owner before claiming any later unobserved Work submission; do not confuse PR #15's proposed `-003` with a submitted handoff.
- Existing `main` inspected at `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. Issue #1 G0-001 and G0 remain OPEN. No application implementation or G0 signoff.
- PR #6 through #16 were OPEN and unmerged during inspection; PR #16 is Draft and targets #15's provisional branch, PR #15 Draft targets main. Unmerged docs can inform compatibility requirements, **not** be cited as implemented or merged contracts.
- This research branch starts directly from main. It adds **only** files in `docs/research-architecture/`; no edits to main-root governance docs, handoff register, contracts, G0/G1 PRs, code or migrations.
- Baseline is evidence bounded to accessible sources. Other originating chats or unseen subsequent instructions are UNVERIFIED, not presumed absent.

## 2. Accessible post-baseline owner decision delta (conversation-only)

| Reference | Owner direction | Scope/status | Disposition here |
|---|---|---|---|
| RESEARCH-MOM-01 | Regime-aware discovery / C | owner-provisional | INCLUDED in Strategy Generation specification |
| RESEARCH-MOM-02 | Separate initiation and continuation | owner-provisional | INCLUDED, distinct target labels/controls |
| RESEARCH-MOM-03 | Hybrid time/event sampling / C delegated | proposed-by-assistant, owner delegated routine choices; no separate explicit final approval | INCLUDED as proposal, weighted base-rate safeguards |
| RESEARCH-MOM-04–12 | comparative statistics, regimes, simple-before-ML, robust OOS, realistic costs, controlled promotion | assistant-selected design proposals, review pending | INCLUDED, not represented as individually approved |
| RESEARCH-MOM-13 | Independent research track | owner-provisional | SUPERSEDED IN SCOPE by general-purpose strategy generation |
| RESEARCH-ARCH-01 | General-purpose multi-family Strategy Generation, momentum first | owner concept approval | INCLUDED |
| RESEARCH-ARCH-03–06 | news/event research input optional; temporal correctness, news/no-news ablation | proposal direction acknowledged | INCLUDED; source rights remain open |
| RESEARCH-ARCH-07 | separate Strategy Generation vs Trader Analysis Lab with shared core | owner direction | INCLUDED |
| RESEARCH-ARCH-v1.0 RA-01–12 | scientific self-diagnostics and controlled self-improvement | assistant design presented; owner 'ابدأ' and 'كمل' authorize developing design, not final G0 | INCLUDED as proposed specification |
| v1.2 RA-13–20 | orthogonal evidence validity, dependency invalidation, RIG, budgeted experiment priority | assistant design presented, owner continued design | INCLUDED as proposed specification |
| 2026-10-22 owner final instruction | work in parallel, no collision; then execute/upload to GitHub | explicit authorization for this scoped documentation deliverable | ACTION AUTHORIZED for isolated docs-only branch/Draft PR; no code/merge/G0 |

**Important:** this is a reconciliation of context actually visible here and named GitHub records, **not** exhaustive certification of all other chats. PR #15 documents owner-provisional G1-ARCH-29–44, PR #16 owner-provisional G1-PLAN-01–09; they are reviewed as design dependencies without falsely treating direct documentation uploads as subsequent Work submissions.

## 3. Compatibility matrix and authorities

| Current source / status | Research concern | Reuse vs addition | Gate / conflict assessment |
|---|---|---|---|
| `01_CONTRACT.md` main Draft: modular monolith, shared data, paper traders, shadow tests | Research service shape | REUSE modular monolith; ADD bounded logical tracks | Compatible; operational implementation gated |
| `09_DATA_SCHEMAS.md` main: UniverseSnapshot, MarketBar, FeatureSnapshot, Observation, Outcome | Time-limited research input | REUSE; PROPOSE versioned dataset/observation attachments | Compatible conceptually; later schema ADR required |
| `09_DATA_SCHEMAS.md` main: Experiment, Trader/Signal/Trade | frozen experiments and trader analysis | REUSE Experiment, immutable trades; ADD run/diagnostic/proposal records | Compatible, not approved physical schema |
| `10_TEST_POLICY.md` main: replay, bias, paper ambiguity, purged splits | scientific validation | REUSE; ADD prospective falsification and lineage tests | Compatible |
| G0-PAPER-01–08 PR #7 OPEN | safe fills/exits, outcomes, missing/ambiguous | READ-ONLY dependencies; research variants isolated | No parent-trader rewrite |
| G0-TIME-01–09 PR #8 OPEN | news first observed, historical availability, intrabar fallback, frozen context | ADOPT stricter provenance in design; avoid new operational policy | Requires G0 decision and consistency audit |
| G0-DATA-01–08 PR #8/#10 OPEN | historical archive, provider budget, Fast protected positions | READ-ONLY, priority/yield and shared budget interfaces | No duplicate Binance data collector |
| G0-GOV-01 PR #9/#10 OPEN | owner-submitted Work continuity | FOLLOW evidence/known gaps; no fabricated Work submission | Audit incomplete for inaccessible chats |
| G1-ARCH-01–28 PRs #12–#14 OPEN | secretary pipeline, shared indicator manager, validity | REUSE logical versioned snapshots; no competing manager | Research validity separate from operational VALID |
| G1-ARCH-29–44 PR #15 Draft OPEN | indicator catalog, quality, observability | READ-ONLY conceptual dependency | No assumption of active runtime |
| G1-PLAN-01–09 PR #16 Draft OPEN | shared collector, durable Inbox, Fast/Slow, backup | Research READ-ONLY consumer with independent low priority | Never equate archive ACK with verified backup |
| Existing `ExternalEvent` main Draft | macro, sector, asset news | REUSE; enrich research visibility, version and ablation | Provider rights/data history unknown |
| `02_ROADMAP.md` main Draft | G1–G6 gate sequencing | RESEARCH SPEC PARALLEL ONLY | Any implemented integration waits relevant gates |
| Existing G1 scanner/trader ownership | actual entries, exits, signals, live validity | NEVER delegated to RIE/RIG | Permission boundary hard-fail |

There is no evidenced direct contradiction forcing branch abort at the **documentation** boundary. Open architectural dependencies remain: time/visibility contractual alignment, source and data licenses, storage/compute/provider budgets, confirmed identity and validity ownership, fill/portfolio models, approval gates.

## 4. Future acceptance tests / negative checks (NOT RUN)

| ID | Required falsification or failure scenario | Pass criterion |
|---|---|---|
| RA-T01 | Future data available after decision, including edited news | No earlier-use eligibility; provenance audit |
| RA-T02 | Data correction after experiments published | All known descendants annotated, old evidence retained |
| RA-T03 | Missing link in evidence graph | UNCERTAIN/UNVERIFIED, never silent VALID |
| RA-T04 | Synthetic null/noise pattern mining with many trials | predeclared false-discovery bound estimated across seeds, not single lucky run |
| RA-T05 | Correlated/overlapping labels | purged/blocked inference, denominator and uncertainty disclosed |
| RA-T06 | Same-bar ambiguity, no fill, fee stress | bound scenarios never reported as confirmed PnL |
| RA-T07 | Research/operational contention | protected core/positions maintain measured resource reservations |
| RA-T08 | Duplicate interrupted research publication | stable immutable logical artifact with idempotency evidence |
| RA-T09 | Parent trader exited but revised hypothetical exit wins | original frozen trade immutable; isolated counterfactual path |
| RA-T10 | RIE requests promotion/paid feed/live trade | denied without human-approved authority |
| RA-T11 | Candidate wins only on a repeatedly exposed holdout | independent OOS claim disqualified |
| RA-T12 | Long-term/Swing adapter added | shared contract untouched; domain-specific evaluation supported |
| RA-T13 | Source outage vs true market drift | diagnosis uncertainty and data quality separate from regime shift |
| RA-T14 | Event-based sampling omits base-rate controls | invalid confirmatory classification until denominator/weights restored |

Evidence required after implementation authorization: input fixture digests, expected/actual outputs, timing traces, split manifests, reproducibility IDs, negative tests, cost/CPU/IO/provider benchmarks, documented limitations, independent reviewer and owner signature. Zero executable tests, runtime probes or profitability evaluations were performed for this docs-only package.

## 5. Phases and non-goals

**D0 — this Draft PR:** architecture, interfaces, risk/acceptance proposals, source provenance and owner summary. No operational changes.

**D1 — future separately authorized contract ADRs:** review with G0 and pending G1; decide temporal eligibility class typing, attachment/lineage storage, resource envelope, ownership and retention.

**R1 — after required data gates:** minimal dataset manifest and experiment registry, baseline tests, mathematical validation and evidence guardian.

**R2:** Momentum Initiation/Continuation with correct matched controls and prospective eligibility; reject unsupported generalization.

**R3:** Trader Analysis Lab with frozen opportunity ledger and matched counterfactual evaluation; no original trade mutation.

**R4:** budgeted RIE planning and adversarial testing only after experiment history and reviewed safety policies.

**R5:** strategy-family expansion (intraday, swing, long-term) by concrete use cases and validated resources.

No implementation work is authorized by this package; do not infer profitability targets, immutable universal TTL, numerical API budget, storage format, paid feeds, provider coverage, or default portfolio sizing.

## 6. Owner approval summary

**Requested (not yet given):** architectural acceptance **in principle** of two independent logical research tracks + shared quantitative/evidence core + read-only G1 data integration + versioned statistical experimentation + bounded, non-authoritative intelligence.

**Design tradeoffs:** stronger temporal and statistical integrity vs additional provenance burden; high extensibility vs adapter complexity; self-diagnostics vs false alarms; richer news/sector data vs cost and historical completeness; research autonomy vs hard promotion barrier.

**No owner decision required to publish documentation-only Draft PR** under the explicit 2026-10-22 instruction. Before actual implementation the owner must approve any shared interface modifications, resource envelope, new paid source, trader promotion or material operational interaction. All named RA decisions remain **proposals**, not final G0 decisions.

## 7. Handoff/status and next exact task

`CURRENT GATE: G0 OPEN | WP: RESEARCH-ARCH-D0 | DONE: isolated research documentation | EVIDENCE: Draft PR and commit refs after publication | OPEN FAILURES: inaccessible other-chat handoffs, untested runtime assumptions, unresolved budgets/source rights | RISKS: leakage, false discovery, collision if future contract writes bypass ADR | NEXT: owner reviews Draft PR; independent G0/G1 contract reconciliation before any implementation`.

Review/check this document with the rest of the new files; this text does not assert that an unwitnessed Work task was executed or that a PR merged.
