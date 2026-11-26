# POST149-001: Factory static input contract, not an execution gate

Owner order #157 consolidates the uncompleted #150 task; no competing second
inspector is delivered. New isolated branch from verified main
`dbc191df72f4b4d1ebb7d490926dcad4325dac12`, no unmerged ancestry/cherry-picks.
Only new uniquely named module, its tests and this document. No Core149/PR155,
Core144, Work148/PR143, strategy/exit/ledger, existing admission or bridge edits.

## No-duplicate matrix / exact source

| Source inspected | Reuse and precise remaining gap |
|---|---|
| Core149/PR155 `752d7cd6d652860134918a35727853b5ba52f876`, `dev_source.py` blob `a1c08a0436b62a5115dc8b741a713f8aad93d8d0` | Owns raw byte/ZIP parsing, SHA/size, envelope identity, positional grid, RETROSPECTIVE normalized7 and receipt. Not imported/copied here. Factory lacks a consumer join of those metadata/records/retained commitments. |
| Work148/PR143 `dee0f088d70122d143118df2e0a0549a564f2380`, `historical_dev_exits_v1.py` blob `bbeae9d7f16f4d2b0738072ec35ea4dd9345639b` | Owns full dictionary rows hash, explicit available_ms/modeled_quote validation, native exits and three separate portfolios. No engine import/call, dictionary conversion or exit logic here. |
| main `sf_historical_admission.py` blob `82156119b18f1af9132f4efb1c5bb222eab0c579` | `preflight_dev(manifest,bars,*,boundary,expected_content_hash,price_unit,volume_unit,session,normalization,adjustment,decision_cutoff_ms=None)` plus `verify_admission_report`. Legacy HistoricalBar/content-hash boundary, not Core149 source envelope; keeps dev_eligible=false. No bypass/wiring. |
| main `historical_evaluation_bridge.py` blob `c6dc423a1dcb24eb6665265718efabf95d51066e` | `prepare_inputs` requires CustodyAccessor and recorded timing. Unknown retrospective source still rejected. |
| Work148 stack `data_admission_b.admit_revision(record,*,cutoff_ms,expected_manifest_digest,verified_source_timing=False)` | Requires first-known/provider/clock evidence. This file is in the unmerged Factory stack, not current main. No import or permission transfer. |
| main `historical_library.validate_bars`, HistoricalBar, DatasetManifest | Reused existing finite/logical OHLCV/finality/checksum and manifest/hash checks. Reconstructs only documented Core HistoricalBar shape in memory, never Work148 execution rows or source timing proof. |
| Work154 result6470946878; newer Work156 notice6471011441 | Read-only seam baseline and distinct hash domains. Reused in future batch below, no new Work order or implementation of binder. |

Existing raw parser/legacy quality validation covers their own forms. The absent
piece is a Factory-only **injected source contract consistency/readiness** port,
with explicit unknown timing/quotes and no consumer ACK/execution authority.
This narrow delta justifies the new module, not another parser or general engine.

## Implemented signature / precise semantics

```python
from research_wp_r0.post149_source_readiness import inspect_source
review = inspect_source(core_envelope_dict, core_receipt_dict, normalized7,
                        expected=retained_commitments,
                        declarations=unknown_provenance_and_quote)
canonical_receipt_bytes = review.payload
receipt_hash = review.receipt_sha256
```

`expected` exact fields: source_id, archive_sha256, archive_size,
normalized7_sha256, core_receipt_sha256. The last hash is a new explicit domain:
canonical JSON of the supplied Core import receipt, not Work152 raw receipt SHA.
Caller retains these separately; they are commitments, not issuer authentication.

`declarations` exact fields:
```json
{
  "availability": "UNKNOWN", "correction_timing": "UNKNOWN",
  "bounded_UTC": "UNKNOWN", "independent_custody": "UNKNOWN",
  "available_ms": null, "modeled_quote": null,
  "verified_source_timing": false, "real_pit_accepted": false
}
```
Unknown fields must be explicit, not defaulted away. This port refuses injected
available_ms or true/false modeled_quote: either would select an execution model
that has not been authorized here. It does not infer arrival from bar close,
ingestion, manifest creation zero, receipt date or publisher checksum. UNKNOWN
correction history does not mean ORIGINAL or PINNED_LINEAGE.

