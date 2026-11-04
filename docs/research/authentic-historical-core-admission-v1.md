# Core #237 — original historical source admission, custody and PIT evidence boundary

**Status: implemented isolated Core admission contract; authentic original bytes NOT_AVAILABLE / NOT_CONNECTED in this execution; no real PIT or scientific admission asserted.** Owner decision A provisionally prioritizes **authentic original historical data → Discoverer → Factory** over Paper/live activation. G0 pending. This is an additive implementation on existing Core Draft #226, not a new data engine.

## Actual source access inventory, 2026-11-04

- The connected GitHub main tree contains Core archive/custody *code*, data contracts, tests and tiny synthetic fixtures; it does not expose authenticated original historical market byte archives or their independent original publication/receipt proof. GitHub PR #223 public intake claims cannot substitute for accessing and verifying the actual bytes; #211 Vault remains a separate unmerged Draft.
- Current Project Files content searches for retained original historical data were empty twice. This is **not proof** private files do not exist in an inaccessible Work environment: no private original bytes were accessed/read here. No credentials, URLs or assumed private archive paths were invented.
- **Observed verdict for authentic data:** `SOURCE_NOT_AVAILABLE`. This code uses only explicitly supplied already-retained bytes; it does NOT download from Binance, activate exchange endpoints or demand owner reupload.

## Reuse / ownership / semantics

Existing Core APIs (unchanged):
- `research_wp_r0.aql_archive_custody_bridge_v1.export_archive_query` and `export_vault_csv`: exact original-byte SHA, source inventory, scope, finality/geometry/duplicates/lineage and explicit retrospective trust.
- `verify_packet`, `OfflineBridgeStager.stage/advance/commit/replay_committed`: canonical packet reconstitution, immutable staged source/packet, bounded fsynced checkpoint, idempotent versioned registration, explicit corrected-version parent source SHA.
- `HistoricalLibrary` and `query_custody`: immutable dataset/version/manifest/hash, read-only half-open UTC epoch-ms range, `COMPLETE|PARTIAL|UNKNOWN` and exact missing opens. `confirmed_only=True` always refuses retrospective bars.
- New Core-only `research_wp_r0.aql_authenticated_historical_admission_v1.admit_original_bytes` accepts existing original bytes, externally pinned `aql.core.external-original-byte-pin.v1` and an existing Bridge stager/library. New canonical output `aql.core.historical-original-admission.v1` seals source SHA, packet SHA, custody receipt SHA, manifest SHA, dataset/version/correction parent, cutoff, missing grid and query. No Factory, Discoverer, Work or Scanner imports.

External source-pin schema fields (exact):
`schema,source_kind,original_object_id,original_sha256,provenance_reference,captured_at_ms,claimed_available_at_ms,expected_inventory_sha256,vault_object_metadata,universe_manifest_sha256,universe_member_count,test_only`.
`source_kind` is `SEALED_ARCHIVE_QUERY` or `RAW_VAULT_CSV`. `captured_at_ms` and `claimed_available_at_ms` may be null to preserve uncertainty. The hash must be independently pinned BEFORE reading the source, not computed from the same untrusted source inside the caller and called authenticated. A `provenance_reference` is **an unverified claim**, not a signature or trust grant. Caller owns proof of lawful access, source attribution, capture chronology, original vendor publication availability, market universe inventory and any independent attestation.

## Example: a bounded TEST_ONLY synthetic source — not original market data

