# Append-only log
2026-10-20 | ChatGPT | Created V8 project governance draft | No code/tests run | G0 OPEN.

## 2026-10-20 — WP-000 bootstrap
Created local Git repository baseline, README, .gitignore, session/handoff protocol, WP tracking. No remote or Supabase connection established. G0 remains open pending owner approval.

## 2026-10-20 — Public repository and G0-001 documentation review

- Confirmed official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8), Public; owner `scannercrypto0-gif`; default branch `main`.
- Previously reviewed baseline: `f25f7072c9dea638d218c7f5e89f165e5a393096`. Re-read latest main before editing and confirmed HEAD was `f25f7072c9dea638d218c7f5e89f165e5a393096`.
- Recorded [G0-001 — Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) and the published [ChatGPT architecture review — Round 1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285495222): **CONDITIONALLY ACCEPTABLE — NOT YET APPROVED**.
- Distinguished WP-000 published bootstrap (owner review pending) from active G0-001 architecture review.
- Five areas remain unresolved: paper execution, temporal integrity, recovery/idempotency, research methodology, and operational budgets.
- Updated scope: `README.md`, `04_STATE.md`, `05_WORK_LOG.md` only. Reviewed Markdown links, remote facts, and cross-file consistency. This was a documentation review; no application tests were executed.
- Historical bootstrap entries above are preserved. Their local `.gitignore` statement is not evidence of remote presence; the file is absent from the inspected main tree. Their no-remote statement describes the earlier bootstrap, not current state.
- Remaining inconsistencies outside scope: former canonical remote in `GITHUB_OPERATING_MODEL.md`; former owner, unchecked review evidence, and missing labels on Issue #1; no exact commit SHA in the existing review comment. No Issues, labels, comments, contracts, roadmap, decisions, schemas, tests, or communication protocols changed.
- G0 and G0-001 remain OPEN. Next: Claude independent review, resolution or justified deferral of critical questions, then owner approval before G0 closure and G1 implementation.

## 2026-10-20 — PR #2 governance cleanup and consistency remediation