Validation: exact supported envelope/receipt version and field shapes; source ID
recomputation using Core canonical JSON; archive commitment/size consistency;
complete bounded UTC interval grid and exact open/close; duplicate/order/gap
rejection before legacy gap enumeration; finite positive logical OHLC/nonnegative
V through validate_bars; exact manifest/bar/source bindings; normalized7 and Core
receipt hash-domain matches; conflicts/escalation refused even after rehashing.
The normalized input is a bounded list/tuple of seven-field rows with integer ms
and Python floats for OHLCV, matching Core's declared normalization. No coercion,
sorting, filling, file reading, ZIP parsing, downloads, source writes or engine
calls. HistoricalBar observation_cutoff=close+1 is reused solely for exact Core
representation/checksum comparison, not emitted as issuer availability.

Result always READY_FOR_CONTRACT_REVIEW; PASS_SOURCE_QUALITY explicitly means
**INJECTED_NORMALIZED_RECORDS_AND_METADATA_ONLY**. BLOCKED_PIT,
NEED_CONSUMER_ACK, archive_readback=NOT_PERFORMED and
factory_execution_eligible=false/verified_source_timing=false/real_pit_accepted=false
are unconditional. Missing evidence lists consumer two-file ACK, issuer vintage,
correction chronology, bounded UTC, independent custody, Council, owner model
permission, signed interface and integration authorization. This is not empirical
admission, a fabricated source readback or acceptance of a strategy study.
No combined DEV/OOS resources should be supplied: scope is checked as caller
metadata, not independently authenticated filesystem partition authority.

Rejected contracts raise ReadinessError/ValueError with concrete reasons such as
SOURCE_ID_MISMATCH, CORE_RECEIPT_COMMITMENT_MISMATCH,
PROVENANCE_OR_QUOTE_CONFLICT, GAP_DUPLICATE_ORDER_OR_CLOSE,
QUALITY_OR_MANIFEST_INVALID, MANIFEST_BINDING_CONFLICT,
NORMALIZED_HASH_MISMATCH. A quality pass cannot repair a bad hash or a PIT claim.
SourceReview payload is immutable bytes; spec is a fresh copy. Digest is integrity
only, not a signature, WORM proof or standalone permission token.

## Evidence / coordination state

Core149 engineering DELIVERED, independent exact-head S/R not accepted here.
Existing automatic Core155 G1 run40700818744 and Integrity40700818892 now completed
SUCCESS (metadata read, no new run). They are not proof of new Factory157 tests.
Work148 engineering delivered, prior exact-head Acceptance40699238038 and
Integrity40699238053 green reused, not rerun. Council AIARC089 covered the older
comparator only; AIARC090 newer exit delta remained pending in reviewed records.
No inferred acceptance transfers between these source versions or tasks.

Work153 result6470810545 verifies **OWNER_LIBRARY_READBACK**, not
**THIS_CODEX_CONSUMER_ACK**. Raw ZIP file_00000000084c8208b5d65c8fc803426c/version0:
68923 bytes,4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e.
Issued Work152 receipt file_0000000070e482089275b5bfdca3fca4/version0:
4203 bytes,ffce2bbe7890414d84360be80a0ac478795ae8d1a28085f8bb34075faca83386.
No bytes from either object accessed here; no new owner ACK request/fetch loop.
The existing private attachment/materialization route remains with #153.

New unit tests use synthetic injected contracts, no Core parser or Work148 rerun:
`python -B -m pytest tests/test_post149_source_readiness.py -q --tb=short`
Actual Windows/Python3.12.10: **39 passed /0 failed /0 skipped,0.98s**.
No broad/manual CI/Guardian/E2E dispatch; automatic PR checks reported separately.

## ONE future integration batch — SPEC ONLY, not authorized to execute

