# ATLAS Quant Lab — Architectural Decisions and Preserved Directions
**Version:** 1.1-DRAFT | **Evidence snapshot:** 2026-10-24
**Main source baseline:** `4e4c3537036bdf2b106c1a63ec65b2a9855972a7` | **Documentation:** PR #74, Draft/unmerged.
Reviewed documentation baseline: `e4ce1c8a5d7911f52fb67e52f7e58c2e0ee5b476`; final document HEAD is in PR metadata/correction matrix, not the main-source SHA.
Evidence IDs and scope: [09_EVIDENCE_REGISTER.md](09_EVIDENCE_REGISTER.md). No production authorization or owner decision is created by this map.

## Decision discipline

Objective→concrete example→A/B/C options→trade-offs→recommendation. These are
review proposals, not approvals or implementation orders. Preserve owner choices
already recorded. Four current architectural choices remain for owner review
(OD-01/02/03/05); OD-04 is only a future alternative, OD-06 a disproved premise,
and OD-07 a conditionally decided direction awaiting final ADR/operating approval.

## OD-01 — comparison identity versus instance integrity

**Status: OWNER DECISION REQUIRED.** Objective: compare equivalent research data
without weakening temporal provenance. Example: two imports of identical bars
at different creation times have equal existing full-bar manifest_hash but
different manifest_integrity_hash; replaying the retained original manifest can
match computation receipts across processes. No accessor object id is hashed.

- A: keep current fields; replay retained manifests and compare ordered full-bar
  commitments with explicit metadata. No schema change; callers must respect scope.
- B: add a versioned semantic content identity over ordered full-bar checksums
  and agreed dataset/source/units metadata, excluding only instance creation/
  self-hash fields. Preserve old instance hash, all market/receipt/availability
  semantics and independently retained anchor separately.
- C: separate OHLCV-only analytical fingerprint. Useful for value comparisons,
  explicitly unsuitable for provenance/PIT equivalence.

**Recommend B as a future authorized contract change; A remains current behavior.**
Adding a field still needs schema/version/consumer review; “additive” is not
automatic authorization. Do not rename/remove old hashes or strip all timestamps.
Related #76/#77; no code fix in this PR.

## OD-02 — shared indicator ownership, separate runtime semantics

**Status: OWNER DECISION REQUIRED.** Objective: reuse maths without coupling
offline research custody to live secretary/trader subscriptions. Example: one
SMA specification may serve batch analysis and a live demand-aware box, with
different availability receipts, freshness and resource budgets.

- A: common versioned calculation specifications/library, distinct research/live
  adapters, schedules and evidence. Reuse without mixing authority.
- B: wholly separate live/research implementations. Strong organizational split,
  more duplicate formula/version drift risk.
- C: one shared runtime box for both. Fewer wrappers, but greater contention and
  contamination risk; must prove isolation before adoption.

**Recommend A**, subject to the existing G1-ARCH-21–44 contract and owner approval.
This does not relocate the approved future central box, grant trading authority,
or turn the accepted offline registry into a live service.

## OD-03 — operational archive to historical custody

**Status: OWNER DECISION REQUIRED.** Objective: an auditable, asynchronous data
artifact boundary. Example: a sealed Draft73 journal segment contains recorded
receipt/commit values but available_ms is unknown; export must not promote its
derived lower bound to CONFIRMED research availability.

- A: explicit offline CLI/export-import protocol with source/version/units/
  listing/adjustment/missingness and retained commitments, validated before use.
- B: scheduled bounded automation using the same reviewed artifact protocol,
  with idempotent replay and failure inventory.
- C: synchronous per-bar core→research callback. Tighter latency coupling and
  backpressure/PIT risk; inconsistent with core-run independence unless redesigned.

**Recommend A first; B only after the contract/measurements warrant automation.**
Draft73 is archival durability, Draft78 input binding; neither implements this
bridge. Import-boundary and source eligibility must be reviewed without runtime
cross-imports or duplicate acquisition.

## OD-04 — Asset Intelligence structure

