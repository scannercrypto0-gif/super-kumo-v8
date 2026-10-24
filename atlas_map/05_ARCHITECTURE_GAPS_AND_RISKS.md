# ATLAS Quant Lab — Architecture Gaps & Risks
**Version:** 1.1-DRAFT | **Evidence snapshot:** 2026-10-24
**Main source baseline:** `4e4c3537036bdf2b106c1a63ec65b2a9855972a7` | **Documentation:** PR #74, Draft/unmerged.
Reviewed documentation baseline: `e4ce1c8a5d7911f52fb67e52f7e58c2e0ee5b476`; final document HEAD is in PR metadata/correction matrix, not the main-source SHA.
Evidence IDs and scope: [09_EVIDENCE_REGISTER.md](09_EVIDENCE_REGISTER.md). No production authorization or owner decision is created by this map.

## 1. Gaps affecting runtime/production, not documentation acceptance

| ID | Accurate current gap | Scope / severity | Evidence and disposition |
|---|---|---|---|
| GAP-01 | Sustained operational acceptance incomplete | HIGH | #64 reports bounded Binance REST/WS/finality/forced reconnect+harness-scheduled recovery ACCEPTED WITH FOLLOW-UPS. No unattended deployment, broad outage or production certification. E-71. |
| GAP-02 | Accepted-main independent holdout integration absent | HIGH for confirmatory research | HoldoutCustody/TrialFamilyLedger/HoldoutEvent code and tests exist in unmerged #46 ancestry. No independently segregated empirical holdout service accepted; do not call all custody code absent. E-80/E-83. |
| GAP-03 | Operational→historical artifact bridge absent | HIGH for data eligibility | Draft73 archive is not a CustodyAccessor importer; Draft78 is an input adapter, not live ingestion. #77 requires provenance/receipt/units/split evidence. |
| GAP-04 | R09 legacy credential resolution not evidenced | CRITICAL owner action | No secrets inspected. Documentation, CI and closed governance issues are not issuer revocation/rotation evidence. E-01/E-50. |
| GAP-05 | Supabase Cloud acceptance absent | Authorization-dependent | Existing adapter/migrations and disposable PostgreSQL tests exist. #65 cloud TLS/role/RLS/restart acceptance remains NOT TESTED without named sandbox authorization. |
| GAP-06 | Integrated accepted Research Lab absent | HIGH mission gap | Main foundations, unmerged synthetic engine/statistics/ledger/custody and Draft78 are real code. Reconcile existing components; do not restart a duplicate engine or treat green synthetic tests as profitability. |
| GAP-07 | #75 unused-WritePriority premise disproved | NOT REPRODUCED as stated | DurableJournal constructs WritePriority; commit() holds foreground/background gate; mark_persisted() holds background gate; pipeline recovery passes background=True and consumer shares journal. No direct pipeline import is required. Source/test evidence E-88; high-load fairness beyond this cooperative instance remains unverified, not a proven current fault. |
| GAP-07b | Windows sustained load/power-loss limits | Operational limitation | Existing throughput/SIGKILL skips are explicit. #73 file fsync/process-exit recovery tested, directory fsync unsupported→DEGRADED. No host-wide I/O quota/power-loss certification. |
| GAP-08 | #76 identity semantics need explicit distinction | Contract limitation, not proven bar-integrity bug | created_at_ms is deliberately covered by instance-integrity hash. Existing manifest_hash commits ordered full bar checksums, including temporal/source fields. Same retained manifest can reproduce cross-process receipts; independent imports differ. New public content identity needs OD-01; do not remove all timestamps. |
| GAP-09 | Accepted-main durable trial-family reconciliation absent | HIGH for formal evaluation | Registries and journal exist in #46, main AttemptRecorder is a different sink port. #77 is blocked on this interface/ancestry reconciliation, not global absence of all trial code. |
| GAP-10 | Unified monitoring UI/alerts absent | FUTURE PHASE | HealthSnapshot code/tests exist; a dashboard/Telegram runtime and operator workflow are not implemented. |
| GAP-11 | Multi-symbol/multi-interval production scale unvalidated | HIGH before scale activation | Synthetic multi-symbol4096-row archive fixture and parameterized single-stream G1 do not certify universe orchestration, global API budgets or sustained scale. |
| GAP-12 | Secretariat/Scanner/Virtual Trader runtime absent | Core mission work remaining | Provisional contracts exist. No paper decision/lifecycle implementation or trading activation is created by this documentation. |

