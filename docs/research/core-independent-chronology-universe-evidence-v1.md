# Core #249 — Independent chronology / historical opportunity-universe evidence contract

**Status: bounded contracts implemented and TEST_ONLY verified. Authentic historical source issuance, publication, per-bar known-at, corrections, and whole-market/opportunity census remain NOT_ATTESTED / NOT_AVAILABLE.** This is an additive Core-owned READ-ONLY evidence junction on existing Draft #226; it does not alter the existing Native ZIP Bridge, price query, Factory evaluator, Work integration or any accepted 106-report arithmetic. It never opens sealed holdout or Paper/live.

## Why this exists
Work #251 (owner dispatched) requires **both** new Factory #250 and Core #249 interfaces before editing its Draft #242. Factory #250 is already delivered and CI-verified at `bf48e77193e69f4e857e0a461b0895ab26af31a8`, but its `aql.factory.opportunity-comparison-plan.v1` cannot manufacture venue release clocks or whole-market eligibility from 53 experimental definitions. Existing Core #245 provides source-pinned original ZIP/member/CHECKSUM and price grid, not an external time-catalog or opportunity population.

New Core entry point:
```python
from research_wp_r0.aql_core_chronology_universe_evidence_v1 import (
    assess_chronology_universe, CHRONOLOGY_SCHEMA, UNIVERSE_SCHEMA,
)
assessment = assess_chronology_universe(
    core_admission, core_price_query,
    chronology_evidence=chronology_or_none,
    universe_evidence=inventory_or_none,
)
```

**Required exact immutable Core parents**:
- `core_admission.schema='aql.core.historical-original-admission.v1'`, `manifest_record_sha256`; original ZIP `source_bytes_sha256`, dataset/version/correction parent, custody manifest, actual Core decision cutoff and COMPLETE/PARTIAL/UNKNOWN.
- `core_price_query.schema='aql.core.historical-price-custody-query.v1'`, `price_query_sha256`; same source, manifest, dataset/version, cutoff, explicit bar IDs/checksums/partial/unknown and `RETROSPECTIVE_NON_PIT`.
- Both parents are recomputed from canonical bytes and cross-checked before sidecars. Tampered or mismatched parents fail CLOSED. The assessment is content-addressed as `aql.core.chronology-universe-assessment.v1`, `assessment_sha256`.

### Chronology sidecar `aql.core.historical-chronology-evidence.v1`

**Exactly**:
`schema,dataset_id,version,original_zip_sha256,manifest_integrity_sha256,issuer_name,evidence_reference,evidence_bytes_sha256,observed_capture_ms,claimed_publication_ms,claimed_historical_known_at_ms,correction_state,correction_parent_sha256,bar_claims,evidence_sha256`.

- `observed_capture_ms`: actual recorded capture/retention timestamp **if supplied**; it is NOT itself a 2024 publication or market-known-at receipt. Nullable if not documented.
- `claimed_publication_ms` and `claimed_historical_known_at_ms`: nullable *source claims*. They cannot be derived from candle close time, ZIP metadata or a 2026 download. No future/capture-inconsistent reported clock is silently admitted.
- `correction_state`: `UNKNOWN | ORIGINAL_CLAIM | CORRECTION_CLAIM`; correction parent must match the existing Core admission, never invented or repaired.
- `bar_claims[]` max Core accepted bar count, each **exact** `bar_open_ms,bar_checksum,claimed_known_at_ms,evidence_record_sha256`. Exact Core bar checksum and unique bar ID are required; any claimed per-bar known-at before bar close+1, after declared capture, duplicate row, forged parent or future claim is rejected. Missing per-bar claims are counted UNKNOWN; neither a checksum nor an unsupported alleged issuer label promotes `CONFIRMED`.
- `evidence_bytes_sha256` and per-record SHA are content pins of **external retained proof**, not an assertion of independent issuer authentication. Independent verification of issuer signatures, publication/distribution history, clock trust and correction log is not implemented and is NOT assumed. The interface stores only safe hashes/references; don't put secret URLs or original bytes on GitHub.
- If the *actual* independently trusted evidence is absent, set `chronology_evidence=None`: `CHRONOLOGY_EVIDENCE_NOT_AVAILABLE`, `bar_timestamps_unknown=core_available_bar_count`, `historical_pit=NOT_ATTESTED`.

### Universe sidecar `aql.core.opportunity-universe-evidence.v1`

**Exactly**:
`schema,dataset_id,version,original_zip_sha256,manifest_integrity_sha256,market,venue,timeframe,start_ms,end_exclusive_ms,source_manifest_sha256,inventory_observed_at_ms,completeness_claim,members,opportunities,evidence_sha256`.

