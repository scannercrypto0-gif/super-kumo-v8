# ATLAS Quant Lab — CURRENT STATE
Project ID: `AQL-CRYPTO-RESEARCH-001`
Former name: SUPER KUMO V8
Operational V8 implementation: not yet verified or started.

Date: 2026-10-20
Snapshot verified_at: 2026-10-20T10:47:11Z (13:47:11 Asia/Riyadh, UTC+03:00)
Verification source: GitHub main/ref, PR #6–#10 APIs, Issue #1 API and commit-pinned documentation. Scope: documentary state; runtime implementation UNVERIFIED.
Gate: G0 OPEN (owner sign-off pending)
Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8) — Public
Official owner: `scannercrypto0-gif`
Default branch: `main`
Previously reviewed baseline: `f25f7072c9dea638d218c7f5e89f165e5a393096`
Latest actual main inspected for G0 reconciliation: `ed188f1902d397fe74613dd966c5a3e88b32f8c0`.
Historical PR #2 head before remediation: `741719fc4e0aecced10fa3317dc354339178f56a`.

## Bootstrap and active work

- WP-000 repository/governance bootstrap: governance files and Issue templates published on GitHub; owner review remains pending. This is not a gate-completion claim.
- Active architecture work: [G0-001 architecture review — Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) — OPEN.
- Done: initial architecture pack, repository publication, session/handoff protocols, work-package tracking, and [ChatGPT architecture review — Round 1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285495222).
- Review verdict: **CONDITIONALLY ACCEPTABLE — NOT YET APPROVED**.
- Pending: Claude independent review, resolution or explicit justified deferral of critical questions, final owner contract approval, and gate sign-off.
- Not implemented/verified: application code/tests, Supabase provisioning, and Binance benchmarks. No application tests were executed during this documentation review.
- Remote inventory: `.gitignore` is absent from the inspected main tree; earlier local bootstrap records do not establish remote presence.

## Five architecture areas — provisional requirements, final review OPEN

1. Paper execution: PAPER-01–08 are preserved in this reconciliation proposal, including conditional fills, factual ambiguity, independent cost stress, reference-notional limits, independent traders, frozen validity/exits and isolated counterfactuals. Numeric execution/policy parameters and implementation evidence remain open.
2. Temporal integrity: TIME-01–09 and INT-04 require trader-specific proven availability, provisional/completed status and explicit policy permission for any qualifying completed-candle fallback; otherwise block and record why. No later recovered/finalized values become earlier knowledge.
3. Recovery/idempotency: PAPER-08 and DATA-05–08 preserve durable state, chronological event replay, no duplicated fills/closes/alerts/accounting, residual gaps and ambiguity. Physical queue ownership/keys and runtime acceptance remain unresolved/NOT TESTED.
4. Research methodology: historical development/OOS/prospective forward and target/off-target specialist evidence remain separate; all-opportunity context stays immutable. Owner A–G, detector reliability, sample adequacy and independent Shadow/Lab evidence are preserved. Thresholds and final promotion approval remain open.
5. Operational budgets: DATA-01–08 preserve shared acquisition/cache/provider budgets, pre-operational library coverage and strict background isolation. Numeric budgets, providers/rights, retention, concurrency and measured objectives remain unresolved; no guaranteed zero cost or 30-second SLA. Paid services require prior owner approval.

Other open questions: event provider access/rights and PC OS/recovery constraints.

## Next exact task

Current documentation item: owner-authorized G0 integration reconciliation on `docs/g0-integration-reconciliation`, prepared for one documentation PR targeting main. Source proposals remain OPEN/unmerged; this branch preserves their requirements without modifying them. INT-01–06 are provisionally owner-approved, not final G0 approval. PR publication/review/merge is not inferred from this pre-publication snapshot.
Next exact action: owner reviews the resulting reconciliation PR and validation evidence, decides source-PR disposition/integration sequence and separately authorizes any merge. No application implementation or source PR merge/closure is authorized.

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

### ATLAS-002 — proactive handoff merged

