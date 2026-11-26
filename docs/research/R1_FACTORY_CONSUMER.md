# R1 Factory consumer — actual producer artifact, market-only evaluation

Owner #77/6570476839 supersedes read-only preflight; handshake #77/6570619492.
Existing Factory Draft #209 only, starting SHA82d2fc881a6b7572e16670216fbaff7d815dc0cc.
Core live SHA4ab3cd6b1cbf83a52f941f22d35892376c6feee7 superseded observed0587305;
the intervening change adds only Core's focused workflow. Read actual Core
delivery #180/6570670255 and run41399990974/job125129533106 before consumption.
Core/Factory/Vault are draft, unmerged; no G0/deployment/Paper/Shadow/Live.

## Exact inputs and reused code

The actual `aql.r1-core-research-handoff.v1` file, not a mock or reconstructed
fixture, is `core-r1-market-research.json` from Core artifact13120952732:
SHA256 `4798de0525be3d94190429b653125d6f3f00d2719d9dbe3e8d5cbda4fbb6c8d6`.
The retained, previously accepted B1 artifact13084775420 SHA256 is
`265b7ade1be307bd2efafbd0a8438e6846c869df6205af717133d490e38aeb59`.
Only February and July original ZIP/checksum/member bytes are parsed, 5760 bars;
no fresh Binance request, full-year analysis, old runner or B1/B2/B3 test rerun.

Reuse: B1 canonical hash encoding; B2 `parse_source_month` and bounded future
window helper; B3 `source_from_accepted_b1` original-parent byte/checksum gate.
B3's Vault imports are supplied read-only from pinned Vault #211
7d97b09c0c6ee2650a61d523acb8d8c771a99c46. No Vault admission or B3 replay is
invoked. Native Factory `indicator_library_v2._ema` blob
87aa21841c7b649d3b860ee1337ccc45fd08e0bf matches Core's consumed indicator code;
no separate #208 dependency is introduced. Version IDs are preserved exactly.
The consumer rechecks features and regime against the exact <=cutoff prefix,
not future bars. Core producer/tests are not rerun by this consumer job.

## Results and denominator policy

Actual Core counts verified: **32 opportunities,64 BASE/SHADOW arm slots,192
4h/24h/72h outcome rows**,32 READY_RESEARCH_ONLY snapshots. Sixteen consecutive
15m opportunities on each of2024-02-15 and2024-07-15, cutoffs00:15–04:00UTC.
Every input opportunity is retained verbatim inside the opportunity ledger,
alongside explicit scheduled arm slots. All64 actual arms are MISSING_CAPTURE /
UNKNOWN_ORIGINAL_DECISION. Nothing becomes NO_SIGNAL/TRIGGERED/LONG/SHORT.
No opportunity is excluded. A missing scheduled opportunity rejects the input;
a missing arm record materializes its slot as MISSING_CAPTURE/supplied=false,
preserving all expected rows. Duplicate identity/pair/arm rejects the input.
This version is locked to the current producer's schedule and unavailable
original-decision scope; a new producer/schedule/status contract needs review
and a new explicit input pin, not silently accepted inferred trading states.

Every market window is `[decision_cutoff_ms, cutoff+horizon)` using16/96/288
future original15m bars. COMPLETE means exact retrospective OHLC coverage only,
not an authenticated original known-at clock or fill. A retained source end
causes CENSORED; an internal missing grid/source causes UNKNOWN. Partial extrema
are null. Each row contains explicit start/end, expected/observed bars, mutually
exclusive complete/censored/unknown flags, original member/source/correction
identity, feature/regime version, opportunity/pair/arm/status. Missing clocks
stay null. Source/correction lookahead, source drift, feature value/version or
regime mismatch and forged parent identity fail closed.

Actual sample: COMPLETE192 (64 per horizon), CENSORED0, UNKNOWN0. Original
strategy decisions0; missing captures64. Regime strata: UP_TREND31 opportunities /
62arms /186horizon rows; RANGE_OR_MIXED1 /2 /6. No DOWN_TREND sample, no broad
regime-generalization or independent-trial inference. Windows overlap and both
arms share market context; these are not192 independent trading trials.

