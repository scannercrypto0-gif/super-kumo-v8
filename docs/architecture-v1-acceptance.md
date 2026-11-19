# Architecture v1 coverage and acceptance

[Architecture](architecture-v1.md) · [Core, lifecycle and evaluation contracts](architecture-v1-contracts.md) · [Intelligence contracts](architecture-v1-intelligence.md)

All acceptance tests below are future runtime tests. MAIN and DRAFT describe exact evidence available at the architecture snapshot. DESIGN denotes a proposed integration or capability; UNKNOWN denotes unavailable evidence. Phase approval is separate from this specification.

## Contract coverage matrix

| Function / contract | Owner and producer → consumer | Evaluation and future acceptance | Authority | Current evidence | Dependency / phase |
| --- | --- | --- | --- | --- | --- |
| Source admission, query, custody / SourceEvidence | Core → Scanner, Factory, Asset | Engineering: pin source/revision/grid, reject duplicate/gap/clock swap; replay readback twice | Rights, custody, source policy | MAIN primitives; DRAFT #304/#305 | Provider terms, witness, source exact use / P1 |
| Opportunity completeness / OpportunityCensus | Scanner → Secretary, G2, Discoverer | Engineering: reconcile frozen universe; NO_SIGNAL, MISSED, DENIED and UNKNOWN totals; reject duplicate | Qualified as-of query | MAIN Generic H bounded; DRAFT #277 | Unified census adapter / P1 |
| Route, ACK and recovery / ResearchRoute, DeliveryReceipt, Envelope | Secretary and recipient → producer, Integration | Engineering: process death before and after commit, same/different hash, out-of-order, dead-letter, restart; one recipient effect | Named recipient and scope | DRAFT #261/#271; MAIN Generic H no route writes | Native transactional binding / P1 |
| Discovery / Hypothesis | Discoverer → Factory | Science/engineering: one family and all invalid/duplicate generation attempts; admissible immutable source | Research policy | DRAFT #276 | Source and registry pin / P1 |
| Trials / ExperimentRecord | Factory → Lab | Engineering: retry resumes same trial with distinct attempt; immutable exact reproducibility | Frozen protocol/source | MAIN bounded Generic H; DRAFT #267/#297/#300 | Release ancestry and crash replay / P1 |
| Independent science / EvaluationContract | Lab → Factory, Audit | Scientific: paired fixed BASE/SHADOW, sealed chronology, leakage/multiplicity and cost-once negatives, independent verdict | Frozen protocol; separately authorized final holdout | DRAFT #291/#301; retrospective #296/#300 | Witnessed prospective custody and adequate sample / P1 |
| Forward maturity / G2Outcome | Core G2 → Lab | Engineering/operations: actual 4/24/72h mature, gap stays MISSING, late record cannot rewrite | Scoped observer admission | MAIN volatile contract; DRAFT #286/#289, 72h pending | Real continuous capture/witness / P1 |
| Outcome and reverse feedback / OpportunityOutcome, NegativeFeedback | Lab → Discoverer, Factory, Asset | Science: Market/Limit/no-fill, preserve failure and missed denominators; feedback ACK and dedupe | Evaluation policy | DRAFT cost and forward primitives; DESIGN return loop | Joined evidence and consumer ACK / P1 |
| Promotion and retirement / StrategyLifecycle | Factory → Paper, Risk, Reporting | Engineering/science: enforce predecessor, block synthetic promotion; auto progression with valid Lab/risk; fail-closed stop | Phase and frozen tests, no per-strategy approval | MAIN experimental only; DESIGN automation | Policy migration and qualified evaluation / P1 |
| Paper eligibility and independent trader / PaperTradingEligibility, PaperExecution | Risk → trader → Lab/Reports | Operations: simulate live-clock limit/market, partial/no-fill, priority, stale stop and restart; zero broker traffic | Enabled phase and risk policy | DRAFT #288 offline, DESIGN real time | Reliable source and risk configuration / P1 |
| Owner scope and revocation / PermissionGrant, PermissionRevocation | Owner → verifier, publishers, executor | Security: wrong owner/nonce, wrong version or destination, cross-capability denial, stop/revoke race | Personal owner grant, independent scopes | DESIGN | Authenticated owner command and fencing implementation / gated |
| Actionable Telegram / TelegramSignal | Reporting → opted-in recipient | Operations: dedupe and timeout ambiguity, suppress stale/revoked sends, no recorded manual fill | TELEGRAM_SIGNAL_AUTHORIZED | DESIGN | Owner grant, recipient and publish reconciliation / gated |
| Real money / LiveTradingAuthorization | Verifier → future executor | Operations/Audit: sandbox auth denial matrix and stable client order ID; venue reconciliation before retry | LIVE_AUTHORIZED and separate activation | DESIGN | Venue and risk evidence, separate owner decision / gated |
| Shared quota/clock/stop / ResourceLease | Operations → Core, Integration, optional jobs | Operations: shared IP concurrent attempts under cap, crash/429/ban and clock faults, stop fence | Provider rights, budgets and lease | DRAFT #305 isolated; shared authority DESIGN | Common admission or sequential exclusivity / P1 |
| Read-only reporting and alerts / OperationalHealth, ReportProjection | Operations and Reporting → operator | Engineering: verify lag/coverage, dedupe alerts, redact restricted evidence, no actionable output without grant | Read/disclosure policy | MAIN local metrics; unified views DESIGN | Joined cursor and disclosure policy / P1 |
| Retrieval and provenance / EvidenceBundle, AIRequest | Gateway → Factory/Lab | Engineering: source-first lookup, known-at and rights, citation and injection negatives | Allowlisted sources/tools, budgets | DESIGN #84 | Source and redaction policy / P2 |
| Provider and response / AIProviderAdapter, AIResponse | Gateway → Lab/research | Engineering: pinned model/prompt/tool/input/output and cost receipts, timeout and failover, invalid output quarantine | Provider approval, resource lease | DESIGN #84 | Provider and retention/security evidence / P2 |
| Advisor and independent shadow / AIAdvice, AIShadowDecision | Factory → Lab | Science: blind timing, paired fixed baseline, abstentions/misses, gross/net and calibration | Research-only opt-in | DESIGN #79 | Frozen independent protocol / P2 |
| Features and training / MLFeatureSet, MLTrainingRun | Factory → Lab/registry | Science: chronological purge/embargo, labels known at freeze, failed run preservation, deterministic replay | Source rights and protocol | DESIGN | Pinned datasets, split and test custody / P2 |
| Model registry and inference / MLModelArtifact, MLInferenceResult | Factory → opted-in research/Lab | Engineering/science: reject incompatible/tampered model, qualify on OOS, stale/paused inference abstains | Research/shadow activation policy | DESIGN | Reused registry and Lab verdict / P2 |
| ML monitoring / MLMonitoringResult | Lab → Factory/Operations | Science/operations: drift and adequacy, independent baseline and rollback to exact pin or disable | Frozen monitoring and rollback policy | DESIGN | Mature labels and approved thresholds / P2 |
| Dossier and features / AssetProfile, AssetFeatureSnapshot | Core → Factory and opted-in research | Engineering: BTC-first UTC final daily/weekly/monthly, revised/missing coverage and venue swap negatives | Admitted Core views | DESIGN #72 over MAIN custody | Source and feature rules / P1 |
| Outlook and trigger / AssetOutlook | Factory → Lab/Discoverer | Science: debounced reassess once, stale/invalid/nonoccurrence and negative analogues; quantify incremental value | Bounded on-demand policy | DESIGN #72 | Dossier, trigger and evaluation / P1 |
| Event memory / AssetEventLink | Core → Lab/Asset | Science: replay prior as-known-at event, preserve later revisions, distinguish consulted and associated | Lawful opted-in events | DESIGN #80 | Versioned source and rights / P2 |
| Governance and stage/release / StageClosure | PM → teams, Audit → Owner | Documentation/engineering: exact pins, scoped claims, no duplicate work; authorized composite release review | Owner ratifies architecture and release scope | #205 PM OS and #134 verdicts | P0 decision; later release-stage review |

