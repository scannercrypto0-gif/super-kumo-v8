# AQL-SF-CODEX-HISTORICAL-INPUT-READINESS-001

## Reconciled authority / non-overlap

Owner instructed execution of #150 in this chat. Base main is
`dbc191df72f4b4d1ebb7d490926dcad4325dac12`.
Latest initially delivered history handoff was #146/6469407856. During source
review, newer #148/6470728543 and #154/6470946878 were read: #148 delivered
`dee0f088d70122d143118df2e0a0549a564f2380` on Draft #143; independent new-head
Council S/R remains separate. Core #149 delivered Draft #155 at
`752d7cd6d652860134918a35727853b5ba52f876`, also unmerged. Core #144 stays
`3fc035b7ae70693e952976e2dcb2fe165a7e1826`. Only accessible GitHub/current chat
were reviewed; unseen originating chats are not claimed inspected.

#150 does not write Work148/Factory143, Core149/155, Core144, factory_exam.py,
strategy/exit/ledger code, original frozen plans, Work146 proposal or Work152
receipt bytes. No unmerged branch code is imported. S/R is requested, not issued
by the implementing assistant. No merge, OOS, Paper, Live or G0 acceptance.

## Reuse vs genuinely missing

All listed main blobs are pinned to the base above. Draft blobs are reference
only; their existence is not main acceptance or permission to import them.

| Component | Blob SHA / source | Reuse / missing boundary |
|---|---|---|
| HistoricalBar and validate_bars, historical_library.py:424 | 4d102025c02f9b0fa7380294612c491893e9e2e1 main/143 | Reuse unchanged for numeric/logical OHLCV; do not register data or trust generated manifest timestamps |
| retrospective_kline_intake.py | 9a74cc4b4903d4ee0452dfc4ae585ce06c6cd33d main/143 | Reuse bounded raw ZIP/hash/member checks via extracted byte helper; legacy path/parser semantics unchanged |
| historical_evaluation_bridge.py | c6dc423a1dcb24eb6665265718efabf95d51066e main | Recorded-receipt input gate, not a byte-quality diagnostic; unchanged, not bypassed |
| sf_historical_admission.py | 82156119b18f1af9132f4efb1c5bb222eab0c579 main | DEV/confirmed-evidence admission unchanged; this report is not its authority |
| core_proof_bridge.py / data_admission_b.py | 6bc7369e1e23a68f03b30ef9c35e21cafd612fb6 / 63c9b94e66307c3242a43e4550638a88bd857a48 at143 | Reference only; verified_source_timing=False remains enforced upstream |
| observation_authority.py / utc_evidence.py | de78ebb547e855e77ff1647f02009af40e1050a0 / 6c6a81635d2a4a50b2d635783419b2f499de63a8 at144 | Core owns external timing/custody; no verifier duplicated here |
| Core149 dev_source.py | a1c08a0436b62a5115dc8b741a713f8aad93d8d0 at155 | Source envelope -> normalized DevHistory/manifest/rows. #150 is not another importer/materializer; it adds bounded aggregate quality diagnostics and complete unverified provenance reason codes, not a dataset or strategy handoff |
| Historical DEV exits (Work148) | bbeae9d7f16f4d2b0738072ec35ea4dd9345639b at143 | Execution/PnL/scenarios owned by Work148; no import, write or execution |

Existing main cannot report leading/trailing missing slots against a pinned
expected window, independently count duplicate/off-grid/unsorted/bad rows,
or emit this stable receipt separating source-byte quality from each missing
first-known/correction/UTC/anchor/ACK dependency. New code implements only that
diagnostic boundary. No parallel OHLCV formulas, HistoricalLibrary registration,
normalizer or PIT verifier is introduced.

## Public contract

```python
from research_wp_r0.historical_input_quality import (
    HistoricalInputSpec, inspect_historical_input, replay_input_quality,
    InputQualityReceipt,
)
spec = HistoricalInputSpec(spec_dictionary)
receipt = inspect_historical_input(injected_bytes, spec,
                                   expected_spec_digest=spec.digest)
restored = InputQualityReceipt.from_json(receipt.to_json(),
                                        expected_digest=receipt.digest)
replay_input_quality(injected_bytes, spec, restored,
                     expected_spec_digest=spec.digest,
                     expected_receipt_digest=receipt.digest)
```

Callers retain digests independently. Hash consistency is not authentication.
Spec schema `historical-input-quality-1`, scope `DEV_INPUT_QUALITY_ONLY`, UTC:

- provider, venue, symbol, minute timeframe, source_uri, license_reference,
  price_unit, volume_unit: explicit nonempty bounded metadata; identity/terms are
  caller declarations, not issuer authentication or license/legal approval.
- start_ms inclusive, end_exclusive_ms, review_cutoff_ms: integer UTC ms,
  aligned minute-timeframe grid, window ends no later than review cutoff.
- version_sha256: mandatory exact SHA256 of injected bytes. Optional
  publisher_checksum_sha256 must also match those bytes. A matching supplied
  publisher checksum is explicitly not independent verification.
- container CSV or BINANCE_SPOT_ZIP. CSV has no header; NORMALIZED_7 order is
  `[open_ms,close_ms,open,high,low,close,base_volume]`. BINANCE_KLINES_12 reads
  timestamps0/6 and OHLCV1..5. Auxiliary Binance columns7..11 are retained only
  in the raw version fingerprint and are NOT liquidity/trade/fill validation.
- timestamp_unit is explicitly ms or us. Microsecond opens must divide by1000
  and closes have remainder999, then normalize for grid inspection. No guessing.
