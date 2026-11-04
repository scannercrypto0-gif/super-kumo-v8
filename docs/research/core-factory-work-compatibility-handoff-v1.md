# Core→Factory #229 / Work #228 Compatibility Handoff — TEST_ONLY V1

**Owner direction:** [Core issue #180/6623594582](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/180#issuecomment-6623594582). **Scope:** bounded offline read-only contract mapping, never Factory/Work activation. **Status:** TESTED_BOUNDED, downstream NOT_CONNECTED.

## Pinned source state when inspected

- Core #226 preceding seam HEAD `6c4ddfe481b89f6fbdc79d1a31a664f65a5fdc54`, Draft/unmerged; retains Bridge and HistoricalLibrary unchanged. This compatibility delta is Core-owned, isolated and additive.
- Factory #229 HEAD `100a0a4bb7d657542099da95f2f21a7a453d7057`, Draft/open, stacked on Factory #222. Consumer schema `aql.factory.research-consumer-seam.v1`. Factory exclusively owns `research_wp_r0/aql_factory_research_consumer_seam.py` and its tests; no Core writes to its branch/paths.
- Work #228 HEAD `827f67ff85f26f863536017217cc36503a655eca`, Draft/open. Work read-only harness `tools/research_integration_harness/**` owns independent pinned-checkout and manifest verification; no Core imports, invokes or edits it.
- Core has **no** direct real Factory paired schedule/attempts or Work original source access. No real-source query or private E2E run is authorized.

## New bounded compatibility fixtures

`research_wp_r0/aql_core_factory_work_compat_v1.py` exports `compatibility_evidence(library, packet, original_source_bytes, receipt, request)`. Its request uses existing `aql.core-research.custody-query.v1`; output schema `aql.core-research.consumer-compatibility.v1` is content-sealed, TEST_ONLY, and **NOT a Factory consumer envelope** or a Work receipt. `tests/test_aql_core_factory_work_compat_v1.py` uses existing sealed archive TEST_ONLY fixture, real Bridge stage+commit, `HistoricalLibrary` and `query_custody`, plus source/receipt corruption, source-version mismatch, cutoff/coverage conservation, correction lineage and explicit replay checks. Neither consumer is imported or activated.

| Source field | Core evidence | Factory #229 contract mapping | Work #228 boundary |
|---|---|---|---|
| Original source bytes | `source_bytes_sha256` recomputed from input | Must be independently connected to actual `source_package_sha256` (NOT interchangeable) | Must be pinned to retained original bytes in independently trusted manifest |
| Source manifest | `manifest_integrity_sha256`, verified registration receipt | Shape fits `source_manifest_sha256`; genuine source association unproven until authorized cross-owner adapter | Existing manifest pin/checkout validation required |
| Corrections | `version`, `parent_source_sha256`, `correction_reason` | Append-only version, no silent shift of source disposition | Replay same source-parent chain, no substitution |
| Temporal | `decision_cutoff_ms`, per-bar observation cutoff | Factory additionally requires actual pair/arm identities and feature snapshots at decision time | Reject late feature and unknown original availability; never mark PIT |
| Coverage | `COMPLETE`, `PARTIAL`, `UNKNOWN`, missing opens, counts | Missing/partial cannot become invented eligible attempts or zero returns; Factory complete denominator independent | Preserve UNKNOWN and NOT_CONNECTED source gaps |
| Authority | `SYNTHETIC_TEST` from independently source-verified packet; `RETROSPECTIVE_NON_PIT` query is possible when zero bars | Factory requires `TEST_ONLY`, `RETROSPECTIVE_NON_PIT`, no execution and distinct Scanner universe | No private source, G0, trade, or scientific authority |

**Important distinction:** the Factory `source_package_sha256` is the P2 schedule's pinned package identity and not equal by definition to the Core Bridge `source_bytes_sha256`. A SHA-shaped Factory manifest input does not independently attest the bridge's issuer/source. Do **not** force the two digests equal, or synthesize an `attempt_id`, `pair_id`, `feature_snapshot_sha256`, Scanner denominator or a Work output receipt.

**Empty-range boundary:** Existing Core `custody_range` returns UNKNOWN and all missing opens when no bar qualifies, with `RETROSPECTIVE_NOT_PIT` availability class (no source bars to infer SYNTHETIC_TEST). The compatibility fixture retains source verification via original packet/receipt and never promotes this observation to CONFIRMED/PIT. Query result `status=ERROR` always fails closed.

## Evidence and gate

New Core-only paths: `research_wp_r0/aql_core_factory_work_compat_v1.py`, `tests/test_aql_core_factory_work_compat_v1.py`, this guide. One existing Core-owned workflow `.github/workflows/aql-core-research-vertical-slice-focused.yml` updated to run the new suite in the single consolidated TEST_ONLY gate alongside prior 10 seam and 21 Bridge tests. No other owner's code changed.

Focused C4 run to pin to final HEAD: **38 tests total** (10 + 21 + 7). Verify exact GitHub Actions HEAD and logs before scientific or integration status claims. Upstream unrelated G1 Windows pip-upgrade failure observed previously is an environment/setup issue, not a proven compatibility-contract defect; separately list any current broader CI anomalies.

## Honest downstream statuses

- `CORE_COMPAT_TEST_ONLY_READY` only means deterministic source→Bridge→HistoricalLibrary→query compatibility mapping succeeds.
- `FACTORY_229_NOT_CONNECTED`: requires a separate authorized adapter that maps actual feature snapshot/pair-arm attempt lineage, not just source SHA shape.
- `WORK_228_NOT_CONNECTED`: requires reviewed source version/manifest anchor and its independent own gate.
- `AUTHENTIC_SOURCE_NOT_CONNECTED` / `SCANNER_UNIVERSE_NOT_CONNECTED` / `PRIVATE_E2E_NOT_PERFORMED`.
- `INDEPENDENT_AUDIT_PENDING`, `PIT_NOT_ATTESTED`, `PRODUCTION_CUSTODY_NOT_ATTESTED`.
- No PR merge, holdout, real-history execution, G0 or trading.