All96 scheduled pair/horizon comparisons are NOT_EVALUABLE, uplift=null.
Direction, signed MFE/MAE, TP/SL, fills, PnL, alpha and costs are null or
NOT_CONFIGURED_NO_EXECUTION. High/low are raw unsigned market observations,
not directional strategy performance. No strategy/monitor association or
positive BASE/SHADOW result is inferred from identical coverage.

## Replay and new checks

Python3.11+ standard library. POSIX because the reused B3 module imports the
existing fcntl Vault; no Windows support or new environment installation claim.
Use this delivered Factory commit, a separate clean Vault worktree at the exact
pin above, the two retained artifacts, and a new output directory:

```bash
PYTHONPATH=.:/absolute/path/vault-pinned python -m research_wp_r0.aql_r1_factory_consumer \
  --core /absolute/path/core-r1-market-research.json \
  --b1-artifact /absolute/path/b1-original.zip --out /absolute/path/new-r1-evaluation

PYTHONPATH=.:/absolute/path/vault-pinned \
AQL_R1_CORE=/absolute/path/core-r1-market-research.json \
AQL_R1_B1=/absolute/path/b1-original.zip \
python -m unittest -v tests.test_aql_r1_factory_consumer

sha256sum /absolute/path/new-r1-evaluation/*
```

Output is ONE deterministic `evaluation.json` plus compact `SUMMARY.md`.
No overwrite. Canonical JSON is ASCII, sorted keys, compact separators, newline;
`evaluation_sha256` is the self-excluding semantic hash, distinct from the
SHA256 of the final file. Input transport pins and internal Core digest are
both checked; adversarial test mutations are resealed to exercise structural
gates beyond the transport pin, never published as original measurements.

New17-test module covers actual artifact/count/identity preservation, transport
and duplicate-JSON-key rejection, duplicate/missing opportunity, cutoff and
source/correction lookahead, source/feature/regime drift, missing/duplicate arms,
missing independent witness, forged parent, mutated retained artifact, source-end
censoring, internal gaps/missing source, and unchanged features under later-bar
mutation. Local Python3.12.14:17pass. Focused CI fetches and verifies actual Core
artifact metadata at the pinned producer commit, runs only new R1 tests, runs
two independent CLI processes and compares both outputs byte-for-byte. It
uploads the evaluation/summary and actual Core input for independent replay.
Exact published SHA/CI/log/artifact identifiers are recorded in #77 delivery.

| Deterministic file | SHA256 |
|---|---|
| evaluation.json | 4f00280112a497d00d22e2fcf5c7694e00e22253770d2b3e563a636b8677123f |
| SUMMARY.md | 4859818934f4661c1eeadc7c7bfd838eb81661f698535f9fb07903dbb945bf81 |

## External evidence matrix

| Boundary | Status | Needed / owner |
|---|---|---|
| Original market byte/hash/grid integrity | PASS_PINNED_ORIGINAL_MONTHS | Already retained; Factory |
| Original per-arm historical strategy decision | MISSING_CAPTURE64 | Original decision/direction/entry records; Core/owner |
| Independent source publication/correction clock | BLOCKED_EXTERNAL_EVIDENCE | Issuer/custodian known-at and correction proof |
| Independent parent custody/freeze/pre-F3 anchor | BLOCKED_EXTERNAL_EVIDENCE | Retained independently verified original receipt/anchor |
| Real production monitor / prospective F3 | NOT_CONNECTED | Actual lifecycle/snapshot links; Core |
| Directional performance / paired uplift | NOT_EVALUABLE | Authentic original direction/entry and separately authorized protocol |

The machine artifact retains this blocker matrix. Prior accepted B3 local
software seam is not rerun or upgraded to operational PIT. Independent Audit
request is delta-only, with prior B1/B2/B3 verdicts preserved. No new PR, merge,
G0, OOS opening or Paper/Shadow/Live activation.