## Gate protocol

- **Engineering** verifies structure, integrity, deterministic exports, safety invariants, recovery and negative cases at exact pinned release SHA. Fail closed for broken hashes, swapped cross-role references, untrusted inputs or conflicting writes.
- **Scientific** verifies adequacy, independent chronology and evaluation, frozen hypothesis/comparator/cost rules and uncertainty. Report retrospective, eligible historical OOS and forward separately. A synthetic fixture can satisfy engineering only.
- **Operational** verifies source terms, clock, rate and cost isolation, stale data, stops, restart and attributable actual evidence. Test #286 and #305 shared-IP exclusivity before any separately authorized provider run. No synthetic proof satisfies provider use.
- **Audit** independently reviews material changes, new external source claims, scientific promotion claims at the protocol/release boundary and stage closure. Routine candidate evaluation is an automated Lab gate. PM records phase inputs, acceptance, scope and exit evidence.

## Worked flows

1. **BTC research to Paper.** A qualified Core BTCUSDT final 15m slot is committed before a strategy cutoff. Scanner persists the full universe, including one NO_SIGNAL slot and one unavailable slot. Secretary delivers a candidate ref; Discoverer records an immutable hypothesis and Factory registers its trial. Lab compares a fixed baseline using eligible cohorts and complete counters. G2 appends 4/24/72h outcomes independently. Once the protocol, release, prospective evidence and risk gates pass, the eligible version enters the activated Paper phase automatically. A Limit touch with ambiguous ordering yields conservative no-fill or UNKNOWN by frozen policy. Net outcomes and rejection reasons return to Discoverer and Asset Intelligence. No actual fill is written.
2. **Paper to Telegram.** A version active in Paper receives a personally issued TELEGRAM grant for a single trader, BTCUSDT, a named destination and a short validity window. The publisher verifies grant and freshness at send time and stores the delivery receipt. A queued AMEND following revocation is suppressed. The original notice is not evidence of a trade by ATLAS or the owner.
3. **Independent live authority.** A venue-ready adapter receives a distinct LIVE grant for an exact strategy version, trader, market and account with caps. Authorization binds one risk-approved intent to a stable order ID. A timeout is reconciled at the venue before retry, and only independent venue evidence may attest an execution. The LIVE grant conveys no Telegram publication.
4. **AI or ML challenge.** A blind AI challenge freezes its proposal from a dated evidence bundle before baseline access. A frozen ML shadow inference uses only features available at the same cutoff. Lab compares each against the fixed baseline on the same opportunities, including abstentions and no-fills. A contender with no incremental net benefit receives NO_INCREMENT feedback and remains outside promotion. A qualifying result can move to its approved research/shadow state with monitoring and rollback.

