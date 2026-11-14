# H2 historical research policy C — versioned two-lane boundary

**Status:** Owner **provisional** choice C, no owner-private data access/execution. Integration #271 Draft only, no merge/G0. This extends (does not overwrite) H2 v1 preflight and the accepted H synthetic engineering baseline. H2 Audit #256/6718011997 `READY_FOR_OWNER_AUTHORIZATION` applies to **previous v1 preparation only**, not automatic independent acceptance of this new v2 policy.

## Exactly two mutually exclusive research classes

| Field | `RETROSPECTIVE_NON_PIT` | `PIT_REQUIRED` |
|---|---|---|
| `source_provenance.publisher_pit_attested` | **must be false** | **must be true** or `WAIT_PROVENANCE` |
| `historical_pit` output | `NOT_ATTESTED` | `NOT_VERIFIED` pending external independent issuer proof |
| Claim authority | No issuer-known-at, PIT-sensitive, alpha, OOS or economic scientific claim | No claim granted by preflight even if self-reported true |
| Use | Bounded *retrospective engineering* readiness only | Separate future PIT evidence workflow |
| Source rights / owner permission / nonzero owner cost | Required as independent future operation blockers in **both** lanes | Same |
| F5 / G0 / holdout / Paper / trading | Blocked / sealed / NONE | Same |

**v2 JSON contract:** `aql.integration.h2.historical-policy-request.v2` adds mandatory `research_class` to the exact v1 request fields, retaining exact-head pins, 15m bounded source/range/cutoff/strategy SHA, explicit scoped permission, seven Decimal SPOT cost strings (funding zero), source-rights and distinct Core245/Core253 hashes. `aql.integration.h2.historical-policy-result.v2` includes `research_class`, `historical_pit`, `pit_sensitive_claims_allowed=false`, `scientific_claims_allowed=false`, `economic_approval=NOT_GRANTED`, `operation=READINESS_ONLY_NO_SOURCE_IO`, F5 blocked and trading NONE.

**No false PIT shortcut:** non-PIT class rejects `publisher_pit_attested=true` with `BLOCKED_CONTRACT/NON_PIT_CANNOT_ASSERT_ISSUER_PIT`; PIT class rejects false with `WAIT_PROVENANCE/INDEPENDENT_ISSUER_PIT_EVIDENCE_REQUIRED`. A synthetic self-declared true in PIT class is NOT independently verified issuer-known-at and never grants scientific/trading authority. A false non-PIT flag does not waive source rights or owner approval.

**Backward compatibility:** Existing `tools/atlas_h2_readiness_preflight.py` v1 remains byte-for-byte unchanged and still requires PIT for its own v1 readiness status. v2 must be invoked explicitly through `tools/atlas_h2_historical_policy_v2.py` and never aliases v1 schema or silently rewrites existing private historical receipts. No generic Scanner/Factory/Lab/Core Secretary code changes. The operator remains **UNIMPLEMENTED AND UNEXECUTED**.

**Validation:** `tests/test_atlas_h2_historical_policy_v2.py` tests both classes, missing/forged PIT, missing owner source permission, cost, source rights, wrong Factory head, unknown mode, v1 rejection and no private path field; GitHub Actions `.github/workflows/atlas-h2-option-c-policy-gate.yml` runs Linux and Windows Python 3.11 using public synthetic fixtures only. Existing accepted H matrix and prior v1 readiness suite are not rerun.

**Separate future owner decision required:** explicit bounded month/range/strategy, owner read-only/no-export source permission, isolated results SQLite destination outside original Warehouse, independent custody/source rights, nonzero seven-field owner-approved cost scenario, and whether to commission issuer-PIT attestation for PIT lane. Neither choice nor this code authorizes E: execution, private source upload, source mutation, signing, merge, G0, holdout, Paper or trading.

**Independent Audit request:** review only v2 branch separation and negative gates; report `ACCEPT_IN_SCOPE` (synthetic policy preparation only), `CHANGES_REQUIRED`, or `BLOCKED`. No historical original-data PASS is possible from this packet.