## 2. #75 call-chain finding, not an architecture decision

At main: journal/durable_journal.py constructs self.write_priority (L88);
commit() enters hold(background) (L120–122); mark_persisted() enters
hold(background=True) (L252–254). pipeline._run_gap_recovery passes
background=True (L78), and JournalConsumer calls mark_persisted through the
shared journal. test_core_waiter_precedes_next_background_writer covers
cooperative ordering; existing G1 CI passes. It cannot preempt a current fsync,
coordinate separate journal objects/processes, or guarantee host-wide fairness.
No code fix, deletion or new wiring is justified by the original zero-caller
claim. OD-06 is a reconciled finding, not a required owner choice.

## 3. #76 instance identity, content and reproducibility

Code-traced facts: validate_bars creates wall-clock created_at_ms;
DatasetManifest._compute_integrity_hash covers it and semantic metadata.
manifest_hash is SHA256 of ordered complete bar checksums. Those checksums bind
chronology, observation/receipt/availability and source, not just prices.
Indicator computation_hash hashes ordered result provenance hashes; it does not
hash Python accessor memory identity. Consequently two fresh imports normally
differ, while replay of the same retained manifest/inputs/configuration can
reproduce across processes (Draft78 tests/CI, E-86). A retained digest detects
tampering only relative to that trusted commitment; self-hashing is not external
custody. This behavior matches current instance-integrity semantics.
OD-01 proposes a separately versioned semantic comparison identity, preserving
all temporal/source distinctions and old hashes. No implementation here.

## 4. Canonical risk IDs (do not redefine 08_RISKS.md)

| ID | Canonical risk | Severity in register | Relevant evidence / residual |
|---|---|---|---|
| R01 | Scope creep | CRITICAL | Bounded issues/ADRs; this PR docs-only, no scope authorization |
| R02 | Future leakage from candles/news/regimes | CRITICAL | PIT contracts/tests; real receipt/availability and integrated capture gaps remain |
| R03 | In-sample overfit | CRITICAL | Unmerged statistical/family/purging foundations; no empirical OOS/forward acceptance |
| R04 | Binance rate limits | HIGH | Code budgets/fixtures and finite #64 observation; no full-load provider validation |
| R05 | Supabase growth/outage | HIGH | Option B conditionally decided; cloud untested, operating quotas unresolved |
| R06 | Event licensing/coverage | HIGH | Source/rights/coverage inventory remains provider-specific; no universal backfill promise |
| R07 | Optimistic paper fills | CRITICAL | Conservative provisional fill/ambiguity rules; no accepted paper execution runtime |
| R08 | Correlated observations | HIGH | Cluster/dependence sensitivity foundations; effective empirical sample size unproven |
| R09 | Exposed token in legacy code | CRITICAL | Owner issuer-side action/evidence still unresolved |
| R10 | PC power/network failure | HIGH | WAL/replay and Draft73 recovery/backup tests; off-device/power-loss protection not certified |

## 5. Open boundary proposals and resolved direction

OD-01/02/03/05 are architectural choices for owner review. OD-04 preserves #72's
current placement, with only a future structural alternative. OD-06's unused
premise is disproved. OD-07 Option B is DECIDED CONDITIONALLY; final ADR and
operating authorization remain separate. These are not seven undecided vetoes
on documentation acceptance. #73's technical acceptance is for optional inactive
code, never production. No new critical issue is created by this map.
