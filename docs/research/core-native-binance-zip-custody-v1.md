# Core #245 — Native original Binance ZIP → immutable custody → OHLCV query V1

**Scope:** owner-provisionally approved option B, Core Draft PR #226. Historical research only, no G0, Paper, live exchange, holdout or merge. Original retained 2024 bytes were observed **only inside Work's authorized environment**; they were **not available for execution in this Core session**. Do not describe the TEST_ONLY gate as real-source acceptance.

## Source of truth / existing dependencies

- Core #226 previously supported `SEALED_ARCHIVE_QUERY` and `RAW_VAULT_CSV` only. Work #239 / Draft #242 proved that retained February and August 2024 **original Binance Spot BTCUSDT 15m ZIP** archives existed in Work's authorized environment, but these were **rejected `UNSUPPORTED_ORIGINAL_SOURCE`** by Core.
- Existing Core Bridge `OfflineBridgeStager`, `HistoricalLibrary`, versioned correction logic, and `query_custody` are reused. No second archive engine, fake source, venue download or new scientific evaluator.
- Existing pin `aql.core.external-original-byte-pin.v1` remains backwards compatible. For new `source_kind=`**`BINANCE_KLINES_ZIP`**, exactly four additional required pin fields are `archive_name,csv_member_name,csv_member_sha256,checksum_file_sha256`. ZIP `original_sha256` must be pinned from retained original ZIP bytes; CHECKSUM must be supplied as **original unmodified ASCII bytes** via the optional `checksum_file_bytes` call keyword. The CHECKSUM file's byte SHA is separately pinned, and its one checksum assertion must exactly match the ZIP hash and declared archive basename.
- The original ZIP is the immutable staged **source** object. The embedded native CSV is SHA-pinned and parsed with exactly **12 original Binance klines columns**; it is NOT relabelled or stored as a seven-column original. Source `packet.source_meta` seals original ZIP SHA, native CSV member SHA, original CHECKSUM file SHA and exact original ASCII CHECKSUM text. Each `packet.origin_lineage[]` pins ZIP/member/CHECKSUM SHA, original line index and original market close, with `historical_known_at_ms=null` and `source_publish_ms=null`.
- Offline archive `spec` fields remain unchanged: `dataset_id,version,symbol,interval,exchange,market,source_label,start_ms,end_exclusive_ms,as_of_ms,parent_source_sha256,correction_reason,test_only`; one packet is bounded to at most **4096 native bars** and original ZIP **8MB**. For the 2024 BTCUSDT-15m monthly files Work reported 2784 and 2976 bars (inside this bound). Valid monthly basename is `{symbol}-{interval}-{YYYY-MM}.zip` and its single CSV member has matching `.csv` basename. Every row must have exact grid open/close, finite valid OHLCV, nonnegative quote/taker volumes and native trade count; no gaps, out-of-order rows, duplicates, unknown extra members, encrypted files, path traversal, symlinks, unsupported ZIP compression or oversized/zip-bomb payloads. Python ZipFile read verifies per-member CRC.
- `export_binance_native_zip` added to the **existing** `research_wp_r0.aql_archive_custody_bridge_v1` API (not a new production storage path). `research_wp_r0.aql_authenticated_historical_admission_v1.admit_original_bytes(..., checksum_file_bytes=original_checksum_bytes)` selects it and returns `aql.core.historical-original-admission.v1`: original ZIP `source_bytes_sha256`, CSV `native_csv_member_sha256`, CHECKSUM `native_checksum_file_sha256`, sealed Bridge packet/registration/manifest pins, dataset/version/correction lineage, cutoff, coverage and missing opens. Unsupported missing checksum fails closed.
- New `research_wp_r0.aql_native_price_custody_query_v1.query_price_custody(library,query_request,expected_source_sha256=...,expected_manifest_integrity_sha256=...)` is **read-only**. Takes unchanged `aql.core-research.custody-query.v1` request (explicit version/half-open UTC ms cutoff) and emits `aql.core.historical-price-custody-query.v1` with original source/manifest hashes, existing Core `COMPLETE/PARTIAL/UNKNOWN` coverage/missing opens, immutable SHA per bar, price-bearing `bar_open_ms,bar_close_ms,open,high,low,close,volume` and derived `observation_lower_bound_ms`. It independently cross-checks the existing Core query and stored HistoricalLibrary bars/manifest; mismatched pins, bar tamper, confirmed-only, or altered time/scope are errors. Stored numeric representation is the existing HistoricalLibrary **Python float projection** from the source's original decimal strings; consumers requiring exact native decimal precision must re-read the pinned original ZIP, not invent precision from floats.

## Reproducible call shape (authorized source bytes supplied by Work, NOT on GitHub)