**Status: CURRENT PLACEMENT PRESERVED; FUTURE ALTERNATIVE ONLY.** #72 owner-approved
concept is a future/unprioritized sub-lab under Strategy Factory. Example: an
owner-requested BTC outlook may later trigger bounded automatic reassessment
when its completed-candle condition is confirmed or its deadline expires; that
does not make the lab a trader.

- A: retain E under C, shared datasets/indicators, F independently validates.
- B: future independent organizational/service domain if workload/ownership
  demands it; requires owner decision, not simply access to live data.
- C: combine specialist and broad-market intelligence with separate contracts;
  fewer organizational boundaries, higher responsibility/authority ambiguity.

**Recommend A now (already the recorded direction).** No new placement approval
is required to document it; no implementation is prioritized. AssetOutlook
machine-readable hypotheses include source/timeframe/session, exact comparator/
units/window/deadline, freshness, debounce and next action. Confirmation,
contradiction, non-occurrence and material-change evidence cause reassessment,
not automatic trade/risk actions. UNKNOWN data stays UNKNOWN. TTL never extends
silently; new deep analysis creates a new immutable linked version.

## OD-05 — specialist outlook versus broad context

**Status: OWNER DECISION REQUIRED for the future contract boundary.** Objective:
prevent ambiguous ownership when BTC appears in both E and J. Example: J may
publish observed BTC/ETH/breadth context; E publishes a hypothesis about BTC
drawdown with uncertainty and horizon. Neither is a trader command.

- A: J owns cross-market context; E under C owns asset-specific outlooks; F owns
  independent claim validation; consumers opt in under approved policy.
- B: combine E/J ownership but preserve separate artifact/validation types.
- C: defer runtime ownership details while retaining the documented distinction;
  no consumer may treat an outlook as approved operational policy.

**Recommend A as the target boundary; C is the safe present non-activation state.**
No code or existing owner placement is changed. Consumer-policy and Core Run
resource-isolation acceptance precede any paper/production influence.

## OD-06 — WritePriority finding disposition

**Status: RECONCILED; NOT AN UNDECIDED WIRING CHOICE.** #75's zero-caller premise
is contradicted by DurableJournal construction, commit()/mark_persisted() and
pipeline background=True recovery calls plus the foreground-order test.
A direct import in pipeline.py is not needed.

- A: retain current shared-journal cooperative gate and document scope.
- B: future cross-process/host resource coordination if measured contention
  requires it, as a new scoped design—not a fix for an absent caller.
- C: remove or duplicate wiring solely because pipeline lacks the import;
  unjustified by current evidence.

**Recommend A; no code change or owner action is requested for the false premise.**
High-load host-wide scheduling remains unverified; no current anomaly is proven.
This docs PR does not close/edit #75 or run scheduling experiments.

## OD-07 — local authority and selective cloud projections

**Status: DECIDED CONDITIONALLY — Option B** (#67 owner decision6382338071).
Objective: preserve economically scalable authoritative evidence independently
of cloud availability. Example: bulk one-minute bars remain local/archived and
backed up; a future read-only dashboard consumes capped rebuildable summaries.

- A: cloud-central bulk candle/evidence storage (old register004 direction).
- B: local authoritative journal/full evidence + immutable bulk archive +
  independent backup; later selective capped cloud projections.
- C: B with paid projection infrastructure only if justified and authorized.

**Recorded direction/recommendation: B, preserve it.** PR73 implements bounded
Phase1 in Draft and has final technical acceptance, but is unmerged and not
production-authorized. Its ADR proposal explicitly reconciles prior004; this
map does not silently supersede the canonical register or approve that ADR.

Remaining operational approvals: disk/capture horizon, independent backup
destination/media, encryption/access, RPO/RTO, activation/retention policy and
merge. Free-tier fit is conditional on measured projection budgets; named
Supabase sandbox/TLS/RLS acceptance is still absent. These are not permission
to revisit A/B/C without new owner direction or to implement cloud services.

## Approval package boundary

Owner may approve this documentation while deferring runtime choices. Decisions
in this file do not authorize source changes, cloud, final-holdout access, paid
services, production activation or merging PR74/73/78. No generic “all seven
must be decided before any progress” gate is invented. Milestone prerequisites
and operational approvals are scoped separately in06 and the relevant issues.
