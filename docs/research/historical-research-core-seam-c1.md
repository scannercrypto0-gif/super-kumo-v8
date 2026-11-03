# AQL Historical Research Vertical Slice — Core Seam C1 (provisional)

Status: CONTRACT_CANDIDATE / OFFLINE_ONLY / NOT_INTEGRATED. Owner's bounded assignment: [Core #180/6605483327](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/180#issuecomment-6605483327). This document is **not** evidence that C2–C4 passed.

## Existing API inventory and ownership

- Core-owned bridge: `research_wp_r0/aql_archive_custody_bridge_v1.py` on Draft #226; `export_existing_archive_backup`, optional `export_existing_raw_vault`, `OfflineBridgeStager.stage/advance/commit/replay_committed`, and `custody_range`. Preserve G1–G6 and existing packet schema.
- Existing library: `research_wp_r0/historical_library.py`, `HistoricalLibrary.register/range_query` and `CustodyAccessor`; **read-only consumer** boundary. No modifications to library or storage ownership.
- Archive: `src/aql/archive/offline.py` sealed snapshot. RAW Vault #211 is **Draft/unmerged**, optional and not an implicit dependency on main.
- P2 Core #221, Factory #222 and Work #228 are independent Drafts. No cross-branch imports or writes without owner approval.
- The in-memory HistoricalLibrary is **not** durable independent custody; local staged recovery is not a production custody attestation.

## Frozen candidate request semantics

`custody_range(library, dataset_id, start_ms, end_exclusive_ms, decision_cutoff_ms, *, version=None, require_complete=True, confirmed_only=False)`

- All times UTC epoch milliseconds. Range is half-open `[start_ms,end_exclusive_ms)`, aligned to native bar width and bounded by MAX_BARS (4096).
- `decision_cutoff_ms` excludes future/unavailable bars; never use query end as proof of historical availability.
- Explicit dataset version is preferred. `version=None` resolves current registered version and **must not be represented as an immutable pinned version until the response is recorded**.
- `require_complete=True` fails closed; `False` allows `COMPLETE`, `PARTIAL`, or `UNKNOWN` with `missing_bar_opens`.
- `confirmed_only=True` rejects retrospective records; no conversion of archive receipt, derived cutoff, or synthetic fixture into prospective PIT.
- Response schema already implemented: `aql.bridge.custody-range.v1`; includes dataset/version, manifest integrity hash, source byte hash, cutoff, counts, missing opens, availability class, source confidence and bar checksums. This is a **data/query** response, not a signal or trade.
- Errors currently surface as `BridgeError(code)` / existing `HistoricalDataError`; a typed external error envelope is **not yet frozen or implemented**. Do not claim stable cross-owner error transport until C2 explicitly wraps and tests it.

## Typed examples (illustrative, NOT authentic market evidence)

Request:
```json
{"dataset_id":"TEST_BTCUSDT_15m","version":1,"start_ms":0,"end_exclusive_ms":900000,"decision_cutoff_ms":900000,"require_complete":false,"confirmed_only":false}
```

Response shape (example only; hash fields are deliberately omitted rather than fabricated):
```json
{"schema":"aql.bridge.custody-range.v1","dataset_id":"TEST_BTCUSDT_15m","version":1,"decision_cutoff_ms":900000,"status":"UNKNOWN","available_bar_count":0,"required_bar_count":1,"missing_bar_opens":[0],"availability_class":"RETROSPECTIVE_NOT_PIT","source_confidence":"LOCAL_CHECKSUM_AND_PIN_ONLY","bars":[],"research_evaluation":"NOT_PERFORMED"}
```
The actual function also supplies `manifest_integrity_sha256` and `source_bytes_sha256`; consumers must validate the full actual response and not treat this shortened example as a valid wire receipt.

## C2–C4 acceptance criteria / no duplicate G6

C2: add **only** a versioned external read-only adapter and typed error envelope if existing API is insufficient; retain underlying source hashes, lineage, coverage and idempotent resume. Never rewrite archive/ingestion/Factory/Work.
C3: adversarial checks for forged manifest/source hash, future cutoff, missing grid, correction conflict, duplicate source, interrupted resume and stale/altered packet; reuse already-proven G6 cases where unchanged.
C4: ONE consolidated deterministic TEST_ONLY archive → Bridge → HistoricalLibrary → research query gate, exact-HEAD CI and independent evidence links. Synthetic success does not prove authentic private historical operation.
Stop and propose a minimal patch instead of editing any cross-owner path.

## Activation guard

No main merge, G0, real-history execution, holdout access, trading, automatic live integration or custody/PIT promotion. The owner must separately authorize any activation.
