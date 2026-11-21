# September 2017 source blocker — scoped recovery report

## Continuity and decision

Owner assignment: #330/7058492639, renewed explicitly 2026-11-21. Reviewed PM #205/6721828613 and latest #330 owner handoff #7058480234. Candidate baseline `96efaeee84fe8356604f0b306230100f895ed1a6`, PR open/draft/unmerged. Owner granted bounded original-source acquisition on Windows E: in #7058450023; no scheduler mutation, PR merge, WS change or trading permission. Last actual host result is **OWNER_REPORTED_LOCAL**: August 21360 bars, September rejected, total stored bytes 17972404. No later owner-host result or access to private E: was available.

**Finding: source-quality blocker; no demonstrated validator bug.** `engine.py::parse_archive` and all its time/price/volume/trade/auxiliary predicates remain byte-for-byte unchanged. No timestamp was normalized, no row skipped, no synthetic fill inserted, no original bytes replaced.

## Direct publisher-original evidence

Inspected four bounded source objects directly over HTTPS from data.binance.vision: monthly September ZIP/CHECKSUM and daily September 6 ZIP/CHECKSUM. These diagnostic copies are distinct from the owner's private retained objects. No full market ZIP/CSV is committed to GitHub. The native values/predicates and hashes are in `september-2017-source-diagnosis.json`.

| Original object | ZIP SHA256 | CHECKSUM file SHA256 |
| --- | --- | --- |
| BTCUSDT-1m-2017-09.zip, 1394854 bytes | b4e525fa0549688dca9e09cc24093f50526db2a255d03961791da3bfd7c24d81 | 50b17e0903e8f657910c08b76b91fddede36fb8584404ff0bebdde627373f683 |
| BTCUSDT-1m-2017-09-06.zip, 33224 bytes | 781905772f8b0366a2a09879fface439f04d41c189e4000e9c960dc7896246a3 | ed5ea4ddfac7bc9115dc60a3d4d8eccc08489f31c4f79ed19cf559c93953637d |

Both ZIPs match their publisher-served checksum exactly. That proves integrity relative to fetched publisher bytes; it does not attest historical PIT or independently certify the data's correctness.

Monthly CSV SHA256 `d103edb024d391f67713e2e9377a9b2f3101ac02700b5e0637c20cea7fe7a149`, 6326365 bytes / 42780 source rows. **First and only native-time predicate failure: line 8160, zero-based field 6 (close time)**:

- Open: `1504713540000` = 2017-09-06 15:59:00 UTC.
- Original close: `1504713600000`.
- Required inclusive 1m close: `1504713599999`.
- Difference: **+1 millisecond**, exclusive-next-minute endpoint rather than the required inclusive endpoint.
- Actual unchanged admission result: `ValueError: NATIVE_TIME_OR_MARKET_FIELDS`.
- Existing source open-time gap: `[1504713600000,1504738800000)` = September 6 16:00–23:00 UTC, **420 missing minutes**. A successful parse would not make this month complete.

Daily alternative has 1021 source rows. Its line 960 has the expected close for 15:59, but **line 961** is a zero-volume, zero-duration record with `open=close=1504713600000`, where a finalized minute would require `1504713659999`. The entire daily object also fails the unchanged validator. Its remaining open-time gap is 419 minutes; the extra row is not an admissible finalized minute. Selecting only its favorable row while hiding the bad placeholder would require an explicit source-selection/correction policy and lineage.

Source semantics checked against official documents:
- https://github.com/binance/binance-public-data/blob/master/README.md — native 12-field schema, checksums and publisher corrections.
- https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market — open time, close time, trade count and auxiliary fields; native examples use inclusive close endpoints. No documented blanket legacy exception was found that justifies accepting arbitrary close-time errors.

## Delivered delta and tests

Adds `aql.warehouse.diagnose` for bounded field-level diagnosis using the **real admission validator first**, and one guarded Windows recovery entry point. The warehouse engine, source acquisition, storage enforcement, forward lane and existing task scripts are unchanged. Existing caps remain 150000000000 managed bytes / 50000000000 free-space reserve.

The recovery command requires the existing warehouse, exactly 21360 validated August bars and the accepted August original SHA `4f96569190147d64b7ce55f6760dc3e7962aeb3e209c969b200200e3d7045e70`. It verifies retained September ZIP/CHECKSUM, snapshots every August shard hash before/after, and writes bounded quarantine-reference and receipt JSON using the existing warehouse writer/quotas. It preserves the original September object in raw. For the currently published invalid source it emits **BLOCKED_INVALID_PUBLISHER_SOURCE, exit 2**, imports zero September bars and does not repeat unchanged backfill.

New generated-source regression cases cover monthly +1ms endpoint, daily zero-duration placeholder, malformed time/price/volume/trades/auxiliary values, correct endpoint acceptance, wrong-checksum rejection, preserving all 21360 August rows/shard bytes and refusing to provision a new warehouse. CI runs on Windows and Ubuntu and parses the new PowerShell script. Original full source files are not downloaded during synthetic CI.

## One owner-local command

Use the exact reviewed candidate SHA in the delivery comment. From an updated PR #330 checkout:

```powershell
.\tools\ATLAS-WAREHOUSE-SEPTEMBER-RECOVERY.ps1 -ExpectedCommit '<reviewed full SHA>'
```

This is the safe **continuation gate**, not a claim that the bad source can now be admitted. Existing authorization can be supplied with `-AuthorizationFile <same private file>`; it is reused for a bounded batch only if the retained publisher source passes strict validation. The default known-bad pin is never relaxed. A genuinely new publisher-corrected source requires its separately verified pin and matching retained bytes, not a locally edited ZIP presented as a publisher original.

The script reads the named existing Windows task with Get/Export operations only, records its XML hash/state/action count/last result without printing private arguments, and does not activate or modify it. An optional known `-DailyArchiveRoot` is inspected only for retained 1m ZIP/CHECKSUM pairs. Seeing pairs does not attest their content or finite-action behavior. With no configured output directory, that seam is explicitly unverified. Actual host inspection evidence still requires this local invocation.

## Specific owner intervention required

Either provide a publisher-corrected September source plus original CHECKSUM and verified expected pin, **or approve an explicit versioned retrospective correction/source-selection policy** for this anomaly (including original preservation, exact field/row lineage, independent review and unresolved-gap reporting). This engineering task does not itself authorize inventing that policy or silently subtracting one millisecond. A policy could make a derived research dataset admissible, but it would not change the original archive or fill the 420 missing minutes.

Until then: **September is NOT accepted; full-history completion is false.** August's 21360 original-host bars and range `1502942400000..1504223940000` remain owner-reported. The new synthetic preservation test verifies the same count/invariants on both CI platforms; it does not inspect the owner's E:. Native Scanner E receipts and PIT/OOS remain outside this recovery claim. PR #330 remains open/draft/unmerged.
