# G1-STORAGE-02 — nonproduction local archive/restore runbook

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

Never copy a live .sqlite file alone. SQLite backup API handles committed WAL. Never pass immutable=1 to a live database: it is used internally only for completed sealed snapshot outputs. Optional hot snapshot is coherent individually; it can lag journal and should be reconstructed from authoritative journal if necessary.

Tests (local disposable files; no external providers):

```powershell
python -B -m pytest -p no:cacheprovider tests/test_g1_storage_02.py -q -rs
python -B -m pytest -p no:cacheprovider tests/test_g1_wp01.py tests/test_g1_wp02.py tests/test_g1_wp03.py tests/test_g1_wp04.py tests/test_g1_wp04_fix01.py tests/test_g1_completion.py -q -rs
python -B scripts/measure_g1_storage_02.py --rows 512
```

Applicable existing suite has intentional Linux SIGKILL skips on Windows and opt-in external tests. Never enable BINANCE_LIVE_TEST or AQL_DISPOSABLE_POSTGRES_TEST for this phase. Record exact checkout/tree, imported path, Python, commands/counts/skips and actual CI job links. Benchmark measures synthetic JSONL/catalog/manifest bytes and extrapolates10/100/500 symbols, separate from journal/hot store/context/research/WAL/backup growth. No compression or cloud result is implied.

R09 CRITICAL/UNRESOLVED. No Supabase connection, account credentials, paid provider, live/paper orders, Strategy Factory, Holdout or automatic pruning authorized. Owner disk/offsite budget and independent review remain acceptance gates.
