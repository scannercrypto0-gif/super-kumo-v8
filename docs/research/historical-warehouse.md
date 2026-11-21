# Historical warehouse — PR #330

## Delivery and authority

Work order: owner supplied 2026-11-21. G0-GOV-01 intake reviewed PM #205/6721828613, #202, latest accessible #271/#275/#277/#267/#276 and Audit #134/#256, #330 discussion through #7011349719. Baseline main `0dad5acc17172754b741b0e8a97d911436c9f4c5`; original #330 head `ec6410d775c7626684c36328f2813ca134838323`. All six role PRs remained open/draft at intake. Reuse existing #330 `ResearchBarStore`, timeframe validator and Core/Factory `HistoricalLibrary`. Existing #312 freshness and #321 recovery are not new implementations or evidence of deployment of this warehouse.

Last actual owner handoff is **OWNER_REPORTED_LOCAL**, capacity PASS on `E:\ATLAS\DataWarehouse`, free 227462017024, cap 150000000000, reserve 50000000000 bytes; downloads had not begun. Work has a Linux workspace and GitHub access, without an executor on the owner's Windows machine. No E: provisioning, source acquisition, task readback/change or stored original-history counts are claimed.

## Executable flow

`aql.warehouse.source.VisionHTTP` lists both publisher monthly/daily BTCUSDT Spot 1m prefixes with bounded pagination. It chooses only complete UTC periods, retains an exact listing snapshot, selects monthly history and daily tail/gap repair. The first source date comes from actual listing, not an invented fixed inception. Spot timestamps in milliseconds and post-2025 microseconds are checked in their original units. Source reference: <https://github.com/binance/binance-public-data/blob/master/README.md>.

Publisher ZIP and `.CHECKSUM` bytes are retained separately by SHA256. Downloads use bounded, rate-limited HTTPS with verified TLS, 30-second request timeout, Range resume and exact Content-Range/length checks. Redirects are denied. Network failure preserves `.part`; retry the same command. Checksum mismatch quarantines the downloaded candidate. There are no Binance exchange REST/WS calls. The listing and checksum establish publisher-served integrity, not independent attestation or historical availability.

Layout: `raw/`, `catalog/`, `bars/`, `receipts/`, `quarantine/`. Initial adoption of an occupied, unmanaged root fails without deleting its data. A root-specific policy rejects changed limits. Every path rejects symlinks/reparse points; traversal, drive escape and externally hard-linked managed files fail. A kernel-released exclusive writer lock covers all modifications. No stale PID unlocking is required.

Runtime managed-file bytes are counted before writes, including original ZIPs, parts, checksums, catalog, quarantine, SQLite staging and receipts. Free disk reserve is checked before growth. SQLite shards cap at 16 MiB and reserve 48 MiB before staging/rollback; a day is copied to scratch, appended using the existing ResearchBarStore validator, checked, closed/fsynced and atomically replaced. Original archives are create-only. Existing minute values/digests never change; corrected conflicting source is retained/quarantined for explicit disposition. A crash after some shard commits and before archive receipt is safe to replay. No source completion receipt is written before all source rows are committed. OS/filesystem errors are reported rather than bypassed. Exclusive warehouse ownership is assumed; this is not an OS quota for unrelated programs modifying the drive.

Queries verify stored bar digests and reuse `project_finalized_1m` for 1m/5m/15m/30m/1h/1d/1w, exact constituent membership, OHLCV and Monday UTC weeks. All constituent availability must precede the supplied research cutoff. Derived bars are calculated on demand: the report distinguishes **stored 1m rows** from **available complete projections**, not materialized derived files. Missing members fail; no filling of candles. Read queries do not create SQLite databases/WAL or write projections.

`full_history_verified` requires the first row of the earliest listed archive to be stored, no internal minute gaps and the last stored close equal to the latest published complete period in that listing snapshot. It is never asserted merely because an archive loop exited. Exchange pre-listing absence and publisher missing archives are reported as boundary/calendar limits; the program does not invent prices. `--recheck-publisher` explicitly revisits completed archives and retains source revisions without overwriting raw objects or changing existing candles.

## One Windows entry point

Install the candidate in the Python environment chosen for this warehouse (`python -m pip install -e .`). Keep the repository at the reviewed candidate commit; PR #330 remains open.

Read-only inspection:

```powershell
.\tools\ATLAS-WAREHOUSE-ONE-SHOT.ps1 -Mode Inspect
```

This checks capacity and reads the existing named daily task. Task arguments are not printed because they can contain private configuration. No task is created or changed.

Actual bulk download is gated on a private JSON file carrying the already granted scoped permission references:

```json
{
  "bulk_download_ref": "owner's explicit bulk BTCUSDT Spot 1m permission reference",
  "source_rights_ref": "applicable authorized retention/use reference",
  "network_permission_ref": "approved host/network/region reference"
}
```

Once those permissions exist, one command provisions, lists, resumes, imports and emits the actual report, up to 10000 archives with the storage cap enforced throughout:

```powershell
.\tools\ATLAS-WAREHOUSE-ONE-SHOT.ps1 -Mode Backfill -AuthorizationFile C:\PRIVATE\warehouse-authority.json
```

Repeat the identical command after interruption. To inspect actual stored coverage later:

```powershell
.\tools\ATLAS-WAREHOUSE-ONE-SHOT.ps1 -Mode Report
```

No commands here authorize a download or host change by themselves.

## Existing daily task integration

The importer consumes the existing task's retained **original 1m ZIP + CHECKSUM** directory, never starts another collector or another scheduled task:

```powershell
.\tools\ATLAS-WAREHOUSE-ONE-SHOT.ps1 -Mode DailyImport -DailyArchiveRoot C:\PRIVATE\ExistingDaily1mArchives
```

A 15m-only archive directory returns `WAIT_NO_1M_DAILY_ARCHIVES`. It cannot provide original 1m candles. Existing output directory and finite-action behavior must be established by the host readback. If the existing task is a continuous poller, do not bind an after-exit hook: the importer must be attached to its successful archive-commit callback instead. That host-specific seam cannot be asserted from GitHub metadata.

`ATLAS-WAREHOUSE-BIND-DAILY.ps1 -Mode Prepare -DailyArchiveRoot <existing directory>` reads the existing task XML and emits its SHA256 and exact activation arguments. It makes zero changes. After separately authorized host action changes, the same script's `Activate` mode requires the current XML pin, `-HostTaskChangeRef` and `-OriginalFiniteActionVerified`. It retains original XML/action/binding/hook privately inside the warehouse, verifies the installed package, changes only the **existing task's action**, then verifies readback. No trigger, principal, settings, enabled state, immediate start or duplicate task is requested. The original action runs first and must exit successfully before offline import. If Windows requires credentials or denies updating the action, leave it unchanged and use the saved preparation output for the authorized host operator. Restore, when separately authorized, uses the retained exact task XML; no automatic rollback changes host state.

## Research consumer interfaces

`HistoricalWarehouse.query(interval,start_ms,end_ms,cutoff_ms=...)` returns digest-sealed finalized research bars. `adapters.register_window(warehouse, existing_HistoricalLibrary, ...)` validates native immutable HistoricalBars, registers an actual DatasetManifest and preserves RETROSPECTIVE availability. It uses the existing Core/Factory research interface; it does not introduce a second strategy engine.

The existing historical Scanner E route requires native Core245/253 original-admission/query receipts and a 15m dataset contract. A warehouse projection is **not** such a receipt. `inspect_consumer_boundary()` explicitly reports `WAIT_NATIVE_CORE_RECEIPTS`. Full native Scanner E/Factory receipt E2E remains unproven; no source class relabeling, fabricated Core receipt or source-original replacement is permitted. The existing forward store remains `FORWARD_UNQUALIFIED`; this historical lane is `RETROSPECTIVE_NON_PIT` and no cross-lane merge occurs. PIT/OOS and trading authority remain ungranted.

## Validation and actual closeout fields

Focused generated-source tests cover interruption/Range resume, replay, checksum corruption/quarantine, source conflicts, missing minute repair, process death and lock release, shard-commit/catalog crash recovery, live runtime byte/free-space limits, path/reparse protections, weekly and all timeframe boundaries, native HistoricalLibrary registration, daily import and source-completeness reporting. A synthetic separate WS-directory sentinel remains unchanged and acquisition has no collector/scheduler dependency. This is isolation evidence, **not a live owner-WS continuity attestation**. Cross-platform CI is `.github/workflows/historical-warehouse.yml`; it also parses all Windows operator scripts. Existing successful unchanged suites are reused.

| Required final field | Evidence available before owner-host operation |
| --- | --- |
| E: warehouse state | Capacity PASS owner-reported; provisioning/data unverified |
| Earliest/latest available/stored | Discovered/reported by authorized runner; no original dates attested here |
| 1m count and interval coverage | Generated fixtures only; actual owner store not inspected |
| Original/stored size | Actual runner report required; cap enforced in implementation/tests |
| Gaps/duplicates/conflicts/repairs | Focused fixtures; actual run receipts pending |
| Daily update | Offline hook implemented; existing task XML/output/activation pending host readback/permission |
| Core/Scanner/Factory | Native HistoricalLibrary research registration implemented; native Scanner E Core-receipt seam unresolved |
| Windows/Ubuntu tests | See candidate-head CI; do not infer original Windows deployment |
| Blockers/solutions | No Windows executor; no scoped bulk permission file; task-output contract unknown; prepared unified local runner and pinned-action activation procedure |
| Completion grade | Engineering implementation with scoped synthetic evidence; full owner-host/source/native E2E success not claimed |


## Observed implementation failure and correction

First candidate `e07f231b1952873f6921196a0017f4696a27b92e`: Ubuntu 18/18 passed. Windows 12/18 passed, six cases failed from one root cause: Python Windows `os.fsync` rejects a read-only file descriptor (`Errno 9`) when flushing the closed SQLite staging file. Changed the flush handle to `r+b`, retaining SQLite FULL synchronous commits and the pre-publication fsync; no exception suppression. Existing cross-platform crash/replay/import cases exercise the correction. Run: https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/44873170795 .

A source-selection regression also verifies that a monthly archive imported earlier in the same run suppresses now-covered daily candidates, avoiding a second download of the same minute history. The daily hook rejects an already-bound action, requires an explicit finite-action verification at activation, and verifies the retained binding/hook content hashes before use.
