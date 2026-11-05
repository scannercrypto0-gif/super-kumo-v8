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
