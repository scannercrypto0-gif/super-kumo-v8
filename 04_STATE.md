## E2E CI correction checkpoint (2026-10-28)

First implementation325cad5: authority CI green both OS; Core proof40666205102
Windows59PASS/1FAIL. Deterministic resume-clock test repair preserves assertions;
production sweep unchanged. Optional benchmark lock/cleanup failure remains OPEN.
New revision CI pending; original red run retained. Owner Windows still unexecuted.

## 2026-10-28 — Observation authority E2E #144 (unmerged, PARTIAL)

Direct owner task AQL-CORE-WORK-OBSERVATION-AUTHORITY-E2E-001 implemented
on existing Draft #144, starting 6cb17079. Automatic local outbox checkpoints,
session-bound unauthenticated UTC diagnostics, separate optional Guardian Drive
readback verifier and Windows runbooks. Actual Work Linux Binance REST capture
4 versions; actual Drive upload/download SHA256 and bundle verification passed.
No owner Windows access; WS timeout, UTC DNS failure => UNKNOWN, no finite
UTC accuracy certified. Same-account Drive is mutable backup. Pinned Factory
rejects empirical/real-PIT promotion. Local final targeted 34 PASS, proof
regression 53 PASS; CI for changed SHA to be recorded in PR/Council report.
No merge/trading/OOS/final G0 action. Owner-device and Council S/R acceptance
pending. [Single report/runbooks](docs/core/observation_authority_e2e_001.md).

## 2026-10-28 — Binance observer branch checkpoint (not merged)

Owner-authorized CORE-TIME-PROOF-01/B is implemented as a standalone process,
stacked on Core #137 d27ddd8f. Genuine Binance WS/REST evidence across restart
is in `evidence/binance-observer-20261028/capture_manifest.json`; six distinct
versions, no naturally observed correction. UTC status UNKNOWN, timing class
FIRST_INDEPENDENT_OBSERVED; issuer time UNATTESTED. Existing Factory #141 pinned
bridge remains fail-closed; no empirical PIT admission or trading activation.
See `docs/core/binance_independent_observer.md` for tests, limits and deployment.
Exact-head CI and independent Council S/R are tracked by the resulting PR and
Issue #134; no completion/merge/G0 declaration is made by this checkpoint.

## Current execution addendum - 2026-10-24 (Draft PR, not merged)

Verified main baseline: 8e8690e58451e4fdd38f3e5e5f3cc89817e59c26. G0 is
APPROVED; Issues #1/#44/#52/#53/#61 closed and PRs #32/#40/#42/#45/#56 merged.
Post-merge G1 baseline run 40062092633 supersedes the older NOT TRIGGERED
snapshot below; it does not certify later research changes.

This owner-authorized G1-only branch implements bounded background recovery,
journal-first ingestion, independent persistence/replay and sandbox PostgreSQL
adapter/migrations. [Scope, evidence, owner-only R09 checklist and limits](docs/operations/G1_COMPLETION_20261024.md).
Public Binance REST/WS transport observed successfully; approximately 635s
source/host clock divergence BLOCKS temporal acceptance. Supabase cloud NOT TESTED.
R09 remains CRITICAL/UNRESOLVED pending real revocation/rotation evidence.
PR #16 remains open; superseded-MVP closure recommendation preserves deferred
Inbox/archive/backup requirements. No research changes, main writes or trading.

# ATLAS Quant Lab — CURRENT STATE
Project ID: `AQL-CRYPTO-RESEARCH-001`
Former name: SUPER KUMO V8

---

## ⚡ CURRENT STATUS ADDENDUM — 2026-10-23 (supersedes stale header below)

