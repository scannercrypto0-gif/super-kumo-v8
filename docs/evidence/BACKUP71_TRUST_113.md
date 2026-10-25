# #113 backup trust hardening and AG-F02 handoff

## Track A: exact reviewed baseline / reproduced defects

Latest parent111 independently re-fetched before coding and before publication:
`5f6f2592b3d24592525d48d078c8e4fcaad1299b`, branch
`feat/issue71-backup-automation`. Read all three conversation reviews, no inline
comments/formal reviews. Author's authoritative CHANGES REQUESTED comment
6396818263 and acceptance boundaries6396819192/6397054335 remain applicable.
Child branch `fix/backup71-trusted-restore` targets that parent branch, not main.
No parent update/merge implied. Dedicated checkout, no new dependencies.

Disposable Windows reproduction against the exact parent showed:

|Input|Parent behavior observed|Child contract|
|---|---|---|
|Change source_version in receipt, recompute its self-hash, leave ciphertext valid|ENCRYPTED_RESTORE_VERIFIED|Externally retained exact receipt-file SHA256 required; rejects forged metadata|
|Rotate current anchor bytes while retaining valid old encrypted backup|Old restore rejected|Old source commitment comes from pinned per-generation receipt; current paths/anchor irrelevant|
|Corrupt first weekly/monthly ciphertext; create next day's same-period point and restore newest|New tiers only daily; health LOCAL_BACKUP_OK_NOT_CUSTODY_ACCEPTANCE despite corrupt older point|Audit all retained points against previously retained local receipt evidence and ciphertext; corruption/missing evidence/quota fail closed before coverage/health|

First case demonstrates a **metadata authenticity gap**, not stolen keys or
arbitrary plaintext acceptance under a genuinely protected original anchor.
Self-hash/ciphertext hash are not independent origin evidence. No exploit against
an actual protected owner backup or private key was attempted.

## Correction / trust boundary

Restore requires `expected_receipt_sha256` / CLI `--receipt-sha256`, SHA256 of raw
receipt.json bytes obtained from an independently retained, authenticated channel.
It never auto-selects that pin from the backup or current mutable config. The
existing receipt self-hash, AES-GCM tag, pinned recovery-key identity, ZIP limits,
payload hash and old source manifest/inventory checks remain mandatory. Pinned
source metadata supports A-after-B and alternate-host paths without old source,
anchor or media. A new local audit anchor is derived from that pinned commitment,
outside backup/restore. It is not a newly claimed independent trust root.

Monitoring has a distinct **local** trust cache outside external_root: durable
raw-receipt intent pin before rename, or the already retained parent111 outbox
receipt for compatibility. Missing cache cannot bootstrap itself from untrusted
backup metadata. Crash-after-publish retry uses pre-publication local intent and
recreates outbox exclusively. It does not create independent custody; a writer
controlling both stores or the expected external pin is outside this gate.

Every retained point is rehashed before any can satisfy weekly/monthly coverage,
health or retention preview. Audit budget2GB total/60s/4096generations; exceeding
it stops rather than reporting false coverage or doing unbounded work. Larger
retention sets need a separately reviewed bounded audit plan. No repair/deletion.

Raw SQLite headers and WAL/SHM/journal sidecars in custody bundles are rejected;
only the existing verified G1 WAL-aware sealed-backup adapter accepts its SQLite
schemas. Fresh-generation freezing/quiescence remains an explicit operator input,
not an atomic snapshot created by file encryption. Backup API outputs are
individually coherent, not a multi-database transaction or PIT guarantee.

Restore audit paths overlapping backup are rejected before any audit-directory
creation. Outbox now also emits exact `<id>.receipt.sha256`; no secrets/keys or
personal source paths in it. Old anchor/ciphertext filenames never overwritten.
Backup receipt schema/encryption format unchanged; legacy files can be restored
with an independently retained raw receipt pin. API/CLI pin requirement is an
intentional fail-closed change to the unmerged parent draft.

## Local targeted evidence

Existing Windows Python3.14.3 / cryptography50.0.2 / pytest9.1.1, no installation.
**53PASS/0FAIL/0SKIP in28.62s**:30 parent cases (29+missing exact before_publish
process-exit stage),21 trust/rotation/coverage/path cases,2 existing targeted WAL
checks. Tests use temporary synthetic data and ephemeral test keys only.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -B -m pytest -p no:cacheprovider tests/test_backup71_automation.py tests/test_backup71_trust.py tests/test_g1_storage_02.py::test_backup_wal_restore_exact_and_out_of_place_replay tests/test_g1_storage_02_followup.py::test_live_wal_snapshot_excludes_uncommitted_transaction_and_reconciles_rows -q -rs --tb=short
```

New/strengthened cases include old A after new B/anchor rotation, alternate paths
without originals, missing/wrong pin, forged self-hashed metadata, preserved GCM
rejection even if outer pin matches deliberately corrupt fixture, wrong keys,
malicious ZIP members, old-tier corruption despite valid newest point, whole-audit
byte/deadline limits, raw SQLite/sidecars, retained-cache forgery/loss/legacy
compatibility, log path containment and exact outbox pin/no overwrite. Existing
real-process interruption now covers before_publish and after_publish, wrong
media/source change/idempotence/no deletion remain. Selected WAL tests verify exact
restored records and exclusion of uncommitted live-WAL transaction rows.

Windows/Ubuntu Python3.11/3.14 CI checks exact child head and53cases with no skips;
actual commit/tree/job URLs/results are added to PR/#113 only after observed
completion. No redundant full G1/Factory sweeps, new native Scheduler run or F:
transfer. Parent111's native synthetic Scheduler observation remains historical,
not new receipt-pin operational acceptance.

## Track B: reuse completed independent branch

Draft112 `fix/windows-ag-f02-lifecycle`, head
`5341c3a7bb8a19dffae8956c9ada1591070dfcb7`, based on main
`c6851bbaf0664d19490e374d6019687d1c234be7`; not imported into this child.
See its [final report](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/112#issuecomment-6397238780)
and [CI40189995921](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40189995921).
Controlled fixture race reproduced5/5 under .25s per upsert; actual pending queued
recovery remained after the unchanged1s bounded shutdown. Strict UNHEALTHY was
correct. Test-only Event ordering fix, unchanged production pipeline/lanes/health;
positive slow-replay and negative held-background regressions preserve invariant.
Unassisted original CI failure was not reproduced; exact historical cause remains
unproven due missing worker telemetry. Passing reruns alone are not resolution.
Windows149PASS/10existingSKIP;Ubuntu157PASS/2SKIP;disposablePG1PASS. No repeat of
unchanged broad suites in#113, no speculative production lifecycle patch.

## Still blocked / owner acceptance

[Exact Windows owner-run checklist](../operations/backup71-owner-acceptance-113.md)
contains commands/evidence paths for frozen source, approved F: identity/ACL,
source snapshot, manual scoped job, independent receipt readback, real-key
alternate-host restore, timezone/task inspection and failure evidence. It does
not activate a schedule, connect an account or generate a production key.

Offline key escrow, logged-off principal, actual external-media independence,
off-device upload/readback, Telegram delivery, MFA/WORM/retention and full host-loss
recovery remain NOT VERIFIED / owner-configured gates. Local hashes/caches,
synthetic tests and same-account cloud storage do not prove independent custody.
No merge, issue closure, main/#110/Factory/Holdout change or original backup access.
