# ATLAS Quant Lab — Canonical Work Handoff Register

Project ID: `AQL-CRYPTO-RESEARCH-001`
Canonical repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8)
Rule: [G0-GOV-01](03_DECISIONS.md#g0-gov-01--work-handoff-continuity-and-completeness), owner-approved provisional.

## Register semantics
This is the single handoff metadata register; full policy text stays in DECISIONS and decision specifications stay in their canonical documents. IDs use `AQL-HO-YYYYMMDD-NNN`; historical IDs below were assigned during registration, not claimed to exist at original issuance.
Track issued/draft date, scope, owner-confirmed submission status and source separately from observed Work receipt, tool-confirmed PR and merge. Never infer a submitted baseline from a PR or secondhand summary. Preserve prior status snapshots using dated evidence updates. Record addenda explicitly; unknown is not “none.”
Before each handoff, verify current GitHub, latest owner-confirmed submitted baseline and accessible records. Missing references are coverage gaps requiring owner clarification. No register entry grants final architecture approval.

## Initial evidence inventory — 2026-10-20
Only the visible current Work thread and GitHub PRs actually retrieved were used. Other chats were NOT accessed. This is not an exhaustive cross-chat backlog audit.
- Dashboard handoff: directly received earlier in this Work thread; [PR #6](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/6) verified OPEN/unmerged. Owner confirmation of submission from another chat is not independently recorded here; earlier full addenda inventory remains unknown.
- Paper handoff: owner-provided attachment received 2026-10-20; [PR #7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7) verified OPEN/unmerged at `79bf0d902fab8fe766962425ca58d0d0528c152c`. Submitted-to-this-thread evidence exists; no assertion of separate-chat confirmation.
- TIME/DATA handoff: attachment plus mandatory final completeness addendum A–G received 2026-10-20; [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8) verified OPEN/unmerged at `19c5a747a568c727deb4cf7eb1320e30a7857241`. Addendum precedence recorded; separate-chat submission confirmation not inferred.

### AQL-HO-20261020-001 — TIME/DATA received handoff
- Date: 2026-10-20; ID assigned retrospectively by this register update.
- Scope: G0-TIME-01–09, G0-DATA-01–04 and owner completeness extensions A–G; documentation only.
- Owner-confirmed submission: **NOT SEPARATELY VERIFIED** for other chats; instruction and addendum were directly received in this Work thread. Do not substitute this receipt for an explicit owner-confirmed external submission checkpoint.
- Addenda: mandatory final completeness A–G directly received; earlier unprovided addenda, if any, unknown.
- Evidence/results: [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8), head above. Review: no final review asserted. Merge: OPEN/unmerged at inspection.
- Coverage: no claim of access to originating chats or all since-baseline decisions. Before issuing a new complete cross-chat handoff, obtain owner confirmation of last actually submitted baseline and any missing references/addenda.

### AQL-HO-20261020-002 — G0-GOV-01 received governance instruction
- Date: 2026-10-20.
- Scope: mandatory cross-chat Work handoff continuity/completeness rule and register integration; documentation only.
- Owner confirmation: rule explicitly approved provisionally in the current user instruction; this is direct Work receipt, not a claim about submission elsewhere.
- Addenda: none supplied with this instruction as of registration; later addenda must be recorded.
- Delta disposition: rule INCLUDED in DECISIONS; workflow links INCLUDED in START_HERE/SESSION/COMMUNICATION; audit fields INCLUDED in HANDOFF_TEMPLATE; initial evidence/coverage gaps INCLUDED here; STATE/LOG INCLUDED. No new architectural decision or application work.
- Completeness audit: PASS for this visible rule implementation only; COVERAGE GAP for unaccessed earlier/originating-chat records. The audit does not certify the prior TIME/DATA handoff's external completeness.
- Resulting PR: [PR #9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9), verified created OPEN on `docs/g0-handoff-completeness`; initial implementation commit `ed217a63d70e66e4d9e49ce14c98cd0a0083529c`.
- Review/merge: pending; no merge authorized. G0 and Issue #1 remain OPEN.

## Historical continuity gaps at initialization
Latest owner-confirmed externally submitted handoff and all originating-chat addenda are not established by this limited register initialization. Ask the owner for the missing confirmation/reference before claiming a future cross-chat handoff complete. Do not invent contents or claim another chat was inspected.

## Evidence update — 2026-10-20 owner-confirmed baseline
The current directly received owner handoff explicitly identifies **PR #8** as the last owner-confirmed submitted Work handoff, including its TIME-01–09/DATA-01–04 owner addenda. This resolves the prior uncertainty about which submitted baseline to use from this point onward; it does not prove access to originating chats or unprovided addenda. Actual PR #8 was re-read OPEN/unmerged at `19c5a747a568c727deb4cf7eb1320e30a7857241`. Prior NOT SEPARATELY VERIFIED entries above are retained as dated historical snapshots, not the current baseline status.

### AQL-HO-20261020-003 — governance and live-data operations
- Date: 2026-10-20. Scope/covered range: G0-GOV-01 and G0-DATA-05–08; documentation only, owner-approved provisional.
- Previous submitted baseline: owner confirms [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8), TIME-01–09/DATA-01–04 plus owner addenda, in section 1 of the directly received Governance & Live Data Operations handoff.
- Current submission: directly received in this Work conversation via owner attachment; no claim of unseen external Work execution. Addenda: none separately supplied with this handoff; all owner extensions in sections 2–10 included.
- Accessed evidence: current visible Work history/received attachments and live GitHub PR #6/#7/#8/#9 plus their retrieved documentation. Other chats were NOT accessed; completeness is bounded to accessible evidence.
- Additional since-baseline item found: G0-GOV-01 proposal already in [PR #9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9), head `8886e69562b880e35c989009961959d4c9163791`, OPEN/unmerged. Its rule/protocol/register contents are reused in this consolidated branch, not merged or silently discarded.
- Resulting consolidated PR: [PR #10](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/10), verified created OPEN on `docs/g0-live-data-governance`; initial head `8b858dc981541226ba3f24f5ba7653ee98acc8eb`. Review pending; merge not authorized.

| Delta item | Disposition and evidence |
| --- | --- |
| G0-GOV-01 plus durable cross-chat continuity | INCLUDED: existing PR #9 proposal reused in DECISIONS, START_HERE, SESSION, COMMUNICATION, HANDOFF_TEMPLATE and this register; owner submission confirmation updated explicitly. |
| G0-DATA-05 | INCLUDED: full canonical rule plus contract/schema/risk/test sections for hybrid centralized WS/REST, budgets, reconnect and provenance. |
| G0-DATA-06 | INCLUDED: deadlines/bounded scheduling, safe scanner coalescing without dropping monitoring/audit event sequences, lag/skip evidence, no fixed SLA. |
| G0-DATA-07 | INCLUDED: independent higher-priority Position Monitor/lower-priority scanner, shared acquisition/cache/budgets and modular monolith. |
| G0-DATA-08 | INCLUDED: scoped health/TTL, selective degradation, positions open with gaps, budgeted recovery, no fabricated fills or recovery guarantees. |
| Prior TIME/DATA owner extensions and PAPER rules | ALREADY DOCUMENTED IN OPEN PROPOSALS ONLY: PR #8 and PR #7 verified, not main/final approval; retained as dependencies rather than copied/simplified. |
| Future dashboard | ALREADY DOCUMENTED IN OPEN PROPOSAL ONLY: PR #6 verified; future health/lag/missingness consideration referenced, no implementation. |
| Inaccessible originating chats or additional unseen decisions | UNRESOLVED COVERAGE GAP: owner reference/content required before claiming exhaustive cross-chat audit. No additional approvals invented. |

Final completeness audit: **PASS for all five named items and explicit extensions in the received handoff; COVERAGE GAP for inaccessible originating chats**. No owner-deferred delta invented. Prior owners' provisional statuses preserved. G0 and Issue #1 remain OPEN.

## Evidence update — current owner-confirmed submitted baseline, 2026-10-20
Historical heading provenance: PR #9 named the initialization gap section "Unresolved continuity references"; PR #10 renamed it "Historical continuity gaps at initialization" and retained its paragraph unchanged. These name the same initialization observation, not two gap events. Neither the original uncertainty nor its later correction is removed.
At 2026-10-20T10:47:11Z (13:47:11 Asia/Riyadh, UTC+03:00), the owner explicitly confirms PR #10 / AQL-HO-20261020-003 as the last actually submitted Work handoff. This is the current baseline for subsequent work; the earlier PR #8 baseline remains the historical baseline of handoff 003. Exactly INT-01–06, all option C/provisional with their mandatory clarifications, are reported since 003; no other post-baseline addenda/decisions reported. This does not establish access to originating chats.

### AQL-HO-20261020-004 — authorized documentation reconciliation
- Date/receipt: 2026-10-20; evidence snapshot 2026-10-20T10:47:11Z (13:47:11 Asia/Riyadh, UTC+03:00). Scope: reconcile PR #6–#10 documentation, record INT-01–06, preserve PAPER/TIME/DATA/GOV and A–G/dashboard.
- Baseline: owner-confirmed submitted PR #10 / 003, explicit visible Execute authorization and preceding read-only handoff. Earlier three-INT draft and later six-INT read-only analysis are preparation/analysis records, not repository execution or additional submitted implementation handoffs. No duplicate ID is assigned to those stages.
- Submission/receipt distinction: owner directly submitted this Execute instruction in this Work conversation and authorizes documentation execution. External submission to unseen chats is not claimed. No subsequent addendum supplied with this Execute instruction; six recorded INT clarifications apply.
- Accessed: current GitHub main and source PR heads/docs, Issue #1 and visible conversation records. Other originating chats inaccessible; exhaustive historical cross-chat coverage remains a disclosed gap, not PASS.
- Result: prepared on `docs/g0-integration-reconciliation`. [Resulting PR lookup](https://github.com/scannercrypto0-gif/super-kumo-v8/pulls?q=is%3Apr+head%3Adocs%2Fg0-integration-reconciliation); PR creation/number not yet observed in this pre-publication commit. The resulting PR body supplies actual publication/validation evidence. Review pending; merge not authorized. This metadata must not be read as proof of a future merge.
- History preservation: events 001/002/003 remain once, including addenda A–G and original source/initial-head/review observations. PR #9 is GOV-01's historical source reused in #10, not a second occurrence of event 002.
- Delta dispositions: INT-01 INCLUDED (decision-level preservation/source matrix); INT-02 INCLUDED (review versus merge sequence); INT-03 INCLUDED (coverage/states/acceptance); INT-04 INCLUDED (policy-qualified fallback/proven availability across docs); INT-05 INCLUDED (ten-clause equality/source evidence/event dedup); INT-06 INCLUDED (dated STATE, append-only historical log and evidence distinctions).
- Earlier requirements: PAPER-01–08, TIME-01–09, DATA-01–08, GOV-01, A–G and future dashboard INCLUDED from verified open source proposals with provenance in DECISIONS. No source PR merged, modified or closed. No additional owner decision invented.
- Audit: documentary coverage of the supplied scope checked; originating-chat COVERAGE GAP remains disclosed. Application tests NOT TESTED. G0 and Issue #1 OPEN; no final architecture, trading, paid-service or merge approval.

## Evidence update — PR #11 publication and current continuity checkpoint
At 2026-10-20T13:38:18Z / 16:38:18 Asia/Riyadh (UTC+03:00), GitHub independently verifies [PR #11](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/11), head `fb79e13b58c91c6b53a7e0489114adcdcc577d15`, OPEN/unmerged, targeting main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. This is a later publication observation for handoff 004, whose pre-publication statement above remains intact. The owner identifies 004/#11 as the latest Work result actually returned and shared back to the architecture conversation. This establishes the supplied current continuity checkpoint, not access to that other conversation or final approval. No later handoff is evidenced in the inspected all-open-PR inventory or supplied records; unseen external submissions remain UNVERIFIED.

### AQL-HO-20261020-005 — G1 secretarial data architecture consolidation
- Date/receipt: 2026-10-20; evidence timestamp 2026-10-20T13:38:18Z / 16:38:18 Asia/Riyadh (UTC+03:00). Source: directly received owner attachment titled "ATLAS Quant Lab — G1 Secretarial Data Architecture Consolidation", normalized-text SHA-256 `47129ebbdf7d89b256f55faf6968692281fae3575f8f4efc159224c0164f4961`, plus visible owner disclosure of inaccessible conversations.
- Baseline: owner-identified returned/shared result AQL-HO-20261020-004 / PR #11. Distinguish this from its earlier 003 submitted baseline and from a claim to inspect another chat. Current handoff was directly submitted in this Work thread; external submission is not independently asserted.
- Scope/delta: G1-ARCH-01–11 (all provisional, C where explicitly recorded) plus owner instruction to defer every existing merge #6–#11. Mandatory corrections on nonblocking fan-out, trader-only strategy authority, durable commit boundary, limited recoverability and paper/future-real distinction are part of these existing IDs, not extra decisions.
- Addenda: all clarifications in source sections 1–6 included; visible message requires honest coverage-gap disclosure. No additional unprovided post-baseline addenda assumed.
- Accessed evidence: GitHub main/ref, open PR inventory, #6–#11 metadata/heads, #11 canonical documentation/coverage/register/protocols and visible record. Other originating chats not accessed. Completeness bounded to supplied scope; inaccessible-chat COVERAGE GAP remains disclosed.
- Owner merge deferral: explicit instruction received in source section 2; ACTIVE / owner-deferred, applies to #6–#11 and their branches. Revisit only on separate explicit owner authorization. No new ADR invented for this instruction; it does not authorize this new PR's merge either.
- Result: isolated `docs/g1-secretarial-data-consolidation`, parent `fb79e13b58c91c6b53a7e0489114adcdcc577d15` from unmerged #11, new PR targeting main. [Resulting PR lookup](https://github.com/scannercrypto0-gif/super-kumo-v8/pulls?q=is%3Apr+head%3Adocs%2Fg1-secretarial-data-consolidation). PR creation/number not yet observed in this pre-publication commit; actual tool response and resulting PR body supply publication evidence. Review pending; merge not authorized.
- Delta audit: every G1-ARCH-01–11 item and merge deferral INCLUDED in canonical source/traceability matrix; historical 001–004 events preserved once. No omitted item is silently treated as already merged or finally approved. Runtime/application/recovery/load/CI NOT TESTED. G0/Issue #1 OPEN.

## Evidence update — PR #12 publication and submitted baseline, 2026-10-21
At 2026-10-21T06:11:44Z / 09:11:44 Asia/Riyadh (UTC+03:00), GitHub verifies [PR #12](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/12) OPEN/unmerged, head `1948132315ee6a5b3174c56f767c84d1063251cd`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. This is later publication evidence for handoff 005; its original pre-publication observation remains unchanged. The current owner instruction explicitly identifies AQL-HO-20261020-005 / PR #12 as the last actually submitted Work handoff, establishing this baseline without claiming access to an originating chat. No later open Work result appears in the accessed inventory; unobserved submissions remain UNVERIFIED.

### AQL-HO-20261021-001 — consolidated G1 ARCH-12–20
- Date/receipt: 2026-10-21; verification timestamp 2026-10-21T06:11:44Z / 09:11:44 Asia/Riyadh (UTC+03:00). Directly submitted visible owner Consolidated G1 Architecture Handoff; previous actually submitted baseline 005/#12 explicitly owner-confirmed, not inferred from a draft or PR creation time.
- Scope/covered delta: G1-ARCH-12–20 and all cross-cutting constraints in the received instruction; nine provisional architecture decisions, no final G0 approval. No other post-baseline decision/addendum supplied; unseen originating records inaccessible, not certified absent.
- Mandatory clarifications included: mandatory secretary inputs may block entry despite Scanner READY; earliest relevant stage prefetch; independent non-linear trader/symbol stages and direct WATCH -> READY; eligible historical cache response need not wait; complete reuse key/consumer eligibility; class not freshness; separate latency attribution; heavy-work cooldown never delays actual transitions/live/position protection.
- Accessed: GitHub current main/startup, open PR inventory #6–#12, #12 pinned contract/roadmap/decisions/state/log/schemas/tests/risks/protocols/register/tree, Issue #1 and visible instructions. Other chats inaccessible; cross-chat COVERAGE GAP disclosed. No unseen Work submission/execution asserted.
- Result preparation: isolated `docs/g1-scanner-readiness-architecture`, parent `1948132315ee6a5b3174c56f767c84d1063251cd`, targeting main with nine-file incremental/thirteen-file cumulative docs scope. [Resulting PR lookup](https://github.com/scannercrypto0-gif/super-kumo-v8/pulls?q=is%3Apr+head%3Adocs%2Fg1-scanner-readiness-architecture); actual PR number/publication not yet observed in this commit, supplied by subsequent PR body/tool result. Review/merge pending, no merge authority.
- Delta dispositions: each ARCH-12–20 INCLUDED with canonical definition, source/conflict/destination row and future acceptance cases. All prior PAPER/TIME/DATA/GOV/INT, ARCH-01–11, owner A–G, future dashboard and distinct events 001–005 preserved; source PRs #6–#12 unchanged/open. Prior owner merge deferral remains active; no new approval to merge any PR.
- Audit: documentary coverage bounded to supplied scope and accessed evidence; originating-chat coverage not claimed. Runtime/application/CI/performance/cache/recovery NOT TESTED. No runtime config, migration, paid provider, real execution, final G0 decision or source PR mutation. G0 and Issue #1 remain OPEN.

## Evidence update — PR #13 publication and submitted baseline
At 2026-10-21T06:42:12Z / 09:42:12 Asia/Riyadh (UTC+03:00), GitHub verifies [PR #13](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/13), head `4a9bd25672d462f6b6b66beae55716942bb4a183`, OPEN/unmerged, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0`, direct parent #12 `1948132315ee6a5b3174c56f767c84d1063251cd`. This is later publication evidence for handoff AQL-HO-20261021-001; its pre-publication statements remain unchanged. Current owner instruction explicitly confirms that handoff/#13 as the last actually submitted baseline. No newer owner-confirmed submission is evidenced in accessible records/open PR inventory; unseen submissions remain UNVERIFIED, not claimed absent.

### AQL-HO-20261021-002 — shared indicator box ARCH-21–28
- Date/receipt: 2026-10-21; verification timestamp 2026-10-21T06:42:12Z / 09:42:12 Asia/Riyadh (UTC+03:00). Directly submitted visible owner Consolidated G1 Shared Indicator Box Architecture handoff; documentation proposal only, no runtime/merge/final approval.
- Baseline: owner-confirmed actually submitted AQL-HO-20261021-001 / PR #13, independently verified unmerged; not substituted by a draft. Scope/delta: G1-ARCH-21–28 plus all cross-decision checks, examples/acceptance/model deliverables and authorization boundaries supplied with the handoff. No unprovided addendum or extra option invented.
- Included mandatory clarifications: full input-version/finality/temporal single-flight identity; independent consumer cancellation; immediate active invalidation without Slow waiting; VALID/UPDATING/UNAVAILABLE with no expired active use; manager technical authority versus secretary eligibility versus trader decision; targeted subscription sequencing/current-state reconciliation; stale work/messages cannot overwrite newer state; historical retention/point-in-time semantics; demand/position priority and non-linear prefetch.
- Accessed: GitHub main/startup, open PRs #6–#13, #13 pinned canonical docs/protocols/register, commit ancestry/tree, Issue #1 and visible owner records. Other chats inaccessible; cross-chat COVERAGE GAP disclosed, unseen changes/submissions UNVERIFIED.
- Result preparation: isolated `docs/g1-shared-indicator-box`, parent `4a9bd25672d462f6b6b66beae55716942bb4a183`, target main. Nine incremental/thirteen cumulative Markdown paths. [Resulting PR lookup](https://github.com/scannercrypto0-gif/super-kumo-v8/pulls?q=is%3Apr+head%3Adocs%2Fg1-shared-indicator-box); PR number/publication not yet observed in this commit, actual PR body/tool result supplies later evidence. Review/merge pending; all existing PRs unchanged and no merge authorized.
- Delta dispositions: eight ARCH-21–28 items INCLUDED with canonical bodies and compatibility/source/destination matrix; inherited G0/G1/A–G/dashboard and each prior handoff/log event preserved. Scope completeness is documentary only and bounded to accessed evidence; originating conversations not claimed inspected.
- Runtime/application/concurrency/notification/recovery/cache/CI/performance NOT TESTED. Implementation mechanisms/numeric parameters remain unselected. No paid service, real execution or final G0 permission. G0/Issue #1 OPEN.


## AQL-HO-20261021-003 — G1 indicator catalog, quality and observability documentation proposal

- **Status:** owner provisionally approved ARCH-29–44/C and explicitly authorized direct documentation execution after Work paste stalled. This is an assistant-created documentary proposal ID, **not** a new owner-actually-submitted Work handoff. Last owner-actually-submitted remains `AQL-HO-20261021-002` / PR #14.
- **G0-GOV-01 audit:** current PR #14 OPEN/unmerged head 275c856c61452fb2fdee2c3de30a2ae9907646a8; PRs #6–#14 OPEN, Issue #1 and G0 OPEN; pinned parent branch ancestry. Accessible conversation covers all sixteen post-baseline approvals; other chats inaccessible, unseen submissions UNVERIFIED.
- **Decision coverage:** ARCH-29–44, option C, sixteen unique canonical definitions, compatibility/destination matrix, conceptual schema and test policy; earlier ARCH-01–28, A–G, future dashboard and PIT/recovery constraints preserved.
- **Limits:** documentation-only proposal; no code, no merge, no G0 closure, no live/paid actions, no technology or numeric SLA selected. Runtime/CI/performance/concurrency/notification/recovery NOT TESTED. Owner review and separate merge approval required.


### G0-REV-01/C addendum to AQL-HO-20261021-003 documentary proposal

Owner approved C documentary remediation on PR #15: sixteen future executable fixtures T29–T44, authoritative revision/reconnect/fencing acceptance, measurement uncertainty and trace criteria, evidence schemas, risks and review log. Existing PR #15 remains Draft, no merge/code/runtime tests; last owner-actually-submitted Work handoff still AQL-HO-20261021-002 / PR #14. G0 OPEN.

## 2026-10-28 — CORE-TIME-PROOF-01/B directly received execution checkpoint

Current owner instruction directly authorizes Binance observer implementation,
tests, PR and Council #134 evidence submission, with no merge/live/G0 completion.
Last explicitly owner-confirmed cross-chat submitted baseline in this register
remains AQL-HO-20261021-002 / PR #14; no later cross-chat submission is inferred.
Current scope is a directly received execution task, not a claim of exhaustive
cross-chat handoff. Accessible GitHub since-baseline history is reconciled against
main dbc191df, open #136 e61e6df, #137 d27ddd8f and Factory #141 fbf70afb, plus
Council #134 latest #6462862444. #136 bounded D3 and prior #137 crash-gap tests
are already documented/reused, not repeated as new work. All new observer scope
is included in work_packages/CORE-TIME-PROOF-01-B.md and associated evidence.
Unseen chat addenda remain UNVERIFIED; no conflicting authority was discovered
in accessible records. Independent S/R and broader external timing/custody remain
unresolved. Branch publication and exact-head validation are reported in the PR
and Council thread; this entry does not assert merge or acceptance.


## 2026-10-28 — AQL-CORE-WORK-OBSERVATION-AUTHORITY-E2E-001

Directly received execution request; not an invented cross-chat submission.
Last explicitly owner-confirmed cross-chat submitted baseline remains
AQL-HO-20261021-002/#14; current code delivery baseline #144/6465387750 at
6cb17079. Accessible GitHub delta inventoried in continuity.json, earlier
D1/D2/D3/Factory work already documented; automatic outbox/UTC/Guardian/Drive
roundtrip included in current report. Unseen chats/addenda UNRESOLVED/COVERAGE
GAP; no exhaustive unified handoff or final G0 claim. Existing Draft #144 updated,
not merged. Windows owner runs and independent Council S/R remain pending.
