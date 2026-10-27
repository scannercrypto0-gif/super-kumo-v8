# CODEX-FACTORY-AUDIT-EXEC-001

## S0 inventory (before implementation)

Accepted base: `10effc6a36fa2d13a71e7db260b7f83f1d9fbb09` (#130 merged).
Reference only: #46 `a4c106a02c55ee012eedf4c55c1488d71d850203`, unmerged.
No other active Factory PR owns this new experiment slice. Core #127/#129 and
old #18-46 research chain remain separate; no cherry-picks or imports from them.

| Component | Status at base / evidence | Owner / reuse action |
|---|---|---|
| Typed immutable Scanner/Decision/Monitoring | ALREADY_IMPLEMENTED: strategy_dna_v2.py:358 evaluate_synthetic | Factory: call unchanged; no F012 repair |
| Both-side fees and execution-price slippage | ALREADY_IMPLEMENTED: synthetic_execution.py:9 account_long_prices | Factory: reuse #108 arithmetic |
| One audited long / retrospective EMA replay | PARTIAL: offline_simulator.py:19; ema_development_replay.py | Factory: preserve accepted adapters; do not replace historical engine |
| Multi-opportunity synthetic capital/fills/marks | MISSING: no general V2-bound portfolio exam on accepted main | Factory: bounded in-memory experiment adapter over shared accounting |
| Fixed universe / two estimands | PARTIAL: #46 evaluation.py:107 and opportunity_clusters.py on incompatible unmerged ancestry | Factory: retain concepts, no imports; freeze source manifest before routing |
| As-of regime gate / optional overlay experiment | MISSING on accepted main | Factory: opt-in frozen synthetic score contract, never generator truth |
| Actual receipts / PIT / venue fill model / OOS | EXTERNALLY_BLOCKED: #134 F005/F006, Core #128 D2 | Core/Data/custodian; no implementation or authority inferred |

Authority: #77 comment 6438456067. Read #134 v0.2, COORD-04, F012 closure,
M09 and M10 plus corrected SF-DEC-49 B, SF-DEC-50 B and SF-DEC-51 B.
Latest delivered Factory code is merged #130, not old #46. Other originating
chats are inaccessible and not claimed read. G0 remains provisional.

## S1-S3 executable slice and limits

`research_wp_r0/factory_exam.py` is a small deterministic adapter over unchanged
V2 signals and shared #108 accounting, not an alternative historical engine.
It supports supplied SYNTHETIC observations only, a shared quote-unit cash account,
spot longs, one declared requested notional per opportunity, no leverage/margin,
and explicit synthetic full/partial/no-fill fractions. A recorded seed has no
randomness: all fills are fixture inputs, not predicted venue outcomes.

ENTRY needs valid Scanner + ENTRY evidence. Missing optional EXIT alone does
not veto ENTRY; confirmed ambiguity does. Native DNA EXIT conditions observed
on later supplied selected events close matching open lots at cutoff+latency,
even when the regime gate abstains. The frozen experiment additionally declares
its native maximum holding horizon; this is not a compulsory global stop. There
is no tick stop/trailing stop or position-specific scanner bypass. Strategies
requiring those exit models are NOT SUPPORTED, not silently certified here.
`protection_required` is opt-in; before exposure a supplied synthetic coverage
claim must span the declared horizon. It is not a real protection service.

Event order is quote -> exit -> decision -> entry, sorted by timestamp and
immutable manifest order. Latency is positive and entry/exit require the exact
scheduled print; no favorable later substitute. Unknown fill/native exit or a
late supplied mark with exposure halts with unknown equity, never a fake no-fill.
Missing decision/regime slots remain UNKNOWN without fabricated PnL. Explicit
Scanner exclusion, valid no-signal/ambiguity, protection/overlay/budget denial,
regime abstain and supplied no-fill are proven zero *simulated* exposure.

Fee bps charge both slipped notionals. Spread bps represent full quoted spread,
half per side, added to slippage before calling shared `account_long_prices`.
Cash conservation is checked against independent Decimal arithmetic in tests.
Equity is cash plus supplied mid-marked inventory; drawdown is sampled MTM,
not continuous/intrabar liquidation DD. Closed gross/net outcomes and actual
portfolio quote PnL are separate from per-requested-notional opportunity means.
Cash-only spot has no funding. No shorting, borrow, liquidation, queue/tick/impact,
uncertain partial exit, real fills or empirical calibration is implemented.

The frozen manifest retains externally enumerated missing slots, the entire
supplied cross-section's Scanner ranking/capacity and exclusions, per-opportunity
critical readings/timestamps, V2 family identity, quotes, fill assumptions and
source fingerprint. Monitoring observations/gaps are retained separately and
never read by admission/accounting. Hashes detect edits relative to retained
digests; they are not authenticated PIT/custody or protected independent anchors.

REGIME consumes only a frozen threshold on supplied `AS_OF_SYNTHETIC_SCORE`
records, with as-of/availability/age checks and explicit unknown vs abstain.
It is a deterministic score adapter, NOT a learned/validated regime detector.
Caller-reported timestamps cannot prove authenticity. Oracle-kind/future records
are rejected, but disguising an oracle as an as-of score cannot be detected by
hashes. The eight-slot hand-designed scores intentionally reproduce M10's
arithmetic selection counterexample; their favorable selection is NOT evidence
of deployable regime prediction or prospective value.

Comparisons require identical manifest, event/family/source fingerprints and
controlled execution assumptions. Different costs/capital/notional/latency need
an explicitly labeled sensitivity. The full-universe mean is null if any slot
is UNKNOWN; observed sums are labeled partial and never substituted for it.
The both-executed net-return lift has its own conditional sample count and is
selection-sensitive. Do not extrapolate it to policy value.

S3 registers R0, base-cost, cost-stress and exactly-one-overlay R1 protocols,
before the declared window, with hashes/seed/parameter count. Parameter count
zero means no fitted/tuned parameters in this engineering fixture, NOT absence
of configurable knobs. Full frozen configurations commit all thresholds/costs.
The sole optional overlay is versioned MAX_CONCURRENT. It is disabled by default.
R1 is compared with R0 separately within ALWAYS and REGIME; the sequential example
has no overlap so R1 has zero effect. A separate overlapping test proves avoided
exposure/selection attrition. R2 is NOT_IMPLEMENTED; no p-values/bootstrap,
calibrated significance, unseen trial-history attestation or promotion exists.

## Reproduction and actual local evidence

From repo root (stdlib runtime; pytest/pytest-timeout for tests):

```sh
python -B -m pytest -p no:cacheprovider tests/test_sf_factory_exam.py -v
python -B research_wp_r0/_dep_guard.py research_wp_r0/factory_exam.py research_wp_r0/factory_exam_example.py
python -B -m research_wp_r0.factory_exam_example
```

Windows 11 CPython 3.14.3: initial 25 tests passed. Two additional causality
checks (late MTM and next-print DNA exit) added: final focused 27 tests passed,
zero fail/error/skip. Dependency guard passed. No old broad suite was manually
rerun. CI checks out native PR HEAD on Ubuntu/Windows Python 3.11, checks exact
27 collection, no skips, twice-reproduced example and uploads source/JUnit/JSON.
Actual published SHA/job links belong in the delivery receipt after completion.

| Audit requirement | Implementation / falsification evidence |
|---|---|
| F007 / S0 ancestry | Accepted base vs #46 merge-base `ed188f1902d397fe74613dd966c5a3e88b32f8c0`; no legacy imports |
| F010 corrected / SF-DEC-49-51 | `test_optional_exit_missing_does_not_veto_entry`, explicit entry missing/protection/ambiguity/excluded tests |
| M09-04 / cost and budget | Decimal conservation, cash denial, partial/no-fill, MTM drawdown, cost/notional sensitivity |
| M10-01 two estimands | Eight-slot test: ALWAYS mean -0.015375, REGIME +0.00525; 4 matched executions with lift 0; portfolio 987.7 vs 1004.2 from 1000 |
| M10-02 denominator/matching | Missing supplied slot and regime unknown not zero; capacity/exclusions; changed quote with same family ID rejected |
| M10-03 leakage/search | Future/oracle records rejected; pre-window trial metadata; no fitted detector/nested walk-forward/inference claim |
| F012 reuse | V2 source unchanged; source-fault cases only test new adapter noninterference, not another F012 patch |

## Explicit NOT_DONE / external dependencies

Real-data readiness remains BLOCKED_BY_PIT / REGIME_PROVENANCE / REAL_FILL_MODEL.
Core F003/F005 D2 and archive/custody are Core/Data-owned, unchanged. F008 issuer
rotation is Owner/Security-owned. F009 RSI V1 convention remains unchanged.
F006/F011 empirical alpha, independently sealed OOS, learned regime calibration,
nested selection, paper/shadow/live and final G0 are NOT ACCEPTED. No secrets,
provider calls, real data downloads or operational writes are used by this adapter.
The implementing assistant's tests are not independent auditor acceptance.
