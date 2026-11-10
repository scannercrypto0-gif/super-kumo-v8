# ATLAS Quant Lab — Lead Systems Implementation Engagement Proposal
**Project ID:** `AQL-CRYPTO-RESEARCH-001`  
**Official Repository:** `scannercrypto0-gif/super-kumo-v8`  
**Target Audience:** Project Manager & Quant Architecture Lead (ChatGPT / PM), Project Owner (`scannercrypto0-gif`)  
**Author:** Antigravity (Advanced Agentic Systems Engineer / Lead Implementer)  
**Baseline Verified:** Commit `dbc191d` on `main`  
**Date:** 2026-11-03  
**Status:** PROPOSED — AWAITING PM ARCHITECTURAL REVIEW & OWNER DECISION  

---

## 1. Executive Handoff Header (Per `COMMUNICATION_PROTOCOL.md`)

* **From:** Lead Systems Implementation Agent (Antigravity)
* **To:** Project Manager & Architecture Lead (ChatGPT / PM) & Project Owner (`scannercrypto0-gif`)
* **Type:** `COLLABORATION_PROPOSAL & IMPLEMENTATION_ROADMAP`
* **Context:** Transition from G0/G1 completion into active G2 Observation & Strategy Factory operationalization
* **Requested Action:** PM architectural review, validation of proposed division of responsibilities, and selection of initial execution work package.

---

## 2. Statement of Capabilities & Verified Local Baseline

The Lead Implementer has performed an independent, comprehensive verification of the entire `AQL-CRYPTO-RESEARCH-001` codebase on a dedicated execution environment (Python 3.12.10 / Windows / SQLite WAL):

* **Test Suite Verification:** 
  * Total tests collected: **1,140 tests** across 51 test suites.
  * Result: **1,130 PASSED, 0 FAILED, 10 SKIPPED** (100% passing across all active platform-compatible tests in 466.63s).
  * Skipped tests are verified platform artifacts: Unix `signal.SIGKILL` assertions (non-fatal on NT) and live Binance REST proxy fallbacks.
* **Execution Capabilities Available to PM:**
  1. **Full Runtime Execution & TDD:** Native Python 3.12 execution, pytest, benchmark profiling, and stress-testing.
  2. **Direct Version-Control Integration:** Local git workspace, branch management, cryptographic commit creation, and automated PR generation via authenticated GitHub CLI (`gh`).
  3. **High-Resilience Systems Engineering:** Deep specialization in SQLite WAL durability (`PRAGMA synchronous=FULL`), bounded thread lanes, crash recovery, adversarial tamper detection, and fail-closed architectures.
  4. **Strict Quant Rigor:** Zero-tolerance enforcement of Point-in-Time (PIT) integrity, elimination of lookahead bias (`decision_cutoff_ms`), explicit cost stress modeling (20 bps fee + 10 bps slippage), and unambiguous resolution of same-bar TP/SL conflicts (`REJECT_AMBIGUOUS`).

---

## 3. Proposed Division of Responsibilities (Division of Labor)

To maximize velocity and eliminate cognitive friction, we propose aligning with the project's original multi-party operating model (`00_START_HERE.md` / `COMMUNICATION_PROTOCOL.md`):

```
+---------------------------------------------------------------------------------+
|                                PROJECT OWNER                                    |
|             Final Gate Sign-off (G0->G1->G2), Merge Approvals, Risk Policy       |
+---------------------------------------------------------------------------------+
                                       ▲
                                       │ (Proposals, Approvals & PR Merges)
                                       ▼
+---------------------------------------------+   +-------------------------------+
|      PROJECT MANAGER & ARCHITECTURE LEAD    |   |     LEAD SYSTEMS IMPLEMENTER   |
|                 (ChatGPT / PM)              |   |          (Antigravity)        |
+---------------------------------------------+   +-------------------------------+
| • Quantitative Alpha & Hypothesis Design    |   | • Production Python Implementation |
| • Market Context, Regimes & Dominance Models|   | • Test-Driven Development (TDD)    |
| • Architectural Decision Records (ADRs)     |   | • Concurrency & Durability Tuning  |
| • Work Package Scoping (WP-xxx)             |   | • CI/CD & Automated Evidence Logs  |
| • Critical Scientific & Code Reviews        |   | • Direct GitHub PR Creation & Fixes|
+---------------------------------------------+   +-------------------------------+
                                       ▲                          ▲
                                       │ (Specifications)         │ (PRs & Evidence)
                                       └───────────┬──────────────┘
                                                   ▼
                               +---------------------------------------+
                               |           GITHUB REPOSITORY           |
                               |    Single Canonical Source of Truth   |
                               |  (Issues, PRs, State & Work Logs)     |
                               +---------------------------------------+
```

### Detailed Role Allocation:
1. **ChatGPT (Project Manager & Quant Architect):**
   * Acts as the *Strategic & Scientific Brain*.
   * Formulates Alpha models, regime definitions, indicator mathematics, and risk parameters.
   * Specifies requirements through structured Work Packages or GitHub Issues.
   * Conducts critical peer review on submitted Pull Requests.
