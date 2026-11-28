# Daily import readiness — prepared, not run

**Disposition:** `DAILY_IMPORT_PACKAGE_READY_NOT_RUN`  
**As of:** 2026-11-25  
**PR #330:** open, draft, unmerged.  
**Purpose:** prepare one retained Daily ZIP import for a later, separately approved quiet window. This document is not an instruction to run anything during the active 24-hour observation.

## Evidence grades and current state

| Item | Current evidence | Grade / limit |
|---|---|---|
| 24-hour BTCUSDT feed | Started at the owner-reported device time 2026-11-25 13:18:45; no final report has been supplied | `OWNER_REPORTED_LOCAL / IN_PROGRESS`; no sustained pass |
| One-candle REST gap recovery | Isolated acceptance returned `CLOSED`, `restored_bars=1` | `OWNER_REPORTED_LOCAL`; does not prove the 24-hour run |
| Daily worker link | Existing #331 verifier reported the 2026-11-24 Daily worker/job/source pin as `VERIFIED` | `OWNER_REPORTED_LOCAL`; verify again in the later preflight |
| Daily archive bytes | `BTCUSDT-1m-2026-11-24.zip`, day `1795478400000` (2026-11-24 00:00 UTC); ZIP SHA256 `40ef687c70c5fd5cd52a35e372dfdc1a6c01d098ec79320977c383dce14e5fbc`; CHECKSUM-file SHA256 `b3861ffa7a1fba395d874d3096c44f6e8bcd8b9cfc3cba7b175c119571845342` | `OWNER_REPORTED_LOCAL`; not re-read from the current host here and must be rehashed |
| Current Warehouse admission for these exact bytes | Last bounded owner inventory found no matching source catalog/import receipt for the then-searched Daily object | `OWNER_REPORTED_LOCAL`, time/path scoped; exact target receipt must be checked by its content-addressed path before any future import |
| Registry baseline | Snapshot SHA `a09721781c6b1a698f2acba8cde42ceeee4c44218fe1d83baec792100d5f526c`, event watermark `354`, event head `1bfc9b3fa8d6977548038101760f433ccbe365cf7a4b4e019b870aaec8535e0d` was previously seal/chain verified | Prior evidence only; a future owner-approved baseline must be re-read. Do not select a file by newest name/time or synthesize a receipt |
| Capacity policy | #330 code pins the Warehouse cap at 150,000,000,000 bytes and free-space reserve at 50,000,000,000 bytes | `IMPLEMENTED`; actual current free/managed bytes are unknown |
| Independent review | #134/7162909290 accepted the #330 one-archive path with an I/O-coverage limitation | `INDEPENDENTLY_REVIEWED` for the reviewed code head only; not host execution or capacity approval |

The prior import authorization remains on record. It does not override the present “prepare only while the 24-hour run is active” restriction. A later execution requires that observation to finish, a fresh host preflight, and a new explicit timing/GO decision.

## Exact interface checked

At #330 code commit `1f9a637aae21fee6dfd17c9a1cdcad969617916e`:

- `src/aql/warehouse/daily.py::import_one_retained` is the exact one-archive entry point.
- CLI: `python -m aql.warehouse.daily --root ROOT --archive ZIP --source-day-ms MS --expected-zip-sha256 HEX --expected-checksum-sha256 HEX`.
- The parser checks final source period, exact UTC day/name, ZIP and CHECKSUM byte pins, publisher checksum, ZIP/member structure, and CSV fields before opening the writer. It then reuses the existing Warehouse importer and Registry; it does not call Binance, `FullHistory`, the journal sidecar, a scheduled task, or the Daily task.
- It emits an `aql.research.warehouse-source.v1` catalog source receipt, Registry evidence, an `ARCHIVE_IMPORTED` result, and a content-addressed report receipt. Identical source replay inserts zero new rows and does not add a duplicate source event; conflicts stop.
- This CLI does not itself consume or verify the Daily worker receipt. The later preflight must separately use the accepted #331 verifier at `9d9e873fbaba8742280846285bd0b5db154ec455` and bind its exact worker receipt/day/ZIP/CHECKSUM to the retained files.
- The parser accepts a nonempty validated archive; it does not require 1,440 rows. A future preflight must report parsed row count and coverage, and post-run Registry checks must keep any missing minutes explicit. Do not infer full-day completeness from a successful import result.
- The single-archive operation still runs existing Registry/warehouse reporting. Import calls native Registry reconciliation; the wrapper then builds a physical report. The existing capacity budget also recursively counts managed files. These may read/inspect the existing warehouse and take material I/O on a large store. This package did not run them. Run only in a later quiet window after capacity and concurrency preflight; do not describe the operation as a one-file-only I/O workload.

