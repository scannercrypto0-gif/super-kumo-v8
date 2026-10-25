# #71 offline kit evidence — synthetic software scope

## Source / authority

Owner handoff6395607248 and next gate6395592427; base main
249210786ef91f2c1c968dd0c5ec8ef7654b917c. Merged101/104 utilities reused unchanged.
Final head/tree and exact CI are in the Draft PR report. No real owner backup
drive, old restored checkout, real research dataset or protected anchor was accessed.

## Observed local Windows execution

Verified Python3.14.3; Git2.52.0.windows.1. Local kit unit suite12PASS, no skips,
1.525s; inherited builder/verifier16PASS, no skips,.511s. Source changes afterward
only added explicit status/network-path refusal; final exact-source cross-platform
CI is required separately, not inferred from these earlier local results.

Actual separate-process CLI drill, SYNTHETIC_TEST only:

Observed UTC `2026-10-25T09:01:46.607159+00:00`, local execution principal `dell`
(not attested custodian); local tool SHA256
`b848bc9d3fd95ca7585d730f399bef61c27dc57b06eb8331c4934429074f1a76`.
The local repository still pointed to2492107 with this new tool uncommitted at
that observation; do not relabel it as exact-final-commit execution. Subsequent
changes only normalize error-report handling; final CI verifies published source.

- Default restore dry-run exit0: no target directory or report created.
- Explicit --execute --quiescent exit0: source byte hashes, copied files,
  separately supplied manifest digest, restored chain/state and report checked.
- Payload file count2 (sample.bin plus standalone SQLite), copied files3 including
  custody-manifest.json. Manifest SHA256:
  `c3ce86f9012293022a87343b72f6d7f3cdbd0ce3c902ee1da08d3c5284d04460`.
- Actual restored receipt/state replay:1PENDING, checkpoint sequence1/hash
  `a4486fbacacd9b458839d149654660f1dd47753ae961dfbc25135a127f9e595e`.
  evaluation_status=NOT_EVALUATED; research_evaluation_replay=NOT_PERFORMED_NO_EVALUATOR.
- Deliberately corrupting only the disposable restore was rejected by merged
  verifier. Source bytes and anchor preserved. Report was unsigned and always
  independent_custody_verified=false, protection/retention/custodian unverified.
- Actual disposable paths for this observation:
  `C:\Users\dell\AppData\Local\Temp\tmpqbzudm61\source`,
  `...\tmpqbzudm61\restored`, `...\tmpqbzudm61\retained.sha256`.
  These are ephemeral test fixtures, cleaned by the fixture, NOT available backups
  or a physically independent/protected destination. Do not attempt to reuse them.

Workspace evidence JSON custody71_local_evidence.json retains complete observed
UTC/tool hash/local principal/commands' outputs and explicit unverified fields;
it is software-test evidence, not an owner's signed custody attestation. No
operator signoff, authenticated timestamp or independent ACL/retention was claimed.

## Deterministic adversarial coverage

12new cases cover no-write planning, explicit quiescence, exclusive manifest/report/
restore creation, coherent finalized-bundle byte/manifest verification, corrupt/
missing/extra/wrong-anchor rejection, overlap/nested/missing anchor, interrupted
copy preserving partials and originals, changed anchor, Windows unsafe names/
traversal/bounds/reparse metadata, no bundle code execution, observed read-only
receipt replay and missing/wrong checkpoint/plan/live-sidecar rejection.
Inherited16cases exercise the unchanged #101/#104 protocols. Optional symlink
tests are reported honestly if a platform skips; kit's reparse case is deterministic
and requires no privilege changes. No hardware disk-full/power-loss certificate.

## Acceptance disposition

Software and synthetic restore/receipt evidence: submitted for independent review.
Real source/PIT data, independent anchor/media/identity/ACL/retention, signed-off
real restore and research evaluator replay: **NOT VERIFIED / BLOCKED**.
The prior2399file backup hash result and auxiliary broken Git refs are reported
owner context only; not reclassified or repaired. #71/#77 remain open. No merge,
backup deletion/pruning, actual owner drive operation, production, holdout or
Factory priority2 integration. Next real drill requires explicit owner-selected
source snapshot and separately protected anchor/destination authorization.
