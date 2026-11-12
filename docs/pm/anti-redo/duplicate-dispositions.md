# Duplicate-work disposition — 2026-11-12

Authority: owner instructions in Issue #205, Work delivery #205/6825191809, independent Audit #134/6825669682. This is a **scoped** disposition, not an exhaustive semantic audit of 195 PRs. No duplicate implementation is proven between the actual old/new components sampled. Unknown future tasks are INVENTORY_REQUIRED.

| Historical/current scope | Evidence-backed classification | Decision | What not to do |
| --- | --- | --- | --- |
| #78 AttemptLedger vs #46 synthetic Batch01 | Complementary: #78 durable attempt identity, commit-before-ACK, replay; #46 synthetic evaluation/holdout/cost formulas | **KEEP #78 as canonical receipts; REVIEW #46 evaluation as reusable candidate**. Only connect if contract seam is proven and authorized | Do not rebuild a second attempt writer; do not infer real PIT/OOS from #46 |
| #267 Factory vs #78/#46 | Open Factory work, exact semantic overlap not exhaustively reviewed | **INVENTORY_REQUIRED** at Factory phase entry: compare exact current code and tests before implementation | No automatic transplant, merge or discard |
| #73 archive/backup vs #308 as-of source vs #305 capture | Complementary: sealed storage/backup, temporal rights eligibility, bounded transport respectively | **REUSE #73** as merged storage; keep #308/#305 separately gated for source/capture | Do not rebuild backup or equate checksum with original custody |
| #304 historical QA vs original February attestation | QA of publisher archive/checksum/timestamps; original Core known_at custody remains distinct and partial | **REUSE #304 QA** where rights/owner gates allow; **evidence-only recovery** for original attestation | No invented known_at, no replay to substitute native custody |
| #12 vs #307/#205 governance | #12 closed-unmerged Markdown-only conceptual policy; #307 open draft, #205 active governance | **PRESERVE #12 lineage** and selectively cite accepted rules; **#205 is canonical decision index** and versioned #307 is draft | Do not give #12 executable or merged authority; no second ledger |
| #276 Discoverer review vs browser dashboard | Joined Python review is test-only; real browser consumer not demonstrated | **REUSE existing review contract**; inventory browser reader at roadmap phase | Do not rebuild Discoverer because browser proof is missing |
| #271 integration vs component tests | Existing joined TEST_ONLY receipts accepted only for exact source/test/fixture and Audit scope | **REUSE prior tests**; test only changed seams and validate hashes | No broad reruns or synthetic-to-live promotion |
| #305 live feed vs G2 observer | Separate bounded one-shot transport vs continuing forward observation | **KEEP BOTH isolated**; preserve shared-egress and host preflight gates | No restart G2, automatic live connection or assumed 72h completion |

## Confirmed overlap prevention
A hypothetical *new* SQLite attempt writer is a duplicate of merged #78 and must be BLOCKED_DUPLICATE_RISK. This is **not** evidence that two such production implementations currently exist.

## Workflow to resolve any newly discovered duplicate
1. Pin old and new exact PR HEAD, code path, caller and accepted tests; classify same contract vs complementary.
2. Compare correctness, source/PIT/OOS, safety, determinism, integration, Windows/Ubuntu and maintainability.
3. Name **one canonical implementation**; retain superior features of the other only through separately authorized minimal adapters and differential/negative/integration tests.
4. Mark superseded path without deleting historical branches, PRs, evidence or accepted CI.
5. Update capabilities.json and evidence.json at exact SHA, index in #205, then independently audit changed scope. If source or semantics are inaccessible, INVENTORY_REQUIRED; do not claim complete.

## Enforcement status
The gate is on #307 draft only; its GitHub Actions workflow must pass on the exact latest HEAD. This workflow is not a required branch-protection check and cannot stop assignments outside PRs. The owner must separately authorize changes to repository protection/merge rules. Human semantic review remains necessary even when syntax checks pass.
