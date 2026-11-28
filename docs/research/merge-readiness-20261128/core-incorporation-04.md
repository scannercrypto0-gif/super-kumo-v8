# Continuation 04 — exact accepted six-fix incorporation

Authority: [#205/7237001473](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-7237001473). Existing PR338 and main-based candidate are reused. No separate merge of336, unrelated ancestry, force push, host deployment, original input execution, provider traffic or scientific approval.

## Frozen sources and exact acceptance

- Previous338 head a0966343cb9582593144d6e18834b35ce119750f; previous tree e00c9717d3bcbb6c19ad818edca61dd78207cf2e.
- Accepted336 head **1d1dfe913455d043c4269891e2e713b1e57ffc97**, tree **41992df27da6384a74d502d896b1f6b14e89ea55**; same main/base0dad5acc17172754b741b0e8a97d911436c9f4c5.
- Prior five bounded acceptances: [#134/7236493465](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-7236493465). D04 bounded acceptance: [#134/7236871431](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-7236871431). These source dispositions are retained, not replaced by an implementer approval of the new integration tree.
- Applied exactly the17-file main-to336 delta cleanly to338. All17 resulting source/test/workflow blobs are byte-identical to336, without conflict or algorithm adaptation. [Machine source map](core-six-source-map.json) contains exact Git blobs and SHA256 values. Targeted LF attributes make working-byte proof portable across Windows/Linux without changing accepted Git blobs.

## Six fixes, evidence and bounds

| ID | Actual main interface | Due integration evidence | Preserved limit |
| --- | --- | --- | --- |
| D03 | src/aql/pipeline.py | actualpipeline1.1s pending-recovery drain test; Core source/recovery |41s bounded drain, not guarantee every queued/provider operation completes |
| D04 | src/aql/collector/binance_collector.py | actual scriptedcallback/reconnect withrealSQLite journal/store, duplicate-only exhausts unhealthy streak, advancing durable newcommit earns reset |existing cap/backoff preserved; not lifetime/IP-provider quota proof or downstreamACK |
| D05 | src/aql/paper_sim/engine.py | adverse simulated taker notional capped beforefill; modeledUNKNOWN branch and existing G3 tests |offline simulation only, no Paper/trading activation |
| D07 | src/aql/recovery/gap_recovery.py | zeroexpected/zero-unresolved ->NONE; actualmissing remainsunresolved |does not hide missingdata |
| D12a | research_wp_r0/attempt_ledger.py | incompatibleexistingpolicy reopen rejected beforemutation, existingstore data/policy preserved |no implicitmigration/OSisolation claim |
| D18 | research_wp_r0/historical_library.py | construction/register/read checks close+1/ingestion/checksum; acceptedSFfixtures andnewavailabilityregressions |standalone validate_bars on deliberatelymutated rows is NOT independentlyaccepted |

The accepted G1 workflow test-list change is preserved. Existing Core/G3/SF workflows remain intact. The combined matrix explicitly adds all affected CDR/Core/G1-drain/G3-engine/SF modules and origin checks on Windows/Ubuntu Python3.12/3.13; no newCDR test is left outside CI. Newworkflow path filters cover the incorporated source and test scope. No prior-head CI is attributed to this new tree.

## Actual loaded module origins: no silent immutable overlay

The accepted336 main HistoricalLibrary/AttemptLedger SHA256 values are:
- attempt_ledger.py: cfecbe1ba2ae7aabf81430fd3a9ab786606a081aef815a4eea0030a15983d767
- historical_library.py:7757efa6722e1ca0dc842897f520315d6644538289c0699429d0b8643241fc69

The unchanged296 Factory reference versions have different manifest-verified hashes:
- attempt_ledger.py:1018d05926c4227bcc3bbe2bc471a026d3776a051841a80e9dd40bb030e4268e
- historical_library.py:a9ae4cb490c3b0eeaa514b25b4c01e1f1617962d5f4639cad0102030cf13c6bd

`test_integrated_core_origins.py` launches isolated processes and checks actual `__file__`, SHA and native evaluator paths. It then exercises the actual generated source->Scanner->Factory/Lab->SecretaryWAIT chain while arming the frozen HistoricalBar/Library registration/snapshot and AttemptLedger constructor to refuse if invoked. They are not invoked by this bounded forward interface; theactualFactory store/Lab/Secretary calls remain real, source unchanged, twelve-slotdenominator preserved.

Thus D12a/D18 are proven on **main's APIs**, not silently applied to the immutable reference. Any later original/historical path that calls the frozen APIs needs its own compatible source/dependency disposition. Likewise D03/D04/D07 belong to the main pipeline/collector/recovery, not the distinct333 WebSocket service. This package does not claim the mainD04 patch rewrote that separateclient.

## Verification, review and remaining operational gates

Local affected Core group:273passed plus3subtests; three new origin tests passed. Final acceptance is the new exact-head CI and its recorded tree, counts, logs, artifacts and source-byte checks. The runner verifies all17 accepted-file SHA values before executing the final combined test list, and repeats the private-index reverse-patch rollback proof. The previous333-per-cell/17-job report remains prior scope only.

One existing Audit intake #134/7236387946 must move to the final head after successfulCI, review material integration/origin/attributes/runner changes, and retain the prior six bounded algorithms' dispositions. NativeGitHub latest-push approval is separate; an old-head review doesnottransfer. No selfapproval, newAuditintake or protectionbypass.

D16/sharedCDR can record exactcandidate-source/import/clean-checkout/rollback evidence, but independent and deployment closure remain separate. No edit to336 or competingD04 work. D01/D02/D06/D10 decisions, D19abound/legacyHOLD,301scientificS7/holdout and activeFullHistory/fresheab5 sessions remain untouched.

Originalretained/fresh research source and current-clock/asof interface, authentic producer/Registry/worker reports and two realMCPcycles remain the unchanged closure03 gates. No clock backdating, fakeSTOP, fakeACK, cross-sessionstitching, newfeed, activeDB/WALscan or hotpatch. Mainmerge/hostactivation/trading/Paper/G0 remain unauthorized.

### Combined-collection correction
The initial final-tree run at 8fd24dde failed six assertions because Realtime's integration test inserted the pinned Warehouse repository root ahead of main during collection. This selected old research modules although all 17 accepted source files were intact. Removed that unnecessary root insertion (retaining its src dependency) and added an in-process origin assertion after collection. No accepted Core algorithm/test bytes or immutable kernel pins changed. The failed run remains evidence; replacement CI must pass before compatibility acceptance.
