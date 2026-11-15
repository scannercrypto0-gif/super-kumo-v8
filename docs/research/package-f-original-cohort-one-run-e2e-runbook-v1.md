# ATLAS Package F4–F5 — one original-source cohort execution runbook

**Scope:** owner provisional Package F #274, PM instruction #267/6655814613.
This is a reproducible *private-execution plan*, NOT evidence that a real
original-source historical run happened. The existing E combined engineering
suite and accepted Audit #272/#273 are not reset. PR #271 is the one pinned
integration vehicle; no second blocked-only PR.

## Exact owner interfaces / commits (all DRAFT and unmerged)

- Core F0–F2 #275: `74602f248b19b142d05aecfef19a560ceaf9ce13`,
  `research_wp_r0/aql_core_f_bulk_source_v1.py` (F0 manifest, opt-in F1
  private fetch, checksum/native 15m preflight, F2 **preflight-only** coverage).
  Its `ACCEPTED_PREFLIGHT` **is not** RAW/warehouse/query admission.
- Scanner F3 #277: `8dcf20021c859eed139c199b31c9d346e6a0be74`,
  `tools/scanner_strategy_f/retrospective_policy.py`. Sealed
  `btc-spot-15m-retrospective-non-pit-v1` **DRAFT**, independent owner
  decision currently conditional/provisional and DORMANT; neither this
  receipt nor #277/6655891514 is trusted activation authority.
- Discoverer F4 #276 (optional): `58959b22de9bc96f03b03dfc565815282fd1a939`,
  `tools/strategy_discoverer_offline/historical_f4_intake.py`; WAIT,
  `NOT_EVALUATED` and `NOT_CONNECTED` until independently approved source
  and policy. Never couple this to operational Scanner.
- Factory #267: `6d5a4dd3e2a701fd14f21820bad549c446c8532b`,
  `aql_factory_f_batch_ledger_v1.py` persists immutable UNKNOWN
  attempt-denominator and replay. It is not a positive historical ledger.
- Integration #271 was `a97a97d46b4a75b6b56ac934929b227387bb96e3`
  before this F runbook/owner repin; final gate must use its **actual new HEAD**
  from GitHub, not hardcoded earlier CI.

## Phase A: external original-source custody (Core owner)

Before executing any historical Lab, an authorized private operator must
provide: publisher-authorized rights/terms confirmation; issuer-verified
original monthly BTCUSDT native 15m ZIP **and separately obtained authentic
publisher CHECKSUM for each new month**; per-file SHA256, native ZIP-member
SHA256, actual rows/coverage/UTC 900000ms, observed acquisition timestamp,
quarantine outcomes and immutable archive custody; actual RAW #211
admission/readback, #226 warehouse persisted/re-read, **distinct** native Core
#245 `price_query_sha256` and local Core #253 `query_sha256` from the
same immutable original rows/cutoff. Core F F1 command is defined in
`docs/research/core-package-f-bulk-source-handoff-v1.md`; run it **only in
an explicitly authorized private executor**, never in public GitHub CI.

A sanitized packet MUST contain accepted / rejected / missing / previously
pinned (not new) counts for **all 12 target 2024 months**. Keep actual
accepted coverage separate from proposed full-year expectation (35,136 bars).
Quarantined/missing file -> no forged hash. Verify checksum provenance out of
band; caller-provided `--publisher-origin-confirmed` is not issuer attestation.
If F1/F2 private path absent, stop here with `F1_SOURCE_ACCESS_REQUIRED /
F2_EXTERNAL_SOURCE_BLOCKED`; do not run a substitute synthetic E2E.

## Phase B: independent historical-policy approval (owner, NOT Scanner)

Obtain a separate and independently verifiable final approval binding:
policy `btc-spot-15m-retrospective-non-pit-v1`, Scanner F3 #277 exact SHA,
issuer identity, explicit `APPROVED` decision and signed/trusted authority
reference, 2024-01..12 permitted month subset, BTCUSDT Spot native 15m,
strategy IDs/versions/definition/DNA/Work235 spec/config and distinct Scanner
native15m config SHA, and no trading authority. **Conditional A is not that
receipt.** Independently validate that exact policy against Scanner's source
and Core's genuinely admitted monthly source receipts.

Date boundary: closed bars only (`bar_close_ms < research_cutoff_ms`), no
lookahead, 900000ms UTC grid, joined source coverage and source/strategy
cutoff. Classification is `RETROSPECTIVE_NON_PIT`: authenticated archive
integrity and a retrospective cutoff do not establish 2024 issuer known-at/PIT.

## Phase C: actual **one** research-only cohort (private, conditional)

Run only after both A and B are independently satisfied **on exactly the same
source/cohort versions**. Canonical pipeline:

1. Core bulk accepted F2 originals → immutable RAW #211 → Core warehouse
   #226 → Core #245 native and #253 local independent readback, with per-month
   accepted/rejected/missing denominator and source ACK. Source ACK is NOT
   research strategy approval.