```python
# Precondition: Core adapter is run inside an owner-authorized, offline source
# environment with retained original ZIP and original companion CHECKSUM bytes.
# The expected values below MUST be copied from a separately trusted manifest.
from research_wp_r0.aql_authenticated_historical_admission_v1 import (
    admit_original_bytes, PIN_SCHEMA,
)
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
# zip_bytes and checksum_bytes are ORIGINAL file bytes, not pasted here.
pin = {
    "schema": PIN_SCHEMA, "source_kind": "BINANCE_KLINES_ZIP",
    "original_object_id": "RETAINED_BTCUSDT_15m_2024_02",
    "original_sha256": "<TRUSTED_PRIOR_ZIP_SHA256>",
    "provenance_reference": "RETAINED_OWNER_RESEARCH_OBSERVATION",
    "captured_at_ms": None, "claimed_available_at_ms": None,
    "expected_inventory_sha256": None, "vault_object_metadata": None,
    "universe_manifest_sha256": None, "universe_member_count": None,
    "test_only": False,
    "archive_name": "BTCUSDT-15m-2024-02.zip",
    "csv_member_name": "BTCUSDT-15m-2024-02.csv",
    "csv_member_sha256": "<TRUSTED_PRIOR_CSV_MEMBER_SHA256>",
    "checksum_file_sha256": "<TRUSTED_PRIOR_CHECKSUM_FILE_SHA256>",
}
# spec = original Core Bridge 13-field dataset/version/range specification;
# never use a TEST_ONLY source as real or backdate captured/known-at timestamps.
admission = admit_original_bytes(
    zip_bytes, pin, spec, stager=existing_bridge_stager,
    library=existing_historical_library, decision_cutoff_ms=cutoff_ms,
    checksum_file_bytes=checksum_bytes,
)
request = {
    "schema": REQUEST_SCHEMA, "dataset_id": spec["dataset_id"],
    "version": spec["version"],
    "start_ms": spec["start_ms"],
    "end_exclusive_ms": spec["end_exclusive_ms"],
    "decision_cutoff_ms": cutoff_ms,
    "require_complete": True, "confirmed_only": False,
}
prices = query_price_custody(
    existing_historical_library, request,
    expected_source_sha256=admission["source_bytes_sha256"],
    expected_manifest_integrity_sha256=admission["manifest_integrity_sha256"],
)
assert prices["status"] == "OK"
assert prices["coverage"] == "COMPLETE"
assert prices["scientific_pit"] == "NOT_ATTESTED"
```

**Important:** this call can prove `original ZIP bytes == externally pinned original SHA`, that the separately retained CHECKSUM bytes assert that ZIP SHA, and that the original member, in-memory bar projection and price grid are consistently linked. It **cannot authenticate venue issuance**, independently verify publication time at any 2024 decision clock, or prove that a 2026-captured monthly ZIP was historically available in 2024. `Captured_at_ms`/`claimed_available_at_ms` are untrusted claims and **never used to promote PIT**. The native `close_time+1` is a theoretical earliest observation bound; all reconstructed HistoricalBars remain `RETROSPECTIVE`, never `CONFIRMED`. The complete single-symbol monthly grid is **not a complete market universe, nomination/attempt census or trial denominator**. Product scientific eligibility remains BLOCKED until separate independently accepted provenance/chronology, strategy rule-trigger evaluation and Factory audit. `confirmed_only=True` intentionally rejects these historic bars.

## Exact Work / Factory contract and blockers

**Work #239 / PR #242:** existing retained ZIP and CHECKSUM bytes must be accessed only in its authorized offline source environment; call new Core native adapter with the **already-recorded immutable ZIP/member/CHECKSUM SHA pins**. Retain original source ZIP, original CHECKSUM content, no 7-column fake normalization. After `admit_original_bytes`, issue `query_price_custody` with explicit version/cutoff/source/manifest pins. Check archived price OHLCV and coverage against original member. If the retained bytes are not accessible in a particular worker, output `SOURCE_NOT_AVAILABLE`; do not copy private bytes to repo/CI. Existing Work #242 TEST_ONLY gate must not be retroactively called authentic E2E.

**Factory #238 / PR #241:** `price_query` returns price-bearing historical data, but only with **`RETROSPECTIVE_NON_PIT / scientific_pit=NOT_ATTESTED`**. It is **not** a source-qualified native strategy rule-trigger output, not an evaluator result or genuine BASE/SHADOW denominator. Factory must independently pin strategy/version/source/manifest/cutoff and refuse lookahead, unknown original availability, partial grid, missing trial/arm census or any false PIT classification. Current Factory preflight remains `INSUFFICIENT_EVIDENCE`.

**Independent Audit #240:** review raw-archived source chronology/correction evidence separately; no signed issuer provenance, historic captured-at or independent known-at guarantee has been created here.

## Consolidated regression gate and source access truth

`tests/test_aql_native_binance_zip_v1.py` performs **10 native synthetic ZIP/CSV/CHECKSUM cases** including whole ZIP and member SHA tamper, checksum assertion, unknown/extra ZIP entries, path traversal, grid gaps/12-column mismatch, future timestamps, price snapshots and cutoff, wrong price manifest, source correction, immutable replay and explicit no-PIT authority. Scope adds to existing **45** focused tests for one Core total **55**, run using `.github/workflows/aql-core-research-vertical-slice-focused.yml` at exact HEAD. **Only the TEST_ONLY fixture is in CI.**

**Status:** implemented and TEST_ONLY CI verified when linked by the issue comment. Authentic retained Feb/Aug ZIP bytes were independently observed by Work with source fingerprints at #239/6625215851; this Core session did **not** access or execute those bytes. Correct status: `SOURCE_AVAILABLE_IN_WORK_ONLY / CORE_AUTHENTIC_RUN_NOT_PERFORMED / PIT_NOT_ATTESTED / FACTORY_SCIENTIFIC_NOT_CONNECTED`. No GitHub published prices or private file locator; no merge, G0, holdout or trading.