## Later quiet-window preflight — read only, not run now

Run this checklist only after the 24-hour observation has ended and the owner explicitly authorizes the timing. No PowerShell command is requested during the observation.

1. **Exact code and interpreter:** locate a trusted checkout containing the reviewed `src/aql/warehouse/daily.py`; verify its commit and the audited #330 source file. Confirm the selected Python environment imports that module and its pinned dependencies. The older owner-reported `E:\\ATLAS\\repo` HEAD is not proof that it has this code.
2. **Daily producer proof:** use the existing #331 verifier with the active Daily task's exact state, policy, config pin, source day and worker receipt. Require `status=VERIFIED`; confirm job/claim/done linkage and that the source day equals `1795478400000`. Use private paths locally and redact them from public output.
3. **Archive identity and finality:** read only the single named ZIP and adjacent `.CHECKSUM`; recompute both SHA256 values and require exact equality with the pins above. Run the pinned native `parse_archive` preflight on those same bytes before the write command. Record row count, first/last open time, and missing-minute ranges. Stop on a changed pin, wrong day/name, malformed checksum, source not final, duplicate/out-of-order rows, parser failure, or unexpected coverage.
4. **Existing admission and idempotency:** inspect only the exact expected source catalog path `catalog/40ef687c70c5fd5cd52a35e372dfdc1a6c01d098ec79320977c383dce14e5fbc.json`. If present, verify its seal, key, source ZIP pin, and retained raw/checksum references; verify the matching source/Registry event. If these already prove the source is admitted, do not import it again. If a same-key different pin, malformed record, or unanchored Registry is found, stop.
5. **Registry baseline:** confirm the owner-approved immutable snapshot SHA and event watermark/head immediately before execution using the approved read-only evidence path. The previously verified `a097...` snapshot is a baseline candidate, not permission to select the newest file. Do not write a snapshot or receipt manually.
6. **Rights and cadence:** confirm the already-approved Binance Vision source/retention references still cover this retained Daily archive and that this operation makes no new network request. The publisher checksum proves byte integrity against its checksum file; it does not prove independent publisher identity, data rights, PIT availability, or source authorization.
7. **Capacity and concurrency:** confirm E: has free space above the 50 GB reserve and that managed usage plus the import's staging/raw/report/Registry writes stays below the 150 GB cap. Use the exact pinned `research_warehouse_plan.py` for free-space policy; the import itself enforces managed-cap budgets. Because writer-budget/report paths inspect existing storage, budget time and I/O for a full current Registry/physical read. Confirm there is no concurrent Warehouse writer, historical loader, or Daily job execution; do not change task settings to create a window. Preserve isolation from the completed 24-hour feed resources.
8. **Baseline seals:** record the approved pre-run snapshot SHA, event watermark/head, and only the specific protected baseline hashes supplied by the custodian. Do not run a full history reconstruction or a multi-million-row scan as preparation.

Any unknown or failed item is `NO_GO`; no file writes occur. Never infer GO from a successful task state, old source pin, or synthetic CI.

## One-archive command — prepared, not executed

Use only after every preflight item passes, the 24-hour observation has completed, and the owner provides the separate explicit GO/timing decision. Replace the three local placeholders privately; do not publish their values.

```powershell
$ErrorActionPreference = 'Stop'
$repo = '<trusted checkout at the exact reviewed #330 code SHA>'
$py = '<approved Python executable for that checkout>'
$archive = '<approved retained Daily directory>\BTCUSDT-1m-2026-11-24.zip'
$expectedCode = '1f9a637aae21fee6dfd17c9a1cdcad969617916e'
$head = (git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -cne $expectedCode) { throw 'EXACT_REVIEWED_CODE_REQUIRED' }
$env:PYTHONPATH = Join-Path $repo 'src'
& $py -B -m aql.warehouse.daily --root 'E:\ATLAS\DataWarehouse' --archive $archive --source-day-ms 1795478400000 --expected-zip-sha256 40ef687c70c5fd5cd52a35e372dfdc1a6c01d098ec79320977c383dce14e5fbc --expected-checksum-sha256 b3861ffa7a1fba395d874d3096c44f6e8bcd8b9cfc3cba7b175c119571845342
if ($LASTEXITCODE -ne 0) { throw "DAILY_IMPORT_FAILED_$LASTEXITCODE" }
```

