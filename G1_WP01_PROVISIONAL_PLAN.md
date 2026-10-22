# G1-WP-01 — Reliable Market Data Foundation: provisional planning decisions

Status: **OWNER PROVISIONAL / PLANNING ONLY — NOT IMPLEMENTED OR TESTED**  
Recorded: 2026-10-21. Source: owner approvals in the ATLAS Quant Lab conversation; this file records those approvals, not independent review.  
Project: AQL-CRYPTO-RESEARCH-001. Base: PR #15 head `ee35d3ced5bc570efa411422c595d4b65757a0da` (OPEN, DRAFT, UNMERGED at preparation).  
G0: **OPEN**; Issue #1 independent Claude review and explicit owner G0 approval pending.  
Last verified owner-actually-submitted Work handoff: `AQL-HO-20261021-002` (PR #14); proposed `-003` is NOT a submitted Work handoff. This documentation was written directly with owner permission, not submitted through Work.

## Scope and provisional decisions

All nine owner selections below are **option C, provisional**. They are not authorization for coding, provisioning, merging, live trading, paid services, or G0 closure.

| ID | Provisional choice | Architectural intent |
| --- | --- | --- |
| G1-PLAN-01 / C | Reliable Market Data Foundation first | Shared Binance Spot USDT collector; durable local Inbox; independent Fast live/position and Slow archive/QC lanes; replay/recovery, quality and latency telemetry. Scanner, indicators and dashboard implementation are not part of this first implementation slice. |
| G1-PLAN-02 / C | Graduated disk/capacity pressure policy | Early warnings, shed optional work, protect Fast/open positions; never reclaim data before applicable durable archival obligations; if safe persistence is impossible, fail safely and record explicit gaps. No invented thresholds; Binance upstream cannot simply be paused arbitrarily. |
| G1-PLAN-03 / C | Technology-neutral durable Inbox contract | Specify commit durability, consumer cursors, ACK, crash recovery, integrity and capacity tests before selecting storage. Local ACID database (e.g., SQLite) and append-only alternatives remain candidates for benchmarking. |
| G1-PLAN-04 / C | Independent Fast/Slow cursors and reclaim gate | Fast progress never implies Slow archive completion. Require durable archive ACK evidence, idempotent replay/effects, crash-safe reconciliation, other retention obligations, explicit gap ledger and safe reclaim. Do not promise literal exactly-once execution. |
| G1-PLAN-05 / C | Hybrid storage | Supabase/PostgreSQL for operational/trader/paper state, metrics and future dashboard; local durable Inbox and compressed raw market archive; selective off-device protection, rather than putting all ticks/raw data in Supabase Postgres. |
| G1-PLAN-06 / C | Tiered off-device protection | P0 irreplaceable operational state/configuration versions/decisions/paper events/recovery state; P1 irreplaceable raw observations, provenance and gap evidence within budget; P2 derived/cache/redownloadable data rebuilt with checks. GitHub for code/docs/schema/migrations (no secrets), Supabase for operational state, external HDD for export/archive/backup. |
| G1-PLAN-07 / C | Hybrid backup operations | Automatic feasible cloud synchronization plus periodic external HDD backup when connected, with prompting/verification and transparent missed-run/lag reporting; HDD can be disconnected and stored safely. Schedule and cadence not yet fixed. |
| G1-PLAN-08 / C | Tier-specific RPO/RTO | Separate recovery point and recovery time objectives for P0/P1/P2, measured on real capacity/network/restore benchmarks before numerical commitments. Display last *verified* successful backup, not merely last attempt. |
| G1-PLAN-09 / C | Consistent, evidenced, encrypted backups | Consistent DB exports/snapshots, versioned backup manifest with source/time/schema/coverage/checksums/location/status, encrypted sensitive copies and separately managed keys, integrity verification, isolated restore drills, rotation/retention, and recovery evidence. Do not equate cloud primary data with an independent backup. |

## WP-01 planning workstreams (not execution authorization)

1. Source event contract: stable event IDs, timestamps and clock uncertainty, source, quality, finality, completeness, provenance and version.
2. Shared Binance Spot USDT collector: websocket/REST behavior, measured provider budgets, deduplication and source-gap accounting.
3. Durable local Inbox: committed writes, capacity bounds, integrity, independent cursors.
4. Fast Lane: prioritize live observations and existing positions without giving the collector trade authority.
5. Slow Lane: archive, QC, gap ledger, archive ACK and bounded recovery.
6. Replay/restart: idempotent effects, crash recovery, gap disclosure; no fabricated historical paper fills.
7. Adaptive backpressure: measurement-driven thresholds and hysteresis, protect Fast/positions.
8. Stage-attributed latency/quality telemetry and future acceptance evidence.

## Recovery and retention distinctions

- **Archive ACK** establishes the required durable archive obligation for Inbox reclaim; **Backup Verified** proves a separate recoverable backup exists. They are **not equivalent**. Explicitly decide whether certain P0/P1 retention obligations block reclaim beyond local archive ACK.
- Supabase is an operational remote database, not automatically an independent, point-in-time recoverable copy of itself. Design independent periodic exports, with destination capacity and failure reporting; do not assume Supabase Free provides a particular backup feature or unlimited quota.
- GitHub must not receive credentials, private keys, sensitive database dumps or bulky rotating market archives.
- External HDD is useful for recovery but may have an older recovery point; disconnect/store safely after a verified copy. HDD-only data is not protected against loss of both device and HDD.
- On a new machine: restore versioned code/schema, P0 from a verified compatible snapshot, available P1 with gap disclosure, rebuild P2, reconcile idempotency and eligibility before enabling any paper-trading workflow.
- Data loss and unavailability are observable; no stale data silently becomes VALID and no retroactive simulated fill is invented.

## Open design decisions / measurable parameters

1. Benchmark storage candidates and commit/fsync durability under realistic ingest, replay and disk pressure.
2. Specify archive ACK and backup-verification retention gates per data class.
3. Measure Inbox thresholds, safety margins, pressure policy and latency budgets.
4. Define cloud P0 export/replication coverage, consistency and outage behavior within actual free-plan capacity.
5. Define backup cross-source cut/manifest and schema/version compatibility between Supabase, local Inbox and archive.
6. Determine HDD backup cadence, lag escalation and key management/recovery.
7. Determine retention generations, rotation and never-delete-last-verified-copy rule.
8. Set measured P0/P1/P2 RPO/RTO and restore drill cadence.
9. Define future acceptance metrics and failure-injection fixtures.

## Future acceptance scenarios — SPECIFIED, NOT EXECUTED

- Power failure during local Inbox commit and during backup: partial artifacts never marked committed/verified.
- Fast consumer advances while Slow lags: independent cursors; no premature reclaim.
- Disk fills / cloud quota exceeded / Supabase offline / HDD disconnected: explicit protection lag, safe failure, no silent data deletion.
- Crash/replay and repeated restore: no duplicate paper effects, stable IDs, explicit unrecoverable gaps.
- Archive/backup missing or corrupt file: checksums, coverage and manifest reject invalid set.
- DB snapshot while writes are active: consistent restore with schema/version checks.
- Lost encryption key: do not claim successful recovery.
- New-device isolated restore: verify P0, quantify P1 coverage, rebuild P2, measure real RPO/RTO and record failures.
- Clock uncertainty and ingestion delay: retain provenance and measured stage latency; never invent performance claims.

## Governance / independent review handoff

This file is a **planning addendum** for Claude's independent G0 architecture review, not a G0-approved baseline or a request to implement G1. Reviewer should challenge feasibility, boundaries, free-tier dependencies, recovery consistency and the Archive ACK vs Backup Verified distinction. Check TIME-01 policy-aware closed-candle fallback and DATA-07 trader-owned exits against original source PRs. Source PR #6–#10 assimilation was previously audited with intentional semantic refinements, but not runtime validated.

Issue #1 remains OPEN. PRs #6–#15 are not presumed merged. All proposed tests are unexecuted. Any future ChatGPT Work instruction must first re-verify the last owner-actually-submitted handoff and reconcile subsequent decisions under G0-GOV-01.


## 2026-10-22 — Owner-approved provisional B: minimal measured ingest first, full Inbox deferred

**Authority and status:** Owner explicitly selected **B provisionally**, and authorized documenting the deferred step. This is a planning-scope change only, **not** final G0 sign-off, G1 implementation authorization, PR merge, or evidence that any test has run. PR #15 cumulative documentation was squash-merged into main as `e4c1f9ec5df9265405c62bab97b2ecc807ceab7b`; this PR #16 remains an independent draft planning proposal.

**Immediate G1-WP01-MVP scope (subject to G0 final authorization):**
1. Benchmark actual Binance Spot REST/WebSocket behavior and limits with a small symbol set; record event, receipt and persistence timestamps, source identity, finality, observed gaps, failures, and measured request/latency budgets.
2. Commit received events to a **minimal restart-readable local durable journal before remote acknowledgement**; explicitly define and test its commit boundary and crash behavior. Do not call a buffered, unflushed file write durable. Replay idempotently into the operational store (Supabase only after provisioning and approval), using stable event keys.
3. Test duplicate delivery, process kill/restart, disconnected network, remote-store failure and REST gap recovery. Distinguish received, locally committed, remotely persisted, recovered and **UNRESOLVED_DATA_GAP**; do not claim zero loss without verified evidence.
4. Report measurable outcomes: input/committed/persisted/replayed counts, duplicate count, gap coverage, restart recovery time, failure modes, API usage and storage footprint. Tests are **NOT RUN** at this documentation checkpoint.

**Explicitly deferred to a later G1 work package, not cancelled:** full multi-consumer Durable Inbox with independent Fast/Slow cursors, archive ACK and reclaim gates, bounded retention and disk-pressure handling, scheduling/priority/backpressure, versioned manifests, P0/P1/P2 backup/restore and measured RPO/RTO. The minimal journal is a narrow precursor, **not** evidence of those capabilities. Before widening ingestion or enabling dependent trading/observation workloads, implement and test the relevant full Inbox/recovery guarantees and demonstrate no silent data loss, false VALID state or fabricated historical fills.

**Reopen/advance trigger:** MVP measured evidence is reviewed; any unbounded journal growth, partial-commit ambiguity, unrecoverable gap, replay mismatch or missing crash durability blocks promotion and becomes a tracked implementation defect. This deferral must be rechecked before G1 foundation acceptance; it is not a waiver of the existing architecture contract.

**Governance:** G0 and Issue #1 remain OPEN until explicit owner sign-off and evidence reconciliation. Research PRs remain separate. No new implementation, CI pass, runtime benchmark, Supabase deployment or production readiness is asserted here.
