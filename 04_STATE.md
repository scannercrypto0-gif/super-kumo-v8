# ATLAS Quant Lab — current isolated research execution snapshot
Project ID: AQL-CRYPTO-RESEARCH-001. Verified `2026-10-22T12:14:00.627993+00:00` UTC (Asia/Riyadh UTC+03:00).
Main observed: `e4c1f9ec5df9265405c62bab97b2ecc807ceab7b`. G0 **APPROVED**, Issue #1 **CLOSED**, verified Issue body/final owner sign-off and #15 merge. R09 **NOT RESOLVED**: mandatory before any legacy code/key reuse; no such reuse in this synthetic offline task.
Active research: WP-R19 read-boundary integrity fixes on `fix/research-r19-read-boundaries-20261022`, parent Draft PR #38 `51b7d8c82ea05fb9438aeb25d9053eb481c0d9c0`. Existing research PRs unmerged; no main or operational code modified. Last owner-submitted baseline: AQL-HO-20261021-002 / #14; current execution handoff AQL-HO-20261022-001. Other originating chats inaccessible.
Done: three defect categories fixed, 16 new regression methods, unified 169 PASS on local Linux/Python 3.12.14, five probes 0/5 -> 5/5 rejected; append evidence bytes/head/fsync unchanged. Windows/current CI and physical failure testing not claimed. [Results, source chain and measured read cost](research_wp_r0/READ_BOUNDARY_REVIEW.md).
Next: review the new Draft fix and source-stack integration; owner approval required before any merge or preservation-policy change. New PR number/publication not guessed in this pre-publication snapshot; actual PR body/tool result supplies later evidence. Existing historical snapshots below remain historical.

## Earlier source-branch snapshot retained verbatim

# ATLAS Quant Lab — CURRENT STATE
Project ID: `AQL-CRYPTO-RESEARCH-001`
Former name: SUPER KUMO V8
Operational V8 implementation: not yet verified or started.

Date: 2026-10-20
Gate: G0 OPEN (owner sign-off pending)
Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8) — Public
Official owner: `scannercrypto0-gif`
Default branch: `main`
Previously reviewed baseline: `f25f7072c9dea638d218c7f5e89f165e5a393096`
Latest actual main inspected for ATLAS-002: `64b47b5c929221277456a85f549183f9e5757d40`.
Historical PR #2 head before remediation: `741719fc4e0aecced10fa3317dc354339178f56a`.

## Bootstrap and active work

- WP-000 repository/governance bootstrap: governance files and Issue templates published on GitHub; owner review remains pending. This is not a gate-completion claim.
- Active architecture work: [G0-001 architecture review — Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) — OPEN.
- Done: initial architecture pack, repository publication, session/handoff protocols, work-package tracking, and [ChatGPT architecture review — Round 1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285495222).
- Review verdict: **CONDITIONALLY ACCEPTABLE — NOT YET APPROVED**.
- Pending: Claude independent review, resolution or explicit justified deferral of critical questions, final owner contract approval, and gate sign-off.
- Not implemented/verified: application code/tests, Supabase provisioning, and Binance benchmarks. No application tests were executed during this documentation review.
- Remote inventory: `.gitignore` is absent from the inspected main tree; earlier local bootstrap records do not establish remote presence.

## Five unresolved architecture areas

1. Paper execution: deterministic entry/fill rules, fees, slippage, no-fill, gaps, and same-bar TP/SL ambiguity.
2. Temporal integrity: candle close time, ingestion time, decision cutoff, and historical replay visibility.
3. Recovery/idempotency: durable queue ownership, idempotency keys, duplicate detection, restart behavior, and recovery acceptance tests.
4. Research methodology: baselines, sample eligibility, experiment registration, temporal holdouts, and shadow promotion criteria.
5. Operational budgets: initial Binance API budget, Supabase storage, and data-retention assumptions; any deferral needs bounded risk and rationale.

Other open questions: event provider access/rights and PC OS/recovery constraints.

## Next exact task

