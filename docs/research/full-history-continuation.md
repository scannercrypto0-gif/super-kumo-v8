# Continue all available BTCUSDT Spot 1m history

Owner continuation: #330/7059048243, following the actual owner-local 64140-bar August+September acceptance #7058983090. This extends the existing authorized E: historical acquisition to one frozen listing of all publisher archives through its latest complete period. It does not authorize new corrections, scheduler/WS changes, merge, PIT/OOS, native Scanner E receipts or trading. PM charter #205/6721828613 and the latest handoff/decisions were reconciled before implementation.

## Existing components reused

The same Vision HTTPS discovery/Range downloader, source checksum/native validator, immutable bar importer, per-day recovery, cap 150000000000 / free-space reserve 50000000000 and approved September derivation are used. No second warehouse, source provider, scheduler or strategy engine is introduced. Existing September correction policy remains the only data exception.

`runner.run` now indexes verified source receipts once, uses exact minute membership for source selection, emits progress and distinguishes unattempted source partitions from coverage gaps. Known pre-listing August absence is not treated as a missing repair day. The September 420-minute exclusion is recognized only after regenerating/verifying its exact approved derivation from the pinned original; it is not a general gap whitelist. The daily zero-duration placeholder is never admitted. New gaps still trigger available daily-source repair attempts; conflicting/invalid source stops with the existing validator and field-level evidence.

`full_history.continue_history` drives that same runner once, default bound 10000 archive objects, preserving all accepted August/September shard hashes before/after and every three completed archives. Each three-archive checkpoint is stored through the existing quota-enforced writer, after validating preservation. No owner confirmation is required between successful bounded checkpoints under the latest continuation instruction. Monthly history is preferred; daily tail and genuine missing ranges use source-listed daily objects. Already-covered days and accepted source objects are not downloaded again. A failed/transient attempt preserves original source/partial files; repeating the same command resumes rather than resetting data.

Import availability is actual local receipt/import time, independently of the discovery timestamp; a clock earlier than discovery fails; the local OS clock is not independently attested. Publication dates are not inferred to be historical known-at/PIT. The final report rereads all stored bar digests and shows the exact source-listing snapshot/time and actual stored range, bars, bytes, gaps and pending partition keys.

## Authorization reuse and host operation

The owner already supplied private source/network/retention permission references for the successful first backfill. They were retained inside content-pinned source-listing snapshots. FullHistory automatically reuses a single consistent set of those references and adds the latest public continuation reference. It checks each snapshot's filename hash; conflicting permission sets or tampering stop, instead of guessing. An explicit `-AuthorizationFile` remains available if required. Reference values are not printed.

The existing PowerShell entry point adds `-Mode FullHistory`. It keeps the reviewed-commit gate, checks unmodified tracked warehouse code, reuses the completed owner read-only daily-task evidence without another task probe, and launches the existing-root operation. Neither task activation, permanent execution-policy changes nor a new scheduler is requested. No direct owner E: executor exists in Work; this command is necessary for actual original multi-year acquisition/receipts.

From the reviewed new commit:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\dell\Desktop\ATLAS-Quant-Lab\tools\ATLAS-WAREHOUSE-SEPTEMBER-RECOVERY.ps1" -ExpectedCommit '<reviewed full SHA>' -Mode FullHistory
```

The delivery comment supplies the complete one-line fast-forward-and-run command. It updates code locally without reset/clean; it does not merge the PR on GitHub. Existing E: originals, accepted August+September bars and the 420-minute gap remain protected. No new private authorization path is needed when the retained set is unique.

## Progress and completion evidence

Console events: FULL_HISTORY_START, SOURCE_LISTING_READY, ARCHIVE_IMPORTED / RETAINED_ARCHIVE_RECONCILED and VERIFYING_FINAL_STORED_COVERAGE. The last stage can take longer on a large history because it validates actual stored payload digests; a successful download loop alone is not proof of complete data.

The final immutable receipt explicitly separates:

- `acquisition_plan_exhausted`: every required source partition in this frozen preferred monthly/daily plan has been admitted, with no acquisition/validation failure.
- `latest_published_close_reached`: the actual last stored close equals the latest complete source period in that listing.
- `all_published_partitions_ingested`: both predicates above hold. This does not mean every overlapping monthly AND daily ZIP was downloaded, or that absent publisher minutes were invented.
- `full_history_verified=false`: the known approved 420-minute gap prevents gap-free full-history claims even after all available preferred partitions are stored.
- `declared_missing_minutes=420` plus any separate `unresolved_gap_ranges`. Unexpected gaps or new source failures are never folded silently into the approved September exception.
- `protected_before` / `protected_after`, `accepted_prefix_unchanged`, actual total rows/timeframe windows/storage/cap/reserve, exact source failures and receipt filename.

Final statuses distinguish published partitions imported with the declared gap, published partitions with additional unresolved source gaps, bounded progress with pending keys, and an exact blocked source. New integrity/time/price/volume/trade/auxiliary errors stop with original-file identity and native field diagnostic where applicable. They do not cause another automatic correction policy. A future publisher update can be examined under the existing explicit recheck flow, not by replacing an accepted bar silently.

## Validation and limits

New generated-source tests cover authorization reuse/tamper/ambiguity, first-native-inception selection, keeping approved gaps unfilled, actual repair of an unapproved missing minute from a valid source, pending-key accounting, real import clock vs discovery clock, clock regression, source failure diagnostics, progress/checkpoints, accepted-prefix change rejection and three-archive continuation over the actual generated 64140-bar approved-prefix cohort. Existing importer/correction checks remain relevant because the runner seam changed. CI runs the combined focused suite on Windows and Ubuntu and parses the operator script. No original bulk history is downloaded by CI or this Linux Work environment.

Actual success of the multi-year E: run requires its new owner-host receipt. The latest actual stored evidence before that operation remains 64140 bars through September 2017, with 420 missing minutes. No later date/count or all-history success is predeclared.

## Concurrent Registry C integration

While publishing this continuation, existing #330 advanced from 30854a2 to
9cebfaf7c8bbf5140d380ebf2ef3be03987d5d0d with the separately owner-authorized
Registry C delta, followed by registry-only adoption at 481e484de73179ca2b1b7869408b594f03585578. The continuation was rebased onto that latest successor, preserving
all registry/event/read-gate/adoption code, the RebuildRegistry operator mode, registry tests, adapter binding and governance
files. The workflow includes both registry and continuation tests. Public research
reads remain gated by verified provenance; no older reader is restored to bypass
that gate. Registry verification/rebuild is retained on every committed archive
and final report, so long runs can spend additional time verifying accumulated
history. This continuation does not claim independent acceptance of that registry
delta; its Audit scope remains separate. The latest actual host result is the
64140-bar receipt #330/7058983090, consistent with the registry proposal's latest continuity addendum. No new host execution is inferred.
