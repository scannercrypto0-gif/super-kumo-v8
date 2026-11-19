# PKG-PM-ANTI-REDO-01 — inventory and reuse control

Snapshot date 2026-11-12 UTC. Main `90af9794880cbeb00e7e974bfa906ff5e9666183`. This is the governance/documentation delivery under Owner provisional B [#205/6824875424](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6824875424). The pre-assignment gate is documented and exercised locally. GitHub enforcement awaits separate approval.

## I0 — coverage and continuity

| Surface | Verified coverage | Boundary |
| --- | --- | --- |
| Main | 321 recursive tree entries, including directories, with object IDs; GitHub response untruncated | Snapshot at pinned main |
| Branches | 211 accessible refs with exact HEAD SHAs; pagination 100 + 100 + 11 + 0 | Deleted/private inaccessible refs excluded |
| PRs | 195 unique: 50 merged, 122 open, 23 closed-unmerged. Date and state partitions below 100 each, with exact head/base SHA and full changed-path count reconciled for all 195 | Base-ref name matches are stack candidates, not proof of every commit ancestry; computed merge SHA on an open PR is not a merge |
| Issues | 114 searchable issue records, with titles, links and partition counts | Discussion retrieval is targeted |
| Work, PM and Audit | 1,105 comments indexed over #134, #202, #205, #271 and #305 | Private chat and unlisted attachment coverage unavailable; link discovery is not evidence acceptance |
| Local code | 12 shallow repository copies, 34 distinct reachable commit trees and 538 Python blobs with AST names/imports; exact multi-path blob hits recorded | Python symbol index is lexical. Semantic and call-graph classification of all paths and remote-only refs is incomplete |
| Targeted source and CI | Six individually read code/doc blobs, seven verified CI run/job sets, three additional detached Audit/Work records | Archived/deleted Git objects and nonpublic evidence excluded; accessible release list empty, tag endpoint unresolved |

The [coverage manifest](coverage-manifest.json) pins both packaged indexes. The packaged `coverage.json` contains exact branch/PR metadata, links, paths and pagination, and `LOCAL_CODE_INDEX.json` contains the read-only symbol index. The GitHub draft carries the authoritative curated [capabilities](capabilities.json), [evidence](evidence.json), [gate](gate.md), [schema](gate.schema.json) and [dry runs](dry-runs.json). The attached inventory is a snapshot, so changes should update the versioned register and refresh affected lookup pins.

G0-GOV-01 continuity anchors: [PM OS](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6721828613), the prior [reuse decision](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6824489663), [gate design](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6824552533), [reuse ruling](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6824603121) and [inventory directive](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6824655018). Owner data handoffs evidenced are the February Vision ZIP/checksum with subsequent private closure packet to Audit and November-10 Vision ZIP/checksum. Later owner directives cover #305/6824024863 and #305/6824296289, followed by #305/6824425927, #271/6824429108 and current B. The latest operational evidence supplied by Owner is Windows-local Check, with prepared HEAD and dependencies, `HOST_PREFLIGHT_BLOCKED`, `network=NOT_STARTED`, a fresh stripchart sample around +24–25 ms at the measurement time, and shared egress reported. The sampled offset expires under the pilot rule and does not satisfy the other gates. [Historical replay handoff](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6823601215) · [Windows status](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6824830000)

## I1 — capability crosswalk and decisions

The register contains 23 curated capability IDs. Path pins, accountable roles, caller, contract, main blob presence, grade and phase accompany each. Use `INVENTORY_REQUIRED` for any proposed function outside the verified semantic coverage.

| Comparison | Actual overlap and choice |
| --- | --- |
| #12 architecture vs #307 and #205 operating rules | #12 is closed-unmerged conceptual prose stacked from #11 by its documented parent; the 13 paths are Markdown. Reuse applicable decision lineage under the current operating record, leaving #307 architecture as a draft. There is no executable duplicate and no new authority in old prose. |
| #46 synthetic Batch01 vs #78 Factory attempt ledger | #46 freezes synthetic families, costs, next-open behavior and reserve separation, with conservative placeholder inference and unverified holdout custody. #78 pins immutable input/attempt identity, transaction-before-ACK, deterministic replay and process-exit recovery. They cover complementary functions. Select merged #78 receipt semantics, retain #46 evaluation formulas as review candidates. No code transplant, PIT/OOS claim, or claim that a receipt completes evaluation. |
| #73 archive/backup vs #308 as-of source vs #305 capture | #73 handles bounded segment bytes and verified copy/restore, cross-platform tested. #308 validates source/rights/known_at and cutoff at read time with explicit gaps. #305 handles bounded transport and shared quotas. These are separate storage, eligibility and capture functions. Select merged #73 for backup and existing #308/#305 for their distinct boundaries once authorized; preserve independent custody checks. |
| #276 review model vs browser visibility | Joined test-only review does not pin an actual browser UI reader. Reuse the Python contract and inventory the exact browser consumer if the roadmap asks for one. |
| February source attestation vs data capture or replay | Detached packet integrity is independently supported. Native Core source/known_at custody is unresolved for original execution. Recover the original attestation under custody approval. Checksum, candle time and replay cannot substitute for it. |

No reviewed overlap justified a `CONFIRMED_DUPLICATE` label for an existing implementation. The duplicate dry run is a proposed second writer. Historical branches and source histories are preserved. Exact reviewed object IDs are in [reviewed-blobs.json](reviewed-blobs.json).

## I2–I4 — reuse and gate proof

Seven workflow job sets verified from GitHub metadata; three separate historical/Audit records retained with their evidence ceilings. Workflow blob hashes, commands and runner pins are recorded where retrieved. Unavailable test/artifact hashes remain null. No accepted source or platform test was rerun. The schema and dispositions were checked locally, including missing IDs, stale main and connect-existing handling.

- Duplicate second SQLite attempt writer: `BLOCKED_DUPLICATE_RISK`. Reuse merged #78 receipt implementation and CI 40101207446 for unchanged scope.
- Original February custody attestation: `PROCEED_TO_APPROVAL`, evidence-only. Obtain original native attestation and verify its source/decision binding; no collector, replay, synthetic substitution or automatic Work assignment.

## Operational limits and next phase

#305 remains open/draft/unmerged at `607f258ce9aa754dca8e1ca8c77a69cf4f498398`, with Windows and Ubuntu offline CI success, and Live not run in the supplied host evidence. Keep its existing independent P0 gate. G2 observation, Paper/LIVE, G0 and real-data runs are outside this package. PM uses the documented gate for new assignments. For unresolved semantic overlap, refresh only affected pins and inspect the smallest relevant code/contract. GitHub workflow and branch-protection enforcement require separate owner approval. This snapshot makes no claim of independently accepted governance, whole-repository semantic proof, or operational readiness.