**Updated:** 2026-10-23T21:30:00Z  
**Verification source:** GitHub API (Issues, PRs, Actions), local test run on main HEAD `0af0dce5b3d5`.  
**Updated by:** Claude Sonnet 4.6 scheduled execution agent — [Issue #53](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/53)

| Item | Status |
|------|--------|
| **G0 Gate** | ✅ **APPROVED** — Issue #1 closed 2026-10-22; owner sign-off recorded. R09 legacy-credential revocation/rotation **mandatory** before any V7 code or credential reuse. |
| **G1 WP01–WP04** | ✅ **MERGED** into `main` — PRs #32→#40→#42→#45 all merged (merge commits below). Runtime implementation verified via synthetic/mock tests. Production/live NOT authorized. |
| **main HEAD** | `0af0dce5b3d5e16f5e44935fef76f77b4b8cdb87` — confirmed 2026-10-23 |
| **Local G1 test run on main** | ✅ 129 passed, 1 skipped (live Binance REST proxy-blocked), 0 failed — Linux/Ubuntu, 2026-10-23 |
| **Post-merge main CI** | ⚠️ **NOT TRIGGERED** — `.github/workflows/g1-tests.yml` push trigger excluded `main`; fix on feature branch PR (this PR or `fix/g1-post-merge-ci-and-docs`) |
| **Binance REST live** | ❌ BLOCKED (proxy) — all REST uses mock fixtures |
| **Binance WebSocket live** | ❌ BLOCKED (proxy) — all WS uses synthetic fixtures |
| **Supabase integration** | ❌ NOT TESTED — not in G1 operational scope |
| **Windows POSIX SIGKILL** | ⏭ SKIPPED — `signal.SIGKILL` unavailable on Windows (9 platform-specific skips in CI) |
| **Production / live trading** | ❌ NOT AUTHORIZED |

### G1 Merge Ancestry (verified 2026-10-23)

| PR | Branch | Merge Commit | Pre-merge CI Run | Result |
|----|--------|-------------|-----------------|--------|
| #32 WP01 | `feat/g1-wp01-minimal-ingest` | `9609711d6ff9` | [40011286037](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40011286037) | ✅ Ubuntu+Win |
| #40 WP02 | `feat/g1-wp02-stress-test` | `fd6f8cfc999e` | [40017268781](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40017268781) | ✅ Ubuntu+Win |
| #42 WP03 | `feat/g1-wp03-health-snapshot` | `c6392150cd9c` | [40018212783](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40018212783) | ✅ Ubuntu+Win |
| #45 WP04 | `feat/g1-wp04-operational-readiness` | `0af0dce5b3d5` | [40018228077](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40018228077) | ✅ Ubuntu+Win |

> **Note:** All CI runs above are **pre-merge branch runs**, not post-merge-to-main runs. Post-merge main CI was not triggered due to the push trigger gap (now fixed on this PR). Local regression on `main` HEAD `0af0dce5` confirms 129 passed on Linux.

### Outstanding gates (owner decision required)

1. **R09** — Legacy V7 credential revocation/rotation **mandatory** before any V7 code/credential reuse. G0 approval does not waive this.
2. **Post-merge main CI** — Merge this PR to add `main` to the push trigger; a CI run on `main` will then be independently verifiable.
3. **Live Binance / Supabase** — Not tested; separate authorized task required.
4. **Windows production throughput** — 5 bars/s floor in CI vs 50 bars/s Linux; not a production SLA.
5. **G1 production/live authorization** — Separate owner decision; G1 code merged ≠ production authorized.

---

## HISTORICAL STATE SNAPSHOT — 2026-10-21 (preserved, not current)

> The content below is the original snapshot dated 2026-10-21. It is preserved for audit/historical continuity. For current state see the addendum above.

Operational V8 implementation: not yet verified or started.

Date: 2026-10-21
Snapshot verified_at: 2026-10-21T06:42:12Z / 09:42:12 Asia/Riyadh (UTC+03:00)
Verification source: GitHub main/ref, PR #6–#10 APIs, Issue #1 API and commit-pinned documentation. Scope: documentary state; runtime implementation UNVERIFIED.
Gate: G0 OPEN (owner sign-off pending)
Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8) — Public
Official owner: `scannercrypto0-gif`
Default branch: `main`
Previously reviewed baseline: `f25f7072c9dea638d218c7f5e89f165e5a393096`
Latest actual main inspected for G1 shared indicator box: `ed188f1902d397fe74613dd966c5a3e88b32f8c0`.
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

Current documentation item: owner-submitted G1-ARCH-21–28 shared indicator box documentation/consistency review, on `docs/g1-shared-indicator-box`. Latest owner-confirmed submitted baseline AQL-HO-20261021-001 / PR #13 remains OPEN/unmerged at `4a9bd25672d462f6b6b66beae55716942bb4a183`. New branch inherits it by ancestry, targeting main with a cumulative documentation proposal, not a source merge.
Next exact action: owner reviews the new shared-box proposal, consistency matrix and unselected implementation parameters. No existing PR/branch is altered; no merge, runtime implementation, paid action, trading or final G0 approval is authorized.

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

- Review this new G1 documentation proposal; PRs #6–#11 remain OPEN/unmerged and their merges are owner-deferred. Future dashboard implementation stays deferred until operational records exist. No source branch is changed.
- Remaining `type:bug`, `type:proposal`, and `type:question` label inventory: UNVERIFIED in this task; earlier absence/tooling reports are historical. No labels are changed.
- Verify remote .gitignore protections in a separately authorized task.
- Hosted Issue Forms smoke verification remains blocked by browser sign-in; missing template labels remain a separate repository prerequisite.
- Obtain Claude independent architecture review, resolve or explicitly defer critical questions with rationale, and obtain final owner approval. G0 and G0-001 remain OPEN; no architecture approval is complete.

SESSION END: changes/commit | tests/evidence | decisions | blockers | active WP | next exact task | reviewer.

## Historical evidence snapshot — INT-06, 2026-10-20T10:47:11Z
The following rows preserve the earlier #11 snapshot, superseded for current status by the ledger below. Proposal content was only on its branch; no historical observation is rewritten as a merge.

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

At the earlier #11 snapshot, baseline owner-confirmed: PR #10 / AQL-HO-20261020-003. Register's older PR #8 baseline describes the earlier handoff event and is preserved, not overwritten. Exactly INT-01–06 comprise the reported post-baseline decision delta. See the decision coverage matrix for source provenance, blockers and future integration choices.

## Historical evidence snapshot — G1 secretarial consolidation, 2026-10-20
Historical snapshot, superseded for current status by the ledger below. Verified_at: 2026-10-20T13:38:18Z / 16:38:18 Asia/Riyadh (UTC+03:00). Source: current GitHub refs, all-open-PR inventory, PR #6–#11 metadata, Issue #1 and commit-pinned documentation; owner attachment supplies decision/deferral authority. This is a pre-publication snapshot of the new proposal, not a claim its PR has already been created.

| Status / scope | Source / evidence | Uncertainty / conflict |
| --- | --- | --- |
| main `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | GitHub heads/main ref | Verified at snapshot; no source proposals merged |
| G0 OPEN / Issue #1 OPEN | Main published identity and Issue API/body | No final sign-off; Issue's stale PR #2 sentence disclosed, not edited |
| PR #6 OPEN / unmerged | [PR #6](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/6), head `93a1a537866fc20059d80f86061676e26fcd971e`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Owner explicitly defers merge; original PR/branch unchanged |
| PR #7 OPEN / unmerged | [PR #7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7), head `79bf0d902fab8fe766962425ca58d0d0528c152c`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Owner explicitly defers merge; original PR/branch unchanged |
| PR #8 OPEN / unmerged | [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8), head `19c5a747a568c727deb4cf7eb1320e30a7857241`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Owner explicitly defers merge; original PR/branch unchanged |
| PR #9 OPEN / unmerged | [PR #9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9), head `8886e69562b880e35c989009961959d4c9163791`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Owner explicitly defers merge; original PR/branch unchanged |
| PR #10 OPEN / unmerged | [PR #10](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/10), head `8f33b50dbec18ff472a59c3505c2dbf6d43b104d`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Owner explicitly defers merge; original PR/branch unchanged |
| PR #11 OPEN / unmerged | [PR #11](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/11), head `fb79e13b58c91c6b53a7e0489114adcdcc577d15`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Owner explicitly defers merge; original PR/branch unchanged |
| G1-ARCH-01–11 PROVISIONAL / docs-only | Owner-supplied Secretarial Data Architecture Consolidation handoff; canonical DECISIONS section | G1 prefix does not close G0 or permit implementation |
| Latest returned Work result / continuity baseline | AQL-HO-20261020-004, PR #11; owner says returned/shared to architecture conversation | Independent access to that originating chat is unavailable; no inference of final approval/merge |
| New handoff 005 / directly received | Attached owner instruction plus visible disclosure; delta = eleven decisions + merge deferral | No later Work submission visible in inspected GitHub inventory or supplied record; unseen submissions UNVERIFIED |
| Implementation / runtime tests | Documentation tree and scope only | Application/recovery/load/CI NOT TESTED; no storage engine/schema/constants selected |

Preserve PAPER/TIME/DATA/GOV/INT, A–G and future dashboard from #11. DATA-07 monitor authority is explicitly clarified by G1-ARCH-05: high-priority state/data support, owning trader decides. Critical events, freshness/fallback and recovery ambiguity remain mandatory. Remaining parameters: durable Inbox engine/capacity/integrity/pressure policy, acknowledgment mechanics, measured resource/hysteresis/concurrency/delivery targets, provider/source limits and permissions. No new paid or real-execution permission.

## Historical evidence snapshot — consolidated G1 ARCH-12–20, 2026-10-21T06:11:44Z
Earlier snapshot, superseded for current status by the ledger below. Verified_at: 2026-10-21T06:11:44Z / 09:11:44 Asia/Riyadh (UTC+03:00); source: GitHub main ref, open PR inventory, PR #12 metadata/tree and pinned canonical docs, Issue #1; owner-visible handoff supplies approval/baseline/delta evidence. Earlier ledgers preserve earlier observations, not current baseline assertions.

| Scope/status | Evidence | Uncertainty/approval |
| --- | --- | --- |
| main `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | GitHub heads/main ref and canonical startup identity | No proposed architecture PR merged at snapshot |
| G0 OPEN / Issue #1 OPEN | Published startup and current Issue API/body | Final owner G0 approval absent; stale Issue PR #2 sentence unchanged |
| PR #6 OPEN / unmerged | [PR #6](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/6), head `93a1a537866fc20059d80f86061676e26fcd971e`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| PR #7 OPEN / unmerged | [PR #7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7), head `79bf0d902fab8fe766962425ca58d0d0528c152c`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| PR #8 OPEN / unmerged | [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8), head `19c5a747a568c727deb4cf7eb1320e30a7857241`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| PR #9 OPEN / unmerged | [PR #9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9), head `8886e69562b880e35c989009961959d4c9163791`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| PR #10 OPEN / unmerged | [PR #10](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/10), head `8f33b50dbec18ff472a59c3505c2dbf6d43b104d`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| PR #11 OPEN / unmerged | [PR #11](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/11), head `fb79e13b58c91c6b53a7e0489114adcdcc577d15`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| PR #12 OPEN / unmerged | [PR #12](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/12), head `1948132315ee6a5b3174c56f767c84d1063251cd`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No source PR/branch modification or merge authorized |
| Latest actually owner-submitted baseline | AQL-HO-20261020-005 / PR #12, explicit current owner confirmation | Other originating conversation not accessed |
| New handoff AQL-HO-20261021-001 directly received | Nine provisional G1-ARCH-12–20 decisions and supplied cross-cutting invariants | No other since-baseline decision/addendum reported; unseen submissions UNVERIFIED |
| New documentation proposal | `docs/g1-scanner-readiness-architecture` starts at pinned #12, targets main; pre-publication snapshot | No invented future PR number; actual PR body/tool result supplies publication evidence |
| Runtime/CI/performance | No application execution in this task | NOT TESTED; measurement spec proposed, no numeric targets/TTL/thresholds/capacity guarantee |

Candidate screening, mandatory evidence readiness and trade decisions are separate; no forced BUILDING path. Shared calculations require full matching identity/temporal evidence and consumer eligibility. LIVE/HISTORICAL classification never guarantees freshness or speed. Fast fan-out/position service and durable Inbox/recovery controls remain intact. Unselected parameters: stage policies/inputs per strategy, actual validity/cache policies, timestamp instrumentation/clock-quality handling and measured service objectives, capacity/resource/provider settings. Only later reviewed authorized work may implement them.

## Current evidence ledger — shared indicator box ARCH-21–28
Verified_at: 2026-10-21T06:42:12Z / 09:42:12 Asia/Riyadh (UTC+03:00). Sources: current GitHub main ref/startup identity, open PR inventory, #13 metadata/commit ancestry/tree and canonical pinned documentation, Issue #1; visible current owner handoff confirms submitted baseline and eight-decision delta. Older ledgers retain earlier observations, not current baseline claims.

| Scope/status | Evidence | Uncertainty/approval |
| --- | --- | --- |
| main `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | GitHub heads/main ref and startup identity | No architecture proposal merged at snapshot |
| G0 OPEN / Issue #1 OPEN | Published startup and current Issue API/body | No final approval; stale Issue PR #2 sentence unchanged |
| PR #6 OPEN / unmerged | [PR #6](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/6), head `93a1a537866fc20059d80f86061676e26fcd971e`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #7 OPEN / unmerged | [PR #7](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/7), head `79bf0d902fab8fe766962425ca58d0d0528c152c`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #8 OPEN / unmerged | [PR #8](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/8), head `19c5a747a568c727deb4cf7eb1320e30a7857241`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #9 OPEN / unmerged | [PR #9](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/9), head `8886e69562b880e35c989009961959d4c9163791`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #10 OPEN / unmerged | [PR #10](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/10), head `8f33b50dbec18ff472a59c3505c2dbf6d43b104d`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #11 OPEN / unmerged | [PR #11](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/11), head `fb79e13b58c91c6b53a7e0489114adcdcc577d15`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #12 OPEN / unmerged | [PR #12](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/12), head `1948132315ee6a5b3174c56f767c84d1063251cd`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| PR #13 OPEN / unmerged | [PR #13](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/13), head `4a9bd25672d462f6b6b66beae55716942bb4a183`, base `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | No merge or existing PR/branch mutation authorized |
| Last actually owner-confirmed submitted handoff | AQL-HO-20261021-001 / PR #13, explicit current owner instruction | Originating conversations not independently accessible |
| New handoff AQL-HO-20261021-002 / directly received | G1-ARCH-21–28, cross-decision checks and doc-only constraints | No newer confirmed submission evidenced in accessible inventory/records; unseen submissions UNVERIFIED |
| New shared-box documentation proposal | `docs/g1-shared-indicator-box` from pinned unmerged #13, targeting main | Pre-publication snapshot; actual PR body/tool result supplies later publication link |
| Runtime/concurrency/notifications/recovery/CI/performance | Not executed | NOT TESTED; technical mechanism/parameters and final G0 review remain gated |

Manager technical validity, secretary per-manifest eligibility and owning-trader decisions are distinct. Invalidate active eligibility independently of archival/recomputation; preserve immutable history. No stale completion/notification may restore an obsolete binding. READY and LIVE/HISTORICAL remain separate from readiness/technical validity. Unselected parameters: dependency catalogs/rules, validation evidence, revision/snapshot/notification protocol, single-flight/cancellation mechanics, storage/transport, recovery/integrity behavior, measured budgets/targets and per-strategy policies. No numeric TTL/latency guarantee or technology selected.


## Provisional current decision delta — AQL-HO-20261021-003 (2026-10-21)

Owner provisionally approved G1-ARCH-29–44, all option C, since last actually submitted AQL-HO-20261021-002 / PR #14. This branch starts at pinned unmerged PR #14 head 275c856c61452fb2fdee2c3de30a2ae9907646a8; PRs #6–#14 were OPEN and Issue #1 OPEN at audit. No evidence of owner-submitted newer Work handoff; other chats inaccessible, unseen changes UNVERIFIED. New documentation proposal does not close G0 or merge prior PRs. Implementation, concurrency, latency, notification, recovery, performance, CI NOT TESTED. New physical mechanisms and thresholds UNSELECTED. Future dashboard deferred.

## G0-REV-01 / C — Review remediation state

Draft PR #15 documentation clarification authorized and applied on its existing branch: test fixture/trigger/expected/forbidden cases T29–T44; revision-safe notification/restart protocol; clock-aware stage latency acceptance and evidence fields. Documentary clarification only, executable tests NOT TESTED, no merge, no final G0. Last owner-actually-submitted Work handoff remains AQL-HO-20261021-002 / PR #14; PR #15 is directly authorized GitHub documentation work.

## 2026-10-28 — Guardian151 isolated DRAFT checkpoint

Direct owner Issue151 execution authority; branch core/guardian-closure-151 starts
at unmerged #144 SHA3fc035b7ae70693e952976e2dcb2fe165a7e1826. Main unchanged.
Guardian-only ACK/readback validation, replay-safe immutable ACK, nonblocking OS
lock and local-only controlled launch preflight; see docs/core/guardian_closure_151.md.
Exact new SHA/local/CI evidence in Issue151 RESULT and linked Draft PR, not a
merge/independent acceptance. Existing bounded owner14ACK accepted; AIARC-088
negative-access DEFERRED, future launch NOT_PROVEN, continuous HOLD, PIT/UTC/
independent custody UNVERIFIED. #148/#149/#150 untouched. No owner-host/cloud/ACL
operation, G0/trading activation or new Work launch. Unseen chats coverage gap.
