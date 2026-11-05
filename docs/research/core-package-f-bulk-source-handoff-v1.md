# ATLAS Package F — Core F0–F2 handoff (PROVISIONAL)

Parent: #274. Source order: Core #269 comment 6655595682. New Core branch is stacked read-only on open/unmerged Core E #269 HEAD `3af5b66d2b381b853a6b5be32c38b3d3d02e1ea7`. Core #226/#211/#245/#253 remain canonical; we do not duplicate vault, warehouse, historical byte parsing or frozen contracts.

## F0 explicit initial target and cost bounds

One configurable initial research cohort: **2024-01 through 2024-12**, 12 Binance Spot BTCUSDT native15m monthly ZIP objects with separate publisher `.CHECKSUM` each. Previously pinned February and August are inventory markers, not newly acquired, and default plan attempts only ten new monthly sources. Each month expects 96 UTC 15m bars per day (2,688 leap-February / 2,784 for a 29-day month; 2,880 for a 30-day month; 2,976 for a 31-day month), exact UTC grid. Total expected year 35,136 bars including retained inventory; target new-month actual bars and raw ZIPs remain UNKNOWN until source is read.

`research_wp_r0/aql_core_f_bulk_source_v1.py::build_manifest(first,last,max_workers)` returns immutable schema `aql.core.f.bulk-source-manifest.v1`, exact expected filenames/source URLs, independently separate publisher checksum URLs, per-month bar counts, explicit UNKNOWN source SHA fields and deterministic SHA-sealed manifest; max 4 workers (default 3). Hard limits: **8,000,000 ZIP bytes and 512 checksum bytes per new month**; default 10 new months bound is 80,000,000 ZIP bytes plus 5,120 checksum bytes (network overhead excluded). Private staging/warehouse can need additional disk; allow e.g. >=3x worst-case archive total plus RAW/SQLite overhead, confirm actual free disk before transfer. Publisher terms/licence and authenticated origin must be verified by the authorized private custodian.

## F1 private acquisition only (conditional)
`acquire_private_batch` requires explicit network permission, source-rights review and independent publisher-origin confirmation; private directory must exist and be permission-restricted. It bounds parallel fetches, fetches checksum separately first, uses existing Core #226 `verify_native_month` for ZIP checksum/member/12-column/UTC/gap/census checks, fsyncs create-only originals and never writes historical OHLCV into public GitHub/CI. Existing unverified files remain `REJECTED_QUARANTINED` pending operator reconciliation (no overwrite). Network errors are returned as rejected reasons without private path leakage. **This is bounded best-effort batch execution, NOT an uninterrupted range-request resume engine:** already staged files need explicit independent reconciliation; no automatic resume of partial downloads or file reuse. A separate resumable checkpoint/partial-range transfer design remains needed if required by the private runner. Caller-supplied publisher-origin confirmation is NOT an independent signature/attestation and no 2024 publication timestamp is claimed.

## F2 batch coverage ledger and explicit scope boundary
`build_coverage_ledger` emits immutable `aql.core.f.bulk-source-coverage-ledger.v1` with `ACCEPTED_PREFLIGHT`, `REJECTED_QUARANTINED`, `MISSING_SOURCE`, `RETAINED_PREVIOUSLY_PINNED`, exact denominator and null absent parent SHAs. `ACCEPTED_PREFLIGHT` means original-format ZIP/CHECKSUM byte/checksum and native bar validation **only**; never silently `RAW_COMMITTED`, actual warehouse/#245/#253 query, strategy approval or PIT. Positive original RAW+query evidence MUST only be produced later in authorized private runner by canonical Core #211/#226/`aql_core_dual_query_identity_map_v1` and Core C/D Secretary, with separate Source ACK, research-policy approval and Factory consumer ACK. Partial/missing months remain excluded from source-dependent historical research.

**Current environment is SOURCE_ACCESS_REQUIRED:** current Project/Library accessible search and prior Core #273 inventory did not expose any new original monthly archive plus separate trusted publisher CHECKSUM bytes; no authorized private runner with verified original bytes was supplied. No network fetch or physical original-source byte admission was performed. F0 manifest and no-source F2 ledger are engineering evidence, NOT historical ingestion, policy approval or actual backtest.

## One runnable private handoff / no public source bytes

Plan only, zero network:

```bash
python -m research_wp_r0.aql_core_f_bulk_source_v1 --first 2024-01 --last 2024-12 --max-workers 3
```

Authorized private runner only, **after custodian independently confirms publisher terms, repository/runner isolation, restricted permissions and source authenticity**:

```bash
python -m research_wp_r0.aql_core_f_bulk_source_v1 --first 2024-01 --last 2024-12 --private-dir /private/aql/historical --max-workers 3 --allow-network --permission-confirmed --terms-reviewed --publisher-origin-confirmed
```

The private path is a placeholder, not a path verified as existing or mounted. The latter command has NOT been run in this session. Quarantined/checkpoint state needs operator review prior to retry. No source checksum/ZIP evidence may be manufactured. No separate per-month Audit; Factory leads one exact pinned final batch F gate after genuine source admission + independent research-only NON_PIT policy approval. G0, holdout, operational Paper/trading and PR merge remain prohibited.
