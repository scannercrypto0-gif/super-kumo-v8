# Core DEV historical source adapter v1 — Issue #149

Engineering contract only, pending independent Council S/R. No source dataset,
strategy execution, empirical PIT or OOS authorization is delivered by this PR.

## Base and reuse

New isolated branch from main `dbc191df72f4b4d1ebb7d490926dcad4325dac12`.
No commits from unmerged #144/#143/#142/#137 are imported. Existing Factory,
HistoricalLibrary and bridge files/serialization are unchanged.

| Inspected contract on pinned main | Reuse / remaining gap |
|---|---|
| `historical_library.py:HistoricalBar`, `validate_bars`, `DatasetManifest` | Reuse finite positive OHLC, nonnegative V, checksum, ordered final bars, correct close, immutable manifest. Add bounded exact declared grid before validation. |
| `historical_library.py:import_fixture_csv` | Keep seven-column API unchanged. New Core port hashes and parses a single bounded byte snapshot with exact format versions. |
| `retrospective_kline_intake.py:inspect_binance_spot_zip` | Existing read-only BTCUSDT/1m path parser inspected; it already handles retrospective ZIP quality. New byte-oriented port adds envelope, exact member/coverage/size and narrower explicitly millisecond-only format; does not change its microsecond support or outputs. No second market quality campaign. |
| `HistoricalLibrary.correct` / manifest version | Local version is not issuer correction ancestry. New schema keeps issuer version and correction UNKNOWN; unsupported asserted correction selection is refused. |
| `CustodyAccessor` / `historical_evaluation_bridge.prepare_inputs` | Continue requiring confirmed timing/receipt. DEV import remains RETROSPECTIVE with ingest=None; no adapter to bypass these gates. |
| Existing immutable manifests | Reuse bar/manifest integrity; bind exact compressed-byte SHA. Runtime hash consistency is not independent custody. |

`core-dev-source-1` is a small implemented import schema, **not** a silent
implementation of the larger Work #147 proposed schema. Its flat fields map
origin/market/symbol/interval/coverage, exact archive identity and opaque artifact
reference. Work147 receipt/licensing/attestation metadata remains in its source
record and Work152 issued receipt; it is not fabricated by the importer.
`source_id=dev1:SHA256(canonical_envelope)` identifies this entire import contract;
it differs intentionally from Work147's logical publisher/day source_id.
`archive_sha256` identifies compressed payload version independently. Changing
metadata, reference, range, parser or bytes yields a new commitment; never edit
an already retained envelope in place.

## Usage (repository checkout, Python 3.11+)

Run with repository root AND `src` on PYTHONPATH (the reused research package is
not packaged in the installed aql wheel). No installation or network is needed
beyond the normal test dependencies. Import performs no file writes.

```python
import json
from pathlib import Path
from aql.historical.dev_source import DevSourceEnvelope, import_local

envelope = DevSourceEnvelope(json.loads(Path("envelope.json").read_text()))
# Caller explicitly resolves the pinned reference using existing authorized access.
# This function never downloads bytes_ref or assumes the referenced object exists.
history = import_local(envelope, "/authorized/read-only/exact-version.zip")
prefix = history.range_query(1704067200000, 1704067260000, 1704067260000)
receipt = history.receipt  # in memory; caller retains separately if authorized
```

Fail categories: SCHEMA (unsupported/missing contract), DATA_AVAILABILITY
(MISSING_BYTES/unreadable), SOURCE_INTEGRITY (hash/size), SOURCE_QUALITY
(malformed/duplicate/unordered/gapped/off-grid/bad close/nonfinite/OHLCV), LOOKAHEAD
(requested DEV bar not yet closed), PIT_QUALIFICATION (stronger claim rejected).
No sorting, interpolation, deduplication, adjustment or auto-refresh-to-latest.
Bounds: 16 MiB compressed and expanded input, 100,000 bars, exact flat ZIP member,
UTC-aligned full range; supported intervals are 1m/5m/15m/1h/1d. Binance format v1
accepts 12 headerless columns with millisecond times only, uses OHLC/base volume,
does not validate quote/trade-count columns as market microstructure evidence.
Canonical CSV v1 uses exactly seven fields open_ms,close_ms,O,H,L,C,V; stream
identity comes from caller envelope, not an identity column in those bytes.
Binance ZIP member additionally must match the declared instrument/interval.
No filesystem extraction; source reference and hash remain caller assertions
until measured byte comparison, and hash alone does not authenticate publisher.