- Scope must have one venue, market, timeframe, bounded half-open UTC-ms historical window. The external manifest source SHA must be pinned independently; inventory-observed-at can be null. `completeness_claim=UNKNOWN|DECLARED_COMPLETE_UNVERIFIED|DECLARED_PARTIAL` is a **claim**, never independent completeness certification.
- `members[]` max 256 unique symbols. Each **exact** `symbol,market,venue,timeframe,status,missing_bar_opens,exclusion_reason`. `status=INCLUDED|EXCLUDED|UNKNOWN`. Excluded members require reason; gap timestamps are bounded/unique/ordered. A missing market catalog cannot be inferred from bars for BTCUSDT, and a complete single-symbol native grid does not certify the population of other symbols.
- `opportunities[]` max 4096 explicitly supplied unique opportunity IDs and unique symbol/open-time slots. Each **exact** `opportunity_id,symbol,bar_open_ms,status,reason,source_bar_checksum`, status `ELIGIBLE|INELIGIBLE|UNSCANNED|REJECTED|UNKNOWN|MISSING`. Must reference a declared member and fall inside its scope. A gap cannot be promoted to ELIGIBLE; excluded symbols cannot be ELIGIBLE. These are **supplied counts** only (the interface cannot prove a missing opportunity does not exist).
- Numeric census fields `reported_member_count,reported_opportunity_count,reported_status_counts,reported_exclusions,reported_gaps` are returned only when a sidecar exists, strictly conserved. `independent_market_opportunity_denominator` remains **null** even if a self-reported manifest claims completeness, because independently attested exchange-wide history is absent.
- If no original independent inventory exists, pass `universe_evidence=None`: `UNIVERSE_EVIDENCE_NOT_AVAILABLE` and **null** counts, not zero.

### Factory #250 & Work #251 integration rule

- Use `assessment_sha256`, admission/price SHA, dataset/version/cutoff and associated sidecar SHA in the new Work integration; do NOT overwrite `aql.factory.opportunity-comparison-plan.v1` or its current `universe_inventory=None` based on the absence of a real independent inventory. If a supplied single-symbol descriptive inventory exists, Factory only accepts `scope='EXPLICIT_SINGLE_SYMBOL_DEVELOPMENT'`, `coverage='SUPPLIED_NOT_INDEPENDENTLY_ATTESTED'`; that schema must NOT be called full-market evidence.
- G0-GOV-01: actual last owner-dispatched Work #251 is confirmed by #251/6626956736, but Work explicitly requires the Core contract before it edits. This Core handoff makes the **interface available**, not authentic inputs. Do not rerun Work #247 accepted 106 reports or Audit #248 accepted original byte/price/arithmetic verification.
- Mandatory scientific status is `EVIDENCE_INCOMPLETE`, `historical_pit=NOT_ATTESTED`, `independent_venue_issuance=NOT_ATTESTED`, `market_universe_completeness=NOT_ATTESTED`, `independent_opportunity_denominator=null`, `factory_scientific_input=BLOCKED`, `work_scientific_e2e=NOT_CONNECTED`, `trading_authority=NONE`. A future genuine proof and independent gate would need a **separate** trusted verifier and owner authorization before such fields could be upgraded. No ability to forge PASS by setting `claimed_publication_ms`, `completeness_claim` or resending a self-consistent SHA.

## Evidence & execution limits

The 2024 Feb/Aug retained ZIP/CHECKSUM/CSV originals were available inside Work #247 and independently rehashed/compared to prices and arithmetic by Audit #248. That acceptance is **not** publisher-issued 2024 chronology, an independently captured complete symbol list, historically predeclared 53 strategies, actual fills or global opportunity coverage. No Core session accessed private originals or created missing timestamps. The source sidecars are **TEST_ONLY** in CI and no package download or live exchange call is performed.

Reproducible focused gate:
```sh
PYTHONPATH=. python -m unittest discover -s tests -p 'test_aql_core_chronology_universe_evidence_v1.py' -v
```
The **one consolidated** Core workflow `.github/workflows/aql-core-research-vertical-slice-focused.yml` combines this 10-test suite with 55 previously accepted tests. Negative cases include source/manifest SHA tamper, unsealed claims, future/capture inconsistent times, correction-parent mismatch, leaked per-bar pre-close timestamps, duplicate claim/opportunity, excluded symbol, invalid gap and forged denominator. No retained source bytes or prices are embedded in the tests.

No PR merge/G0/holdout/Paper/live/trading. **This is a completed code/schema handoff with authentic chronology/universe evidence still NOT_ATTESTED; Work is allowed to consume the missingness response as specified by its already-dispatched #251 task.**