2. Scanner source-bound F3 *approved* RESEARCH_ONLY NON_PIT policy; run genuine
   historical screening on that source, not Work235 synthetic AAA policy,
   record complete selected/denied/unknown strategy×symbol×cohort denominator,
   exact definition/DNA/config/cutoff. An approval **request** or conditional
   policy decision is NOT an independently verified approval.
3. Core Secretary records separate source ACK vs independently approved
   StrategyApproval; Factory separately recomputes the source/query and
   policy/strategy SHA graph and issues a **different** Factory consumer ACK.
   No automatic source→strategy→consumer ACK promotion.
4. Factory executes existing `research_wp_r0/aql_factory_historical_rule_projection.py`
   indicator/rule kernels only on verified original 15m bars, using
   prefix/no-future decisions, explicitly configured entry/exit fees, spread,
   slippage and ambiguous intrabar stop/target = UNKNOWN. This module's
   `ORIGINAL_UNVERIFIED` output is not itself scientific or source approval:
   the independent outer Core/Scanner/Secretary admission wrapper is mandatory.
   Classify outputs as diagnostic `RETROSPECTIVE_NON_PIT` and never alpha
   certification. Actual strategy validity remains unassessed.
5. Persist immutable results in Factory E SQLite store with all candidate
   receipts, original source/native/local query/config/definition/approval/
   decision/result SHA; validate exact restart/readback and duplicate-attempt
   rejection. Do **not** rewrite blocked batch ID or silently upgrade UNKNOWN
   rows: use new source-versioned immutable research batch plus explicit link
   to its prior blocked cohort and full attempt reconciliation.
6. Optional isolated TEST_ONLY Paper intent must be **declined**, with zero
   orders/fills/positions, `NOT_ACTIVATED`, no broker or exchange requests,
   no G0, no holdout. Discoverer #276 is an optional independent research
   candidate lane; verify durable ledger/candidate/member and source/policy
   identities separately before *any* Factory intake, never a Scanner ACK.

## Required minimal contract delta before a positive F4 execution

Current F0/F2 reports only preflight/census, not a signed admitted RAW/warehouse
dual-query readback packet. F3 `historical_route_gate` is fixed to WAIT and
requires a **new independently signed owner approval/issuer source trust root**;
there is no source-bound historical positive Scanner/Secretary ACK contract.
Factory `aql_factory_f_batch_ledger_v1.py` is deliberately immutable UNKNOWN
only. **Do not edit these accepted safety constraints to force a PASS.**

Needed on the owners' **new versions** before E2E:
- Core F2: authenticated immutable original-source batch manifest **PLUS**
  true source ACK and #211/#226/#245/#253 readback/per-month coverage SHA.
- Scanner F3: independently approver-bound versioned RESEARCH_ONLY
  **positive** source-bound StrategyApproval receipt, with full attempt census,
  mandatory cutoff and explicit NON_PIT / zero trading authority.
- Core Secretary: separate source/strategy ACK, exact parent SHA and no
  auto-promotion; can return `WAIT` for missing any parent.
- Factory F4: an independent canonical consumer ACK and real source-backed
  Lab/results receipt, plus a new research batch state for selected/denied/
  unknown after actual approval. Never call the blocked-batch ledger's
  `start_blocked_batch` as a positive path.
- Independent verifier/trust policy: a self-signed scanner/core hash
  (or conditional owner decision text) is not trusted external evidence.

## F5 final gate and release packet

One final pinned exact-head run, with Python 3.11/3.12/3.13 and SHA parity
after the source & policy owners deliver real positive interface evidence.
Adversarial source/checksum, cross-month gap, cutoff/future bars, strategy
definition/config/approval/consumer ACK swaps, duplicate/restart/schema and
full denominator. Benchmark **actual indicator/backtest CPU/RSS** with bounded
representative bars/strategy count and clearly separate it from Factory E's
earlier generated-*metadata-only* benchmark. Use private runner to protect
original OHLCV; public CI can test fail-closed contracts without private source.
Send **one final** read-only Audit #256 package with exact SHA/CI, accepted
coverage, source/policy evidence, modeled costs, attempt denominator and
limits. Never claim PIT or operational Paper/live success; don't merge any PR
or authorize G0.

## Current observed disposition (2026-11-05)

`F0_READY / F1_SOURCE_ACCESS_REQUIRED / F2_EXTERNAL_SOURCE_BLOCKED /
F3_CONDITIONAL_APPROVAL_DORMANT / F4_NOT_EVALUATED / F5_FINAL_AUTHENTIC_GATE_PENDING`.

Core #275's one actionable private owner handoff is PR comment #6655880209.
Scanner #277 owner provisional A is issue #274 comment #6655892391.
Discoverer #276 provides WAIT only. These missing external inputs are NOT
fixed by more synthetic fixtures or another blocked-only PR.
