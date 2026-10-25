# G1-STORAGE-02 — nonproduction local archive/restore runbook

## Consolidated follow-up: explicit finite restore drill

Read [delta evidence](evidence/G1_STORAGE_02_FOLLOWUP.md) and
[offline contract](G1_STORAGE_02_OFFLINE_CONTRACT.md). Reuse the existing writer;
no service, pipeline activation, download or second archiver is installed.
After owner identifies an approved disposable journal/archive/backup parent and
new restore target, the existing CLI can batch the local drill:

```powershell
python -B -m aql.archive --journal <approved-journal.sqlite> --root <approved-archive> --market spot --build <same-build> --policy <same-policy> --batches 4 --batch-size 64 --backup-to <approved-backup-parent> --restore-to <new-disposable-restore>
```

This command **writes opt-in local archive/backup/restore files**. Review paths,
identity, free space and budgets first; it is not a dry run. Use only authorized
disposable scope. Optional `--operational <approved-hot.sqlite>` includes an
individually coherent hot snapshot, not a global journal/hot transaction.
`--restore-to` and `--operational` require `--backup-to`. Output reports remaining
backlog; finite execution is not continuous coverage. Periodic external scheduling
is a separate operating choice; do not create autostart or duplicate fetch cycles.

Same-run restore uses the just-created inventory digest for **local reconciliation**;
output says `SAME_RUN_LOCAL_COMMITMENT_NOT_INDEPENDENT_CUSTODY`. Retain the digest
under approved independent protection before claiming independent recovery.
Source backup completion time is locally observed, hashed metadata; clock trust
and actual provider availability remain unverified. Future source rows fail
verification, including unarchived backlog. Legacy inventories without completion
time use verification time without retroactive timestamp attestation.

Failure preserves primary and partial siblings; no cleanup command. Verify
returned row/key/hash parity, review health/backlog and retain command output.
For a previously retained digest use the existing `restore_backup` API; never
copy a live database file directly. The custody-kit CLI remains separately scoped
to finalized bundles and does not replace WAL-aware backup.

Read [ADR proposal](adr/G1_STORAGE_02_v1.md) first. All paths below are explicit placeholders for an owner-approved **disposable** environment. Existing pipeline and Strategy Factory stay untouched. Do not apply examples to production or choose a real off-device destination without approval.

Python≥3.11, stdlib archive/backup only. Existing project dependencies needed by reused interval/journal code are declared in pyproject.toml; no Parquet/duckdb install. To use a verified interpreter without editable installation, set PYTHONPATH to this checkout's src for that command/session and verify `aql.archive.local.__file__` belongs to this checkout.

Finite opt-in sidecar (default64 rows/batch, max128 API,256 KiB payload,16 KiB source record):

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -B -m aql.archive --journal <disposable-journal.sqlite> --root <new-local-archive> --market spot --build <reviewed-sha> --policy phase1-v1 --batches 4
```

An external nonproduction scheduler may invoke finite runs or ArchiveService.request(). No new daemon/autostart is installed. A full wake-up queue rejects the request, increments lane.rejected, and leaves records durably pending in the journal. Retry on a later scheduled invocation. stop/finish is bounded and reports an uncooperative worker still alive.

Optional local backup only, separate configured destination:

```powershell
python -B -m aql.archive --journal <disposable-journal.sqlite> --root <same-archive> --market spot --build <same-reviewed-sha> --policy phase1-v1 --batches 4 --backup-to <approved-new-local-backup-parent>
```

Do not lower the default10 GB reserve merely to hide pressure. Tests/benchmarks set0 **only on disposable temporary files**. A changed market/build/policy/source requires a new archive generation/root, not overwriting an existing one. Check actual free space, journal and archive growth, pending errors, backup age, quarantine and partial directories. No cleanup command is provided.

Backup API: `create_backup(archive, destination, operational_path=optional_hot_sqlite)` returns a new sealed path and evidence with inventory_hash/records/journal_records/watermark/bytes. Retain inventory_hash independently (non-secret approval/evidence store); do not trust an expected digest supplied only by the backup itself. Same-disk return always says off_device_protection=NOT_VERIFIED.

Restore drill: `restore_backup(backup_path, new_disposable_path, expected_digest=retained_hash)` verifies inventory, SQLite integrity, every archive/source key and full envelope hash before and after copy. Success creates the target by rename; failure leaves only an explicitly partial sibling. This is not production cutover. Rebuild a new archive root from restored journal if testing continued delivery at a new path; old index is preserved forensic, not silently rebound.

Acceptance hardening: journal, catalog **and optional operational SQLite** must
pass integrity_check against the sealed bytes. Inventory hash alone does not
prove a SQLite file is usable. Verification streams directory entries, rejects
unlisted directories/files and nonregular entries, checks the deadline during
traversal and bounds inventory path depth to16 components. Hash/read helpers
reject nonregular files before opening them (real FIFO test on POSIX; simulated
file-type metadata on Windows). Ordinary blocking filesystem calls/fsync remain
nonpreemptible; timeout is a cooperative work limit, not a hard I/O deadline.

Interrupted backup/restore copies retain partial siblings, never a successful
final destination. Retry uses a new unique temporary attempt and leaves the
primary journal unchanged. No partial cleanup/pruning is automatic. A valid
backup may predate concurrent core commits; inspect journal_max_seq and the
independently retained inventory commitment when setting RPO. The optional hot
store is individually coherent and rebuildable, not a global snapshot.

Never copy a live .sqlite file alone. SQLite backup API handles committed WAL. Never pass immutable=1 to a live database: it is used internally only for completed sealed snapshot outputs. Optional hot snapshot is coherent individually; it can lag journal and should be reconstructed from authoritative journal if necessary.

Tests (local disposable files; no external providers):

```powershell
python -B -m pytest -p no:cacheprovider tests/test_g1_storage_02.py -q -rs
python -B -m pytest -p no:cacheprovider tests/test_g1_wp01.py tests/test_g1_wp02.py tests/test_g1_wp03.py tests/test_g1_wp04.py tests/test_g1_wp04_fix01.py tests/test_g1_completion.py -q -rs
python -B scripts/measure_g1_storage_02.py --rows 512
```

Applicable existing suite has intentional Linux SIGKILL skips on Windows and opt-in external tests. Never enable BINANCE_LIVE_TEST or AQL_DISPOSABLE_POSTGRES_TEST for this phase. Record exact checkout/tree, imported path, Python, commands/counts/skips and actual CI job links. Benchmark measures synthetic JSONL/catalog/manifest bytes and extrapolates10/100/500 symbols, separate from journal/hot store/context/research/WAL/backup growth. No compression or cloud result is implied.

R09 CRITICAL/UNRESOLVED. No Supabase connection, account credentials, paid provider, live/paper orders, Strategy Factory, Holdout or automatic pruning authorized. Owner disk/offsite budget and independent review remain acceptance gates.