- PR #5 integrates the owner-approved logical pending-change ledger, proactive checkpoints, one consolidated Work instruction, direct authorized-write alternative and next-session reconciliation into existing protocols and template.
- Confirmed facts/hypotheses and approved/proposed decisions remain distinct; no upload is claimed without tool evidence. No duplicate governance document or background agent runtime is created.
- [PR #5](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/5) was squash merged as [ed188f1902d397fe74613dd966c5a3e88b32f8c0](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/ed188f1902d397fe74613dd966c5a3e88b32f8c0); session continuity and proactive handoff instructions are published on main. G0 and Issue #1 remain OPEN.

### Remaining unresolved governance tasks

- Review this reconciliation proposal. PR #2 through PR #5 are merged; #6–#10 remain OPEN/unmerged at the evidence timestamp. Future dashboard requirement is preserved; implementation is owner-deferred until operational records exist.
- Remaining `type:bug`, `type:proposal`, and `type:question` label inventory: UNVERIFIED in this task; earlier absence/tooling reports are historical. No labels are changed.
- Verify remote .gitignore protections in a separately authorized task.
- Hosted Issue Forms smoke verification remains blocked by browser sign-in; missing template labels remain a separate repository prerequisite.
- Obtain Claude independent architecture review, resolve or explicitly defer critical questions with rationale, and obtain final owner approval. G0 and G0-001 remain OPEN; no architecture approval is complete.

SESSION END: changes/commit | tests/evidence | decisions | blockers | active WP | next exact task | reviewer.

## Current evidence ledger — INT-06
All rows share verified_at `2026-10-20T10:47:11Z (13:47:11 Asia/Riyadh, UTC+03:00)`. Current facts come from GitHub reads; proposal contents are only on the reconciliation branch until merged.

| Status / scope | Verification source and reference | Uncertainty / conflict |
| --- | --- | --- |
| main `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | GitHub heads/main ref | Verified current at snapshot; later changes require re-read |
| G0 OPEN / G0-001 Issue #1 OPEN | main START_HERE and Issue #1 API/body | No final owner sign-off; Claude review remains pending in published state |
| PR #5 MERGED; protocols published | main commit `ed188f1902d397fe74613dd966c5a3e88b32f8c0` and source state evidence | Historical WORK_LOG pending observations remain unchanged |
| PR #6 OPEN / unmerged | [PR #6](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/6), head `93a1a537866fc20059d80f86061676e26fcd971e`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Individually mergeable/clean at read; sequential semantic integration not established |
| PR #7 OPEN / unmerged | [PR #7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7), head `79bf0d902fab8fe766962425ca58d0d0528c152c`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Individually mergeable/clean at read; sequential semantic integration not established |
| PR #8 OPEN / unmerged | [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8), head `19c5a747a568c727deb4cf7eb1320e30a7857241`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Individually mergeable/clean at read; sequential semantic integration not established |
| PR #9 OPEN / unmerged | [PR #9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9), head `8886e69562b880e35c989009961959d4c9163791`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Individually mergeable/clean at read; sequential semantic integration not established |
| PR #10 OPEN / unmerged | [PR #10](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/10), head `8f33b50dbec18ff472a59c3505c2dbf6d43b104d`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Individually mergeable/clean at read; sequential semantic integration not established |
| INT-01–06 C / provisional; execution docs-only authorized | Visible owner read-only handoff plus Execute authorization dated 2026-10-20; canonical decision sections in this branch | No final G0 approval or merge authority |
| Issue #1 owner/labels already corrected | Current Issue API: scannercrypto0-gif; type:work-package/status:review | Body still describes PR #2 as unmerged: stale current claim; Issue edit requires separate approval |
| Originating chats / runtime evidence | Only visible conversation and accessed GitHub records | Other chats inaccessible; runtime tests NOT TESTED; implementation not independently established |

Baseline now owner-confirmed: PR #10 / AQL-HO-20261020-003. Register's older PR #8 baseline describes the earlier handoff event and is preserved, not overwritten. Exactly INT-01–06 comprise the reported post-baseline decision delta. See the decision coverage matrix for source provenance, blockers and future integration choices.