Normalization uses Python float64 and existing HistoricalBar checksums; normalized
seven-field JSON digest is separate from compressed archive SHA and legacy
manifest digest. `created_at_ms=0` is a documented deterministic UNRECORDED
manifest sentinel, **not** an actual creation/ingestion/publication timestamp.
`version=1` is local manifest-format version, never issuer-original assertion.
All bars have RETROSPECTIVE availability and unknown ingestion. Closed-bar cutoff
is only a DEV causality lower bound; revisions might have appeared later. Neither
prefix access nor a quality receipt proves historical issuer as-of availability.

## Illustrative Work146 source (not a locally verified import)

```json
{
  "schema": "core-dev-source-1",
  "scope": "DEV_ONLY",
  "origin": "BINANCE_VISION",
  "market": "SPOT",
  "symbol": "BTCUSDT",
  "interval": "1m",
  "start_ms": 1704067200000,
  "end_ms_exclusive": 1704153600000,
  "bytes_ref": "chatgpt-library:file_00000000084c8208b5d65c8fc803426c:version0",
  "archive_sha256": "4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e",
  "archive_size": 68923,
  "format": "binance-spot-zip-12-ms-v1",
  "member": "BTCUSDT-1m-2024-01-01.csv",
  "checksum_provenance": "SAME_PUBLISHER_REPORTED",
  "normalization": "ohlcv-ms-float64-grid-1",
  "source_version": "UNKNOWN",
  "correction_status": "UNKNOWN",
  "issuer_first_available_at": "UNKNOWN",
  "bounded_UTC": "UNKNOWN",
  "independent_custody": "UNKNOWN"
}
```

**MISSING_BYTES_IN_THIS_CODEX_ENVIRONMENT / CONSUMER_ACCESS_NOT_VERIFIED.** This
example is metadata, not a delivered/readable dataset or an issued import receipt.
The 1,440-bar count and earlier quality checks are Work146 observations, not tests
performed by this PR. No market bytes are downloaded/committed/redistributed here.

Continuity correction: Work147 result6470454981 now exists (initial149 start note
predated its readback). Work152 result6470687502 subsequently retained an actual
owner-controlled Library ZIP and separately issued receipt, with exact-version
readback hash verified in that Work environment. This supersedes global claims
of no retained archive; it does NOT establish access from this Codex checkout.
Library object backing file/version above is a reported immutable-version
reference, not proof of WORM or independently controlled custody. Work152 receipt
SHA is ffce2bbe7890414d84360be80a0ac478795ae8d1a28085f8bb34075faca83386.
Its seven-tuple normalized digest aa740790922df44afb50059f5816771bfe97e0316f7eea6657ad5400c5585008
was measured with Python3.12.14 and the pinned old parser. No equality claim is
made here without those actual bytes. Caller must independently verify exact
archive hash/size and declared serializer before issuing consumer ACK.

Source references: [Work146](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/146#issuecomment-6469407856),
[Work147](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/147#issuecomment-6470454981),
[Work152](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/152#issuecomment-6470687502).
Publisher/checksum URLs are origin locators in those receipts, not immutable
handoff locations. Recorded research licensing assumption: Binance Vision
CC BY-NC-SA4.0, personal noncommercial nonproduction use with attribution;
owner must assess actual use, no commercial rights inferred here.

## Handoff and pending independent acceptance

Core output is immutable envelope + tuple of existing HistoricalBars + existing
manifest + deterministic in-memory receipt. Factory may later consume this
separate DEV port after owner/Council review; no bridge to existing confirmed/PIT
input preparation or real-PnL executor is installed. Scope/receipt flags remain
DEV_ONLY, verified_source_timing=false, real_pit_accepted=false,
empirical_eligible=false. OOS/PAPER/LIVE, source acquisition and actual strategy
execution are not authorized by this interface.

BLOCKS_DEV_NOW: recipient-specific byte access/ACK; Core/Factory agreement on this
versioned contract; independent Council S (rejects/integrity/legacy isolation)
and R (retrospective interpretation/correction uncertainty). Work148 now delivered
Factory exit code at dee0f088; this PR does not import or accept it. Work150 owns
its separate quality/provenance interface; no overlapping Factory edits here.
BLOCKS_PIT_LATER: authenticated per-vintage original/correction first-known,
finite independent UTC evidence and independently immutable custody/anchor.
DEFERRED: Guardian operational HOLD/ACL controls, extra strategies, broad CI/E2E.
Do not equate local import, publisher checksum, Library version, Drive ACK or
archive close time with issuer publication proof. No empirical claim follows.

Focused reproducibility command:
`python -B -m pytest tests/test_core_dev_source.py tests/test_sf_data_01.py tests/test_sf_research_int_01.py -q --tb=short`
Use the configured PYTHONPATH above. Tests use synthetic CSV/ZIP only. The latter
two suites verify unchanged public library/bridge contracts. No Guardian or
strategy PnL run; no broad CI rerun required. Keep Draft pending independent S/R.