Current documentation item: **ATLAS-002 — Session Continuity and Mandatory Automatic Work Handoff**, proposed in [PR #5](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/5) on `docs/atlas-session-continuity`; review before deciding on merge. No merge is authorized by this task. After documentation sync, the next substantive work item remains G0-001: Claude independent review and owner resolution of the open architecture questions. No implementation is authorized.

Claude reads `07_CLAUDE_HANDOFF.md` and independently challenges the architecture review; availability recorded in the handoff is Thu 2026-10-22 13:00 Asia/Riyadh. The owner resolves or explicitly defers critical questions, approves the final contract, and authorizes G0 closure before G1 Market Foundation / WP-001 implementation. G0 and G0-001 remain OPEN. No production implementation is authorized by this review.

## Documentation evidence and remaining inconsistencies

### Completed on GitHub

- [Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) owner corrected to `scannercrypto0-gif`; labels `type:work-package` and `status:review` applied.
- Issue checklist reflects completed ChatGPT Round 1, documented open questions, STATE/WORK_LOG sync, and the documented WP-001 handoff. Claude review, critical-question resolution, contract/roadmap finalization, and owner approval remain unchecked.
- [Traceability annotation](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285973428) associates the unchanged original architecture review with baseline `f25f7072c9dea638d218c7f5e89f165e5a393096` and distinguishes later documentation commit `879233525b2b716514076654d7c9195efaaf70b0`.

### Merged PR #2 — documentation governance cleanup

- [PR #2](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/2) was squash merged on 2026-10-20 as [cc32203300a7c71b089811c90920beb6e39a48ac](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/cc32203300a7c71b089811c90920beb6e39a48ac), now published on main.
- Canonical repository references, bootstrap/status documentation, and WP-000 public-remote acceptance are synchronized. The .gitignore acceptance item remains unchecked.
- The one-time owner-authorized direct-to-main exception for `8792335` is documented; PR-first policy remains unchanged.
- The initial REQUEST CHANGES for STATE/WORK_LOG consistency and owner-authorized expansion to eight files remain recorded in [the historical work log](05_WORK_LOG.md#2026-10-20--pr-2-governance-cleanup-and-consistency-remediation). Final documentation verification recommended APPROVE; this was not architecture approval.
- No application tests or CI success are claimed.

### Merged PR #3 — issue-form repair

- [PR #3](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/3) was squash merged as [b98b4231447b3f57570628b0808496439c745d80](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/b98b4231447b3f57570628b0808496439c745d80).
- The repaired mappings preserve intended questions, IDs, required fields, dropdown choices and labels. Prior YAML parsing and local structure evidence is retained; no repeated form tests are performed by ATLAS-001.
- GitHub UI smoke test was BLOCKED by browser sign-in; hosted functional PASS is not claimed.

### ATLAS-001 — identity migration merged

- Owner approved ATLAS Quant Lab as the provisional name and `AQL-CRYPTO-RESEARCH-001` as the canonical Project ID; repository and owner remain `scannercrypto0-gif/super-kumo-v8` and `scannercrypto0-gif`.
- [PR #4](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/4) was squash merged as [64b47b5c929221277456a85f549183f9e5757d40](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/64b47b5c929221277456a85f549183f9e5757d40); canonical identity and session checks are published on main.
- Former name SUPER KUMO V8, legitimate history, commit/Issue/PR links, legacy technical version names and architecture meaning are preserved.
- New sessions must verify Project ID and canonical repository before using earlier context; stop on mismatch. Unrelated V7 step 311, `gate_spot_cvd.py`, or other-project conversations are not authoritative implementation evidence.
- G0 and G0-001 remain OPEN. No architecture approval, operational implementation, repository rename or settings change is authorized by this migration.

### ATLAS-002 — proactive handoff implementation pending merge

- PR #5 integrates the owner-approved logical pending-change ledger, proactive checkpoints, one consolidated Work instruction, direct authorized-write alternative and next-session reconciliation into existing protocols and template.
- Confirmed facts/hypotheses and approved/proposed decisions remain distinct; no upload is claimed without tool evidence. No duplicate governance document or background agent runtime is created.
- Implementation is on the PR branch, not published on main until merge. G0 and Issue #1 remain OPEN.

### Remaining unresolved governance tasks

- Review ATLAS-002 session-continuity documentation; its merge remains pending. PR #2, PR #3 and PR #4 are already merged.
- Create remaining `type:bug`, `type:proposal`, and `type:question` labels: previously verified absent; creation remains blocked by available tooling/authentication and is not performed in this remediation.
- Verify remote .gitignore protections in a separately authorized task.
- Hosted Issue Forms smoke verification remains blocked by browser sign-in; missing template labels remain a separate repository prerequisite.
- Obtain Claude independent architecture review, resolve or explicitly defer critical questions with rationale, and obtain final owner approval. G0 and G0-001 remain OPEN; no architecture approval is complete.

SESSION END: changes/commit | tests/evidence | decisions | blockers | active WP | next exact task | reviewer.


## 2026-10-22 — Strategy Factory Batch 01 current snapshot

Verified `2026-10-22T13:22:37.459341+00:00` UTC against GitHub: main `e4c1f9ec5df9265405c62bab97b2ecc807ceab7b`; Issue #1 CLOSED, final G0 owner sign-off in its current description. Historical OPEN observations above remain unchanged. R09 still required before legacy/key reuse; no such use here.

Research head #43 `0a3d900d5d85a6d987f1e26eac8f99660f05b2e5` is Draft/unmerged, parent #41 `06d1c2c218aeb3553b0c761c659fd0a8a143d93c`. Isolated Batch 01 targets #43, not main. Separate ingest chain #32/#40/#42 is not imported; owner review on #42 reports health/recovery blockers, resolution not verified here.

Completed locally: three frozen synthetic families / 12 candidates, 29 new tests in 12 groups, 204 unified tests PASS, reproducible evidence, conditional/full-opportunity baselines and journal-bound result checks. All candidates INSUFFICIENT_EVIDENCE; real historical/OOS and prospective validation NOT TESTED, final holdout NOT OPENED. [Batch report](research_wp_r0/BATCH01_REPORT.md) contains counts, metrics, limits and estimated six remaining work checkpoints. CI exact-head outcome and actual Draft PR publication are subsequent evidence in the PR body.

Next action: review the isolated Batch 01 Draft PR and research ancestry; separately authorize integration and trustworthy historical/independent-holdout inputs. No merge, strategy admission, live/paid action or main change authorized. Other chats inaccessible; coverage limited to visible instructions and inspected GitHub records.
