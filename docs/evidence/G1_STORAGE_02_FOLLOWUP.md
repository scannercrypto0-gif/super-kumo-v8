# #71 consolidated follow-up — evidence and acceptance boundaries

Owner authority: issue #71 comment 6396104313, subsequently invoked by owner in
Codex. Baseline main `097a8682ecbc41bb79450370a48c2d01742a66f7` includes merged
#73 and #106. This document is not a production activation or final G0 decision.

## Delta inventory

| Requirement | Existing implementation / this follow-up |
|---|---|
| Durable writer from authoritative finalized journal | Reuse `LocalArchive`, canonical sealed JSONL, bounded batches, interprocess lock, intent/restart/quarantine and independent catalog watermark from #73. No duplicate writer or automatic pipeline activation. |
| Queue/core isolation, health, crash/conflict/disk failures | Reuse `ArchiveService` queue1 and existing 60-case storage suite, including real subprocess termination. No network or additional rate-limit consumer; filesystem calls remain nonpreemptible. |
| Coherent WAL backup and new-target restore | Reuse #73 backup API, inventory, exact source/index/envelope reconciliation. Expose optional hot snapshot + disposable restore in the finite CLI; report same-run local digest honestly. |
| Future source rejection in backup | **Confirmed defect fixed:** unarchived records were validated with cutoff year9999. Reproduction with a final-flagged bar ten minutes in the future, normal current receipt/commit, empty archive: baseline create_backup succeeded (0 archived/1 source). New backup rejects, preserves primary and partial attempt, publishes no verified backup. |
| Snapshot time | Add hashed `journal_snapshot_completed_ms`, observed after source backup completion; validate source against it. This is local wall-clock observation, not trusted time/PIT or a cross-database transaction. Legacy inventories validate against verification time without retroactive capture attestation. |
| Offline data contract for #77 | New `aql.archive.offline.snapshot`: verified sealed backup + retained inventory hash; canonical bounded retrospective envelope query. No research imports/registration/runtime changes. |
| PIT decisions/outcomes | Existing immutable serialization contract only. Runtime capture of full decisions/outcomes is **not implemented**; no strategy/paper lifecycle exists in this storage scope. Unknown availability remains unknown. |
| Independent custody / production | Not verified or activated. Real sample evidence remains owner-reported bounded external-drive trial; no repeated Binance trial or access to old backups. |

## Reproducible local commands

Windows Python3.14.3, pytest9.1.1, existing interpreter
`C:\dev\ATLAS\g1-completion\.venv\Scripts\python.exe`; no installations.
Set `PYTHONPATH` to this checkout's `src` and verify imports first.

```powershell
python -B -m pytest -p no:cacheprovider tests/test_g1_storage_02.py tests/test_g1_storage_02_followup.py -q -rs --tb=short
python -B -m pytest -p no:cacheprovider tests/test_g1_wp01.py tests/test_g1_wp02.py tests/test_g1_wp03.py tests/test_g1_wp04.py tests/test_g1_wp04_fix01.py tests/test_g1_completion.py -q -rs --tb=short
python -B scripts/measure_g1_storage_02.py --rows 512
```

Observed local run: **78 PASS, 0 SKIP/FAIL in61.01s**. Applicable G1 regression:
**147 PASS,10 existing SKIP,1 existing utcnow warning in107.01s**. Skips: one
opt-in live Binance, six Windows SIGKILL exclusions, two Windows throughput
exclusions and one CI-only disposable PostgreSQL. No new storage test is skipped.

Final exact SHA, test outcomes and CI URLs are recorded in the linked PR and
issue #71 RESULT after publication; pending work must not be read as CI success.
Workflow requires 78 passing cases (60 reused +18 delta), zero skips, on
Windows/Ubuntu Python3.11/3.12/3.14, checkout head and source artifacts.

Delta cases cover the actual future-backlog defect, future snapshot time, legacy
inventory compatibility, immutable read-only query parity before/after restore,
half-open selection, unselected corruption, mutation between verification and
selection, limits/no truncation, visible unarchived backlog, cross-process byte
identity, CLI bounded archive→backup→restore and unchanged journal ACK, malformed
CLI denial before directory creation, and a real WAL write transaction whose
uncommitted row is excluded from coherent SQLite snapshot. Existing 60 tests
retain crash/lock/disk-full/permission/latency and tamper coverage.

## Observed measurement (synthetic, not the owner's CSV sample)

[Raw JSON](g1_storage02_followup_windows.json), observed 2026-10-25T09:52Z,
512 rows, 8 symbols, 8 batches. Source SHA256 hashes in JSON identify measured
worktree bytes; this is pre-publication local evidence, not a claim it ran on a
later commit identity. Concurrent local test activity affects timings.

| Item | Measured |
|---|---:|
| JSONL / manifests / catalog | 558728 /16929 /135168 B |
| Archive bytes/row incl. fixed catalog allocation | 1388.330078125 B |
| Journal snapshot | 344064 B |
| Archive / verified backup / restore | 1.203 /1.352 /1.526 s |
| Core commit median /p95 | 31.288 /98.018 ms |
| 20 core commits while archive blocked median /p95 /max | 15.533 /19.974 /22.672 ms |
| Restored source /archived rows | 512 /512 |
| Inventory files /bytes (inventory itself excluded) | 18 /1054889 B |

512 exact source rows and archived keys/envelope hashes reconciled. These are
same-device disposable snapshots cleaned after measurement, not available backup
media. No power-loss, independent custody, host I/O isolation or RPO/RTO guarantee.

Extrapolation: symbols×1440×days×1388.330078125/1e9 decimal GB:

| #67 scenario |30 days|90 days|365 days|
|---|---:|---:|---:|
|10 symbols low|0.5998|1.7993|7.2971|
|100 base|5.9976|17.9928|72.9706|
|500 high|29.9879|89.9638|364.8531|

Excludes original journal/hot/WAL, PIT/outcomes, research files, quarantines and
backup copies. Not a measured deployment rate, Parquet estimate or disk approval.
Sparse schedules create tiny segments. Default2GB/8192-file/60s backup limits
bound a generation, not full-scale archive capacity. Compression, incremental
backup and separately versioned corrections require future design/evidence.

## Remaining acceptance gates

Independent protected anchor (ACL, writer denial, retention, custodian signoff),
approved disk/horizon/media and recovery targets, finalized real evidence scope,
actual PIT/provenance and research evaluator/reconciliation remain external or
separate work. No Git fsck/recovery claim. No cloud, R09 resolution, pruning,
production migration/activation or #77 completion. Do not close #71/#67/#77 or
merge this PR automatically. Proposed ADR remains provisional.
