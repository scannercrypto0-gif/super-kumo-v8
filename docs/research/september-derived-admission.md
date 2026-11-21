# Approved September derivative v1 — implementation and local handoff

## Authority / actual latest handoff

Owner decision: https://github.com/scannercrypto0-gif/super-kumo-v8/pull/330#issuecomment-7058751093 . G0-GOV-01 reviewed #205/6721828613 and #330 after the last actual host receipt #7058739302. Baseline candidate `c6fc9e2125ebdd1a56cb50745bf3b9901c9cad2c`, PR open/draft/unmerged. The actual owner-local baseline is 21360 August rows, fifteen supplied daily-shard hashes, source ZIP SHA `4f96569190147d64b7ce55f6760dc3e7962aeb3e209c969b200200e3d7045e70`, and zero accepted September rows. The daily task was inspected read-only: Ready, one pwsh action, result 0, XML SHA `cd8cf4f14c87a3c880defd05e902370a913fea95f8fbcaeb689bd31e5750a4b4`. Its finite-action/output contract remains unproven.

This policy is provisional pending final G0. It authorizes only retrospective derived admission, not publisher-source replacement, trading, PIT/OOS promotion, original Scanner E receipts, task activation or PR merge.

## Exact transformation and immutable provenance

Policy `AQL-2017-09-CLOSE-8160-v1` pins original ZIP, CHECKSUM object and CSV to the three owner-approved digests. It changes native CSV line 8160, zero-based field 6, `1504713600000` to `1504713599999`. The byte-preserving transform does not serialize other rows/fields, change OHLCV/trades, interpolate, or admit the daily zero-duration placeholder. All other source bytes remain identical.

Original objects stay untouched in `raw/`. The new ZIP and its **local derivative checksum** have separate content-addressed immutable object identities. The ZIP uses one fixed-timestamp ZIP_STORED member, making packaging deterministic across platforms without zlib-version differences. A version-1 immutable derivation manifest records the exact decision, original/derived pins, field transformation and unresolved gap. The source catalog explicitly labels `OWNER_AUTHORIZED_DERIVATIVE` and `ORIGINAL_PINNED_DERIVATIVE_LOCAL_CHECKSUM`; no locally created checksum is labeled a publisher checksum. Root capacity checks include all additional artifacts, manifests and SQLite staging.

Actual original-derived digests from the retained publisher ZIP:

| Object | SHA256 |
| --- | --- |
| Original publisher ZIP | b4e525fa0549688dca9e09cc24093f50526db2a255d03961791da3bfd7c24d81 |
| Original publisher CHECKSUM object | 50b17e0903e8f657910c08b76b91fddede36fb8584404ff0bebdde627373f683 |
| Original CSV | d103edb024d391f67713e2e9377a9b2f3101ac02700b5e0637c20cea7fe7a149 |
| Derived v1 ZIP (6326507 bytes) | 91f6a6d573d35118c6248021c465ec0194ef40096109d9664cd3696475c318d4 |
| Derived CSV | 6b0376305b080a61a7977ebfd18386cc1ee3bbfc2eb1263f43e83745584813e0 |
| Derived LOCAL checksum object | e49164ec6fbbab7508c2b51b8ed05a3698eba0644e55d093c252f138d98dffd5 |

Strict `parse_archive` validation is unchanged. The derived bytes must pass the same complete validator; every other anomaly still rejects. The importer verifies original custody and regenerates the exact expected derivative/lineage before mutation. Existing accepted bars remain immutable. Normal retained replay forwards the explicit derivation instead of reclassifying the derivative as publisher-original data.

## Runtime owner invariants and recovery

`apply_correction()` requires the existing warehouse (no rebuild), the original accepted August source pin, exactly 21360 August bars, and **all fifteen hashes exactly matching the owner-supplied baseline**. It snapshots August again after admission and fails on any difference. It also rejects extra existing September bars in the missing interval or any conflicting existing bar before writing a derivation manifest.

Every accepted September bar comes from the strictly validated derived artifact. Per-day atomic, bounded SQLite staging, source replay, crash recovery, writer locking, cap 150000000000 and reserve 50000000000 bytes reuse the existing warehouse. Missing/unavailable pins, altered source/manifest, unexpected fields/census/gaps, budget failures or August mismatch stop rather than bypassing a check.

Expected first successful owner-local result:

- `status=SEPTEMBER_DERIVED_ADMISSION_PASS_WITH_EXPLICIT_GAP`.
- `september_rows=42780`; September range `1504224000000..1506815940000`.
- Total August + September `one_minute_rows=64140`, if no other cohort exists.
- `september_gaps=[[1504713600000,1504738800000]]`, `missing_minutes=420`.
- `august_unchanged=true`, identical `august_before` and `august_after` dictionaries, `original_bytes_unchanged=true`.
- `full_history_verified=false`; `RETROSPECTIVE_NON_PIT`, orders disabled, forward lane separate.
- Subsequent replay inserts zero rows and reports 42780 existing rows. Source/data anomalies remain fail-closed; no automatic exception is granted to other records.

## Evidence grade / tests

`september-derived-original-proof.json` records a **real original-publisher-input derived import into an isolated Linux diagnostic store**: 42780 inserted, replay inserts 0, gap remains 420 minutes and originals survive. This uses the existing original downloaded during the prior authorized diagnosis; no new source acquisition or full market-data upload is required. It is not the owner's E: warehouse; its test-only free-space reserve is 0, whereas the actual Windows operator constructs the warehouse with the unchanged 50GB reserve.

New generated-only tests verify every unchanged byte/field, deterministic packaging/lineage, all source pins, extra-anomaly rejection, unapproved/malformed derivatives, native validator rejection of the uncorrected source, August count/hash preservation, owner-baseline mismatch, replay/restart, crash after partial September shard commits, retained runner behavior, storage-budget rejection, and refusal to hide an extra candle in the 420-minute gap. CI runs the changed importer/runner scope and regression suite on Windows and Ubuntu; the operator script is parsed on Windows. See exact candidate-head CI and delivery comment for counts/results; no owner-host acceptance is inferred from CI.

## One Windows operation

Use the exact reviewed candidate SHA in the delivery comment, fast-forward the existing local checkout without reset/clean, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\dell\Desktop\ATLAS-Quant-Lab\tools\ATLAS-WAREHOUSE-SEPTEMBER-RECOVERY.ps1" -ExpectedCommit '<reviewed full SHA>' -Mode ApplyApprovedCorrection
```

The process-local execution flag avoids the previously observed script launch block without changing permanent policy. The command uses the **already-retained** E: ZIP/CHECKSUM; no authority file or new download is required for this exact approved admission. It performs only read-only task inspection before correction, leaves scheduler/service state untouched, and emits source/derived/receipt digests, counts, gaps, both August hash dictionaries and actual storage state. The default `Diagnose` mode remains read-only as to candle data and still rejects the original source.

Full owner-host success remains pending that command's actual receipt. No repeated original diagnostic/backfill loop is needed. No task activation, original-source overwrite, data-gap filling, PR merge or trading is part of this handoff.
