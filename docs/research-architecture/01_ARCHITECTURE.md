# ATLAS Research Architecture — Independent Design Specification v1.0

Status: **PROPOSED / DOCUMENTATION ONLY / NOT G0 APPROVED**  
Project: `AQL-CRYPTO-RESEARCH-001` | Repository: `scannercrypto0-gif/super-kumo-v8`  
Handoff: `AQL-RESEARCH-HO-20261022-001` (direct owner authorization to produce documentation; **not** proof a ChatGPT Work task was submitted).  
Branch base: `main@ed188f1902d397fe74613dd966c5a3e88b32f8c0`.  
Dependencies: G0 OPEN, Issue #1 OPEN; G1 designs in open PRs are provisional, not merged.

## 1. Purpose, boundaries and non-goals

Design a reusable quantitative research capability for **many** strategy families, initially momentum initiation and continuation, then intraday, swing, long-horizon investment and other approaches. Separate two **logical** tracks:

1. **Strategy Generation Track (SGT)**: starts from time-eligible market/event observations, discovers opportunity structures, generates falsifiable hypotheses, constructs versioned candidate strategies, and challenges their statistical and economic validity.
2. **Trader Analysis & Optimization Lab (TAL)**: starts from all trader opportunities (triggered, rejected, expired, unfilled, unselected where recorded) and executions; measures failure mechanisms, attribution and risk; proposes isolated counterfactual improvements without mutating actual trade/accounting records.

Both use a **Shared Quantitative Research Core (QRC)**: dataset access, statistical tests, independent simulation models, risk metrics, experiment governance, evidence graph, diagnostics and versioned candidate registry. The **Research Intelligence Engine (RIE)** may recommend and, only within a future separately approved research permission envelope, run bounded non-operational experiments. The **Research Integrity Guardian (RIG)** monitors data, analysis, reproducibility and dependencies.

**Architecture:** Python modular monolith with explicit module contracts and isolated low-priority research jobs. Logical divisions do not mandate separately deployed services, databases, queues, microservices or paid systems.

**Non-goals now:** application code, migrations, deployment, production data acquisition, provisioning, subscriptions, paid APIs, live trading, changing paper trader exit/entry authority, implementing all strategy families, AI model training, and claiming profit. No autonomous promotion or self-modifying production code.

## 2. Component ownership and allowed information flow

```text
ATLAS shared data authority (G1, later G2/G5)
 finalized bars / verified intrabar observations / context / events / trader histories
                          |
                   read-only, versioned
                          v
 Research Dataset Builder + Temporal Eligibility Gate
                          |
           +--------------+--------------+
           |                             |
 Strategy Generation Track      Trader Analysis Lab
           |                             |
           +------------+----------------+
                        v
      Hypothesis Registry -> Frozen Experiment Protocol
                        |
             Reproducible Simulation
                        |
        Statistical / Economic / Risk Validation
                        |
              Adversarial Challenge
                        |
            Evidence + Dependency Graph
                        |
         RIG diagnostics / RIE recommendations
                        |
          Propose or Reject / Owner Gate
```

**Authority matrix:**
- Market data source, indicator manager, health/invalidation, budget scheduler: **operational ATLAS owner**, not research.
- Historical research dataset selection and quality eligibility: Research Dataset Builder; cannot mark source data operationally VALID.
- Research hypotheses/protocols/evidence: QRC, append/version-only.
- Original trader decisions, frozen entry/exit policies, paper fills and accounting: trader/paper authorities exclusively.
- Candidate promotion, paid resource activation, operational modifications: owner via separately approved gate and work package.
- RIE/RIG: read evidence, raise findings, recommend work; never rewrite original decisions, call broker, alter approved traders, elevate privileges or bypass G0.

Consumers request shared versioned snapshots rather than issuing redundant provider requests. Research must use bounded CPU/RAM/IO/DB/provider budgets and yield/stop before core/position-monitor starvation. No synchronous research/data backfill/news enrichment in operational decision path.

## 3. Research lifecycle and state independence

**Hypothesis:** PROPOSED -> REGISTERED -> FROZEN -> TESTED -> REJECTED or NOMINATED. Revisions are new versions, not in-place edit to frozen records.

**Experiment execution:** PROPOSED -> REGISTERED/FROZEN -> QUEUED -> RUNNING -> COMPLETED | FAILED | CANCELLED | INTERRUPTED. Resume only idempotently with checkpoints and manifest-equivalent inputs.

**Evidence validity (orthogonal):** UNVERIFIED -> VALID / DEGRADED / INVALID; reassessment records a new validity event with reason, timestamp and affected dependency scope. COMPLETED != VALID != profitable.

**Candidate:** DISCOVERED -> ELIGIBLE_FOR_HISTORICAL_TEST -> HISTORICAL_OOS_REVIEW -> FORWARD_SHADOW_CANDIDATE -> PAPER_CANDIDATE -> OWNER_DECISION. These are proposed research statuses, **not** operational trader state enums. A research label may not authorize next gate. Historical dev, historical untouched OOS and prospective forward/shadow reports remain separate; holdout reuse taints independence.