- Shared ZIP support deliberately remains Binance SPOT BTCUSDT1m only; exact
  member_name required. Other instruments can use declared injected CSV; no
  implied broader source parser certification.
- provenance requires explicit nulls for unknown observed_at_ms,
  publisher_available_at_ms, first_known_at_ms, vintage_id, supersedes_version,
  correction_history_ref, independent_utc_ref, independent_anchor_ref,
  source_ack_ref and target_ack_ref; boolean claim flags are explicit.

16MiB raw/expanded CSV,100k rows/expected slots. No file or network operations in
the inspector. Malformed contracts raise ValueError before parsing; malformed
bytes produce SOURCE_QUALITY_BLOCKED plus reason/counts. No sorting, filling,
deduplication or repair. Leading/trailing/internal missing slots are counted
against the entire declared range. Before parsing is possible, missing_slots is
null, not an invented zero. Blank/missing-column rows are invalid.

Per-row OHLCV reuses validate_bars without retaining its temporary manifest or
clock. The internally constructed RETROSPECTIVE bar's derived close and
observation_cutoff are validation scaffolding only, never emitted as observed
availability. Supplied close time is separately checked exactly. CSV interval
closure is structural, not an authenticated finality receipt.

## Two independent classifications

SOURCE_QUALITY_ACCEPTED means only version-pinned, structurally complete declared
OHLCV in this scope. It can coexist with PIT_UNKNOWN or PIT_BLOCKED. It grants
no strategy execution authority. Quality and metadata problems are not conflated.

Missing first-known, publisher availability, vintage ID, correction history,
independent UTC, independent anchor, source ACK and target ACK each have explicit
MISSING reason codes. Supplied references stay CALLER_SUPPLIED_NOT_VERIFIED with
UNVERIFIED reason codes. No external verification implementation exists here.
Local observed_at_ms is diagnostic only; never substituted for first_known.
An asserted true verified_source_timing or real_pit_accepted is rejected with
CALLER_PIT_CLAIM_REJECTED and PIT_BLOCKED; both returned flags remain false.
Inconsistent/after-cutoff source availability also blocks PIT metadata. Even all
plausible references present cannot produce accepted PIT. Every receipt fixes:
`verified_source_timing=false`, `real_pit_accepted=false`,
`performance_execution_allowed=false`, `strategy_executed=false`.

## Read-only real-source demonstration

No network request. A previously retained local ZIP was actually read and
rehashed, matching the exact public Work146 pin. This is not access to the
Work152 Library object or its separately issued receipt, and is NOT their
consumer two-file/version ACK. Work153 private artifact access remains separate.

Local file: `C:/dev/ATLAS/sf-p0-evidence/BTCUSDT-1m-2024-01-01.zip`.
Measured raw68923bytes; SHA256
`4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e`.
The locally retained .CHECKSUM value matches; no fresh publisher attestation.
Window `[1704067200000,1704153600000)` UTC, timestamp unit ms:
1440 parsed/expected/observed rows; missing, duplicate, off-grid, unordered,
outside-window, bad-close, malformed and invalid/nonfinite OHLCV all0.
SOURCE_QUALITY_ACCEPTED; PIT_UNKNOWN; no strategy executed.

Observed-at1793196196178 is the local diagnostic time of this inspection,
not trusted UTC or historical availability. Frozen sample spec digest
`f0921b4450da2f360fed11cdf96d141545e0bc6b639cb322b3d30575d7dbc97b`;
quality receipt digest
`e83944031ac8c6e63c0825bfdd8dab83f454e7b2cc11f9b7aafe4520e3a74bd9`.
Artifacts are local at `C:/dev/ATLAS/sf-historical-readiness-150-evidence/`;
raw archive is not committed or redistributed. Repeating with the exact frozen
sample spec and same source bytes reproduces the receipt, without sampling time.

## Future Work148 consumption: documentation only

Read the receipt/pinned source bytes and check spec/receipt digests, exact window,
symbol/timeframe/version and quality_status. Preserve PIT_UNKNOWN/BLOCKED and
all false authority flags. Do NOT translate quality acceptance into actual
available_ms, modeled_quote, normalized rows or F148 source.rows_sha256.
Raw ZIP SHA, CSV SHA, quality receipt SHA, Core149 normalized7 SHA and F148
dictionary-row SHA are distinct domains; no digest equality is assumed.
No converter/binder or strategy call is included. #154's separate model-policy,
exact-version access and independent Council gates remain unresolved.

## Focused verification / independent Council handoff

```sh
python -B -m pytest -p no:cacheprovider tests/test_sf_historical_input_quality.py tests/test_sf_retrospective_kline_intake.py -v
```

Windows CPython3.14.3: first run43pass/1fail in a new AST-isolation test (it
mistakenly checked imported attributes rather than the stdlib module). Corrected
that test's module check, not the runtime boundary; final44pass/0fail/0skip,
including40 new quality cases plus4 unchanged ZIP compatibility cases. No broad
baseline or Work148 suite rerun. Exact-head Ubuntu/Windows workflow runs the
same focused44 cases, enforces counts/no skips and emits deterministic synthetic
receipt, source/environment and JUnit artifacts. Actual CI links follow in the
delivery receipt after completion; CI cannot issue independent S/R acceptance.

Request Council S on byte/window/grid/count/replay integrity and unchanged legacy
parser behavior; R on honest quality-vs-PIT/first-known/correction/clock/anchor/ACK
classification and non-admission. Core/Data own authenticated evidence; Work148
owns modeled execution; #150 remains input-quality only. Independent S/R pending.