From the repository's existing `tests/test_aql_archive_custody_bridge_v1.py` fixture only:
```python
from tempfile import TemporaryDirectory
from research_wp_r0.aql_authenticated_historical_admission_v1 import (
    PIN_SCHEMA, admit_original_bytes,
)
from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager, raw_sha
from research_wp_r0.historical_library import HistoricalLibrary
from test_aql_archive_custody_bridge_v1 import archive_payload, spec, H, START, N, WIDTH
raw = archive_payload()
source_pin = {
    "schema": PIN_SCHEMA, "source_kind": "SEALED_ARCHIVE_QUERY",
    "original_object_id": "TEST_ARCHIVE_0001",
    "original_sha256": raw_sha(raw),  # test only: NOT an independent original anchor
    "provenance_reference": "TEST_ONLY_UNVERIFIED",
    "captured_at_ms": START+N*WIDTH+10000,
    "claimed_available_at_ms": None,
    "expected_inventory_sha256": H,
    "vault_object_metadata": None,
    "universe_manifest_sha256": None,
    "universe_member_count": None,
    "test_only": True,
}
with TemporaryDirectory() as stage_path:
    result = admit_original_bytes(
        raw, source_pin, spec(), stager=OfflineBridgeStager(stage_path),
        library=HistoricalLibrary(), decision_cutoff_ms=START+N*WIDTH+2000,
    )
    assert result["coverage"] == "COMPLETE"
    assert result["confirmed_pit"] == "NOT_ATTESTED"
    assert result["factory_scientific_input"] == "BLOCKED"
```

If original bytes are missing, calling with `source_bytes=None` returns `SOURCE_NOT_AVAILABLE`, never a synthetic substitute. Given bytes with a matching external pin, the code verifies **local byte identity/integrity** and original format and can stage/query existing custody, but returns `ORIGINAL_PIN_MATCHED_PROVENANCE_PENDING` for a non-test source. This is NOT `AUTHENTICATED`: independent attestation and exact decision-time availability remain `NOT_ATTESTED`. The complete requested candle grid does **not** prove complete market-symbol universe/scan denominator. A claimed capture time is not a verified historical publication timestamp.

## Critical trust boundary: no false PIT

- Existing archive envelopes record source journal ingestion/receipt proxies and `DERIVED_LOWER_BOUND_NOT_CONFIRMED`. Neither `source_availability_at_cutoff` nor actual venue publication latency is independently proven.
- The existing Bridge represents imported archives with `DataAvailabilityKind.RETROSPECTIVE`; it cannot lawfully set `CONFIRMED` without separate independently verified source receipt evidence. Caller-supplied `claimed_available_at_ms` is checked for contradictions, NEVER upgraded to a verified PIT receipt.
- `require_complete=True` remains the query's strict fail-closed policy for scientific consumers. The admission wrapper queries with `require_complete=False` solely to report precise `PARTIAL/UNKNOWN` missing-grid evidence. Downstream Factory/Work must reject those as eligible scientific attempts and account for all missing members; the wrapper outputs `factory_scientific_input=BLOCKED` even when synthetic complete.
- A source pin matching its bytes proves that those two inputs match, **not** that independent external custody, historical publication availability or origin authenticity has been established. Mislabeling a `spec.test_only=False` fixture is not proof of real data; a separate independent source attestation is mandatory.

## Hand-off to Work #239 and Factory #238

When owner-authorized retained original bytes and independently trusted anchors become accessible, callers must pass: (a) exact original bytes, externally trusted prior SHA, source/vendor identity and legal-access proof; (b) original capture/available chronology with independent evidence or explicit UNKNOWN; (c) source `dataset_id,version,symbol,interval,start_ms,end_exclusive_ms,as_of_ms,parent_source_sha256,correction_reason`; (d) market universe/coverage denominator from an independently validated catalog; (e) existing immutable-stage root and `HistoricalLibrary` receiver.

Core returns exact `aql.core.historical-original-admission.v1` manifest and nested `aql.core-research.custody-query-result.v1`. Work/Factory must independently verify source checksum, manifest, provenance and cutoff; they must **not** convert Core's retrospective trust class into `CONFIRMED` or infer `PIT_PASS` from a complete historical grid. Their authentic E2E remains `AUTHENTIC_NOT_CONNECTED` until source and external trust are verified and the separate Audit scope is approved.

**Out of scope:** no new acquisition, storage system, script to fake vendor metadata, scientific Factory evaluator, strategy promotion, sealed holdout, Paper consumer, live trading, G0 or PR merge. No modifications to Factory#229, Work#228/#235, Discoverer#230 or Scanner#227.
