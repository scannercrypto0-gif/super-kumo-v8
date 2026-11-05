# Core Package E — historical source boundary delta (provisional)

Parent: #266. Core task: #264/6654461630. Based on Core D #264 a86a590a5e2c32c18e03522f52896dbcf50c60ff; all upstream PRs remain unmerged.

## New code scope
- `aql_core_e_historical_boundary_v1.py`: SHA-sealed local original-ZIP preflight with explicit publisher-checksum input; absent source, invalid checksum, mismatched bytes and synthetic source fail closed.
- `tests/test_aql_core_e_historical_boundary_v1.py`: positive fixture and negative/tamper/unknown-timeframe tests.
- `aql-core-e-historical-boundary.yml`: Python 3.11/3.12/3.13 focused gate.

## Critical limitations
A caller-supplied checksum is NOT independently verified as publisher-authentic by this helper. The caller/custodian MUST separately authenticate publisher origin and ZIP naming/dataset identity before treating the preflight as an original-source admission. The positive test uses **fixture bytes only** and does not constitute authentic market data, valid ZIP contents, or PIT attestation. This code does not ingest RAW, validate OHLCV/bar chronology, run #245/#253, evaluate Scanner/Secretary, or enable Factory Lab/Paper. Those E G3/G4/G5/G6/G10/G11 checks remain pending an integrated owner gate; do not claim Package E complete.

## Explicit outcomes
- `WAIT_SOURCE_PROVENANCE_NOT_CONNECTED` for unavailable/invalid/synthetic data.
- `HISTORICAL_SOURCE_VERIFIED_CUSTODY_ONLY` means a local byte digest matched the supplied checksum, **not** source authenticity or full admission.
- `historical_pit=NOT_ATTESTED`, `trading_authority=NONE` always.

## Next integration dependency
Factory final E gate must use pinned Core #211/#226/#245/#253, Scanner, Discoverer and Secretary, independently authenticated source custody, temporal/warehouse receipts, full parent lineage and cross-interpreter normalized SHA agreement. If the original new-month publisher ZIP/checksum is not actually available in authorized private execution, report `SOURCE_BLOCKED`; never upload private OHLCV to public Actions or substitute synthetic AAA as historical proof. No merge, G0, trading, or holdout release.

## Final consolidated closure #272 — Core owner delta

New files: `research_wp_r0/aql_core_e_status_evidence_v1.py`, `tests/test_aql_core_e_status_evidence_v1.py`; Core E preflight verifier patched to return False for malformed false-VERIFIED receipts instead of raising on null/non-string checksum, plus adversarial test. Factory #267 independently observed this malformed-input path and kept its own fail-closed guard; this Core fix addresses the actual producer contract.

The new status record `aql.core.e.historical-integration-status.v1` is SHA-sealed, replay-equal, records explicit external access needs and requires unknown source/query hashes to be null, unlike fabricated same-source receipts. Its verifier enforces the original preflight parent and no authority/PIT promotion. It deliberately **refuses to claim warehouse, native #245 or local #253 validation without actual canonical receipts**.

### G3/G5/G6/G11 owner evidence classification
- G3 genuine new-month original ZIP publisher-authenticated: **SOURCE_BLOCKED / UNVERIFIED**, not Core historical PASS. Existing `aql_core_bounded_monthly_source_preflight_v1.verify_native_month`, `aql_authenticated_historical_admission_v1.admit_original_bytes`, RAW #211 and `aql_core_backbone_local_v1` already implement the bounded authorized source validation and durable indexed readback. Reuse only on actual permitted private bytes; no additional mock ingestion.
- G5 historical UTC/bar/known-at: implementation exists in `verify_native_month` and Core chronology/universe module; original independent issuer known-at remains **PIT_NOT_ATTESTED**; no fresh private original-byte execution in this delivery.
- G6 durable Secretary: Core C/D separate Source ACK, TEST_ONLY strategy approval and Factory ACK, persistent event trace and fail-closed replay already tested in D; no historical ACK authorized under Scanner E frozen historical policy. Do not use D synthetic ACK to establish actual historical route.
- G11 original BTCUSDT versus synthetic AAA: explicit `WAIT_SOURCE_PROVENANCE_NOT_CONNECTED` and `SOURCE_BLOCKED`. The verified historical policy needs a **separate owner-approved versioned historical 15m policy**. Scanner E #270 correctly refuses frozen Work235 BTCUSDT approval.

### External dependency needed for true historical E
Owner-authorized private local runner holding *original* new BTCUSDT Spot15m monthly ZIP plus separate publisher CHECKSUM obtained through a trusted channel; verifiable publisher provenance and source acquisition time; authorized versioned historical research-only strategy config/policy; independent historical known-at attestation for scientific PIT. The last item is a separate stronger requirement than retrospective engineering replay. Do not push private CSV/OHLCV in public GitHub/Actions.

### Integration handoff
Factory #267 and pinned final gate #271 should add `aql.core.e.historical-integration-status.v1` as an optional read-only Core E evidence parent after pinning new HEAD. This PR does not mutate Factory/Scanner/Discoverer branches or presume that previous pinned #271 re-runs automatically. Full Package E is **CLOSED_ENGINEERING_WITH_EXTERNAL_BLOCKERS only after Factory's one final exact-head combined gate and independent Audit verdict**, not by this Core owner PR alone.
