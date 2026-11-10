# CODEX-PKG-01: prospective safety rehearsal

Dispatch: #271 issuecomment-6768334518. Base: Core #275
`99c27ea2c1a4d41aaae361141301a8a9ea3b33c3`.

## Demonstrated gap and reuse

Core #245 `query_price_custody` and #253 local backbone deliberately preserve
`RETROSPECTIVE_NON_PIT`; they do not implement prospective sample admission.
`frozen_research_plan` already freezes candidates, protocol, source/split,
metrics, selection, cost and null baseline. G1 `DurableJournal` already supplies
post-COMMIT observed receipts and quarantines content conflicts. Those paths
are reused without changing historical authority or adding a warehouse.

The missing slice added here binds that existing plan to source/version/rights,
time anchors, evaluator/search/all-attempt/risk-exit digests, a MOCK prefreeze
witness, a journal instance and strictly future first sample. The seal is
create-only and independently pinned on each read; byte-identical replay is
allowed, replacement with changed bytes is denied. The caller must preserve
the digest outside the mutable authority; a file hash is not external custody.

All modes are **SYNTHETIC_PROVIDER_MOCK_ONLY**. Even a supplied real authority
claim is rejected. Public accessibility, checksums, dates, synthetic receipts
and G2 observation are not proof of rights or genuine PIT.

## Reproduce offline

From the checkout, set `PYTHONPATH=src` and run:

```text
python -m tools.core_prospective_readiness_smoke --output pkg01-receipt.json
python -m unittest discover -s tests -p test_aql_core_prospective_readiness_v1.py -v
```

The command uses one disposable temporary directory and existing journal. It
returns the sealed pre-sample manifest, deterministic admission receipt,
restart/replay assertion and ten negative rejection records. Fixed clock/UUID
are explicit fixture mocks. No network, source acquisition or original
March/April/private E: bytes are accessed. CI runs Windows/Linux, Python 3.11/3.13.

Timestamp meanings: `available_at_ms` is the asserted source publication time,
`observed_at_ms` local receipt observation, and `committed_at_ms` metadata
custody. Require publication <= observation <= commit <= freeze. For bars,
close < publication <= observation <= ingest <= actual G1 COMMIT-return
observation <= consumer cutoff. The metadata times and source publication
are MOCK assertions, not independently authenticated clocks.

The immutable OOS range is sealed before sampling; its consumer always rejects
OOS access, including after the range ends. There is no unseal/release API or
evaluator execution. A predeclared >=72h validation-to-OOS embargo is checked;
this is separate from, and does not wait for or certify, any G2 72h horizon.
No consumer-facing prices or results are returned by this admission guard.
This is an API no-peek boundary, not an OS access-control sandbox: an actor
with direct access to the journal can bypass this API. Actual OOS custody,
separate permissions and independent witness remain externally gated.

## Coverage and unsupported matrix

| Capability | Status |
|---|---|
| Source/version/rights field and time cross-bind | PASS, mocked metadata only |
| Existing plan source/split/protocol hashes bound to freeze | PASS |
| First eligible sample strictly future, freeze after first journal row refused | PASS |
| Missing post-COMMIT receipt after injected failure | PASS, denied across restart/retry |
| Replay idempotency/source-journal isolation/file mutation | PASS |
| Retrospective checksum/G2 substitution/provisional/future-cutoff/embargo | PASS, rejected |
| OOS no-peek | PASS, no release capability |
| Genuine external witness/rights authentication/clock attestation | NOT IMPLEMENTED; owner/external dependency |
| Real cohort acquisition/scientific PIT/OOS performance | BLOCKED_OWNER_AUTHORIZATION |
| Actual evaluator/search census generation | NOT RUN; only predeclared digests pinned |
| Trading, routing, G0, observer reset | NONE |

## One selected provider/cohort proposal and owner authorization envelope

**Selected proposal, not permission:** Coinbase Exchange BTC-USD spot native
15-minute candles, prospective research only. Reuse the existing bounded
Coinbase adapter (#217) if separately authorized; no second downloader.
OHLCV alone cannot establish maker queue/fill, spread or intrabar ordering.

Proposed UTC schedule (must be replaced if prefreeze cannot be witnessed in
time): freeze and independent custody witness before **2026-11-12 00:00 UTC**;
first eligible bar **2026-11-12 00:15 UTC**; train to **2026-11-13 00:00 UTC**;
validation to **2026-11-14 00:00 UTC**; embargo until **2026-11-17 00:00 UTC**;
sealed OOS **2026-11-17 00:00–2026-11-18 00:00 UTC**. Half-open ranges;
captured sample starts strictly after the actual witnessed freeze, otherwise
reschedule and reseal before acquisition. These are proposed dates, not an
automatic future job or authorization to acquire historical bars later.

One owner envelope must provide all of:

1. Exact provider product/API version, venue/spot/cohort and allowed research,
   storage, derivative-output and retention/use rights, with reviewed terms
   document digest/reference; public API access alone is insufficient.
2. Explicit approval of the date ranges, immutable candidate/evaluator/search,
   ALL attempted/generated/failed variants, selection, initial risk/exits,
   fee/slippage model and independent null baseline commitment.
3. Budget: proposed **zero spend**, maximum 672 finalized 15m bars (all proposed
   train/validation/embargo/OOS windows), <=1 bounded polling request/minute,
   <=8 MiB retained payload, bounded retries and no paid/account/private API.
   Provider actual limits and approved retention must be verified first.
4. Isolated named custody location, access/retention policy, immutable manifest
   pin outside the mutable writer, independent prefreeze and source receive/
   COMMIT witness, source-version/correction lineage and no-peek OOS owner.
5. Explicit owner signature/reference approving **data acquisition only**;
   no orders, broker, live/paper execution, G0 or G2 reset. No live acquisition
   path is implemented by this package even if such an envelope is later signed.

Missing essential decision: lawful provider-specific rights + signed owner
authorization and genuine externally witnessed prospective custody. Current
status remains `BLOCKED_OWNER_AUTHORIZATION`; no real request was made.