2. **Antigravity (Lead Systems Implementation Agent):**
   * Acts as the *Lead Software Engineer & Execution Engine*.
   * Translates PM specifications into modular, clean, type-annotated, and robust Python code.
   * Writes adversarial unit tests, load tests, and integrity verification fixtures.
   * Executes local regressions, generates cryptographic evidence files, and opens PRs on GitHub.
   * Implements fixes requested during PM code reviews with rapid turnaround.
3. **Project Owner (`scannercrypto0-gif`):**
   * Acts as the *Sovereign Authority*.
   * Confirms project milestones, gate closures, repository merges, and production/exchange authorizations.

---

## 4. Key Engineering Services & System Accelerations Proposed

To accelerate ATLAS Quant Lab toward an operational, robust, and verifiable trading system, the Lead Implementer proposes the following high-impact engineering workstreams:

### Workstream 1: Vertical Slice of G2 Virtual Trader Runtime (`CAP-21` / `CAP-08`)
* **Problem:** G1 live data ingestion is complete and verified, and G2 observation contracts exist in theory, but there is no continuous running service that instantiates virtual paper traders and tracks executions against real-time WebSocket feeds.
* **Proposal:** Implement an event-driven `VirtualTraderService` that consumes verified bars from `DurableJournal` / `OperationalStore`, evaluates frozen `StrategyDefinition` models in real time, logs orders into a crash-resilient `PositionJournal`, and produces immutable trade receipts without risking live capital.

### Workstream 2: Historical Archive to Custody Bridge (`GAP-03`)
* **Problem:** The operational store (`OperationalStore`) and local archive (`LocalArchive`) are currently decoupled from the quantitative research library (`CustodyAccessor` / `HistoricalLibrary`).
* **Proposal:** Build a verified, deterministic data bridge allowing live-collected, verified bars to be seamlessly partitioned, checksummed, and ingested into `HistoricalLibrary` datasets with full audit provenance.

### Workstream 3: Post-Merge CI Trigger & Automated Evidence Capture
* **Problem:** Post-merge main CI was previously bypassed due to trigger scope mismatches, and evidence registration involves significant manual overhead.
* **Proposal:** 
  1. Patch GitHub Actions workflows to ensure seamless pre-merge and post-merge automated verification across Ubuntu and Windows runners.
  2. Implement an automated evidence capture tool that compiles test matrices, SHA-256 digests, and hardware latency figures into machine-readable JSON artifacts.

### Workstream 4: Telegram Health & Incident Dispatcher (`CAP-23`)
* **Problem:** `HealthSnapshot` reports system degradation, clock skews, and data gaps effectively, but requires manual polling.
* **Proposal:** Implement a decoupled, lightweight alert dispatcher communicating with Telegram via official bot webhooks (rate-limited and non-blocking) to alert the operator immediately upon `UNHEALTHY` or `CLOCK_UNCERTAIN` events.

---

## 5. Proposed Workflow Protocol (The Exact Collaboration Cycle)

1. **Task Commissioning:**
   * PM posts a task specification or Work Package in a dedicated GitHub Issue (e.g., `[WP-G2-01] Virtual Trader Runtime Specification`).
2. **Branch Creation & Implementation:**
   * Lead Implementer branches off latest `main`: `git switch -c feat/wp-g2-01-virtual-trader`.
   * Implements requested modules and matching test suites in `src/aql` and `tests/`.
3. **Local Rigorous Verification:**
   * Lead Implementer executes `pytest`, verifies zero regressions across all 1,140+ tests, and collects performance evidence.
4. **Pull Request Submission:**
   * Lead Implementer pushes branch and opens an evidence-backed Pull Request referencing the Issue (`gh pr create`).
   * The PR includes:
     * Precise diff summary.
     * Full local test output log.
     * Updated `04_STATE.md` and `05_WORK_LOG.md`.
5. **Architectural Review & Feedback:**
   * PM (ChatGPT) reviews the PR diff and evidence comment.
   * If revisions are requested (`CHANGES_REQUESTED`), Lead Implementer updates the branch immediately.
   * If approved (`APPROVED`), Owner merges to `main`.

---

## 6. Open Questions for Project Manager Review

We invite the Project Manager (ChatGPT) to review this proposal and provide guidance on:

1. **Work Prioritization:** Does PM prefer commencing immediately with **Workstream 1 (G2 Virtual Trader Runtime)**, or prioritizing **Workstream 2 (Archive-to-Custody Bridge)** or **Remediation (#215)**?
2. **Contract Specifics:** Are there specific state machine transitions or data contracts the PM would like enforced for G2 paper positions beyond those defined in `docs/core/g2_position_lifecycle.md`?
3. **Handoff Format:** Does PM confirm that GitHub Issues / PR comments are the preferred communication medium, or is a specific markdown handoff template required for each batch?

---
*Submitted for architectural review by Lead Systems Implementation Agent (Antigravity).*
