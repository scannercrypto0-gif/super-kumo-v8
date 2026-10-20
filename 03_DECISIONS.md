# ADR register — PROPOSED, not yet approved
001 new V8, legacy V7.3 read-only reference
002 modular monolith
003 Binance Spot USDT only
004 Supabase central, optional object storage and local spool
005 independent paper trades without capital portfolio
006 momentum first
007 independent same-symbol traders, correlated evidence
008 external events research-first
009 owner approves shadow promotion
010 point-in-time immutable decisions
011 4/24/72h forward horizons, max/min
012 gate evidence and owner signoff required
New ADR: ID | problem | options | decision | tradeoffs | affected interfaces | migration | approval.
Never overwrite approved decisions; supersede explicitly.

## G0-GOV-01 — Work Handoff Continuity and Completeness

Status: **OWNER-APPROVED PROVISIONAL GOVERNANCE RULE — NOT FINAL G0 APPROVAL**.
Scope: every future Work handoff across ChatGPT, ChatGPT Work and Claude conversations for ATLAS Quant Lab (`AQL-CRYPTO-RESEARCH-001`). Recording this rule does not implement application code or authorize merges.

Before issuing a new handoff:
1. Identify the latest handoff the owner confirms was actually submitted, including every subsequent addendum. Do not substitute the latest draft, PR creation time or tool-received instruction for explicit owner confirmation of submission elsewhere.
2. Consult [the canonical handoff register](HANDOFF_REGISTER.md), current GitHub evidence, and available conversation records, including other chats only when actually accessible.
3. Build a delta ledger of EVERY decision, owner clarification, requirement, correction and exception agreed since that submitted baseline; capture source/reference, date, approval status and known addenda.
4. Cross-check each delta item against the new handoff and repository documentation actually verified, including unmerged branches distinguished from main.
5. Give every item exactly one accountable disposition: INCLUDED (new handoff section), ALREADY DOCUMENTED (verified file/commit/PR evidence and merge state), OWNER-DEFERRED (owner decision/reference and revisit condition), or UNRESOLVED (gap/blocker and next action). Never silently drop an item.
6. Never claim another conversation, Work execution, PR or repository change was inspected unless its evidence was actually accessed; summaries and hearsay are not execution confirmation.
7. If an earlier handoff/addendum is inaccessible, explicitly mark the coverage gap and request the missing reference/content. Do not claim full completeness; do not issue a purportedly complete handoff until material gaps are resolved or explicitly scoped/deferred by the owner.
8. Run a final completeness audit before issuing: baseline/submission evidence and addenda identified, ledger items all mapped, approvals/proposals separated, repository evidence current, gaps stated. Report PASS or COVERAGE GAP; do not relabel a gap as PASS.
9. Record new handoff ID, date, scope, owner-confirmed submission status/evidence, addenda, resulting PR and review/merge status in [HANDOFF_REGISTER.md](HANDOFF_REGISTER.md). Distinguish drafted, submitted, tool-received, PR-open and merged facts; reconcile later updates with evidence rather than guessing.
10. All decisions remain provisional until the owner explicitly grants final approval; neither handoff completeness nor a documentation merge is architecture/trading/gate approval.

Use existing protocols and [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md); register only traceability metadata and delta audit, not duplicate full decision specifications. Direct authorized-write checkpoints use the same evidence/continuity discipline and record actual actions, without generating duplicate copy/paste work.

## G0 live-data operations decisions — DATA-05–08

