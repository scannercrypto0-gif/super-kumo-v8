# Continuous full-history recovery, with strict source admission

Owner approved this continuation in chat on 2026-11-21: recover network failures,
try original daily alternatives, isolate invalid sources and continue later
periods, document every obstacle and resolution. This changes FullHistory's
source orchestration only; default backfill/daily behavior is unchanged. It
adds no data correction authority. September's single-field policy remains the
only authorized derivative.

## Last actual owner-host handoff

The supplied terminal fragment reports candidate 6a6639c3, receipt
`f8222181413ad700a3b9d429c8a93da79e0c040902e184bb6c15092e265e36c8.json`:
151980 bars, through 2017-11-30 23:59 UTC, 130708644 managed bytes. October
44640 and November 43200 were admitted without duplicates/conflicts. The
August 21360 and September 42780 before/after snapshots in the fragment are
identical. This is OWNER_REPORTED_LOCAL, not independent private E: inspection.
The attachment begins inside the December diagnostic, so it is a terminal
fragment rather than an independently verified sealed receipt file.

December's publisher ZIP SHA256 is
`3d41da2da488a69a21e9223221863c3a8ed6ccb9263d30cf1d3a012a48cfffc1`.
A bounded Linux re-download independently matched its publisher CHECKSUM and
CSV hash: 44564 rows, 20403 failing native rows. 20401 off-grid opens and three
close-time predicate failures overlap in that census. Original daily alternatives
for December 4 and 18 also fail strict validation. See the adjacent
`december-source-recovery-proof.json` for original ZIP/CHECKSUM/member hashes,
first failures and source gaps. A matching checksum proves the fetched bytes,
not validity of their market/time fields. No rounding or row correction follows.

A second bounded run on those original bytes plus checksum-verified December 5
actually deferred the rejected sources, imported all 1440 December 5 rows and
continued to December 18. Its original-file pins and exact result are in
`december-continuous-recovery-proof.json`. This is an isolated Linux source
recovery proof, not execution against the owner warehouse.

## Runtime behavior

- Freeze the complete publisher listing; reuse the existing authorization,
  downloader, 1m validator, importer, registry and storage policy.
- Process monthly originals, then all daily candidates still lacking coverage.
  A rejected monthly file does not prevent later months or daily alternatives.
  Do not redownload an already covered day. Failed daily archives are isolated
  whole; valid rows inside an invalid archive are not silently extracted.
- Retry transient acquisition/discovery errors up to three attempts with bounded
  one/two-second delays. Range and partial-file validation remain in the existing
  downloader. After processing other periods, retry deferred transient sources
  once more with the same three-attempt bound. No infinite retry or owner loop.
- Pure source failures in acquisition or unchanged parser preflight are written
  to immutable quarantine records. Native diagnostics have separate hashed
  evidence objects; console progress emits compact reason/first-failure/pins.
- Coverage skipping requires both physical minute membership and exact parsed
  committed-source coverage. An interruption after the final shard but before
  its receipt is replayed; physical rows alone cannot mark it completed. A
  bounded two-source minute cache avoids unbounded history memory.
- Import, conflicts, local retained-byte corruption, clock, registry, unknown
  errors, path/link protection and storage cap/reserve violations are fatal.
  Never continue past an uncertain local commit. Reuse sealed-source recovery
  after interruption; no task/WS modification, destructive rollback or bypass.
- Final receipts retain the obstacle history, alternative-coverage resolution,
  unresolved source periods and pending partitions. Monthly rejection may be
  resolved by complete verified daily coverage, without forging a monthly
  admission receipt. The source failure evidence remains retained.
- Existing accepted-prefix snapshots/checkpoints, immutable original custody,
  research lanes, 150000000000-byte cap/50000000000-byte reserve and final
  registry verification are unchanged. All writes remain inside the approved
  root. No full-history download runs on CI.

## Exit evidence

`source_scan_exhausted=true` means the bounded source scan and final transient
retry pass finished. It does not mean the missing data was repaired.
`PUBLISHED_SOURCE_SCAN_FINISHED_WITH_QUARANTINED_PARTITIONS` means later periods
were processed but isolated sources remain unresolved. CLI exit 2 deliberately
keeps that result distinct from full admission; no operator intervention was
needed to continue past individual source obstacles.

`all_published_partitions_ingested=true` still requires no pending sources or
unresolved obstacles and reaching the latest published close. Declared
September 420 minutes and any new internal gaps remain visible;
`full_history_verified=false` remains mandatory in the FullHistory driver.
An unfinished archive bound also exits 2 and preserves pending work. Restarting
the one operator command reuses accepted shards and retained originals; it does
not rerun the September correction or modify the Windows scheduled task.

The daily scheduled task is not activated or probed again. Core/Scanner/Factory
continue through the existing registry-bound research readers; no PIT/OOS,
native execution receipt or trading authority is created. PR330 remains open.
