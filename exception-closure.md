# ATLAS consolidation 02 | Exception-closure receipt

**State: engineering verification complete for the four partial candidates. Release remains blocked on independent Audit, formal review controls, final PM disposition and separate owner authorization.** The [frozen dossier](https://github.com/scannercrypto0-gif/super-kumo-v8/tree/522522279d6e6be634830ec9d1a96d0f9d1635e1) is unchanged. The owner-supplied conditional Audit assessment is chat evidence. A terminal independent verdict has not appeared on the existing GitHub request. [Owner dispatch](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6943948982) · [PM preliminary decision](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6943444254)

## Exact ordered manifest and proof

Main is `90af9794880cbeb00e7e974bfa906ff5e9666183`. The four source heads still match the frozen manifest. Manifest SHA-256 `121223a3697877b12408e7cfaa5d0c6fef453baab08ccaa4c5bfa2df331db139`. Candidate bundle SHA-256 `b2a8b98be6d8ec1a2c17d98e6679e7c4c5cc028c6bdbc07abe2de98a8ca29d32`. The bundle transports the actual commit objects. It uses content IDs and checksums and carries no cryptographic signer attestation.

| Order | Source | Candidate | Tree |
| --- | --- | --- | --- |
| B01 | #287 `852f6fcce1dbb4dede6259fe8d0498d19ff19078` | `b6a0fc5ad9fff8204c29fab51a9720e984389d53` | `f2f257e5d8a81fabbaf569a2e56da1727c215253` |
| B02 | #304 `e0e08a8381a8cceaaa44d6ae2721e9cb0d004648` | `17a8ede53b45c7dcb5c76109bb2e90470adb84ed` | `2466f58c8fd263456ca1c2739c3ca94f66c862ae` |
| B03 | #308 `84649a323613bf4415c7abc41e774381aa379428` | `cf10fb7d0a97c830f40b0246b9ed0d6e78f8736d` | `7e253b4c5ee90fa13a1bf15785a8100bf12cb863` |
| B04 | #288 `3e7afd10497365dbbfb2a0760bf5f6d0a4591fd1` | `5b51d984ef02ba73943112267032665d28bb42a1` | `7868843ce51e59fc045132b3fc945b3a8ff6edfd` |

The verifier authenticates frozen file checksums and bundle refs, runs strict Git object validation, rehashes each raw commit object, checks parent and source author metadata, recomputes source commits for selected paths, and builds each tree independently from the pinned parent and per-path source blob/mode. No paths overlap among the four batches. Read the [object proof](object-proof.json) for all 33 paths. Proof SHA-256 `5b27474fecf2ce979b72f3b2db572391754a2e4e64e8a4014782f07ab135ed75`. Repeat with `python -B verify-candidates.py FROZEN_DOSSIER NEW_CLONE NEW_UPSTREAM proof.json`. Frozen sources and candidate commits are read via the existing public review branch. No new code branch, PR, or changed source head was required.

## Hosted evidence and exception disposition

| Exception | Outcome | Evidence or next action |
| --- | --- | --- |
| Candidate provenance and compatibility | PASS | Disposable local clone plus both hosted runners reconstructed every tree from individually selected source blobs and modes, checked raw object IDs and tested the identical B04 checkout |
| Windows and Ubuntu candidate CI | PASS | [Run 44056867578](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/44056867578), 16 passed each, zero skipped. B01 restart/idempotence, B02 native control, B03 pinned Discoverer/Scanner/Factory, B04 real pinned observer→synthetic Paper native journal/replay. Workflow head is `2bfad5795e1ef3ccd742ef5064a006d62d6feb76`; tested checkout is the B04 commit/tree above |
| Fixture visibility | PASS | [First hosted attempt](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/44055758394) passed object reconstruction and native Paper, but pytest's dynamic namespace lookup lost the pinned Discoverer fixture path. The review-only test plugin preserved the candidate namespace paths. Candidate bytes stayed frozen. The 97 prior Windows cases were reused |
| Rollback readiness | PASS for frozen trees | Applied inverse patches B04 → B03 → B02 → B01 to a scratch index and proved each predecessor tree, ending at main. Real rollback remains a reviewed revert sequence, with no force-write and no runtime/data mutation |
| Security of selected delta | PASS, scoped | [Static screen](security-screen.json) found no credential-pattern hits or workflow, migration, DB or archive additions in these 33 paths. Existing provider REST client only gains a finite, nonnegative Retry-After guard. No new route or call site. Hosted socket guard blocked Python outbound connections during tests. Git fetched public pinned repository objects for setup and pip installed a test dependency. Workflow uses write-disabled token permissions, no persisted checkout credentials and pinned GitHub Actions |
| Repository security controls | Observed | Public repository. Secret scanning and provider push protection enabled; sampled alert endpoint returned zero. Non-provider patterns and validity checks disabled. Default Actions token read-only; Actions PR approval disabled. These facts provide no independent guarantee about private credentials |
| Branch controls and formal eligibility | BLOCKED for release | Main reports protected=false, classic protection 404 and effective rules empty. Existing review branch effective rules empty. No formal approvals returned on the four source PRs. GitHub reports admin and write collaborators capable of review, but an eligible reviewer independent of the changes has not been established and nobody has approved the candidates in a native review. After Audit/PM, the repository admin must designate the independent reviewer and establish the approval/check enforcement for the precise release vehicle before the single owner approval |
| Independent Audit and PM | BLOCKED for release | Owner-supplied conditional assessment and PM preliminary note are recorded. Obtain one terminal verdict on the existing #134 thread and one reconciled PM decision before asking for merge authorization |

## Ten-stage engineering / main / operations readback

This preserves the earlier reporting decomposition. Tests establish the stated engineering seams only.

| Stage | Engineering after this package | Main | Operational disposition |
| --- | --- | --- | --- |
| 1 Governance (G0) | Frozen candidate proof and scoped release controls documented | Existing roadmap and ADR | Final G0 and formal approval controls pending |
| 2 Market foundation (G1) | B01 composed restart/idempotence verified | Existing collector, journal, storage | Selected slice remains offline |
| 3 Historical custody | B02 QA and B03 Core fixture composition verified | Archive primitives | Daily Vision lane independent. No publisher acquisition |
| 4 Scanner/forward observation (G2) | B03 pinned Scanner fixture verified | Existing bounded research path | Portable #286/#289 dependency closure remains separate |
| 5 Secretary/execution simulation (G3) | B04 upstream synthetic observer/journal seam verified | Native position and read-only route primitives | No Paper activation or orders |
| 6 Discoverer/Factory/Lab (G4) | B03 pinned Discoverer/Factory seams verified | Generic H bounded research path | Full Lab/registry and prospective independent evidence remain gated |
| 7 Event provenance (G5) | Fixture revision/rights evidence in composed test | Archive/as-of primitives | No real connector or source intake |
| 8 Multi-trader (G6) | Isolated simulation only | Core contracts | Load, same-symbol isolation and policy activation pending |
| 9 Reporting/Telegram | #310/#311 landing ancestry checked outside main | Generic H read-only reporting | #312 import closure separate. No Telegram or dashboard activation |
| 10 Operations and recovery | Reused owner-host rollover evidence. This package adds no operating evidence | Existing local recovery primitives | Stage remains open. Genuine post-fault recovery unproven. Neither Windows task was operated |

The exact #310/#311 topic landing commits `6c0cd7549d41f657cb3077853465ba4bb10cd558` and `1df72b3cdc3dd551fd6d42ec2b83d4925c4b7cdd` remain outside main. The full frozen inventory and unresolved stacks carry forward.

## Ordered execution boundary

Freeze B01 → B02 → B03 → B04 on the pinned main and keep cumulative tree verification at every boundary. Before any release, recheck main, source heads and branch rules, obtain formal review and the terminal independent Audit and PM decisions, then obtain the single exact-manifest owner approval. If a later authorized merge fails acceptance, stop and propose revert commits in reverse order, proving the same predecessor trees after approval. The live service, daily Vision task, data custody and secrets are outside the merge and rollback.
