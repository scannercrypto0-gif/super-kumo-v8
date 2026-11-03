# AQL-HISTORICAL-ARCHIVE-CUSTODY-BRIDGE-001 — isolated OFFLINE V1

**Status: NOT_INTEGRATED / NOT_AUDIT_ACCEPTED / DRAFT.**
This package has NO production scheduler, live market feed, orders, new warehouse,
G0 approval or automatic P2 / Scanner / Factory connection. It cannot establish
independent issuer custody or prospective point-in-time market availability.

## Collision guard / interfaces reviewed before implementation

| Owner | Existing API | Bridge decision |
|---|---|---|
| Core main `src/aql/archive/offline.py` | `snapshot(root, expected_digest, symbol, interval, start_ms, end_ms)` verifies sealed backup and returns canonical query JSON | Read-only source via `export_existing_archive_backup` |
| Core main `src/aql/archive/contracts.py` | `aql.offline-archive-query.v1`, `aql.market-archive.v1` and original journal receipt/derived availability fields | Verify exact source/record/envelope SHA and timestamp truth; never claim CONFIRMED |
| Core main `research_wp_r0/historical_library.py` | `HistoricalLibrary.register`, `DatasetManifest`, `range_query`, `CustodyAccessor` | Use existing validated versioned library, not a replacement warehouse |
| Draft #211, RAW Vault (UNMERGED) | `RawVault.read`, `manifest_entries`, `raw_object.v1`, original object SHA | Optional duck-typed, read-only `RAW_CSV` adapter when that installed branch is available; do NOT import or merge #211 |
| Drafts #221/#222/#223 | P2 policy/Factory/private Work | NO edits, NO run, no producer backfill and NO P2 data copied |
| `src/aql/storage/operational_store.py` and journal | live operational/store receipt | Not modified or imported as custody evidence |

**One writer:** independent Draft branch `aql/historical-archive-custody-bridge-offline-20261103`. Changed files only inside new bridge module, its tests, dedicated focused CI workflow and this guide.

## G1–G5 cohesive implementation

1. **G1 Immutable packet contract.** `aql.archive-custody.offline-packet.v1` is exact canonical JSON. It binds the original raw source-object SHA, scope, symbol/interval, UTC millisecond half-open range, source inventory/RAW Vault identity, per-bar checksums and original archive journal references. Both original receipt and ingest timestamp are preserved where actually present. A recorded journal `ingested_at` is NOT proof of source publication or actual availability. The bridge always tags converted bars **RETROSPECTIVE** (or **SYNTHETIC_TEST** for explicit fixtures); never CONFIRMED.
2. **G2 Existing source adapter.** `export_existing_archive_backup` calls the existing validated offline snapshot, refusing incomplete source grids and mismatched record/object/manifest hashes, bar finality, OHLCV, duplicates and future/invalid recorded ingestion. `export_existing_raw_vault` only reads existing `read()/manifest_entries()` and can parse verified `RAW_CSV` bytes; ZIP_CSV and unknown formats STOP instead of guessing. Direct `export_archive_query` / `export_vault_csv` demand exact caller-supplied raw SHA and are **pin verification only**, not independent custody evidence.
3. **G3 Staged importer.** `OfflineBridgeStager(root).stage(packet,raw)` creates source and packet files with content-addressed immutable paths. `advance(key,batch_size=64)` verifies bounded chunks and fsync/atomic-checkpoints progress. `commit(key, HistoricalLibrary())` waits for complete checkpoint then calls existing registration **once** after full packet replay and quality verification. A crash after registering but before receipt can be retried idempotently.
4. **G4 Correction/idempotency.** The exact existing `dataset_id,version` is idempotent only if source SHA, manifest integrity SHA and every stored bar checksum match. Different bytes at same version STOP; version N>1 requires previously registered N−1 matching `parent_source_sha256` and explicit reason. No overwrite. `replay_committed(library)` explicitly rehydrates an in-memory library after process restart from locally retained files. This is NOT an automatic or independently durable production custody service.
5. **G5 Research query boundary.** `custody_range(library,dataset_id,start,end_exclusive,decision_cutoff,...)` uses the existing `HistoricalLibrary.range_query` or `CustodyAccessor`. It returns COMPLETE / PARTIAL / UNKNOWN with precise missing native bar opens, source SHA, dataset version and immutable manifest digest. Default completeness fails closed. `confirmed_only=True` rejects archived retrospective records, even if source receipts are present.

**Timing interpretation:** exported packet `spec.as_of_ms` is an operator-supplied snapshot upper bound; `DatasetManifest.created_at_ms` uses this pinned bound for deterministic in-memory metadata, NOT evidence of actual registration wall-clock. Original source recorded ingest/commit fields are retained separately; UNKNOWN remains UNKNOWN. No theoretical close+1 is promoted to a confirmed receipt.

## G6 one consolidated offline gate

Run against the exact branch commit (no external data download):

```sh
PYTHONPATH=. python -m unittest discover -s tests -p 'test_aql_archive_custody_bridge_v1.py' -v
```

Dedicated workflow: `.github/workflows/aql-archive-custody-bridge-focused.yml`.
Synthetic chain: canonical archive journal evidence → verified byte-pinned packet → immutable bounded staging → interrupted/resumed checkpoint → single HistoricalLibrary register → read-only cutoff range. Additional negative cases: tampered source, wrong inventory, scope, future receipt, non-final, gap, corrected-version conflict, altered packet/manifest, checkpoint corruption, synthetic promotion attempt, vault unsupported format.

The fixture has **zero real original Binance/Work/owner-private bars**. Any deterministic hash generated by it proves only synthetic-code repeatability; no synthetic artifact can be labeled as authentic market evidence.

## Pending activation / critical stop

Build can proceed while owner handles independent P2 Audit. This bridge **must not be integrated** with Core live capture, HistoricalLibrary production consumers, Factory, Scanner or Vault writers until owner explicitly authorizes integration AFTER the independent P2 audit gate. A new consumer/shared file change requires a separate minimal-delta proposal, never hidden edits on existing Draft PR branches.

No merge, G0, live or paper trading, sealed holdout, production schedule, unbounded ingestion, private-source copy or scientific/custody approval. Known limitations: destination `HistoricalLibrary` is in-memory; on-process restart needs explicit rehydration and external operational authorization; bounded 4096-bar/8 MB per packet, RAW_VAULT supports only `RAW_CSV`; external issuer custody and source publication chronology are NOT ATTESTED.