## 4. Time and market truth invariants

- At decision cutoff `t`, a feature/event is eligible only if its verified availability evidence is <= `t` and all required inputs meet the consumer's frozen freshness/finality policy.
- An event occurring or being published before `t` does not imply that ATLAS knew it before `t`; record event/published/receipt/first observed/usable times separately. Archive import never backdates live receipt.
- For bars, a finalized OHLCV cannot masquerade as an earlier intra-bar snapshot. Policy-aware verified intra-bar and explicit completed-candle fallback are permitted only as specified in pending TIME-01; never guess the fallback.
- Distinguish VERIFIED_LIVE_AVAILABLE, MODELED_HISTORICAL_AVAILABILITY and RETROSPECTIVE_EXPLANATION; the last category cannot create a historical trading decision.
- Original observation/trade contexts are immutable. Open-position context changes are new timestamped records.
- Label horizons and outcomes are stored separately from contemporaneous snapshots. Missing data or ambiguous fill/order are never silently converted to zero or assumed valid.
- Historical universe membership, sector/project classification and delistings require point-in-time coverage; absent historical membership means eligibility uncertainty and explicit survivor-bias risk.

## 5. Multi-strategy extensibility

Provide a **StrategyFamilyAdapter** logical contract (schema/version + discovery policy + signals + exit/evaluation requirements + permitted data families), independent of execution authority. A shared QRC supplies hypothesis protocol, dataset snapshots, comparison, uncertainty, risk, experiment logging and evidence lineage.

**Momentum initiation:** time-grid + event studies, pre-move features and matched negative/neutral windows; avoid choosing only historic winners. **Momentum continuation:** condition on a momentum state measurable at decision time and predict additional tradable move, separately account for late entry. Both analyze BTC/asset/sector regimes and verified news while controlling for sampling weights and overlapping labels.

**Intraday:** microstructure and fill uncertainty, short horizon and sensitivity to latency/fees.
**Swing:** regime continuity, overnight/gap risk, multi-day event timing.
**Long-term:** portfolio/rebalance policy and horizons, project fundamentals/corporate actions/crypto tokenomics where legitimately available, survivorship/selection and multi-cycle uncertainty. No universal bar-based execution abstraction forced on portfolio research.

Extensibility proof is conceptual: a new family adds an adapter and domain metrics while reusing dataset, experiment, evidence and diagnostics contracts; if shared interface modification is needed, propose ADR rather than quietly changing it.

## 6. News/event intelligence

The existing `ExternalEvent` conceptual contract is authoritative starting point. Event adapters are optional research inputs with source/licensing, dedupe/content revisions, affected-asset/sector scope, event vs publication vs first observed vs availability time. Distinguish scheduled future events known beforehand from surprise reports. Test ablation (no news vs news) on identical eligible data and cost assumptions. Null feed coverage != no news. Sentiment/LLM labels carry model version, prompt/content digest, generation time and temporally appropriate access; prohibit retrospective sentiment features leaking edited future content.

## 7. Deliverables, staged future execution and approval

This package is **architecture-only**. Future authorized stages:
- R0: cross-G0/G1 contract reconciliation; finalize ADRs, threat models and test vectors after owner approval.
- R1: reproducible dataset manifest, experiment ledger, baseline math and integrity checks (after needed G1 data gate).
- R2: momentum initiation/continuation discovery under temporal splits.
- R3: trader opportunity attribution and safe counterfactuals when paper records are reliable.
- R4: bounded hypothesis scheduling/adversarial research and meta-learning only after evidence.
- R5: additional strategy families by measured value, not speculative infrastructure.

Research work may be specified in parallel with G0/G1; **operational integration/implementation remains blocked by relevant gates**. Each future WP must state scope/non-goals, versioned interfaces, acceptance tests, resource budget, evidence, failure handling, rollback, reviewer and owner signoff.

## 8. Design risks

- Selecting historical winners creates target leakage/selection bias; denominator and control groups mandatory.
- Large hypothesis search creates false discovery; full trial-family ledger plus independent tests mandatory.
- Historical news availability is rarely proven; explicit visibility classes and licensing/cost limits.
- Hidden reuse of final holdout destroys independence; lock/record holdout accesses.
- Counterfactual exits cannot infer intrabar sequence from OHLCV; preserve ambiguity bounds.
- Self-retraining on recent losers can chase noise; the model is not authorized to change itself operationally.
- Multiple sector-specialist models may overfit thin samples; compare against pooled baselines.
- Local PC resource constraints may compromise operational monitor; lower priority research yields first.
- A research evidence validity state must not be confused with G1 indicator validity or trader READY state.

Design status: **PROVISIONAL**. No runtime tests performed and no profitability claims.