Baseline is [Work154 field map](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/154#issuecomment-6470946878).
No new study assumptions or numeric lag/quote policy are selected here.

**No-merge dependency graph:**
Core155 pinned output + Factory157 static contract + Work153 actual consumer ACK
+ Council S/R on148/149/157 + explicit owner retrospective model permission
+ signed interface + explicit owner integration-code authorization
→ one future isolated binder implementation/review
→ targeted integration acceptance
→ separately authorized study, never automatic execution/merge.
Any missing node = WAITING_ON_DEPENDENCY. This PR supplies only the Factory157
contract node; no PR143/155 cross-branch integration or executable gateway.

Future binder input contract (proposal, not an existing callable):
- Exact code SHAs for Core155, Factory143 engine, Factory157 validator and binder;
  expected raw ZIP and Work152 receipt file/version/size/hash; actual consumer
  ACK records task/environment and measured hashes, not owner-only testimony.
- Core canonical envelope/source_id, archive version, normalized7 digest,
  Core receipt digest, Factory157 receipt; explicit symbol/market/interval/UTC
  full DEV range, immutable chronological warmup prefix and unit declarations.
- Owner/Council accepted model policy ID/hash, explicit nonnegative availability
  lag rule, quote policy/unknown behavior, config/cost assumptions and sensitivity
  labels; no defaults selected from this document. Missing policy = refuse.
- Separate accepted interface agreement and authorization references; no boolean
  flag that silently promotes inferred evidence to confirmed source timing.

Minimal mapping after authorization: 7-field values → same OHLCV/open/close names
in F148 dictionaries, only then add explicitly **modeled** available_ms and
modeled_quote from approved policy; retain UNKNOWN issuer/correction/clock/custody
and model evidence labels. Never call closed-bar lower bound historical
first-known. Symbol/date/source identities remain upstream because F148 rows lack
instrument fields. No optimistic timestamp/quote synthesis from metadata quality.
Target real-study function would be F148 `replay(bars,*,source,config=Config())`,
never handcrafted replay_contract_fixture. Integration must be a separate reviewed
DEV port, not weakened CustodyAccessor/prepare_inputs or data_admission_b flags.

Distinct hash domains that the binder must retain together, not equate:
1. raw compressed ZIP SHA; 2. exact issued Work152 receipt raw SHA;
3. numeric normalized7 canonical JSON SHA (Work152 aa740790... under its pinned
parser/Python contract, not remeasured here); 4. Core envelope/source_id and Core
import receipt SHA; 5. Factory157 readiness receipt; 6. full F148 dictionary
rows_sha256 including available_ms/modeled_quote; 7. binder mapping/model/config
and code hashes; 8. downstream F148 signals/receipt/scenario ledger hashes.
Core149 and F148 current digest source both default ensure_ascii=True; do not
generalize other Factory canonicalizers or force cross-domain hash equality.

One future targeted acceptance/falsifier set, only for a new authorized delta:
- Missing/wrong-version two-file consumer ACK, code/model/interface drift, hash
  domain substitution or malformed full-range quality ⇒ HOLD/no engine call.
- Missing/rejected modeled-time or quote policy ⇒ no generated rows. With an
  accepted policy, recursive EMA prefix max availability + latency must precede
  scheduled next grid open; warmup22 closed bars and fixed history prefix, no
  later correction or future-bar leak. Keep historical as_known claims false.
- Identical pinned package replay gives identical rows/config/mapping/receipt
  and scenario chains. Row/source/model/config tamper refuses; no sort/repair.
- Reuse Work148 existing synthetic falsifiers for UNKNOWN_EXIT_ORDER and
  separate TARGET_FIRST/STOP_FIRST downstream capacity/cash/positions/fees,
  complete denominators, factual missing quote and ambiguous primary nulls.
  Test only binder-specific propagation, not duplicate the engine's suite.
- No forced24h exit; open/censored exposure and sampled MTM distinct from
  realized/settled totals; scenarios hypothetical, not guaranteed extrema.
  Preserve missing-opportunity interpretation and legacy synthetic receipts.

**Current disposition:** READY_FOR_CONTRACT_REVIEW / WAITING_ON_DEPENDENCY.
BLOCKS_DEV_NOW: consumer access/ACK, independent S/R, retrospective time/quote
model decision, interface agreement and integration authorization.
BLOCKS_PIT_LATER: authenticated per-vintage issuer first-known/corrections,
independently bounded UTC and independent immutable anchor/custody.
DEFERRED: Guardian/continuous operations, sealed OOS, Paper/Live, extra strategies
and broad CI. No PnL/run, OOS access, G0, source acquisition or merge authorized.