- [PR #2](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/2) proposes public-repository governance cleanup; merge remains pending.
- Independent read-only review of head `741719fc4e0aecced10fa3317dc354339178f56a` against base `879233525b2b716514076654d7c9195efaaf70b0`: **REQUEST CHANGES**.
- Review findings: STATE still described corrected Issue #1 owner, checklist, labels, and traceability as current problems; STATE/WORK_LOG were excluded despite session consistency requirements in README and governance protocols. Checks 1–8 passed; check 9 needed changes. This was a conversational review, not a submitted GitHub PR review.
- Owner explicitly authorized expanding PR #2 from six to eight files by adding only `04_STATE.md` and `05_WORK_LOG.md`. This is documentation-consistency remediation, not architecture approval.
- Re-fetched PR head/base before editing; both matched the reviewed SHAs. Updated STATE to distinguish completed [Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) corrections, unmerged PR proposals, and remaining governance work. Existing log entries above are preserved verbatim as historical records.
- [Historical traceability annotation](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285973428) links the original architecture review to `f25f7072c9dea638d218c7f5e89f165e5a393096`; later documentation sync is `879233525b2b716514076654d7c9195efaaf70b0`.
- Verification: only STATE and WORK_LOG added to the original six-file PR scope; historical log preserved; consistency reviewed against README and governance documents; no application tests executed, secrets, architecture approvals, application changes, or issue-form edits introduced by this remediation.
- Remaining blockers/tasks: PR re-review and owner merge approval; three missing type labels; remote .gitignore verification; pre-existing issue-form schema concerns. Five architecture areas and Claude review/owner sign-off remain unresolved. G0 and G0-001 remain OPEN.
- Next exact task: reviewer checks the amended eight-file PR; owner decides whether to merge. This entry does not approve or merge the PR.

## 2026-10-20 — PR #2 merge and issue-form repair

- Confirmed [PR #2](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/2) was squash merged into main at [cc32203300a7c71b089811c90920beb6e39a48ac](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/cc32203300a7c71b089811c90920beb6e39a48ac). Earlier pending-merge entries above remain intact as historical records.
- Read latest main `cc32203300a7c71b089811c90920beb6e39a48ac` before editing. Authorized scope is only the three issue forms, STATE, and WORK_LOG; a new branch/PR carries this work and is not merged.
- Repaired comma-containing attributes labels using expanded YAML mappings in `02_bug.yml`, `03_proposal.yml`, and `04_question.yml`; preserved full intended question text, IDs, types, required fields, dropdown choices and template labels.
- Validation: YAML parsing plus local structural validation against GitHub Issue Forms documentation; checked top-level fields, allowed element/attribute keys, unique IDs, nonempty string labels, dropdown options and boolean required flags. Compared form semantics with the intended original labels and checked append-only log preservation.
- STATE now distinguishes merged PR #2 governance cleanup from this proposed form-repair PR. No application tests executed; no CI success or GitHub-hosted form acceptance is claimed.
- No Issues or labels created/edited; no credentials, secrets, architecture files, or application code added. Missing `type:bug`, `type:proposal`, `type:question` labels and remote .gitignore verification remain separate tasks.
- Next exact task: review the new five-file PR and decide whether to merge; no merge performed. G0 and G0-001 remain OPEN; architecture approval remains pending.

## 2026-10-20 — ATLAS-001 project identity migration

- Owner approved provisional project name **ATLAS Quant Lab** and Project ID `AQL-CRYPTO-RESEARCH-001`; former name SUPER KUMO V8 is retained for historical traceability.
- Official owner `scannercrypto0-gif` and repository [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8) remain unchanged; no repository rename or GitHub settings change.
- Latest main inspected: `b98b4231447b3f57570628b0808496439c745d80`. [PR #3](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/3) is already merged at `b98b4231447b3f57570628b0808496439c745d80`; prior pending-merge entries above are historical snapshots. Its UI smoke test was blocked by sign-in, not passed.
- Branch `docs/atlas-project-identity` carries only current-facing documentation identity updates, session/context isolation, and STATE/WORK_LOG synchronization. The identity PR is not merged.
- New ChatGPT, Work and Claude sessions must verify Project ID and canonical repository before using previous context; stop and report a possible cross-project context collision if either mismatches.
- Unrelated V7 step 311, `gate_spot_cvd.py`, and other-project conversations are not authoritative evidence of ATLAS Quant Lab implementation. Legitimate repository history, legacy references, Issues, PRs and commits remain intact.
- Smart Validation only: changed-file/scope check, canonical identity/link consistency, and append-only historical log preservation. No application tests or unrelated reviews run.
- Operational V8 implementation is not yet verified or started; architecture decisions, strategy logic, data schemas and application code are unchanged. G0 and G0-001 remain OPEN; architecture approval remains pending.
- Next exact task: review the identity migration PR; merge remains pending.

## 2026-10-20 — ATLAS-002 session continuity

- Verified ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001` against canonical repository `scannercrypto0-gif/super-kumo-v8`; latest main inspected `64b47b5c929221277456a85f549183f9e5757d40`.
- Recorded [PR #4](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/4) merged at [64b47b5c929221277456a85f549183f9e5757d40](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/64b47b5c929221277456a85f549183f9e5757d40); earlier pending-merge statements remain historical entries.
- Reused existing documents: START_HERE now provides exact reading order, status/task/blocker/next-action map and one reusable startup prompt. SESSION_PROTOCOL points to that order and requires completed work to update GitHub STATE/WORK_LOG with evidence links through the authorized PR workflow.
- STATE identifies ATLAS-002 as the proposed documentation task and G0-001 as the next substantive architecture-review work. Branch `docs/atlas-session-continuity`; PR merge remains pending.
- Smart Validation: canonical identity consistency, startup targets exist, necessary documentation-only scope; previous log preserved. No application tests or unrelated reviews run.
- No architecture decisions, strategy logic, schemas, application code, Issues or settings changed. G0 and Issue #1 remain OPEN. Next: review this continuity PR; no implementation or gate closure authorized.

## 2026-10-20 — ATLAS-002 mandatory proactive Work handoff

- Updated existing [PR #5](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/5); no duplicate PR or governance document created.
- Integrated owner-approved pending-change ledger categories, checkpoint triggers, automatic consolidated copy-ready Work instruction, confirmed direct-write alternative, evidence-based persistence reporting and next-session reconciliation.
- SESSION_PROTOCOL is the behavior source; COMMUNICATION_PROTOCOL and START_HERE link to it; HANDOFF_TEMPLATE contains one reusable Work instruction block. STATE records branch-only implementation pending merge.
- Smart Validation limited to identity/protocol consistency and exact six-document scope; all previous log entries preserved. No application tests or unrelated reviews run.
- No architecture/trading approvals, Issues, labels, settings or application code changed. G0 and Issue #1 remain OPEN. Next: owner reviews PR #5; merge is not authorized.

## 2026-10-20 — Future dashboard requirement recorded

- Read current main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`, architecture contract, roadmap and conceptual schemas after verifying ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`.
- Added the requirement once in [the roadmap](02_ROADMAP.md#future-requirement--unified-monitoring-dashboard); STATE links to that source instead of duplicating its specification.
- Future views cover paper positions/signals, independent trader performance, Lab/Shadow comparisons, historical outcomes, health/freshness/errors. Telegram remains the notification channel; design considerations preserve consistent records/events, identifiers/timestamps/history/outcomes and secure read-only initial access.
- No frontend or final architecture choice made. Implementation is deferred until operational data exists and requires a separately approved work package. No UI, API endpoints, tables, migrations, infrastructure or schema changes.
- Synchronized stale STATE references to [PR #5](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/5), merged as `ed188f1902d397fe74613dd966c5a3e88b32f8c0`; older log entries remain historical snapshots.
- Smart Validation: documentation-only scope and consistency; original roadmap gate text and historical WORK_LOG prefix preserved. No application tests or repeated architecture review.
- New documentation PR is not merged. G0 and Issue #1 remain OPEN. Next: review the recorded requirement; continue G0-001 before gated implementation.

## 2026-10-20 — Provisional G0 Paper Trading decisions 01–08

- Verified ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001` and canonical repository `scannercrypto0-gif/super-kumo-v8`; current main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. ATLAS-002 / PR #5 is merged; PR #6 dashboard documentation is OPEN/unmerged and left untouched.
- Owner-provided handoff selects option C for G0-PAPER-01–08 with ambiguity and exit-research extensions. Status: **PROVISIONALLY OWNER-APPROVED — NOT FINAL G0 APPROVAL**.
- Captured full owner rules in the existing decision register; contract invariants, residual risks, conceptual schema/event requirements and future regression expectations refer to that source. Existing ADR IDs, enums, versions and technical history preserved.
- Provisional 1,000 USDT reference notional is research-only; 100/10,000 USDT are sensitivity examples. Future real-capital/10% allocation discussion is nonbinding, not funded capital, approved risk policy or live authorization. No fixed Binance fee percentage adopted; official effective schedule must be checked at implementation.
- Exact strategy entry/expiry/exit values, adjustment timing, partial quantities, post-exit horizons, identity keys and promotion criteria remain deferred. Future Lab/Shadow paths must not rewrite original trade decisions/results.
- Documentation-only branch `docs/g0-paper-decisions`; one consolidated PR targeting main, no merge. STATE/WORK_LOG overlap with pending PR #6 requires preserving both sets on later reconciliation; no dashboard changes overwritten.
- Lightweight validation: eight unique decision IDs, canonical internal references/identity, full owner-decision text preservation, historical log prefix and documentation-only scope. Future scenarios specified, not executed; no application tests or implementation.
- No Issues closed or edited, strategy promoted, live execution, tables/migrations or infrastructure created. G0/G0-001 remain OPEN; next action is independent review and owner resolution/final approval.

## 2026-10-20 — Consolidated provisional G0 TIME and DATA decisions

- Verified ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001` / `scannercrypto0-gif/super-kumo-v8`; latest main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. PR #6 dashboard and PR #7 PAPER decisions remain OPEN/unmerged and untouched; review overlapping documentation after either merges.
- Canonical register captures G0-TIME-01–09 and G0-DATA-01–04, selected C, with mandatory owner clarifications A–F taking precedence; G requires explicit cross-document acceptance/traceability before PR creation. All remain PROVISIONALLY OWNER-APPROVED, not final G0 approval.
- Contract, roadmap G1 and conceptual MarketBar wording explicitly reconcile eligible verified intra-candle observations with closed-bar fallback; receipt/availability integrity remains mandatory. Existing decisions/history preserved.
- Specialist reporting separates historical development/OOS/forward, target/off-target counts/net costs/drawdown-risk/uncertainty/sample adequacy, detector evaluation and divergence causes; rich all-opportunity snapshots remain immutable with separate later observations.
- Pre-operational initial backfill has a scoped coverage inventory; incremental repairs update same library without core dependency. Independent bounded queues/shared API budgets/resource controls keep background work from blocking/starving core. Monitor paid-service budgets and require prior owner approval; no zero-cost/30-second guarantee.
- Future tests specify negative temporal/news/version/research/context/backfill/budget/isolation/gap cases; no application tests or CI pass claimed.
- Acceptance G verified owner A–F against contract, register, conceptual schemas, risks and test policy; completion/PR description contains decision/extension traceability matrix. Lightweight checks: 13 unique IDs, internal refs/identity, explicit closed-bar reconciliation, pending PAPER-01–08 cross-references, preserved log prefix and documentation-only scope.
- Branch `docs/g0-time-data-decisions`; one documentation PR targeting main; no code, executable schema, migration, paid action, strategy promotion, Issue edit or merge. G0 and Issue #1 remain OPEN. Next: independent review and owner approval before final G0 or implementation.

## 2026-10-20 — G0-GOV-01 handoff continuity and completeness

- Owner explicitly approved provisional rule G0-GOV-01. Canonical identity verified: ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`; current main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`.
- Added rule to existing decision register and linked startup/session/communication instructions; expanded existing handoff template with submitted-baseline/addenda evidence, complete delta dispositions, coverage gaps and final audit.
- No canonical handoff register existed in inspected main, so added the single necessary HANDOFF_REGISTER.md. Initial records distinguish direct instruction receipt, owner approval, unverified external submission confirmation, PR execution evidence and review/merge state.
- Verified PR #6/#7/#8 OPEN/unmerged; originating chats were not accessed. Coverage gaps are explicit; no exhaustive prior cross-chat audit claimed. Prior TIME/DATA addendum A–G noted without inventing further addenda.
- Smart Validation: provisional rule's ten obligations represented, identity/references/scope checked; historical WORK_LOG preserved. No application tests or unrelated architecture reviews run.
- Documentation branch `docs/g0-handoff-completeness`; PR review/merge pending. No application code, paid action, Issues or settings changes; G0 and Issue #1 remain OPEN. Next: review this PR; request missing baseline confirmation/references before a future completeness claim.

## 2026-10-20 — Consolidated governance and live-data operations handoff
- Verified ATLAS Quant Lab / `AQL-CRYPTO-RESEARCH-001`, main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. PR #6/#7/#8/#9 OPEN/unmerged; no branches merged/edited. Reused PR #9 governance text in this new consolidated proposal to avoid divergent duplicate policy.
- Current owner attachment explicitly confirms PR #8 as submitted baseline, updating prior register uncertainty via dated evidence, not rewriting history. Delta ledger covers GOV-01 and DATA-05–08, owner extensions and inaccessible-chat gap.
- Preserved full four owner DATA rules; documented hybrid WS/REST, bounded scheduling with monitoring-event retention, higher-priority independent Position Monitor and selective health/recovery. Conceptual records and 14 future acceptance scenarios specified; no executable design/constants.
- Earlier TIME/DATA/PAPER/dashboard proposals remain referenced as unmerged dependencies, not silently approved or simplified. Shared docs will need reconciliation on later merges; do not double-apply PR #9.
- Smart Validation: five-item uniqueness/completeness, owner-text retention, references/identity, delta dispositions, documentation-only scope and log preservation. PASS is scoped to received instructions; originating chats were not inspected. No CI/application tests or paid actions.
- One new PR on `docs/g0-live-data-governance`, targeting main; no merge authorized. G0 and Issue #1 OPEN; decisions remain provisional. Next: owner review.

## 2026-10-20 — G0 documentation reconciliation authorized and prepared
- Verified 2026-10-20T10:47:11Z (13:47:11 Asia/Riyadh, UTC+03:00): main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`, PR #6–#10 OPEN/unmerged at the source heads in the decision coverage matrix; Issue #1 OPEN. Project identity verified against current 00_START_HERE.md. Source PRs and Issue #1 are unchanged.
- Owner confirms PR #10 / AQL-HO-20261020-003 as last submitted baseline; subsequent delta INT-01–06, all C/provisional. Earlier read-only report and draft were analysis/preparation, not repository execution. This later explicit Execute instruction authorizes this dedicated documentation branch and one PR only.
- Reconciled decision-level clauses in review order #7 -> #8 -> #10, compared #9 independently, preserved #6 dashboard. Retained PAPER-01–08, TIME-01–09, DATA-01–08 and owner A–G. Added INT-01–06 with owner clarifications, restricted completed-candle fallback to explicit predeclared trader policy, and removed conflicting current-only closed-bar restrictions.
- Kept one identical GOV-01 definition with clause provenance; retained distinct handoffs 001/002/003 once. Historical source log entries above remain unchanged; original OPEN observations and prior initial-head references are historical, not current claims.
- Current snapshot and handoff evidence distinguish main/branch/proposal/receipt/submission/review/merge. Proposed PR on `docs/g0-integration-reconciliation`; opening/number is not claimed in this pre-publication snapshot. The resulting PR body supplies publication evidence and validation summary.
- Documentation consistency/traceability validation only. Application/runtime/recovery tests: NOT TESTED. No CI success, paid action, provider selection, code, Issue edit, source PR closure/rebase/merge or final G0 approval. Other originating chats inaccessible; no exhaustive cross-chat claim.
- Next: owner reviews reconciliation PR and separately authorizes any integration/merge disposition. G0 and G0-001 remain OPEN.

## 2026-10-20 — G1 secretarial data architecture documentation
- Inspected at 2026-10-20T13:38:18Z / 16:38:18 Asia/Riyadh (UTC+03:00): main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`, PR #11 `fb79e13b58c91c6b53a7e0489114adcdcc577d15`, all source PRs #6–#11 OPEN/unmerged and Issue #1 OPEN. No newer open Work PR appeared in the accessed inventory. Other chats/submissions are inaccessible or UNVERIFIED; no exhaustive cross-chat audit claimed.
- Owner identifies AQL-HO-20261020-004 / PR #11 as latest returned/shared Work result. Earlier 003 baseline and 004 pre-publication observation remain unchanged; register appends current publication/baseline evidence and new handoff 005. Delta consists of eleven provisional G1-ARCH decisions plus explicit owner deferral of all source merges.
- Compared starting from main (would require recopying/reconciling #11) versus starting from pinned #11 (preserves prior reconciliation by ancestry). Selected isolated `docs/g1-secretarial-data-consolidation` from `fb79e13b58c91c6b53a7e0489114adcdcc577d15`, targeting main with a cumulative documentation diff. No source branch/PR is modified, retargeted, rebased, closed or merged.
- Recorded all supplied G1-ARCH-01–11 text and clarifications; minimally refined DATA-07 monitor authority in DECISIONS/CONTRACT/test policy. Preserved high-priority observation/recovery duties, independent nonblocking delivery, owning-trader decisions, durable commit/archival acknowledgment boundaries, bounded capacity and explicit gap/quality provenance. A recovered paper crossing is not a verified fill.
- Added conceptual lifecycle/responsibilities, source-conflict/12-item delta traceability and future negative acceptance scenarios. Nine-document incremental scope; thirteen-document cumulative scope including inherited #11. No application code/runtime configuration/migration/provider purchase/live order action.
- Documentation checks only; all runtime/application/recovery/load/CI behavior NOT TESTED. This pre-publication record does not assert a future PR number or merge; actual PR publication evidence is returned by the tool/result and PR body. Owner review and all merge/final G0/implementation approvals remain pending. G0 and Issue #1 OPEN.

## 2026-10-21 — Consolidated G1 ARCH-12–20 documentation
- Verified 2026-10-21T06:11:44Z / 09:11:44 Asia/Riyadh (UTC+03:00): main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`, PR #12 `1948132315ee6a5b3174c56f767c84d1063251cd`, PRs #6–#12 OPEN/unmerged, Issue #1 OPEN; canonical identity verified. No later open Work PR evidenced; inaccessible conversations/submissions remain disclosed gaps, not an exhaustive audit.
- Owner explicitly confirms AQL-HO-20261020-005 / PR #12 as last actually submitted baseline. Current delta is nine provisional G1-ARCH-12–20 decisions with supplied invariants; registered as AQL-HO-20261021-001. Earlier publication/receipt/baseline observations remain unchanged.
- Chose isolated `docs/g1-scanner-readiness-architecture` from pinned unmerged #12 to preserve all prior reconciliation and ancestry; PR target main yields a cumulative diff. Starting from main alone would require recopying the unmerged requirements. No existing PR/branch modified, retargeted, rebased, closed or merged.
- Added central trader-specific screening, two requirement lists, per-trader non-linear stages, early progressive prefetch, qualified computation/cache reuse, per-decision evidence readiness and LIVE/HISTORICAL planning distinction. Only trader decides; READY cannot bypass mandatory evidence and heavy scheduling cooldown cannot delay actual stages/live/position protection.
- Proposed separate timestamps/attribution for delivery, history request, readiness, strategy waiting and actual trader processing; missing/unsynchronized evidence is not zero latency and parallel waits are not double-counted. No numeric target or implementation selected.
- Nine Markdown files changed incrementally above #12; thirteen cumulative Markdown files against main. Full prior decisions/addenda/dashboard/protocols and handoff/log history preserved. Documentation consistency checks only; runtime/CI/recovery/cache/performance NOT TESTED.
- Pre-publication record: resulting PR number not guessed; PR/tool response supplies actual publication evidence. Next: owner review, separate explicit approval before any merge/implementation/final G0 decision. No paid/live trading/code action. G0 and Issue #1 OPEN.

## 2026-10-21 — G1 shared indicator box documentation
- Verified 2026-10-21T06:42:12Z / 09:42:12 Asia/Riyadh (UTC+03:00): main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`; PR #13 `4a9bd25672d462f6b6b66beae55716942bb4a183` OPEN/unmerged, direct parent #12 `1948132315ee6a5b3174c56f767c84d1063251cd`; open proposals #6–#13 and Issue #1 OPEN. Canonical identity verified; no later open result visible. Other chats/unseen external changes are inaccessible or UNVERIFIED, not exhaustively reviewed.
- Owner explicitly confirms AQL-HO-20261021-001 / PR #13 as last actually submitted baseline. New AQL-HO-20261021-002 covers eight provisional G1-ARCH-21–28 decisions and supplied checks/constraints. Earlier handoff observations and original decision records remain unchanged.
- Selected isolated `docs/g1-shared-indicator-box` from pinned #13 to preserve prior unmerged ancestry; target main gives a cumulative proposal. Starting from main alone would require recopying/reconciling essential source proposals. No existing PR/branch modified, merged, closed, rebased, overwritten or retargeted.
- Added complete owner records, explicit central technical-validity/secretary eligibility/trader authority boundaries, dependency-aware single-flight identity, immediate active invalidation independent of archive, no expired active result while updating, validated current-revision publication and targeted subscription/reconnect safeguards. Historical evidence remains immutable; current invalidity cannot be overridden as fallback.
- Added conceptual states/subscriptions, eight example event sequences and negative acceptance cases including stale-completion overwrite, subscription race, missed notification/restart, cancellation of one consumer and demand-aware invalidation without all-symbol recomputation. Existing Fast/position priority and Slow budget/durability/recovery constraints retained.
- Nine incremental Markdown files above #13; thirteen cumulative above main. Documentary consistency checks only; application/runtime/concurrency/notification/recovery/cache/CI/performance NOT TESTED. No secrets, new provider/technology, numerical TTL/latency/capacity guarantee, paid action or real trading.
- Pre-publication entry: future PR number not guessed; actual PR/tool result supplies publication evidence. Next owner review and separate authorization before merge/implementation/final G0 decision. G0 and Issue #1 remain OPEN.


## 2026-10-21 — G1-ARCH-29–44 owner-provisional documentary consolidation

- Owner explicitly authorized documentation execution in this conversation after ChatGPT Work paste stalled; scope limited to a new reviewable documentation PR, no code or merges.
- G0-GOV-01 baseline: last actually owner-submitted AQL-HO-20261021-002 / PR #14, pinned head 275c856c61452fb2fdee2c3de30a2ae9907646a8; PRs #6–#14 OPEN, Issue #1 and G0 OPEN at inspection. No newer owner-submitted Work handoff evidenced. Other conversations inaccessible; unseen submissions UNVERIFIED.
- Sixteen decisions (ARCH-29–44) option C recorded canonically; reconcile inherited 01–28, A–G, deferred dashboard and research-library phase. New proposal ID AQL-HO-20261021-003 is documentary identifier, NOT a claim owner submitted it to Work.
- Documentation checks only; runtime, CI, concurrency, notifications, recovery, performance NOT TESTED. No numerical thresholds, physical implementation, paid actions, code, merges or G0 approval.

## 2026-10-21 — G0-REV-01/C documentation remediation of draft PR #15

Owner explicitly approved C: improve documentary acceptance scenarios, notification/recovery invariants and performance measurement criteria, without code, merge, technology selection or fabricated numerical SLA. Same draft PR #15 branch updated. New test cases T29–T44 are SPECIFIED / NOT EXECUTED; conceptual evidence fields added. No independent runtime, concurrency, recovery, notification, CI or performance test performed. G0 OPEN; all earlier PRs preserved; owner review required.

## 2026-10-22 — G0 approved; G1 WP01–WP04 implemented and CI-fixed (Issues #52, #53)

- **G0 approved:** Owner closed Issue #1 on 2026-10-22 with explicit sign-off. R09 mandatory credential revocation/rotation before V7 reuse remains binding.
- **G1 WP01 (PR #32):** Binance Spot USDT shared SQLite journal collector — merged to main as `9609711d6ff9c1ca446519b1347e46ebb74db06a`. Pre-merge CI run 40011286037: Ubuntu ✅ Windows ✅.
- **G1 WP02 (PR #40):** Durable SQLite WAL journal stress tests — merged to main as `fd6f8cfc999e94204ecabd732028a621abc50346`. Pre-merge CI run 40017268781: Ubuntu ✅ Windows ✅.
- **G1 WP03 (PR #42):** Health snapshot monitoring — merged to main as `c6392150cd9c7e49fe98f5076dce5017ece89df4`. Pre-merge CI run 40018212783: Ubuntu ✅ Windows ✅.
- **G1 WP04 (PR #45):** Operational readiness + SIGKILL recovery (Issue #44) — merged to main as `0af0dce5b3d5e16f5e44935fef76f77b4b8cdb87`. Pre-merge CI run 40018228077: Ubuntu ✅ Windows ✅.
- **CI fixes (Issue #52):** `setuptools.build_meta` backend fix, Windows SIGKILL/throughput skips, platform-aware throughput floors — included in WP02/03/04 branches before merge.
- **Stack ancestry reconciliation (Issue #53):** Conflict on `.github/workflows/g1-tests.yml` resolved via forward-merge commit `2e2035d`; PR #45 `mergeable_state` restored to `clean` before merge.
- **Draft state:** PRs #40, #42, #45 marked `draft=true` before final owner-authorized merge sequence.
- **Windows test coverage gaps (pre-existing, documented):** POSIX SIGKILL (9 skips), heavy fsync throughput/10k-candle tests skipped; Windows throughput floor 5 bars/s vs Linux 50 bars/s. Accepted limitation.
- **Live integration:** Binance REST/WS BLOCKED (proxy policy); Supabase NOT TESTED. Synthetic/mock pass ≠ live readiness.
- Application/runtime tests executed and passed: 129 passed / 1 skipped (live Binance REST) / 0 failed — Linux Ubuntu, Python 3.11.

## 2026-10-23 — Post-merge G1 verification, CI trigger fix, documentation hygiene (Issue #53)

- **Verified** by Claude Sonnet 4.6 scheduled execution agent, session https://claude.ai/code/session_01H5cqvL3durEYQzY6x6P5oi.
- **main HEAD** confirmed `0af0dce5b3d5e16f5e44935fef76f77b4b8cdb87` — all four WP merge commits present and accounted for.
- **Local full G1 regression on main HEAD:** `PYTHONPATH=src python -m pytest tests/test_g1_wp01.py tests/test_g1_wp02.py tests/test_g1_wp03.py tests/test_g1_wp04.py tests/test_g1_wp04_fix01.py -v --tb=short` → **129 passed, 1 skipped, 0 failed in 69.98s** (Linux/Ubuntu, Python 3.11). Full-pipeline POSIX SIGKILL test `test_ag_fp01_full_pipeline_sigkill_and_restart` PASSED. This is a local Claude run, not independent GitHub Actions CI.
- **Post-merge main CI gap:** `.github/workflows/g1-tests.yml` push trigger did not include `main`; no GitHub Actions run was triggered on the post-merge main HEAD. Fixed on feature branch `fix/g1-post-merge-ci-and-docs` — added `main` to push.branches; DRAFT PR opened for owner review.
- **CI trigger fix** (`.github/workflows/g1-tests.yml`): added `- main` under `push.branches`. No tests, logic or runtime code changed.
- **Documentation updates:** `04_STATE.md` updated with current-status addendum (historical content preserved); `05_WORK_LOG.md` this entry appended. PR descriptions for #32–#45 updated in earlier sessions (see Issue #53 comment trail).
- **G1 safety audit findings (not critical defects):** All G1 core behaviors (durable journal, duplicate suppression, crash/restart replay, gap detection, SIGKILL recovery, health snapshots) are implemented and pass synthetic tests. No critical G1 bug or post-merge regression found. Live Binance/Supabase not tested (not in G1 scope per G1-PLAN-01/C).
- **R09:** Remains mandatory; no V7 credentials accessed or present in this session.
- **Production authorization:** NOT granted. G1 code merged ≠ G1 production authorized.
- No merges, no main modifications, no live trading/deployment, no Strategy Factory work performed in this session.

## 2026-10-24 - Owner-authorized G1 operational completion (Draft, not merged)

Inspected current main 8e8690e58451e4fdd38f3e5e5f3cc89817e59c26 and live
G0/G1 metadata. Reconciled closed #61 preflight with direct owner Final Execution
Mission. No claim of reviewing inaccessible originating chats.
Implemented bounded recovery/persistence lanes, core-first local journal writes,
REST cooldown/bounds, clock fail-closed checks, sandbox adapter/migrations and
independent durable remote cursor. Preserved SQLite and Linux SIGKILL tests.
Public read-only Binance smoke returned HTTP200/100 unique contiguous candles
and three WS observations; source/host clock divergence prevents temporal PASS.
No orders, production DB, credentials, research changes or merges.
See docs/operations/G1_COMPLETION_20261024.md and evidence/g1_completion_public_smoke.json.
Final-head local/CI evidence belongs to the resulting consolidated Draft PR.
R09 unresolved; PR16 left open with a scoped supersession recommendation.

## 2026-10-28 — CORE-TIME-PROOF-01/B observer implementation, branch only

Reconciled owner task, last registered submitted baseline, main dbc191df, Core
#136/#137 and Council #134 through #6462862444; reused prior D3/local proof.
Added separate-process Binance WS/REST watcher, canonical ObservationVersion,
WAL/FULL raw+revision evidence, hash-chain/pinned envelope verification, conservative
as-of selection, UNKNOWN clock/coverage and existing pinned Factory E2E tests.
Two real cumulative captures across restart retained; six unique versions,
22 REST and two final WS receives. No natural correction/issuer attestation,
independent UTC or continuous immutable off-host custody proven. Eight focused
tests pass locally. Broad local run initially 436 pass/two skip/one missing
user-site dependency in isolated child; rerun in dedicated venv recorded in PR.
Exact-head Ubuntu/Windows CI and Council independent S/R are required; no merge,
historical/OOS, paper/live, final acceptance or G0 completion authorized.

### CORE-TIME-PROOF-01/B — Windows byte-custody correction

First CI run 40648887094 on bbad777: Ubuntu 445 pass / 2 skip; Windows
436 pass / 10 skip / 1 failure. The real-capture file pin correctly rejected
Git autocrlf-transformed evidence bytes. Reproduced the exact failing SHA256
locally by LF→CRLF conversion. Added path-scoped `.gitattributes -text` to retain
archive bytes, preserved original manifest hashes and strict raw-byte assertions,
and added attribute changes to the workflow trigger. New exact-head CI required;
the earlier failed run is not acceptance evidence for the corrected commit.


## 2026-10-28 — AQL-CORE-WORK-OBSERVATION-AUTHORITY-E2E-001 / Draft #144

Starting head6cb17079b71e7aaa33de756b60ad59686b260aad, main dbc191df.
Scoped direct owner authority; continuity #144/6465387750, UTC B owner
#144/6465335332, #128 through6463127686, Council #134 through6465410783;
unseen-chat coverage gap disclosed. Existing open stack preserved.
Automatic observer local snapshot queue, process-local expiring UTC diagnostic
with event/session binding, separate optional rclone Guardian full readback
before ACK, read-only verifier, Windows1/Windows2 runbooks delivered.
Baseline tests24 PASS after correcting local import setup; dependency install
resolved missing websocket-client in new integration test collection, no assertion
weakening. Final targeted34 PASS/0.58s, Core proof53 PASS/3.31s, JUnit retained.
Historical starting SHA six workflows SUCCESS, no rerun. Changed-source CI and
final exact SHA to be linked from PR #144 final delivery/Council #134 request.
Actual Linux capture4 Binance REST versions, WS timeout GAP and UTC DNS failure
UNKNOWN. Actual Drive raw upload/download23148 bytes verified SHA256
05e0f25a13b633f50e4f870ac79943414111c8a19fee717c2c4259144a9bad10;
file1RuR86eEZ3NaASymm3oz698N7uJQbOtau, verified ledger/raw/version/envelope.
No Windows owner-device/rclone runtime or physical power-loss test. Guardian
stop/restart is synthetic/fault injection only. No finite UTC bound established;
no independent custody/issuer timestamp, no empirical/PIT promotion.
See docs/core/observation_authority_e2e_001.md and evidence/observation-e2e-20261028.
No merge/OOS/PAPER/LIVE/final G0. Owner executes device runbooks; independent
Council S safety and R scientific comparison requested against final SHA.


### E2E first-head CI correction (not a rerun)

Source325cad581dcb4222ec007338294c6001971fc921 published in existing #144.
Authority40666205121 both OS green; observer Ubuntu446PASS/2SKIP. Core proof
40666205102 Windows122741211366 genuinely failed59PASS/1FAIL: time-budget
resume fixture assumed real250ms disk completion. Source explicitly allows soft
incomplete slices. Repaired test clock in resume phase; original assertions
retained and cleared-progress assertion added, no production thresholds changed.
Optional benchmark SQLite lock/WinError32 remains OPEN, no SLO acceptance.
Original failure retained, new revision required, no manual CI retry.
### E2E additive reconciliation after concurrent 325cad5

Fetched and preserved concurrent #144 runtime delivery; reused its canonical UTC
parser, verifier and Guardian instead of duplicating APIs. Moved snapshot work to
read-only child process and UTC network collection to separate Windows1 process;
added W32Time dispersion fail-closed parsing and corrupted-ACK detection. Local
reconciled 39 PASS, then 8 affected runtime cases PASS including three added
W32Time cases. New actual Linux REST capture 4 versions, final Drive object
15-3KbuiR_n88YeSwVtZ2GR5YgIjjqTIC 22877 bytes SHA36b7c8ca… matched after
full download; canonical bundle verified before local ACK. Windows owner devices
and rclone live deployment remain NOT EXECUTED; no finite UTC bound. Updated
single report/runbooks and Python3.14 CI; exact delivery SHA/CI in PR comment.
