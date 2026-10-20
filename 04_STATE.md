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
Latest actual main inspected for future dashboard requirement: `ed188f1902d397fe74613dd966c5a3e88b32f8c0`.
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

Current documentation item: record the future dashboard requirement in the roadmap via a documentation PR; review before any merge. Dashboard implementation is deferred until operational data exists. The next substantive work item remains G0-001: Claude independent review and owner resolution of the open architecture questions. No implementation is authorized.

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

- Review the proposed [future dashboard requirement](02_ROADMAP.md#future-requirement--unified-monitoring-dashboard); its documentation PR is not merged. PR #2 through PR #5 are already merged. Dashboard scope/architecture/implementation remain deferred and unapproved.
- Create remaining `type:bug`, `type:proposal`, and `type:question` labels: previously verified absent; creation remains blocked by available tooling/authentication and is not performed in this remediation.
- Verify remote .gitignore protections in a separately authorized task.
- Hosted Issue Forms smoke verification remains blocked by browser sign-in; missing template labels remain a separate repository prerequisite.
- Obtain Claude independent architecture review, resolve or explicitly defer critical questions with rationale, and obtain final owner approval. G0 and G0-001 remain OPEN; no architecture approval is complete.

SESSION END: changes/commit | tests/evidence | decisions | blockers | active WP | next exact task | reviewer.
