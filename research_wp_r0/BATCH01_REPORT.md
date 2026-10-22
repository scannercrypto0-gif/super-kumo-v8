# Strategy Factory — Batch 01 (synthetic research only)

Project: `AQL-CRYPTO-RESEARCH-001`. All 12 candidates: **INSUFFICIENT_EVIDENCE**. No accepted/promoted trader, real historical result, prospective result or profitability claim. No final holdout opened.

## Evidence and ancestry

- Inspection timestamp: `2026-10-22T13:22:37.459341+00:00` UTC. Main `e4c1f9ec5df9265405c62bab97b2ecc807ceab7b`; [Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) CLOSED with explicit final G0 owner sign-off in its current description. Earlier OPEN observations are historical snapshots. R09 is still mandatory before legacy/key reuse; none used here.
- Parent [PR #43](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/43) `0a3d900d5d85a6d987f1e26eac8f99660f05b2e5`, based on #41 `06d1c2c218aeb3553b0c761c659fd0a8a143d93c`. Incremental Draft PR targets the #43 branch, avoiding repetition of the whole unmerged research chain. No source branch/PR modified.
- Research dependency chain: #18–#31 → #33–#39 → #41 → #43 → this batch. #17 remains a proposal. #32 → #40 → #42 is an independent ingest/stress/health chain, not incorporated. All remain subject to separate owner review/merge authorization.
- The research ancestry started from old main `ed188f1902d397fe74613dd966c5a3e88b32f8c0`; it does not contain all subsequently merged #15 architecture changes. Do not merge cumulative old branch documents over current main. Future integration must preserve current main documents and reconcile overlapping STATE/WORK_LOG/register/CI changes.
- Open PR metadata/bodies and research comments/reviews through #43 inspected. [Owner review on #42](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/42#pullrequestreview-5614480596) reports false HEALTHY risks; [#32 review](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/32#pullrequestreview-5613458567) describes recovery/finality defects. These are operational-source review findings, not fixes or runtime validations performed here; actual resolution remains UNVERIFIED outside this synthetic research scope.
- Main startup/decisions/state/risks/test policy/register and the exact #43 engine, tests and workflows were consulted. No real market data archive appeared in the inspected research tree; no external data fetched. Other chats/original Work sessions inaccessible; no exhaustive cross-chat audit claimed.

## Frozen research specification

- [Protocol](batch01_protocol.json): 3 families × 2 lookbacks × 2 thresholds = 12 candidates; formulas, grids, exits, entry TTL, fees/slippage, baselines, denominators, ranking and holdout restriction frozen as canonical immutable bytes before batch evaluation. The commit pins the implementation; this is local logical freezing, not independently timestamped preregistration.
- Protocol SHA256: `b6cfe6f64d3bb793096c03a7761132e08fb4c468e2dff2bf8f3a1c79c3a428a3`.
- Long-only, next executable synthetic open within 2 bars; maximum 8 holding bars; stop 2%, target 3%; fees 10 bp/side and adverse slippage 5 bp/side. These are explicitly hypothetical research assumptions, not owner-approved real market constants. Entry-notional accounting, no compounding or leverage claim.
- Market-open gaps use observed synthetic opening price. Same-bar stop + target is AMBIGUOUS with net bounds, never a chosen profitable ordering. Stops, targets and exit liquidity are simulated assumptions; no queue, funding, capacity, borrow or real execution assurance.
- Momentum: prior 8/16-bar return > 0/0.004. Breakout: final close above prior 8/16-bar high × (1 + 0/0.002). Mean reversion: prior-window population z-score > 1/1.5 below its mean. Strategies only see final decision-time prefixes; generator regime truth is diagnostic, never an entry feature.
- Intended specialist regimes: momentum UP; breakout UP/VOLATILE; mean reversion RANGE. All regimes are reported, with multiple generator occurrences. No live regime detector or independently verified eligibility policy is implemented. Off-target losses do not establish global failure or profitability of a specialist.
- Development: 94 fixed opportunities; visible synthetic chronological validation: 30; disjoint 10-bar outcome windows on a 12-bar schedule, with partition warm-up. Purged forward-fold specification is checked with the existing utility; there is no learned model and no claimed walk-forward fit. Reserved 384-bar final tail is never generated/read by this workflow.
- Development alone determines the descriptive order: sample adequacy (≥12 known trades), lower-bound net/opportunity, lower-scenario close-marked drawdown, stable ID. Validation cannot rerank candidates. No synthetic candidate is selected for promotion.
- All 12 attempts remain in one multiplicity family. Holm adjusted values are all 1 because no calibrated strategy marginal p-values exist; values of 1 are deliberately conservative placeholders, not measured significance. Resampling intervals below are unadjusted descriptive sensitivity, not familywise confidence or profitability proof.

## Quantitative candidate tables

Units: gross/net sums are percentages of a single entry notional summed without compounding; these are NOT portfolio percentage returns. DD is close-marked lower-ambiguity scenario drawdown divided by initial unit equity, not worst intrabar equity or percentage of a changing peak. Executed includes ambiguous entries; known counts exclude ambiguity. NO_SIGNAL is separate from attempted NO_FILL. Full counts, costs, dispersion, outcome bounds, regime counts and both baseline comparisons are in [results.json](evidence/batch01/results.json); [CSV](evidence/batch01/candidates.csv).

### development

| Candidate | Opp. | Attempts | Executed | No fill | No signal | Ambig. | Gross units % | Net units % | DD units % | Known n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum-L8-T0 | 94 | 42 | 40 | 2 | 52 | 0 | 21.474 | 9.442 | 10.094 | 40 |
| momentum-L8-T0.004 | 94 | 40 | 38 | 2 | 54 | 0 | 22.234 | 10.801 | 7.797 | 38 |
| momentum-L16-T0 | 94 | 46 | 44 | 2 | 48 | 0 | 20.049 | 6.819 | 12.077 | 44 |
| momentum-L16-T0.004 | 94 | 41 | 39 | 2 | 53 | 0 | 23.181 | 11.446 | 11.638 | 39 |
| breakout-L8-T0 | 94 | 17 | 16 | 1 | 77 | 0 | 15.134 | 10.312 | 3.275 | 16 |
| breakout-L8-T0.002 | 94 | 13 | 12 | 1 | 81 | 0 | 10.861 | 7.245 | 3.275 | 12 |
| breakout-L16-T0 | 94 | 16 | 15 | 1 | 78 | 0 | 15.274 | 10.751 | 2.636 | 15 |
| breakout-L16-T0.002 | 94 | 12 | 11 | 1 | 82 | 0 | 11.001 | 7.684 | 2.636 | 11 |
| mean_reversion-L8-T1 | 94 | 35 | 34 | 1 | 59 | 0 | -18.716 | -28.888 | 29.558 | 34 |
| mean_reversion-L8-T1.5 | 94 | 27 | 26 | 1 | 67 | 0 | -15.475 | -23.251 | 24.723 | 26 |
| mean_reversion-L16-T1 | 94 | 37 | 37 | 0 | 57 | 0 | -25.803 | -36.864 | 36.873 | 37 |
| mean_reversion-L16-T1.5 | 94 | 23 | 23 | 0 | 71 | 0 | -16.058 | -22.934 | 25.223 | 23 |

### development — regime net / known trade count

| Candidate | UP | DOWN | RANGE | VOLATILE |
|---|---:|---:|---:|---:|
| momentum-L8-T0 | 27.553% / n=22 | -4.594% / n=2 | -5.369% / n=5 | -8.148% / n=11 |
| momentum-L8-T0.004 | 27.553% / n=22 | -4.594% / n=2 | -5.369% / n=5 | -6.789% / n=9 |
| momentum-L16-T0 | 32.944% / n=24 | -11.485% / n=5 | -3.160% / n=3 | -11.480% / n=12 |
| momentum-L16-T0.004 | 32.098% / n=23 | -11.485% / n=5 | 0.000% / n=0 | -9.167% / n=11 |
| breakout-L8-T0 | 11.799% / n=13 | 0.000% / n=0 | -0.439% / n=1 | -1.048% / n=2 |
| breakout-L8-T0.002 | 8.732% / n=9 | 0.000% / n=0 | -0.439% / n=1 | -1.048% / n=2 |
| breakout-L16-T0 | 11.799% / n=13 | 0.000% / n=0 | 0.000% / n=0 | -1.048% / n=2 |
| breakout-L16-T0.002 | 8.732% / n=9 | 0.000% / n=0 | 0.000% / n=0 | -1.048% / n=2 |
| mean_reversion-L8-T1 | 0.000% / n=0 | -26.165% / n=16 | -3.863% / n=10 | 1.140% / n=8 |
| mean_reversion-L8-T1.5 | 0.000% / n=0 | -19.538% / n=12 | -2.852% / n=9 | -0.861% / n=5 |
| mean_reversion-L16-T1 | 0.000% / n=0 | -29.778% / n=18 | -8.964% / n=15 | 1.877% / n=4 |
| mean_reversion-L16-T1.5 | 0.000% / n=0 | -19.349% / n=12 | -3.983% / n=9 | 0.399% / n=2 |

### development — baseline comparison and uncertainty

Lift units: net entry-notional fraction per scheduled opportunity. Brackets are the existing circular paired block bootstrap, block=3, 200 resamples, approximate 95% unadjusted percentile sensitivity. Confirmed no-exposure decisions have zero exposure under the frozen policy; ambiguous/missing evidence is never zeroed. The conditional both-executed comparison is retained separately. One synthetic instrument gives insufficient sector diversity; sector/multiway confidence remains unavailable.

| Candidate | vs random [low, high] | vs simple momentum [low, high] |
|---|---:|---:|
| momentum-L8-T0 | 0.002968 [0.000595, 0.005308] | 0.000000 [0.000000, 0.000000] |
| momentum-L8-T0.004 | 0.003112 [0.000993, 0.005354] | 0.000145 [-0.000299, 0.000733] |
| momentum-L16-T0 | 0.002689 [0.000432, 0.005088] | -0.000279 [-0.001678, 0.000951] |
| momentum-L16-T0.004 | 0.003181 [0.000643, 0.005664] | 0.000213 [-0.001302, 0.001815] |
| breakout-L8-T0 | 0.003060 [0.001165, 0.005070] | 0.000093 [-0.001804, 0.001931] |
| breakout-L8-T0.002 | 0.002734 [0.000576, 0.004652] | -0.000234 [-0.002145, 0.001856] |
| breakout-L16-T0 | 0.003107 [0.001241, 0.005070] | 0.000139 [-0.001770, 0.002024] |
| breakout-L16-T0.002 | 0.002781 [0.000624, 0.004743] | -0.000187 [-0.002109, 0.001995] |
| mean_reversion-L8-T1 | -0.001110 [-0.003446, 0.001593] | -0.004078 [-0.006912, -0.000888] |
| mean_reversion-L8-T1.5 | -0.000510 [-0.002910, 0.002065] | -0.003478 [-0.006306, -0.000663] |
| mean_reversion-L16-T1 | -0.001959 [-0.004138, 0.000683] | -0.004926 [-0.007957, -0.001874] |
| mean_reversion-L16-T1.5 | -0.000477 [-0.002525, 0.002226] | -0.003444 [-0.006092, -0.000609] |

### synthetic_validation

| Candidate | Opp. | Attempts | Executed | No fill | No signal | Ambig. | Gross units % | Net units % | DD units % | Known n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum-L8-T0 | 30 | 18 | 17 | 1 | 12 | 0 | 8.346 | 3.234 | 3.709 | 17 |
| momentum-L8-T0.004 | 30 | 16 | 15 | 1 | 14 | 0 | 8.584 | 4.071 | 4.621 | 15 |
| momentum-L16-T0 | 30 | 15 | 14 | 1 | 15 | 0 | 6.378 | 2.168 | 3.709 | 14 |
| momentum-L16-T0.004 | 30 | 14 | 13 | 1 | 16 | 0 | 7.717 | 3.805 | 3.709 | 13 |
| breakout-L8-T0 | 30 | 5 | 5 | 0 | 25 | 0 | 1.073 | -0.428 | 2.297 | 5 |
| breakout-L8-T0.002 | 30 | 3 | 3 | 0 | 27 | 0 | 0.496 | -0.405 | 2.297 | 3 |
| breakout-L16-T0 | 30 | 4 | 4 | 0 | 26 | 0 | 0.107 | -1.093 | 2.382 | 4 |
| breakout-L16-T0.002 | 30 | 2 | 2 | 0 | 28 | 0 | -0.471 | -1.070 | 2.382 | 2 |
| mean_reversion-L8-T1 | 30 | 7 | 7 | 0 | 23 | 0 | -9.894 | -11.980 | 11.980 | 7 |
| mean_reversion-L8-T1.5 | 30 | 6 | 6 | 0 | 24 | 0 | -7.894 | -9.683 | 9.683 | 6 |
| mean_reversion-L16-T1 | 30 | 8 | 8 | 0 | 22 | 0 | -6.143 | -8.534 | 8.955 | 8 |
| mean_reversion-L16-T1.5 | 30 | 4 | 4 | 0 | 26 | 0 | -6.438 | -7.628 | 7.628 | 4 |

### synthetic_validation — regime net / known trade count

| Candidate | UP | DOWN | RANGE | VOLATILE |
|---|---:|---:|---:|---:|
| momentum-L8-T0 | 2.499% / n=5 | -2.297% / n=1 | 1.366% / n=6 | 1.666% / n=5 |
| momentum-L8-T0.004 | 2.499% / n=5 | -2.297% / n=1 | -0.093% / n=5 | 3.963% / n=4 |
| momentum-L16-T0 | 2.499% / n=5 | 0.000% / n=0 | -0.450% / n=4 | 0.120% / n=5 |
| momentum-L16-T0.004 | 2.499% / n=5 | 0.000% / n=0 | 1.186% / n=3 | 0.120% / n=5 |
| breakout-L8-T0 | 1.204% / n=3 | 0.000% / n=0 | 0.665% / n=1 | -2.297% / n=1 |
| breakout-L8-T0.002 | 1.227% / n=1 | 0.000% / n=0 | 0.665% / n=1 | -2.297% / n=1 |
| breakout-L16-T0 | 1.204% / n=3 | 0.000% / n=0 | 0.000% / n=0 | -2.297% / n=1 |
| breakout-L16-T0.002 | 1.227% / n=1 | 0.000% / n=0 | 0.000% / n=0 | -2.297% / n=1 |
| mean_reversion-L8-T1 | 0.000% / n=0 | -7.628% / n=4 | 0.000% / n=0 | -4.351% / n=3 |
| mean_reversion-L8-T1.5 | 0.000% / n=0 | -5.331% / n=3 | 0.000% / n=0 | -4.351% / n=3 |
| mean_reversion-L16-T1 | 1.257% / n=1 | -7.628% / n=4 | -0.108% / n=1 | -2.054% / n=2 |
| mean_reversion-L16-T1.5 | 0.000% / n=0 | -5.331% / n=3 | 0.000% / n=0 | -2.297% / n=1 |

### synthetic_validation — baseline comparison and uncertainty

Lift units: net entry-notional fraction per scheduled opportunity. Brackets are the existing circular paired block bootstrap, block=3, 200 resamples, approximate 95% unadjusted percentile sensitivity. Confirmed no-exposure decisions have zero exposure under the frozen policy; ambiguous/missing evidence is never zeroed. The conditional both-executed comparison is retained separately. One synthetic instrument gives insufficient sector diversity; sector/multiway confidence remains unavailable.

| Candidate | vs random [low, high] | vs simple momentum [low, high] |
|---|---:|---:|
| momentum-L8-T0 | 0.003929 [0.000349, 0.007856] | 0.000000 [0.000000, 0.000000] |
| momentum-L8-T0.004 | 0.004208 [0.000447, 0.008165] | 0.000279 [-0.000973, 0.002297] |
| momentum-L16-T0 | 0.003573 [-0.000743, 0.009195] | -0.000355 [-0.002399, 0.002026] |
| momentum-L16-T0.004 | 0.004119 [-0.000009, 0.009195] | 0.000190 [-0.001960, 0.002548] |
| breakout-L8-T0 | 0.002708 [-0.002513, 0.008451] | -0.001221 [-0.003979, 0.002173] |
| breakout-L8-T0.002 | 0.002716 [-0.002585, 0.008473] | -0.001213 [-0.003977, 0.002107] |
| breakout-L16-T0 | 0.002486 [-0.002538, 0.008234] | -0.001442 [-0.004001, 0.001952] |
| breakout-L16-T0.002 | 0.002494 [-0.002669, 0.008386] | -0.001435 [-0.004073, 0.001885] |
| mean_reversion-L8-T1 | -0.001142 [-0.004390, 0.001996] | -0.005071 [-0.008158, -0.001733] |
| mean_reversion-L8-T1.5 | -0.000377 [-0.004037, 0.003366] | -0.004305 [-0.007329, -0.001168] |
| mean_reversion-L16-T1 | 0.000006 [-0.001910, 0.002560] | -0.003922 [-0.007561, -0.000102] |
| mean_reversion-L16-T1.5 | 0.000308 [-0.002126, 0.003852] | -0.003621 [-0.006793, -0.000134] |

## Selection and evidence status

- Accepted/promoted: **0**. Rejected as economically disproven: **0**. Insufficient evidence: **12**. Synthetic PnL, including positive figures, cannot establish crypto profitability. Small per-regime samples remain explicitly inadequate. No combined historical/forward score.
- Real historical development/OOS: **NOT AVAILABLE / NOT TESTED**. Prospective forward/shadow: **NOT STARTED / NOT TESTED**. Final holdout: **NOT OPENED**. Ledger awaits eligible pre-holdout selection; no artificial winner was selected. Synthetic validation has been visible during engineering and is exploratory, not an independent untouched holdout.
- Developer-visible synthetic seed is reproducible and therefore not blind custody. Independent owner custody remains false; locally replaceable receipts/hash manifests do not prove authenticity against complete coordinated replacement. No evidence guarantee or per-event fsync changed.

## Validation and measurements

- Local Linux Python 3.12.14: baseline **175 tests / 0.556 s** unittest time (0.766 s wall); final **204 tests / 1.462 s** unittest time (1.668 s wall). Added 29 tests in 12 named groups. Broader coverage, not a performance speedup claim.
- Official synthetic batch: **12 candidates, 1736 candidate/baseline opportunity evaluations, 0.401 s**. Counts are repeated evaluations of 124 scheduled opportunities, not independent market samples. Timing is a single local observation, no latency/capacity guarantee.
- Two independent output directories in the acceptance test matched byte-for-byte artifact hash manifests on this machine. Reopening an existing output directory is refused. Replay/checkpoint, changed bytes and forged result + rewritten local manifest are exercised. Inherited tests cover rollback, full chain rewrite versus assumed pinned receipt and fsync failure; no actual independent custody or hardware power-loss test claimed.
- Prototype findings repaired before publication: conditional both-filled baseline lift was identically zero for common entry paths, hiding selection effects; full-opportunity comparison now measures selection. For momentum-L16-T0.004 versus random development, omitted population effect is now +0.003180752/opportunity, CI [0.000642606, 0.005663772]. This is synthetic descriptive evidence only. Result metrics and baseline tables are now committed by trial result digests; editing metrics plus local artifact hashes is detected against unchanged journal. Candidate and baseline opportunity records are also bound through result commitments; altered timestamps plus a rewritten local manifest are rejected.
- CI configuration: one unified regression suite per Ubuntu/Windows job, followed by the actual batch export and artifact upload. This PR does not touch R40 or targeted-performance trigger paths, avoiding their duplicate suites. New exact-head GitHub CI status must be verified after PR publication; no pass inferred from local tests.

| Group | Verification scope | Local result |
|---|---|---|
| 1 | Deterministic candidates / seeded prefix | PASS |
| 2 | Canonical family/parameter/cost freeze | PASS |
| 3 | Prefix-only dispatch / future availability / regime-label separation | PASS |
| 4 | Chronological partitions / overlapping-label purging | PASS |
| 5 | Exact two-leg fees and adverse slippage | PASS |
| 6 | NO_SIGNAL versus NO_FILL, expiry and no fabricated return | PASS |
| 7 | Stop/target ambiguity, gaps, time exit and marked risk | PASS |
| 8 | Regime coverage and repeated diagnostic occurrences | PASS |
| 9 | Frozen random/momentum baselines and development-only ranking | PASS |
| 10 | Existing bootstrap / all-family Holm / ambiguity exclusion | PASS (calibration NOT TESTED) |
| 11 | Final-tail access denied; existing ledger selection gate | PASS (actual final holdout NOT OPENED) |
| 12 | Journal replay, checkpoint, deterministic files and tamper detection | PASS (independent custody NOT VERIFIED) |

## Reproduction and artifacts

```bash
python -B -m unittest discover -s tests -p "test_research_wp_r*.py"
python -B -m research_wp_r0.strategy_factory --output /tmp/atlas-batch01-new
```

The command requires a new directory and creates full `opportunities.jsonl`, results JSON/CSV, frozen protocol, durable journal, checkpoint, SHA256 manifest and separate timing. The committed [evidence snapshot](evidence/batch01/) contains the compact summary/CSV/protocol/journal/checkpoint/manifest/timing; the approximately 1 MB opportunity log is regenerated and uploaded by CI, not duplicated in Git. Thus the compact snapshot alone is not a full directory accepted by `verify_batch`. Regenerated files are hashed against the manifest; timing is intentionally excluded. `verify_batch(new_output)` is called automatically after export. Byte identity has been demonstrated locally, not guaranteed across Python/libm/OS versions; CI records its own exact environment/artifacts.

## Remaining work before paper admission — estimated six work checkpoints

This is a planning estimate, not six new approved architectural gates or a guarantee of readiness:
1. Owner-reviewed integration of the unmerged research dependency chain, preserving current main architecture and resolving file/workflow overlap.
2. Authorized, trustworthy real historical source/coverage/receipt-quality evidence and provider budgets; resolve relevant ingest health/recovery blockers. R09 before any legacy/key use.
3. Preregister a real-data strategy family, target-regime detector/eligibility, cost/liquidity/ambiguity policy and calibrated dependence/search inference; evaluate development and temporal OOS separately.
4. Independently retained frozen selection/receipt and authorized one-time untouched holdout evaluation; no same-family retuning from that holdout.
5. Validated isolated paper runtime: actual event provenance, entry/no-fill/exit/recovery/idempotency and open-position monitoring, plus shadow collection without capital exposure.
6. Explicit owner admission of a candidate to prospective paper/Shadow evaluation under a versioned policy, reporting historical and prospective evidence separately. Forward sample collection and review are further work before any stronger claim.

No merge, live trading, paid action, old key, production/provider integration or final strategy approval was performed.