Project: ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`.
**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**
Source: directly received owner governance/live-data handoff dated 2026-10-20. All four select C. Canonical full requirements follow; no runtime framework, deployment split, constants or implementation authorized.

### G0-DATA-05 — Hybrid WebSocket + REST: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves a centralized hybrid market-data ingestion architecture:

- Use Binance Spot WebSocket streams where suitable for timely live-market observations.
- Use REST for initialization, reconciliation, validation, and bounded gap recovery.
- Maintain shared market-data acquisition, caching, and request deduplication across traders and jobs.
- Coordinate WebSocket subscription/connection limits and REST request-weight budgets.
- Reconnect with controlled retry/backoff, without creating connection storms.
- Distinguish actual live-observed messages from data obtained later during REST backfill.
- Preserve event time, system receipt/availability time, processing/decision time, and source evidence.
- Do not retroactively present REST-recovered observations as though they were available to earlier live decisions.
- Use only data demonstrably available at decision time, consistent with TIME-01 and TIME-02.
- When data is unavailable or stale, apply trader-specific eligibility/freshness rules rather than fabricating current prices.

No fixed polling interval, endpoint list, stream count, or request-weight budget is approved yet. These require later validation against actual Binance Spot documentation and workload tests.

### G0-DATA-06 — Intelligent Core Run Scheduling: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves deadline-aware, non-accumulating core scheduling.

Requirements:

- Prevent uncontrolled overlapping core runs.
- Prevent an unbounded backlog of missed or duplicate scheduled runs.
- Prefer processing the latest valid market state for current scanning when intermediate display/scanning snapshots can safely be coalesced.
- **Do not discard event sequences required for paper-position monitoring, fill ambiguity analysis, chronological replay, or auditability.**
- Track run start/end, duration, lag, deadline misses, queue depth, and skipped/coalesced work.
- Set bounded execution and concurrency policies, to be determined through measurement.
- Give open-position monitoring higher priority than new-opportunity scanning.
- Keep archive backfill, news enrichment, heavy reports, and Research Lab jobs outside the critical live-run path.
- Preserve idempotency and deterministic event ordering when work is retried.
- On stale or missing essential data, block affected decisions and record why.
- Do not invent a fixed 30-second SLA: the owner's 30-second example is illustrative, not a committed performance target.
- Ensure any skipped scanning cycle is recorded accurately; do not backfill missed opportunities as if they were generated live.

### G0-DATA-07 — Independent Position Monitor & Opportunity Scanner: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves two logically independent operating paths that share a central market-data service:

**Higher-priority Position Monitor**
- Monitor open paper positions and evaluate their predeclared TP, SL, time-based, trailing, and early-exit policies.
- Do not wait for a full-universe scan to finish.
- Preserve event chronology, point-in-time data validity, and same-bar ambiguity handling.
- Never fabricate TP/SL hits or fills based on stale or later-discovered prices.

**Lower-priority Opportunity Scanner**
- Evaluate symbols and trader entry eligibility using shared, freshness-qualified market data.
- Scan in bounded batches or adaptive schedules.
- Under load, reduce or defer new-opportunity scanning before starving open-position monitoring.
- Log skipped or delayed scans and their reasons.
- A trader requiring a stale/missing shared regime input must not open a new position.

**Shared foundation**
- Reuse centralized WebSocket/REST ingestion, caches, market-context snapshots, provider budgets, and provenance.
- Avoid duplicated per-trader API requests.
- Preserve independent trader strategy/rule state and decision identity.
- Do not let heavy Research Lab or archive tasks monopolize CPU, memory, I/O, database connections, or network resources.

Logical independence does not require separate deployed applications or services. Keep the modular-monolith architecture unless later approved otherwise.

### G0-DATA-08 — Feed Health & Selective Recovery: C

**PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL.**

The owner provisionally approves health-aware selective degradation and recovery.

Track feed health at an appropriate granularity, including source, symbol, stream, and data type.

Conceptual states:
- `HEALTHY`: Evidence supports the required freshness and integrity.
- `DEGRADED`: Delayed, incomplete, or uncertain observations; affected decision eligibility must be evaluated explicitly.
- `UNAVAILABLE`: Required data cannot be trusted for the intended decision.

Requirements:

- Monitor connection liveness, provider messages, relevant event sequencing, timestamp freshness, data continuity, and reconciliation results.
- Do not treat the absence of new trades alone as proof of a broken WebSocket connection.
- Apply source- and indicator-specific TTL/freshness policies consistent with TIME-09.
- On feed failure, block only decisions whose required data is unavailable; unaffected independent symbols/traders may continue.
- Open paper positions remain tracked as open during outages, with explicit monitoring gaps and uncertainty.
- Do not invent current prices, entry fills, exits, or retroactive real-time decisions.
- Attempt bounded reconnection, REST reconciliation, and gap recovery within provider budgets.
- Store recovery provenance and distinguish historical reconstruction from live observations.
- Replay recovered events chronologically and idempotently under PAPER-08, preserving ambiguity where the available evidence cannot resolve event order or fill outcomes.
- Log feed-state transitions, outage windows, affected traders/positions, recovery actions, and residual gaps.
- Keep independent failure domains where possible; one impaired feed should not unnecessarily stop unrelated healthy workloads.
- Do not promise uninterrupted monitoring or guaranteed recovery during provider-wide outages.
### Dependency and governance reconciliation
G0-GOV-01 above is a durable rule applying to all future cross-chat handoffs; provisional governance status does not make it optional or grant final G0 approval. Covered decision range must be recorded for every handoff. Owner confirmation in the current received handoff establishes PR #8 as the submitted baseline, updating earlier register uncertainty without rewriting its historical snapshots.
TIME-01–09 and DATA-01–04 are proposed in PR #8, not merged; PAPER-01–08 in PR #7 and dashboard in PR #6 are also proposals. These new rules preserve their point-in-time, specialist reporting, cost control, backfill/isolation, independent trader, ambiguity and recovery constraints without simplifying or replacing their owner extensions. The closed-bars-only feature default on current main is not permission to use a later-finalized candle as earlier live data: the new live-observation path requires exact available-at-decision evidence under proposed TIME-01/02. No missing or reconstructed data may be labeled live-known.
Unresolved: source/stream/endpoint selection and limits, reconnect/backoff/deadline/TTL/concurrency numbers, scheduling implementation, feed-health transition thresholds and workload objectives; actual Binance documentation/measurement required later, not invented here.