## #306 completion review

| Requirement | Canonical location |
| --- | --- |
| 1 objective, custody to feedback, non-alpha fixture | Architecture objective and flow; matrix and flow 1 |
| 2 sole owners, consumers, evaluator/fallback, status | Architecture responsibilities and pin snapshot; matrix |
| 3 ARCH-P0-01 delivery and return route | Shared delivery, Core-to-Lab and feedback contracts |
| 4 ARCH-P0-02 lifecycle and authority | Lifecycle and permissions; matrix; flows 1–3 |
| 5 ARCH-P0-03 recovery and shared resources | ResourceLease, OperationalHealth and decision register |
| 6 Asset Intelligence and Event Memory | Asset contracts and P1/P2 roadmap |
| 7 AI/ML and source-first retrieval | Evidence/AI and ML contracts; flow 4 |
| 8 Telegram and no manual-fill inference | TelegramSignal and distinct grants; flow 2 |
| 9 independent evaluation and evidence grades | Evaluation and feedback contracts; gate protocol |
| 10 incremental roadmap and handoff examples | Architecture roadmap; worked flows |
| 11 provisional decisions and open questions | Architecture decision register |
| User supplement stages 0–7 | Evidence/continuity, architecture, typed contracts, intelligence, permissions, evaluation, matrix and this review |