The code itself re-hashes and parses the same ZIP/CHECKSUM bytes before opening the writer. The pins above remain owner-reported historical values until the future local rehash passes. Do not substitute `--input-directory`, invoke `FullHistory`, or run this during the current observation.

## Post-run readback

Keep the original retained ZIP/CHECKSUM untouched. Capture sanitized command JSON and verify all of the following before connecting any downstream consumer:

- Exact source catalog receipt: schema `aql.research.warehouse-source.v1`, source key/day, ZIP and checksum pins, row count, first/last open times, `RETROSPECTIVE_NON_PIT`, receipt seal, source class and authority fields.
- Matching `ARCHIVE_IMPORTED` result: source pin, actual inserted/duplicate/conflict counts, no unexplained conflict, and successful exit. For an already-admitted identical replay, expect `inserted_rows=0`; confirm the event watermark does not advance with a duplicate source event.
- New canonical Registry snapshot and event chain: compare pre/post watermark/head, verify the new source receipt is in `sources`, and record snapshot seal, coverage, gaps, unavailable boundaries and conflicts. Keep every gap explicit. Never manufacture a receipt or choose the latest snapshot by filename.
- Content-addressed daily report receipt: verify `warehouse_receipt_sha256` points to the exact report bytes. Recheck only the designated protected baseline hashes and require equality.
- Run the #331 Watchdog lineage check only after these genuine host receipts exist and after its own exact-head gate. Until then Watchdog/MCP remain `UNKNOWN/HELD`; #333's 24-hour status is independent. No claim of full history, PIT/OOS, strategy acceptance, G0 or trading readiness.

## Failure and recovery

There is no destructive rollback command. Raw publisher originals and append-only Registry events are preserved. Daily import is not globally atomic across ZIP, checksum, per-day shard, catalog source receipt, Registry event and final report. If any command or disk operation fails:

1. Stop; do not blindly rerun or delete/quarantine/rewrite any original, shard, receipt, snapshot, or Registry event.
2. Preserve the exact exit code and sanitized output. Leave any partial original inputs untouched and allow the writer process to exit naturally.
3. In a later approved quiet window, use the existing native read/recovery path to determine whether the fault occurred before admission, after shard publication, or after source receipt. The current importer has tested recovery after shard publication before catalog receipt in its archive-level suite; the new focused regression below will exercise the same fault through `import_one_retained`.
4. Retry only if the native source pin, source row set, partial shard, catalog receipt and Registry chain are consistent and the reviewed importer confirms idempotent recovery. Otherwise preserve state and stop for source-owner/Registry review. Never fabricate an `ARCHIVE_IMPORTED` receipt or repair the event chain by hand.

## Isolated failure/recovery regression

A generated temporary-warehouse test injects one I/O failure while publishing the source catalog receipt after the day shard is published. It asserts that the same `import_one_retained` path used by the CLI fails without publishing a false source receipt, then restores `write_once` and retries the identical pinned bytes through that API, and verifies zero re-inserted rows, the genuine source receipt, Registry lineage and report receipt. It uses no network, host paths or owner data.

## Decision matrix

| Gate | GO condition | NO-GO condition |
|---|---|---|
| 24-hour observation | Final owner result received and accepted; resources idle | Still active, no final result, or unresolved resource overlap |
| Code | Trusted interpreter and exact reviewed SHA available | Checkout/interpreter pin mismatch |
| Daily lineage | #331 verifier says `VERIFIED`; worker/job/day/pins align | Missing/stale/mismatched claim, job, done record or worker receipt |
| Source | Current byte hashes match pins; source final and covered by existing rights | Pin drift, malformed or incomplete source, authorization/cadence unclear |
| Warehouse target | Exact existing root/policy and canonical baseline verified | Root/policy drift, unverified Registry anchor, same-key conflict |
| Capacity/lock | 150 GB cap and 50 GB reserve pass; no concurrent writer | Unknown/insufficient budget, writer busy, task/source concurrency |
| Import result | Source receipt, Registry event and report seal read back | Partial state, missing receipt, gap/conflict outside approved policy |
| Approval | Separate explicit owner GO/timing after quiet-window preflight | Any missing gate |

**One residual operational blocker:** the future owner-host preflight and separate quiet-window GO have not happened. Current result is ready-to-run documentation plus synthetic recovery coverage only; no import or host change has occurred.
