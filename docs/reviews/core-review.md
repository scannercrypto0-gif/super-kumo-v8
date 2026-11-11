# ATLAS — CORE departmental review / living reference
**AQL-CRYPTO-RESEARCH-001 | 2026-11-11 | v0.1 | PROVISIONAL / OWNER-AUTHORIZED CODEX PACKAGE / NOT G0**

## Purpose and continuity
This is the **living Core review file**. Update it after Codex's evidenced handoff; preserve prior status, links, version history and unresolved items. Source-of-truth vision: [owner #202/6796603961](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/202#issuecomment-6796603961). [Codex Core mandate #273/6796830279](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/273#issuecomment-6796830279). [Architecture v1 draft #307](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/307) OPEN/DRAFT/UNMERGED at previously reviewed HEAD 202624a7300be06f50a20a51e3a103cede294b60. [Audit whole-system](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6794166523), [Asset Intelligence](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6794354966), [Lab/Discoverer split](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6796197377). Refresh all refs at execution.

## Method — repeat for every department
1. Owner target and concrete scenario; explicit boundaries.
2. Inventory current main, open Draft PRs, source code paths, tests, receipts, CI and external evidence.
3. Classify each claim MAIN_VERIFIED / DRAFT_TESTED / SYNTHETIC_ONLY / OWNER_REPORTED / DESIGN_ONLY / MISSING_OR_BLOCKED; no implicit upgrade.
4. Gap map by function, data/source, interface/ACK, quality/time, science, operation and permissions; identify overlap before proposing code.
5. Choose minimal A/B/C architecture when a genuine decision exists; document owner provisional choice.
6. Deliverable package: precise tasks, owners, dependencies, tests, negative cases, exact-head proof and residual blockers. Reassess only after evidence.
7. After Codex completion append update with date, PR HEAD, tests/CI, closed gaps, blocked gaps and any changed interdepartmental contracts; **never overwrite history or infer merge**.

## CORE target — provisional option B
One **logical Core-owned authoritative source warehouse** using existing immutable RAW archives, MarketBar, DurableJournal/OperationalStore, HistoricalLibrary/CustodyAccessor, physical files/databases/read-only indexes. Core owns authorized live/historical market, news/events, macro/cross-asset sources, provenance, rights/retention, event/published/received/known-at clocks, immutable revisions, quality, finality, as-of query, source budgets with Operations, recovery. **No duplicate warehouse.** Factory owns trials and research outcomes linked to Core evidence; Core is not the evaluator/trader.

Core must support 24/7 research consumers: Scanner decision features distinct from MONITOR_ONLY features; Discoverer **mandatory target watch** of Top Gainers, Top Losers, BTC, Top 10 Alt, PAXG, sector movement/rotation; Lab and Factory need historical/news/macro as-of context. These are **target obligations**, not claims of licensed or deployed feeds. Definitions of top-10 ranking/membership, gainer/loser horizon, sectors, PAXG vs gold, sources, cadence and rights remain explicit design decisions.

## Evidence inventory — preliminary, not exhaustive code audit
| Capability | Evidence | Status/limit |
|---|---|---|
| MarketBar/journal/store, HistoricalLibrary/CustodyAccessor | Architecture #307 inventory; main primitives and Core reports #180 | Existing components; not proof of all live integrations |
| Source→archive→query→consumer compatibility | [Core #180/6623820626](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/180#issuecomment-6623820626), draft #226: 38 focused TEST_ONLY tests | DRAFT_TESTED/SYNTHETIC_ONLY; authentic consumers not fully connected then |
| G1 and source prefreeze | Draft #287/#290/#304, [Core #273/6768081055](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/273#issuecomment-6768081055) | Bounded engineering and documentary/owner reports, not universal PIT |
| BTC historical owner data | Owner March/April reports, #273 | OWNER_REPORTED originals; retrospective NON_PIT |
| Unified news/macro/PAXG/sectors warehouse | Architecture target #307, Asset Intelligence audit | NOT_VERIFIED as deployed end-to-end |
| Sustainable continuous 24/7 source and shared IP | Draft #286/#305, integration #271 | PARTIAL/BLOCKED; no unqualified sustained-operation claim |

## Core gaps and Codex work package
| ID | Priority | Work | Acceptance |
|---|---|---|---|
| C1 | P0 | Exhaustive source/storage/query/consumer inventory on main and Drafts; map canonical owner per datum and overlaps | Exact-head path/PR/CI evidence map, no duplicate work |
| C2 | P0 | Logical warehouse contracts: identity, chronology, rights, corrections, coverage, quality and as-of access | Compatible versioned contracts and negative tests for lookahead, revisions, wrong source, missingness and conflicts |
| C3 | P0 | Source and coverage matrix for BTC, Top 10 Alt, gainers/losers, PAXG, sectors, Scanner, Discoverer and news/macro context | Provider/rights/venue/time/rank/cadence/coverage/quotas/UNKNOWN for each, no invented feeds |
| C4 | P1 | Close actual Core→Scanner/Discoverer/Factory/Lab seams only, reuse receipts and journal | Same-source, hash, ACK, replay, crash, stale/denied and idempotent recovery focused tests |
| C5 | P1 | Continuous ingest/recovery, freshness/clock/quotas and shared-IP safety | Offline fault tests and **actual** runtime evidence only where permitted; otherwise BLOCKED_EXTERNAL |
| C6 | P1/P2 | Progressive permitted news/macro/gold/PAXG/sector inputs and evidence; defer unauthorized sources | Rights/retention/first-known-at, cost/latency/quality and value-vs-baseline; missing sources explicitly blocked |

## Boundaries and risks
No private owner E: files, March/April original replay, unapproved source/provider traffic, paid subscriptions, changes to active #286 observer, concurrent #305 shared-IP pilot, code merge, G0, Paper/live trading. Reuse accepted tests; synthetic engineering success ≠ prospective PIT/OOS or continuous runtime proof. PR #307 remains an unmerged design draft. Any changed Core contract needs compatibility review with Scanner, Discoverer, Factory, Lab and Integration.

## Codex completion update template — REQUIRED
- Date / author / owner actual handoff and decisions reviewed:
- Branch / PR / exact HEAD / base ancestry / merge status:
- C1–C6 status (PASS/PARTIAL/BLOCKED_EXTERNAL/DESIGN_ONLY), with evidence URLs:
- New source/coverage matrix version and rights/clock evidence:
- Focused tests, negative cases, CI links, real vs synthetic classification:
- Interfaces impacted / consumer ACK and recovery:
- Remaining blockers, accountable owner and smallest next step:
- Audit/owner decisions pending; G0 remains provisional:
- Prior version retained; update link to this review:
