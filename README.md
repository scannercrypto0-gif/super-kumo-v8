# ATLAS Quant Lab | PKG-REPOSITORY-CONSOLIDATION-01

**Disposition:** Proposed release manifest prepared for one independent Audit verdict and one PM decision. A separate owner decision on the exact reviewed manifest is required before any merge. Main is pinned at `90af9794880cbeb00e7e974bfa906ff5e9666183`.

[Owner directive](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6942719994) · [PM Operating System](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6721828613) · [System map](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/202)

## Evidence and exhaustive disposition

[PR inventory](pr-inventory.json) is the authoritative row-by-row record. [Disposition CSV](pr-disposition.csv) indexes it. The inventory contains the exact heads, target bases, author, age from opening, changed paths, postimage comparison vs main (blob and mode), local conflict paths, cross-PR path overlap, exact-head checks and status contexts, formal reviews, branch rules and security-sensitive scope. The Git comparison uses each target's actual Git merge base. Path identity is evidence of identical bytes and modes. A differing path can still overlap semantically and requires the named integration review. A clean simulated merge shows textual compatibility only. Independent Audit comments are graded separately from native GitHub review state.

- **123 open:** 96 draft, 27 non-draft. Four supply narrow candidates, 30 stay deferred for governance/science, 87 carry blockers or unverified release necessity, two have an explicit no-merge disposition. These are recommendations. Source PR states were preserved.
- **75 closed:** 52 GitHub-reported merged, 50 of those merge commits reachable from pinned main. #310 and #311 landed on Factory E and are not in main. #281, #283 and #285 are main ancestry. See the historical rows with exact-head check links for recent release-relevant landings. Closed state without a merge record supplies no main-coverage claim.
- **34** open heads conflict in local Git simulation against main. **115** open heads have a captured check or status; the other eight have no captured check or status. Zero formal GitHub PR reviews returned for the open snapshot. Scoped issue-comment audits exist independently of formal review. Check inventories are a point-in-time view and never substitute for current approval.
- GitHub classic branch-protection endpoint returned HTTP 404 and effective rule queries returned empty lists for all 71 current target branches, including main. Treat the observed absence of enforced rules as a release-control exposure. Preserve the exact-head review and approval gates in this dossier. Recheck GitHub rules and main immediately before any later authorized execution.

## Ten-stage closure matrix

The current roadmap formally names seven gates (G0–G6). The ten rows below are a reporting decomposition that adds three cross-cutting stages. It neither changes the roadmap nor closes a gate.

| Stage | Engineering evidence | Main coverage | Operational closure / manifest |
| --- | --- | --- | --- |
| 1 Governance and architecture (G0) | PM/Audit controls and architecture v1 draft #307 | Baseline contract/roadmap/ADR | Final freeze and evidence reconciliation pending. No candidate |
| 2 Market foundation (G1) | #287 isolated census, as-of readiness and scheduling | Journal, collector, storage and delivery/recovery | B01, offline only. Broader resource/custody gates remain open |
| 3 Historical intake and custody | #304 native archive QA, #308 Core projections | Existing archive primitives | B02 then B03. Publisher Windows task is separate. Original acquisition and rights remain scoped |
| 4 Scanner and forward observations (G2) | #286/#289 prospective plus forward evidence. #277 Scanner prototypes | #281/#283/#285 bounded read-only research seam | Candidate blocked on dependency-minimal observer/Scanner and archive import split |
| 5 Secretary and execution simulation (G3) | #288 isolated simulation and #271 SMA3/12 synthetic integration | Native position contracts/journal and typed research handoff | B04 simulator-only. Continuous Paper/operational routing have separate gates |
| 6 Discoverer, Factory and Lab (G4) | #267, #276, #291, #297, #300, #301 | Main Generic H bounded research authority | Keep retrospective and sealed prospective claims separate. Registry/import closure and scientific gates pending |
| 7 Event provenance (G5) | #308 test fixture revision/rights path; owner design | Archive/as-of primitives | No real event connector in this manifest. Requires source rights, clocks and leakage evidence |
| 8 Multi-trader (G6) | Isolated simulator and strategy identity contracts | Core contracts, no operational multi-trader closure | Separate policy, same-symbol isolation, owner grant and soak required |
| 9 Reporting, dashboard and Telegram | #310/#311 Factory-topic landings, #312 saved daily freshness and #271 Windows reports | Generic H read-only research path | Saved-operator split needs #267/#297 dependency resolution. No dashboard/Telegram activation |
| 10 Operations, observability and recovery | Audited diagnostic delta, owner-host rollover, first daily source poll pending in supplied handoff | Main has local journal/archive/recovery primitives | Existing Windows runtime is outside this release. New post-fault recovery remains unproven |

## Ordered candidates

[Exact manifest](ordered-merge-manifest.json) · [Verified Git bundle](candidates.bundle)

| Order | Selected source | Candidate SHA | Scope |
| --- | --- | --- | --- |
| B01 | [#287](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/287) | `b6a0fc5ad9fff8204c29fab51a9720e984389d53` | Foundation code, focused test and measurement docs. Original workflow stays separate |
| B02 | [#304](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/304) | `17a8ede53b45c7dcb5c76109bb2e90470adb84ed` | Offline historical validation only |
| B03 | [#308](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/308) | `cf10fb7d0a97c830f40b0246b9ed0d6e78f8736d` | Read-only custody and projections plus fixture-scoped recovery fence |
| B04 | [#288](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/288) | `5b51d984ef02ba73943112267032665d28bb42a1` | Isolated simulator and native journal. Promotion and dashboard excluded |

The prepared prefix is B01 → B02 → B03 → B04. Those arrows specify release-tree order, not a claim of software import dependencies between every adjacent batch. Each selected patch applied without conflicts against its prepared parent. All selected files match source-head blob and mode. The manifest carries the source-author endpoints and per-path source commit list. The bundle requires the pinned main commit. It can be inspected in a disposable repository with `git bundle verify`, `git bundle list-heads`, and fetching bundle refs into an isolated namespace. This publishes no code to main or to a live runtime.

### Acceptance and blockers

- **Candidate tree:** 97 unique focused Windows cases passed. A shared pytest temp cleanup permission issue was handled with a private temp path. The next run passed 91, with six cross-branch fixture cases failing because a plain Git archive could not resolve two pinned source objects. The six passed when supplied access to the existing read-only Git object database with the same candidate work tree. Main/source code was unchanged during those remedies. The candidate Windows run selected Paper engine and adapter tests. The pinned upstream Paper acceptance remains upstream evidence.
- **CI:** Exact upstream CI is included for every candidate source in the PR inventory. The selected Git objects are new candidates, with no exact-candidate hosted result. Before merge, run focused Windows/Ubuntu checks for the assembled prefix, including the pinned Discoverer/Scanner fixtures for B03 and #288 native upstream seam for B04. Report any newly demonstrated cross-batch regression. Do not rerun successful unrelated upstream pipelines or acquire sources.
- **Portable G2 and Windows WS split:** #271 conflicts with main in Factory E result store, historical rules and Generic Secretary bridge. Extract the prospective observer/forward contract, separate the archive intake, and make the #286/#289/#305 transitive import pins explicit against the selected Factory interface. Require read-only Windows saved status and cross-platform fixtures before adding any merge batch. The narrow WS Audit only accepted diagnostics [#134](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6939826057).
- **Saved operator split:** #312 is clean on its topic parent. It has three conflicts when the whole ancestry is simulated on main. Import closure depends on #267/#297. Compare the main Generic H contract and reduce the Factory renderer before adding a candidate.
- **Science and authority:** #301 has external chronology, rights and custody gates. The 15,381 SMA3/12 modeled rows remain retrospective. Existing Paper Audit stays separate [#134](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6917064338). None carries trading, Telegram, source expansion or G0 authority. Older research ladders and unresolved alternatives remain itemized in the disposition matrix.

### Approval and rollback

1. Audit returns one independent overall verdict with itemized exceptions against the pinned bundle. PM returns one consolidated disposition on the same manifest. Resolve material findings together and regenerate manifest and hashes if any tree changes.
2. Refresh main, source pins and branch rules, and obtain needed exact-candidate CI/security evidence. Verify no hidden workflow permissions, provider traffic, secrets, credential changes, retained raw market data, unsafe migration or authority widening. Confirm every excluded path remains excluded.
3. Obtain one distinct owner approval of the reviewed SHA/order, test evidence and rollback policy before changing any target branch. An advanced main or changed candidate invalidates this exact manifest until reviewed on the new base.
4. If later authorized, land batches in order and verify each landed tree, integration seam and read-only boundary. Stop on any mismatch. Prepare reverse-order revert patches B04 → B01 on the resulting main and route them through the approval and CI policy. Never rewrite main history or use rollback as permission to mutate data or Windows tasks.

## Owner-local operating continuity

Reused the supplied November 17 Windows acceptance, where activation at 08:56:57 Riyadh yielded nine consecutive authentic finals to 11:00, one scheduled rollover, matched dual native readback and 67 prior missed slots without backfill. The local read-only check during this preparation saw the installed task Running, the next local saved receipt, and the daily XML matching its pinned previous definition. This is executor-side owner-host evidence. Independent access to private files is not assumed. The daily Vision and WS services were neither deployed nor restarted for repository consolidation. Secretary WAIT, zero actual orders/Telegram and no raw WS retention are scoped to the inspected owner acceptance. No genuine post-fault reconnection or legacy root cause is asserted.
